import asyncio
import os
import tempfile
import warnings
from zipfile import ZipFile

from lbry.testcase import IntegrationTestCase, CommandTestCase
from lbry.crypto.hash import sha256
from lbry.crypto.crypt import better_aes_decrypt

from papr.manuscript import Manuscript
from papr.utilities import file_sha256
from papr.config import Config
from papr.user import User

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class DevTestCase(CommandTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, result=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config = Config(submission_dir=tmpdir)
            super(DevTestCase, self).run(result)

    async def test_create_unencrypted_manuscript(self):
        user = User(self.daemon)
        tx = user.channel_create(name="@Steve", bid="0.001")

        await self.generate(1)
        await tx

        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase")
        hash_i = file_sha256(file_path)
        tx = await man.create_submission(
            name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user,
            encrypt=False,
        )

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("test_preprint")
        assert "test_preprint" in res
        assert not isinstance(res["test_preprint"], dict)
        assert res["test_preprint"].permanent_url == pub.permanent_url

        await self.daemon.jsonrpc_file_save(
            "test_preprint.zip", self.daemon.conf.data_dir, claim_name="test_preprint"
        )

        assert os.path.isfile(
            os.path.join(self.daemon.conf.data_dir, "test_preprint.zip")
        )

        with ZipFile(os.path.join(self.daemon.conf.data_dir, "test_preprint.zip")) as z:
            zipped_files = z.namelist()

            assert len(zipped_files) == 2
            assert "Manuscript_test_preprint.pdf" in zipped_files
            assert "test_preprint_key.pub" in zipped_files

            pdf = z.read("Manuscript_test_preprint.pdf")
            hash_f = sha256(pdf)
            assert hash_f == hash_i

    async def test_create_encrypted_manuscript(self):
        user = User(self.daemon)
        await user.channel_create(name="@Steve", bid="0.001")

        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase")
        hash_i = file_sha256(file_path)
        tx = await man.create_submission(
            name="tremblay-project",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user,
            encrypt=True,
        )

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("tremblay-project_preprint")
        assert res["tremblay-project_preprint"].permanent_url == pub.permanent_url

        await self.daemon.jsonrpc_file_save(
            "tremblay-project_preprint.zip",
            self.daemon.conf.data_dir,
            claim_name="tremblay-project_preprint",
        )

        assert os.path.isfile(
            os.path.join(self.daemon.conf.data_dir, "tremblay-project_preprint.zip")
        )

        passphrase = man.encryption_passphrase

        with ZipFile(
            os.path.join(self.daemon.conf.data_dir, "tremblay-project_preprint.zip")
        ) as z:
            zipped_files = z.namelist()

            assert len(zipped_files) == 2
            assert "Manuscript_tremblay-project_preprint.pdf" in zipped_files
            assert "tremblay-project_preprint_key.pub" in zipped_files

            data_enc = z.read("Manuscript_tremblay-project_preprint.pdf")
            hash_enc = sha256(data_enc)
            assert hash_enc != hash_i

            data_dec = better_aes_decrypt(passphrase, data_enc)
            hash_dec = sha256(data_dec)
            assert hash_dec == hash_i

    async def test_create_duplicate_manuscript(self):
        user = User(self.daemon)
        tx = user.channel_create(name="@Steve", bid="0.001")

        await self.generate(1)
        await tx

        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase")
        hash_i = file_sha256(file_path)
        tx = await man.create_submission(
            name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user,
            encrypt=False,
        )

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        file_path2 = os.path.join(TESTS_DIR, "data", "document2.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase2")
        hash_i = file_sha256(file_path)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tx = await man.create_submission(
                name="test",
                bid="0.001",
                file_path=file_path,
                title="My other title",
                abstract="we did some more great stuff",
                author="Steve Tremblay and Bob Roberts",
                tags=["test"],
                user=user,
                encrypt=False,
            )

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("test_preprint")
        assert res["test_preprint"].claim.stream.title == "My title"

    async def test_create_duplicate_manuscript_no_zip(self):
        user = User(self.daemon)
        tx = user.channel_create(name="@Steve", bid="0.001")

        await self.generate(1)
        await tx

        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase")
        hash_i = file_sha256(file_path)
        tx = await man.create_submission(
            name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user,
            encrypt=False,
        )

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        os.remove(os.path.join(self.config.submission_dir, "test_preprint.zip"))

        file_path2 = os.path.join(TESTS_DIR, "data", "document2.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase2")
        hash_i = file_sha256(file_path)

        tx = await man.create_submission(
            name="test",
            bid="0.001",
            file_path=file_path,
            title="My other title",
            abstract="we did some more great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user,
            encrypt=False,
        )

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("test_preprint")
        assert res["test_preprint"].claim.stream.title == "My title"

    async def test_create_manuscript_multiple_duplicates(self):
        daemon2 = await self.add_daemon()
        user2 = User(daemon2)
        await self.generate(2)
        addresses = (
            await daemon2.wallet_manager.default_account.receiving.get_addresses()
        )
        await self.send_to_address_and_wait(addresses[0], 1, 1, ledger=daemon2.ledger)

        tx = user2.channel_create(name="@Steve", bid="0.001")

        await self.generate(2)
        await tx

        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        man = Manuscript(self.config, user2.network, "unused_review_passphrase")
        tx = await man.create_submission(
            name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user2,
            encrypt=False,
            ignore_duplicate_names=True,
        )
        os.remove(os.path.join(self.config.submission_dir, "test_preprint.zip"))

        await self.generate(2)

        daemon3 = await self.add_daemon()
        user3 = User(daemon3)

        addresses = (
            await daemon3.wallet_manager.default_account.receiving.get_addresses()
        )
        await self.send_to_address_and_wait(addresses[0], 1, 1, ledger=daemon3.ledger)

        tx = user3.channel_create(name="@Bob", bid="0.001")

        await self.generate(1)
        await tx

        file_path = os.path.join(TESTS_DIR, "data", "document2.pdf")

        man = Manuscript(self.config, user3.network, "unused_review_passphrase")
        tx = await man.create_submission(
            name="test",
            bid="0.002",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user3,
            encrypt=False,
            ignore_duplicate_names=True,
        )
        os.remove(os.path.join(self.config.submission_dir, "test_preprint.zip"))

        await self.generate(2)

        user = User(self.daemon)
        tx = user3.channel_create(name="@Robert", bid="0.001")

        await self.generate(1)
        await tx

        file_path2 = os.path.join(TESTS_DIR, "data", "document3.pdf")

        man = Manuscript(self.config, user.network, "unused_review_passphrase2")

        tx = await man.create_submission(
            name="test",
            bid="0.001",
            file_path=file_path,
            title="My other title",
            abstract="we did some more great stuff",
            author="Steve Tremblay and Bob Roberts",
            tags=["test"],
            user=user,
            encrypt=False,
        )

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 0

    async def test_load_channel(self):
        user = User(self.daemon)
        tx = user.channel_create(name="@Steve", bid="0.001")

        await self.generate(1)
        await tx

        user2 = User(self.daemon)
        assert user2.channel is None

        await user2.channel_load("@Steve")

        assert user2.channel.public_key == user.channel.public_key
        assert user2.public_key_bytes == user.public_key_bytes
