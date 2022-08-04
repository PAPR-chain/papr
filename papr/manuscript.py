import asyncio
import zipfile
import os

from lbry.crypto.crypt import better_aes_encrypt, better_aes_decrypt

from .settings import CHUNK_SIZE
from .utilities import generate_human_readable_passphrase, generate_rsa_keys


class Manuscript:
    def __init__(self, config, review_passphrase, **args):
        self.config = config
        self.review_passphrase = review_passphrase

    async def create_submission(self, name, bid, file_path, title, abstract, author, tags, channel_id, channel_name, daemon, encrypt=False):
        if not os.path.isfile(file_path):
            logger.error(f"Cannot create a new manuscript: file {file_path} does not exist")
            return

        self.raw_file_path = file_path
        # abstract?

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
        with zipfile.ZipFile(zip_path, 'w') as z: # check if exists...
            z.writestr(f"Manuscript_{name}.pdf", processed_file) # pdf hardcoded
            z.writestr(f"{name}_key.pub", self.public_key)

        # get channel data from "User" instance?
        # Thumbnail
        tx = await daemon.jsonrpc_stream_create(name, bid, file_path=zip_path, title=title, author=author, tags=tags, channel_id=channel_id, channel_name=channel_name, description=abstract)
        return tx
