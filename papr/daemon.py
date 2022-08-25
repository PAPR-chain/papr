import os
import json
import typing
import asyncio
import signal
import logging
import datetime
import binascii
import zipfile
import base64
from aiohttp.web import GracefulExit

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from lbry.extras.daemon.daemon import Daemon, JSONRPCServerType
from lbry.extras.cli import ensure_directory_exists
from lbry.extras.daemon.componentmanager import ComponentManager
from lbry.wallet.transaction import Output
from lbry.crypto.crypt import better_aes_encrypt, better_aes_decrypt

from papr.models import Base, Article, Manuscript, Server, Review
from papr.config import Config, IS_TEST, CHUNK_SIZE
from papr.exceptions import PaprException
from papr.utilities import generate_rsa_keys, generate_human_readable_passphrase

logger = logging.getLogger(__name__)


class PAPRJSONRPCServerType(JSONRPCServerType):
    def __new__(mcs, name, bases, newattrs):
        klass = type.__new__(mcs, name, bases, newattrs)
        klass.callable_methods = {}
        klass.deprecated_methods = {}

        for methodname in dir(klass):
            name = ""
            if methodname.startswith("jsonrpc_"):
                name = methodname.split("jsonrpc_")[1]
            elif methodname.startswith("papr_"):
                name = methodname
            else:
                continue

            method = getattr(klass, methodname)
            if not hasattr(method, "_deprecated"):
                klass.callable_methods.update({name: method})
            else:
                klass.deprecated_methods.update({name: method})
        return klass


class PaprDaemon(Daemon, metaclass=PAPRJSONRPCServerType):
    def __init__(
        self, conf: Config, component_manager: typing.Optional[ComponentManager] = None
    ):
        super().__init__(conf, component_manager)

        if IS_TEST:
            self.engine = create_engine(
                "sqlite+pysqlite:///:memory:", echo=True, future=True
            )
        else:
            self.engine = create_engine(
                f"sqlite+pysqlite:///{conf.database_dir}/papr.sqlite",
                echo=True,
                future=True,
            )

        self.conn = self.engine.connect()

        Base.metadata.create_all(self.conn)

    async def initialize(self):
        await super().initialize()

        if self.conf.active_channel:
            try:
                await self.channel_load(conf.active_channel)
            except PaprException:
                logger.error(
                    f"Could not load channel {conf.active_channel}, some features will not be available"
                )
            else:
                logger.info(f"Channel {conf.active_channel} loaded")

    async def stop(self):
        print("PAPR daemon closing")
        await super().stop()
        self.conn.close()
        self.engine.dispose()

    async def channel_load(self, name):
        tx = await self.jsonrpc_channel_list()
        for res in tx["items"]:
            if res.claim_name == name:
                self.channel_id = res.claim_id
                self.channel_name = res.claim_name
                self.channel = res.claim.channel
                break
        else:
            raise PaprException(f"Could not find channel {name}")

    async def verify_claim_free(self, name):
        hits = await self.jsonrpc_resolve(name)

        if not isinstance(hits[name], Output):
            logger.info(f"Found no claim with name {name}")
            return True

        logger.warning(f"Found claim(s) with name {name}")

        return False

    async def get_public_key(self, channel_name):
        hits = await self.jsonrpc_resolve(channel_name)

        if not isinstance(hits[channel_name], Output):
            logger.info(f"Found no claim with name {channel_name}")
            return

        return hits[channel_name].claim.channel.public_key

    async def papr_review_create(self, submission_claim_name, review_text=""):
        sub_claim = await self.jsonrpc_get(submission_claim_name)

        if "error" in sub_claim:
            logger.error(
                f"Failed to resolve submission {submission_claim_name}: {sub_claim['error']}"
            )
            return

        # if not "result" in sub_resolve:  ##
        #    pass

        submission = sub_resolve["result"][submission_claim_name]

        submission_ts = submission["timestamp"]
        submission_date = datetime.datetime.utcfromtimestamp(submission_ts)

        if "author" not in submission["value"]:
            logger.warning(f"No author list for {submission_claim_name}")
            submission_authors = "Unknown"
        else:
            submission_authors = submission["value"]["author"]

        if "author" not in submission["value"]:
            logger.warning(f"No title for {submission_claim_name}")
            submission_title = "Untitled"
        else:
            submission_title = submission["value"]["title"]

        if "signing_channel" not in submission:
            logger.error(
                f"The submission {submission_claim_name} is not associated with any channel"
            )
            return

        submission_channel_name = submission["signing_channel"]["name"]

        with Session(self.engine) as session:
            review = Review(
                submission_title=submission_title,
                submission_claim_name=submission_claim_name,
                submission_channel_name=submission_channel_name,
                submission_authors=submission_authors,
                submission_date=submission_date,
                review_text=review_text,
            )
            session.add(review)
            session.commit()

        logger.info(f"Review created for submission {submission_claim_name}")

    async def papr_review_save(self, reviewed_submission_claim_name: str, text: str):
        with Session(self.engine) as session:
            session.execute(
                update(Review)
                .where(Review.submission_claim_name == reviewed_submission_claim_name)
                .values(review_text=text)
            )
            # not found error

            session.commit()

        logger.info(f"Review of {reviewed_submission_claim_name} saved")

    async def papr_review_send(
        self, reviewed_submission_claim_name: str, server_channel_name: str
    ):
        with Session(self.engine) as session:
            review = session.execute(
                select(Review).filter_by(
                    submission_claim_name=reviewed_submission_claim_name
                )
            ).scalar_one()
            server = session.execute(
                select(Server).filter_by(channel_name=server_channel_name)
            ).scalar_one()

            full_review = f"Review for submission {review.submission_name} ({review.submission_claim_name}) by {review.submission_authors_name} ({review.submission_channel_name})"
            review_hex = binascii.hexlify(full_review.encode("UTF-8")).decode("UTF-8")

            signed = await self.jsonrpc_channel_sign(
                channel_name=self.channel_name, hexdata=review_hex
            )

            review.signature = signed["signature"]
            review.signing_ts = datetime.datetime.utcfromtimestamp(signed["signing_ts"])
            session.commit()

            link = f"{server.url}/review"

        # TODO: encrypt for server?
        payload = {
            "review": full_review,
            "signature": signed["signature"],
            "signing_ts": signed["signing_ts"],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(link, json=payload) as resp:
                status_code = resp.status
                if status_code == 201:
                    logger.info(
                        f"Review of {reviewed_submission_claim_name} accepted by {server_channel_name}"
                    )
                else:
                    text = await resp.text()
                    logger.error(
                        f"Error while submitting the review of {reviewed_submission_claim_name} to {server_channel_name}\nStatus code: {status_code}\nReason: {text['reason']}"
                    )

    async def _publish_manuscript(
        self,
        base_claim_name,
        bid,
        file_path,
        title,
        abstract,
        author,
        tags,
        revision=0,
        encrypt=True,
        reviewed=False,
        ignore_duplicate_names=False,
    ):

        if not os.path.isfile(file_path):
            logger.error(
                f"Cannot create a new manuscript: file {file_path} does not exist"
            )
            return  # return error?

        if reviewed:
            claim_name = f"{base_claim_name}_v{revision}"
        else:
            if revision == 0:
                claim_name = f"{base_claim_name}_preprint"
            else:
                claim_name = f"{base_claim_name}_r{revision}"

        raw_file = b""
        with open(file_path, "rb") as raw:
            while True:
                chunk = raw.read(CHUNK_SIZE)

                if chunk == b"":
                    break
                raw_file += chunk

        if reviewed and encrypt:
            raise Exception(
                "Invalid combination of parameters: cannot encrypt a reviewed version"
            )

        with Session(self.engine) as session:
            article = session.execute(
                select(Article).filter_by(base_claim_name=base_claim_name)
            ).scalar_one()

            if encrypt:
                processed_file = better_aes_encrypt(
                    article.encryption_passphrase, raw_file
                )
            else:
                processed_file = raw_file

            zip_path = os.path.join(self.conf.submission_dir, claim_name + ".zip")

            if os.path.isfile(zip_path):
                logger.error(f"You have already submitted a manuscript with this name!")
                return None

            if not ignore_duplicate_names:
                is_free = await self.verify_claim_free(claim_name)

                if not is_free:
                    logger.error(
                        f"Cannot submit manuscript: another claim with this name exists"
                    )
                    return None

            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr(
                    f"Manuscript_{claim_name}.pdf", processed_file
                )  # pdf hardcoded
                z.writestr(f"{claim_name}_key.pub", article.public_key)  # just name?

            # Thumbnail
            try:
                tx = await self.jsonrpc_stream_create(
                    claim_name,
                    bid,
                    file_path=zip_path,
                    title=title,
                    author=author,
                    description=abstract,
                    tags=tags,
                    channel_id=self.channel_id,
                    channel_name=self.channel_name,
                )
            except Exception as e:
                logger.error(f"Could not submit the document: {str(e)}")
                session.rollback()
                raise

            _tags = ";".join(tags)
            man = Manuscript(
                claim_name=claim_name,
                bid=bid,
                file_path=file_path,
                submission_date=datetime.datetime.utcnow(),
                title=title,
                abstract=abstract,
                authors=author,
                tags=_tags,
                article=article,
                txid=tx.id,
                txhash=tx.hash,
            )
            session.add(man)

            logger.info(f"Manuscript published as {claim_name}!")

            session.commit()

        # return tx

    async def papr_article_create(
        self,
        base_claim_name,
        bid,
        file_path,
        title,
        abstract,
        authors,
        tags,
        encrypt=False,
    ):

        ret = {}
        with Session(self.engine) as session:
            existing_articles = session.execute(
                select(func.count()).select_from(
                    select(Article).filter_by(base_claim_name=base_claim_name)
                )
            ).scalar_one()
            if existing_articles > 0:
                logger.error(
                    f"Cannot create a new article with claim name {base_claim_name}: such an article already exists"
                )
                if existing_articles > 1:
                    logger.error(
                        f"Found {existing_articles} existing articles in the database with claim name {base_claim_name}"
                    )
                return (
                    {}
                )  # TODO: add wrapper function to handle logging + return values

            article = Article(
                base_claim_name=base_claim_name, channel_name=self.channel_name
            )

            article.review_passphrase = generate_human_readable_passphrase()
            ret["review_passphrase"] = article.review_passphrase

            if encrypt:
                article.encryption_passphrase = generate_human_readable_passphrase()
                ret["encryption_passphrase"] = article.encryption_passphrase

            private_key, public_key = generate_rsa_keys(article.review_passphrase)
            article.public_key = public_key
            article.private_key = private_key

            session.add(article)
            session.commit()

        await self._publish_manuscript(
            base_claim_name,
            bid,
            file_path,
            title,
            abstract,
            authors,
            tags,
            revision=0,
            encrypt=encrypt,
        )

        return ret


def run_daemon(daemon):
    loop = asyncio.get_event_loop()

    def __exit():
        raise GracefulExit()

    try:
        loop.add_signal_handler(signal.SIGINT, __exit)
        loop.add_signal_handler(signal.SIGTERM, __exit)
    except NotImplementedError:
        pass  # Not implemented on Windows

    try:
        loop.run_until_complete(daemon.start())
        loop.run_forever()
    except (GracefulExit, KeyboardInterrupt, asyncio.exceptions.CancelledError):
        pass
    finally:
        loop.run_until_complete(daemon.stop())

    if hasattr(loop, "shutdown_asyncgens"):
        loop.run_until_complete(loop.shutdown_asyncgens())


def run_from_args(args):
    conf = Config(**args)

    for directory in (
        conf.data_dir,
        conf.download_dir,
        conf.wallet_dir,
        conf.submission_dir,
        conf.review_dir,
        conf.database_dir,
    ):
        ensure_directory_exists(directory)

    pd = PaprDaemon(conf)
    run_daemon(pd)


if __name__ == "__main__":
    if os.path.isfile("papr.json"):
        with open("papr.json") as f:
            args = json.load(f)

    run_from_args(args)
