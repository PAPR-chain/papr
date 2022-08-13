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
        self.review_passphrase = review_passphrase

    async def create_submission(self, name, bid, file_path, title, abstract, author, tags, user, encrypt=False, ignore_duplicate_names=False):
        if not os.path.isfile(file_path):
            logger.error(f"Cannot create a new manuscript: file {file_path} does not exist")
            return

        self.raw_file_path = file_path

        raw_file = b""
        with open(file_path, 'rb') as raw:
            while True:
                chunk = raw.read(CHUNK_SIZE)

                if chunk == b"":
                    break
                raw_file += chunk

        if encrypt:
            self.encryption_passphrase = generate_human_readable_passphrase()
            processed_file = better_aes_encrypt(self.encryption_passphrase, raw_file)
        else:
            self.encryption_passphrase = None
            processed_file = raw_file

        self.pem, self.public_key = generate_rsa_keys(self.review_passphrase)

        with open(os.path.join(self.config.submission_dir, f"{name}_key"), "wb") as out:
            out.write(self.pem)

        with open(os.path.join(self.config.submission_dir, f"{name}_key.pub"), "wb") as out:
            out.write(self.public_key)

        zip_path = os.path.join(self.config.submission_dir, name + '.zip')

        if os.path.isfile(zip_path):
            logger.error(f"You have already submitted a manuscript with this name!")
            return None

        if not ignore_duplicate_names:
            is_free = await self.network.verify_claim_free(name)

            if not is_free:
                logger.error(f"Cannot submit manuscript: another claim with this name exists")
                return None

        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr(f"Manuscript_{name}.pdf", processed_file) # pdf hardcoded
            z.writestr(f"{name}_key.pub", self.public_key)

        # Thumbnail
        tx = await user.daemon.jsonrpc_stream_create(name, bid, file_path=zip_path, title=title, author=author, description=abstract, tags=tags, channel_id=user.channel_id, channel_name=user.channel_name)
        return tx

    async def submit_revision(self, name, bid, file_path, title, abstract, author, tags, user, encrypt=False):
        pass

    async def calculate_rating(self):
        pass
