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
import json
import binascii

import aiohttp
from aiohttp.web import GracefulExit

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from lbry.extras.daemon.daemon import Daemon, JSONRPCServerType
from lbry.extras.cli import ensure_directory_exists
from lbry.extras.daemon.componentmanager import ComponentManager
from lbry.wallet.transaction import Output
from lbry.wallet.bip32 import PublicKey
from lbry.crypto.crypt import better_aes_encrypt, better_aes_decrypt

from papr.utilities import SECP_decrypt_text
from papr.models import Base, Article, Manuscript, Server, Review
from papr.config import Config, IS_TEST, CHUNK_SIZE
from papr.exceptions import PaprException
from papr.utilities import (
    generate_rsa_keys,
    generate_human_readable_passphrase,
    DualLogger,
)

logger = DualLogger(logging.getLogger(__name__))


class PAPRJSONRPCServerType(JSONRPCServerType):
    def __new__(mcs, name, bases, newattrs):
        klass = type.__new__(mcs, name, bases, newattrs)
        klass.callable_methods = {}
        klass.deprecated_methods = {}

        for methodname in dir(klass):
            name = ""
            if methodname.startswith("jsonrpc_"):
                name = methodname.split("jsonrpc_")[1]
            elif methodname.startswith("papr_") or methodname.startswith("macro_"):
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
        self.channel_id = None
        self.channel_name = None
        self.channel = None

        self.headers = {}

        Base.metadata.create_all(self.conn)

    async def initialize(self):
        await super().initialize()

        if self.conf.active_channel:
            try:
                await self.channel_load(conf.active_channel)
            except PaprException:
                logger.warning(
                    f"Could not load channel {conf.active_channel}, some features will not be available"
                )
            else:
                logger.info(f"Channel {conf.active_channel} loaded")

    async def stop(self):
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

    async def macro_get_public_key(self, channel_name):
        """
        Retrieves the (SECP) public key for a given channel and returns it in base64
        """
        hits = await self.jsonrpc_resolve(channel_name)

        if not isinstance(hits[channel_name], Output):
            return logger.info(f"Found no claim with name {channel_name}")

        tpub_hex = hits[channel_name].claim.channel.public_key
        tpub = base64.b64encode(bytes.fromhex(tpub_hex)).decode()
        return {"public_key": tpub}

    async def papr_server_add(self, url):
        # clean and certify url

        if self.channel_name is None:
            return logger.error(f"Cannot register to the server, no channel is loaded")

        payload = {
            "channel_name": self.channel_name,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/api/register/", json=payload) as resp:
                status_code = resp.status
                data = await resp.json()

        if status_code == 201:
            with Session(self.engine) as session:
                server = Server(url=url, **data)
                session.add(server)
                session.commit()
                logger.info(
                    f"Added server {server.name} ({server.channel_name}) to the list of known servers!"
                )
        else:
            return logger.error(
                f"Could not register to {url}, received status code {status_code}"
            )

        return data

    async def papr_review_create(self, submission_claim_name, review_text=""):
        sub_claim = await self.jsonrpc_get(submission_claim_name)

        if "error" in sub_claim:
            return logger.error(
                f"Failed to resolve submission {submission_claim_name}: {sub_claim['error']}"
            )

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
            return logger.error(
                f"The submission {submission_claim_name} is not associated with any channel"
            )

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

            link = f"{server.url}/api/review"

        # TODO: encrypt for server?
        payload = {
            "review": full_review,
            "signature": signed["signature"],
            "signing_ts": signed["signing_ts"],
        }

        async with aiohttp.ClientSession() as session:  # wrapper to handle token
            async with session.post(link, json=payload) as resp:
                status_code = resp.status
                if status_code == 201:
                    logger.info(
                        f"Review of {reviewed_submission_claim_name} accepted by {server_channel_name}"
                    )
                else:
                    text = await resp.text()
                    return logger.error(
                        f"Error while submitting the review of {reviewed_submission_claim_name} to {server_channel_name}\nStatus code: {status_code}\nReason: {text['reason']}"
                    )

    async def papr_review_verify(review, channel_name):
        """
        Verifies that a review has been signed by the expected channel.
        Used by: Server
        """

        # TODO: use channel_id to further verify the claim

        signature = binascii.unhexlify(review["signature"].encode())

        ext_reviewer_chan = await daemon.jsonrpc_resolve(channel_name)
        res = ext_reviewer_chan[channel_name]

        pubkey = PublicKey.from_compressed(res.claim.channel.public_key_bytes)
        digest = sha256(
            review["signing_ts"].encode() + res.claim_hash + review["review"].encode()
        )

        return pubkey.verify(signature, digest)

    async def papr_reviewround_publish(self, sub_name, sub_channel_id, encrypt=True):
        """
        Publishes the reviews on the LBRY blockchain using the identity of the server.
        The authenticity of the reviews is assumed to have been verified already.
        The reviews must be in the desired order (reviewer number).
        Used by: Server
        """

        title = f"Review 1 of {sub_name} by {sub_channel_id}"
        description = f"Peer review of the manuscript {sub_name} by {sub_channel_id}. The content is encrypted for objectivity during the peer review process. The decryption key will be published once the manuscript reaches the official publication stage."  # TODO: better
        tags = ["PAPR", "PAPR-review"]
        tx = await self.server.daemon.jsonrpc_stream_create(
            name,
            "0.0001",
            file_path=self.enc_review_path,
            title=title,
            author=self.server.name,  ###
            tags=tags,
            channel_id=self.server.channel["claim_id"],
            channel_name=self.server.channel["name"],
            description=description,
        )

        return tx

    async def _publish_manuscript(
        self,
        base_claim_name,
        bid,
        file_path,
        title,
        abstract,
        authors,
        tags,
        revision=0,
        encrypt=True,
        ignore_duplicate_names=False,
    ):

        if not os.path.isfile(file_path):
            return logger.error(
                f"Cannot create a new manuscript: file {file_path} does not exist"
            )
            return

        raw_file = b""
        with open(file_path, "rb") as raw:
            while True:
                chunk = raw.read(CHUNK_SIZE)

                if chunk == b"":
                    break
                raw_file += chunk

        with Session(self.engine) as session:
            article = session.execute(
                select(Article).filter_by(base_claim_name=base_claim_name)
            ).scalar_one()

            if article.reviewed and encrypt:
                raise Exception(
                    "Invalid combination of parameters: cannot encrypt a reviewed version"
                )

            article.revision = revision

            if article.reviewed:
                claim_name = f"{base_claim_name}_v{revision}"
            else:
                if revision == 0:
                    claim_name = f"{base_claim_name}_preprint"
                else:
                    claim_name = f"{base_claim_name}_r{revision}"

                if article.review_server is None and not IS_TEST:
                    raise PaprException(
                        f"No server given for publishing the unreviewed manuscript {claim_name}"
                    )

            if encrypt:
                processed_file = better_aes_encrypt(
                    article.encryption_passphrase, raw_file
                )
            else:
                processed_file = raw_file

            zip_path = os.path.join(self.conf.submission_dir, claim_name + ".zip")

            if os.path.isfile(zip_path):
                return logger.error(
                    f"You have already submitted a manuscript with this name!"
                )

            if not ignore_duplicate_names:
                is_free = await self.verify_claim_free(claim_name)

                if not is_free:
                    return logger.error(
                        f"Cannot submit manuscript: another claim with this name exists"
                    )

            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr(
                    f"Manuscript_{claim_name}.pdf", processed_file
                )  # pdf hardcoded
                """
                z.writestr(
                    f"{claim_name}_key.pub", article.public_key
                )  # just name? useful?
                """
                # Add reference to reviewing server

            # Thumbnail
            try:
                tx = await self.jsonrpc_stream_create(  # explicit review server request
                    claim_name,
                    bid,
                    file_path=zip_path,
                    title=title,
                    author=authors,
                    description=abstract,
                    tags=tags,
                    channel_id=self.channel_id,
                    channel_name=self.channel_name,
                )
            except Exception as e:
                session.rollback()
                return logger.error(f"Could not submit the document: {str(e)}")

            logger.info(f"Manuscript published as {claim_name}!")

            _tags = ";".join(tags)
            man = Manuscript(
                claim_name=claim_name,
                bid=bid,
                file_path=file_path,
                submission_date=datetime.datetime.utcnow(),
                title=title,
                abstract=abstract,
                authors=authors,
                tags=_tags,
                article=article,
                txid=tx.id,
                txhash=tx.hash,
            )
            session.add(man)
            session.add(article)

            session.commit()

        return tx

    async def _get_api_token(self, base_url):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/api/token/{self.channel_name}") as resp:
                if resp.status != 200:
                    raise Exception(
                        f"Could not get token from API server at {base_url}/api/token/{self.channel_name}"
                    )
                data = await resp.json()

        chans = (await self.jsonrpc_channel_list())["items"]
        for c in chans:
            if c.claim_name == self.channel_name:
                private_pem = c.private_key.to_pem()
                break
        else:
            return logger.error(
                f"Could not find channel {self.channel_name} in the channel list, authentication to API server aborted..."
            )

        # Inflates the private key... could be marginally more efficient
        private_key = base64.b64encode(private_pem).decode()

        self.token_access = SECP_decrypt_text(
            private_key, data["pub_key"], data["access"]
        )

        # The refresh token should be used too
        self.token_refresh = SECP_decrypt_text(
            private_key, data["pub_key"], data["refresh"]
        )

        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {str(self.token_access)}"}

    async def _get_url(self, base_url, suburl):
        if self.headers == {}:
            error = await self._get_api_token(base_url)
            if error:
                return error

        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{base_url}{suburl}",
                        headers=self.headers,
                    ) as resp:
                        msg = await resp.text()
                        data = await resp.json()
                        status = resp.status
                if (
                    status == 401
                    and data["detail"].find(
                        "Authentication credentials were not provided."
                    )
                    != -1
                ):
                    if attempt == 1:
                        return {
                            "error": f"Could not authenticate and get {base_url}",
                            "status_code": status,
                        }
                    error = await self._get_api_token(base_url)
                    if error:
                        return error
                    else:
                        continue

                if status in [200, 201, 204]:
                    return {"status_code": resp.status, "json": data, "content": msg}
            except aiohttp.client_exceptions.ClientConnectionError:
                logger.info(
                    f"Error while trying to get {base_url}{suburl}  (Code {status})..."
                )

        else:
            return {
                "error": f"Failed to get {base_url}{suburl} (Code {status})",
                "status_code": status,
            }

    async def _post_to_url(self, base_url, suburl, payload):
        if self.headers == {}:
            error = await self._get_api_token(base_url)
            if error:
                return error

        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{base_url}{suburl}",
                        json=payload,
                        headers=self.headers,
                    ) as resp:
                        msg = await resp.text()
                        data = await resp.json()
                        status = resp.status
                if (
                    status == 401
                    and data["detail"].find(
                        "Authentication credentials were not provided."
                    )
                    != -1
                ):
                    if attempt == 1:
                        return {
                            **logger.error(
                                f"Could not authenticate and post to {base_url}"
                            ),
                            "status_code": status,
                        }
                    error = await self._get_api_token(base_url)
                    if error:
                        return error
                    else:
                        continue

                if status in [200, 201, 204]:
                    return {"status_code": resp.status, "json": data}
            except aiohttp.client_exceptions.ClientConnectionError:
                logger.info(
                    f"Error while trying to post to {base_url}{suburl}  (Code {status})..."
                )

        else:
            return {
                **logger.error(f"Failed to post to {base_url}{suburl} (Code {status})"),
                "status_code": status,
            }

    async def papr_article_request_review(self, article_claim, server_name):
        with Session(self.engine) as session:
            article = session.execute(
                select(Article).filter_by(base_claim_name=article_claim)
            ).scalar_one_or_none()

            if not article:
                return logger.error(
                    f"Cannot send a review request for article {article_claim}: no such article found"
                )

            server = session.execute(
                select(Server).filter_by(name=server_name)
            ).scalar_one_or_none()

            if not server:
                return logger.error(
                    f"Cannot send a review request for article {article_claim} to server {server_name}: no such server found"
                )

            payload = {
                "title": article.title,
                "article": article.base_claim_name,
                "claim_name": article.latest_manuscript.claim_name,
                "authors": article.authors,
                "corresponding_author": article.channel_name,
                "revision": article.revision,
            }
            return await self._post_to_url(server.url, "/api/submit/", payload)

    async def papr_article_create(
        self,
        base_claim_name,
        bid,
        file_path,
        title,
        abstract,
        authors,
        tags,
        server_name="",
        encrypt=False,
    ):

        # serverless?

        ret = {}
        with Session(self.engine) as session:
            existing_articles = session.execute(
                select(func.count()).select_from(
                    select(Article).filter_by(base_claim_name=base_claim_name)
                )
            ).scalar_one()

            if existing_articles > 0:
                return logger.error(
                    f"Cannot create a new article with claim name {base_claim_name}: such an article already exists"
                )
                if existing_articles > 1:
                    return logger.error(
                        f"Found {existing_articles} existing articles in the database with claim name {base_claim_name}"
                    )

            if server_name:
                server = session.execute(
                    select(Server).filter_by(name=server_name)
                ).scalar_one_or_none()

                if not server:
                    return logger.error(
                        f"The review server {server_name} is not known. First register to the server."
                    )
            else:
                server = None

            article = Article(
                base_claim_name=base_claim_name,
                channel_name=self.channel_name,
                reviewed=False,
                revision=0,
            )

            if server:
                article.review_server = server

            article.review_passphrase = generate_human_readable_passphrase()
            ret["review_passphrase"] = article.review_passphrase

            if encrypt:
                article.encryption_passphrase = generate_human_readable_passphrase()
                ret["encryption_passphrase"] = article.encryption_passphrase

            session.add(article)
            session.commit()

        tx = await self._publish_manuscript(
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

        if isinstance(tx, dict):
            # Delete article
            return tx
        else:
            ret["tx"] = tx
            return ret

    async def papr_article_revise(
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
        with Session(self.engine) as session:
            article = session.execute(
                select(Article).filter_by(base_claim_name=base_claim_name)
            ).scalar_one_or_none()

            if article is None:
                return logger.error(
                    f"Cannot revise the article with claim name {base_claim_name}: such an article does not exists"
                )

            rev = article.revision + 1

        tx = await self._publish_manuscript(
            base_claim_name,
            bid,
            file_path,
            title=title,
            abstract=abstract,
            authors=authors,
            tags=tags,
            revision=rev,
            encrypt=encrypt,
        )

        if isinstance(tx, dict):
            return tx
        else:
            return {"tx": tx}

    async def papr_article_accept(
        self,
        base_claim_name,
    ):
        with Session(self.engine) as session:
            article = session.execute(
                select(Article).filter_by(base_claim_name=base_claim_name)
            ).scalar_one_or_none()

            if article is None:
                return logger.error(
                    f"Cannot revise the article with claim name {base_claim_name}: such an article does not exists"
                )

            article.reviewed = True
            article.revision = 1

            payload = {
                "base_claim_name": article.base_claim_name,
                "channel_name": article.channel_name,
                "review_passphrase": article.review_passphrase,
                "revision": article.revision,
                "title": article.title,
                "abstract": article.abstract,
                "authors": article.authors,
                "tags": article.tags,
            }

            if article.encryption_passphrase:
                payload["encryption_passphrase"] = article.encryption_passphrase

            # get server
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{article.review_server.url}/accept", json=payload
                ) as resp:
                    status_code = resp.status
                    msg = await resp.text()

            if status_code != 200:
                session.rollback()
                return logger.error(
                    f"Error while sending acceptance of {base_claim_name} to the server.\n Status code: {status_code}\nReason: {msg}"
                )

            session.add(article)
            session.commit()

        return logger.info(
            f"Sent review acceptance of article {article.base_claim_name} to the server"
        )

    async def papr_article_status(
        self,
        base_claim_name,
    ):
        with Session(self.engine) as session:
            article = session.execute(
                select(Article).filter_by(base_claim_name=base_claim_name)
            ).scalar_one_or_none()

            if article is None:
                return logger.error(
                    f"Cannot revise the article with claim name {base_claim_name}: such an article does not exists"
                )

            status = {
                "reviewed": article.reviewed,
                "revision": article.revision,
                "review_server": article.review_server.name,
            }
            server_status = await self._get_url(
                article.review_server.url, f"/api/status/{base_claim_name}"
            )
            status["article"] = server_status["json"]
        return status

    async def _get_article_review_server(self, claim_name):
        res = await self.jsonrpc_get(claim_name)

        if "error" in res:
            return logger.error(f"Could not resolve {claim_name}")

        path = res["results"]["download_path"]

        with ZipFile(path) as z:
            zipped_files = z.namelist()
            if "server.json" not in zipped_files:
                return logger.error(
                    f"Manuscript {claim_name} does not contain a reference to its review server"
                )

            try:
                server_data = json.reads(z.read("server.json"))
            except json.JSONDecodeError:
                return logger.error(
                    f"Could not decode JSON from manuscript {claim_name}"
                )

        return server_data

    async def papr_reviewer_recommend(
        self, claim_name, reviewer_name, reviewer_channel="", reviewer_email=""
    ):
        if not email and not reviewer_channel:
            return logger.error(
                f"Cannot submit reviewer recommendation: no contact information provided. A channel or an email is required."
            )

        if not self.channel_name:
            return logger.error(
                f"Cannot submit reviewer recommendation: no channel loaded. Recommendations cannot be anonymous"
            )

        server_data = await self._get_article_review_server(claim_name)
        if "error" in server_data:
            return server_data

        # Check status?
        # Add reason text possibly
        # Add recommendation degree

        payload = {
            "claim_name": claim_name,
            "reviewer_name": reviewer_name,
            "recommender_channel": self.channel_name,
        }

        if reviewer_channel:
            payload["reviewer_channel"] = reviewer_channel

        if email:
            payload["reviewer_email"] = reviewer_email

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server_data['url']}/api/recommend", json=payload
            ) as resp:
                status_code = resp.status
                msg = await resp.text()

        if status_code != 200:
            return logger.error(
                f"Error while sending reviewer recommendation for {base_claim_name} to the server.\n Status code: {status_code}\nReason: {msg}"
            )

        return logger.info(f"Reviewer recommendation sent to the server, thank you!")


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
