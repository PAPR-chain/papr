import logging
import asyncio
import zipfile
import os

from lbry.crypto.crypt import better_aes_encrypt, better_aes_decrypt

from papr.settings import CHUNK_SIZE
from papr.utilities import generate_human_readable_passphrase, generate_rsa_keys

logger = logging.getLogger(__name__)


class Manuscript:
    ### Load from file
    def __init__(self, config, network, review_passphrase, **args):
        self.config = config
        self.network = network

        # Passphrase to encrypt communications between reviewers and authors during the review process, mandatory (?)
        # Used to encrypt the RSA private key
        self.review_passphrase = review_passphrase

        # Passphrase to encrypt the original publication ("private" submission). Optional (no encryption = "preprint" submission)
        self.encryption_passphrase = None

        self.status = 0

    async def _publish(
        self,
        claim_name,
        bid,
        file_path,
        title,
        abstract,
        author,
        tags,
        user,
        revision=0,
        encrypt=True,
        official=False,
        ignore_duplicate_names=False,
    ):

        if not os.path.isfile(file_path):
            logger.error(
                f"Cannot create a new manuscript: file {file_path} does not exist"
            )
            return  # return error?

        raw_file = b""
        with open(file_path, "rb") as raw:
            while True:
                chunk = raw.read(CHUNK_SIZE)

                if chunk == b"":
                    break
                raw_file += chunk

        if official and encrypt:
            raise Exception(
                "Invalid combination of parameters: cannot encrypt an official version"
            )
        if encrypt:
            processed_file = better_aes_encrypt(self.encryption_passphrase, raw_file)
        else:
            processed_file = raw_file

        zip_path = os.path.join(self.config.submission_dir, claim_name + ".zip")

        if os.path.isfile(zip_path):
            logger.error(f"You have already submitted a manuscript with this name!")
            return None

        if not ignore_duplicate_names:
            is_free = await self.network.verify_claim_free(claim_name)

            if not is_free:
                logger.error(
                    f"Cannot submit manuscript: another claim with this name exists"
                )
                return None

        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr(f"Manuscript_{claim_name}.pdf", processed_file)  # pdf hardcoded
            z.writestr(f"{claim_name}_key.pub", self.public_key)  # just name?

        # Thumbnail
        tx = await user.daemon.jsonrpc_stream_create(
            claim_name,
            bid,
            file_path=zip_path,
            title=title,
            author=author,
            description=abstract,
            tags=tags,
            channel_id=user.channel_id,
            channel_name=user.channel_name,
        )
        return tx

    async def create_submission(
        self,
        name,
        bid,
        file_path,
        title,
        abstract,
        author,
        tags,
        user,
        encrypt=False,
        **kwargs,
    ):
        if encrypt:
            self.encryption_passphrase = generate_human_readable_passphrase()

        self.pem, self.public_key = generate_rsa_keys(self.review_passphrase)

        with open(os.path.join(self.config.submission_dir, f"{name}_key"), "wb") as out:
            out.write(self.pem)

        with open(
            os.path.join(self.config.submission_dir, f"{name}_key.pub"), "wb"
        ) as out:
            out.write(self.public_key)

        self.status = 1  # ?

        claim_name = f"{name}_preprint"
        return await self._publish(
            claim_name,
            bid,
            file_path,
            title,
            abstract,
            author,
            tags,
            user,
            revision=0,
            encrypt=encrypt,
            **kwargs,
        )

    async def submit_revision(
        self,
        name,
        bid,
        file_path,
        title,
        abstract,
        author,
        tags,
        user,
        revision,
        encrypt=True,
        **kwargs,
    ):
        claim_name = f"{name}_r{revision}"
        return await self._publish(
            claim_name,
            bid,
            file_path,
            title,
            abstract,
            author,
            tags,
            user,
            revision=revision,
            encrypt=encrypt,
            **kwargs,
        )

    async def submit_official_version(
        self, name, bid, file_path, title, abstract, author, tags, user, **kwargs
    ):
        claim_name = f"{name}_v1"
        return await self._publish(
            claim_name,
            bid,
            file_path,
            title,
            abstract,
            author,
            tags,
            user,
            encrypt=False,
            official=True,
            **kwargs,
        )

    async def calculate_rating(self):
        pass
