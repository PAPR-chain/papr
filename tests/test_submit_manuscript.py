import asyncio
import os
import tempfile
from zipfile import ZipFile

from lbry.testcase import IntegrationTestCase, CommandTestCase
from lbry.crypto.hash import sha256
from lbry.crypto.crypt import better_aes_decrypt

from papr.manuscript import Manuscript
from papr.utilities import file_sha256
from papr.settings import Config

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

class DevTestCase(CommandTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, result=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config = Config(submission_dir=tmpdir)
            super(DevTestCase, self).run(result)

    async def test_create_unencrypted_manuscript(self):
        chan = await self.channel_create(name="@Steve", bid="0.001")
        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, "unused_review_passphrase")
        hash_i = file_sha256(file_path)
        tx = await man.create_submission(name="test", bid="0.001", file_path=file_path, title="My title", abstract="we did great stuff", author="Steve Tremblay and Bob Roberts", tags=["test"], channel_id=chan['outputs'][0]['claim_id'], channel_name=chan['outputs'][0]['name'], daemon=self.daemon, encrypt=False)

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll['items']) == 1
        pub = ll['items'][0]

        res = await self.daemon.jsonrpc_resolve('test')
        assert res['test'].permanent_url == pub.permanent_url

        await self.daemon.jsonrpc_file_save('test.zip', self.daemon.conf.data_dir, claim_name="test")

        assert os.path.isfile(os.path.join(self.daemon.conf.data_dir, 'test.zip'))

        with ZipFile(os.path.join(self.daemon.conf.data_dir, 'test.zip')) as z:
            zipped_files = z.namelist()

            assert len(zipped_files) == 2
            assert "Manuscript_test.pdf" in zipped_files
            assert "test_key.pub" in zipped_files

            pdf = z.read("Manuscript_test.pdf")
            hash_f = sha256(pdf)
            assert hash_f == hash_i

    async def test_create_encrypted_manuscript(self):
        chan = await self.channel_create(name="@Steve", bid="0.001")
        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, "unused_review_passphrase")
        hash_i = file_sha256(file_path)
        tx = await man.create_submission(name="test", bid="0.001", file_path=file_path, title="My title", abstract="we did great stuff", author="Steve Tremblay and Bob Roberts", tags=["test"], channel_id=chan['outputs'][0]['claim_id'], channel_name=chan['outputs'][0]['name'], daemon=self.daemon, encrypt=True)

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll['items']) == 1
        pub = ll['items'][0]

        res = await self.daemon.jsonrpc_resolve('test')
        assert res['test'].permanent_url == pub.permanent_url

        await self.daemon.jsonrpc_file_save('test.zip', self.daemon.conf.data_dir, claim_name="test")

        assert os.path.isfile(os.path.join(self.daemon.conf.data_dir, 'test.zip'))

        passphrase = man.encryption_passphrase

        with ZipFile(os.path.join(self.daemon.conf.data_dir, 'test.zip')) as z:
            zipped_files = z.namelist()

            assert len(zipped_files) == 2
            assert "Manuscript_test.pdf" in zipped_files
            assert "test_key.pub" in zipped_files

            data_enc = z.read("Manuscript_test.pdf")
            hash_enc = sha256(data_enc)
            assert hash_enc != hash_i

            data_dec = better_aes_decrypt(passphrase, data_enc)
            hash_dec = sha256(data_dec)
            assert hash_dec == hash_i



