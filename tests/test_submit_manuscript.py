import asyncio
import os
import tempfile
import warnings
import json
from zipfile import ZipFile
from aioresponses import CallbackResult, aioresponses

from lbry.testcase import IntegrationTestCase, CommandTestCase
from lbry.crypto.hash import sha256
from lbry.crypto.crypt import better_aes_decrypt

from papr.utilities import file_sha256
from papr.config import Config
from papr.testcase import PaprDaemonTestCase

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class ManuscriptTests(PaprDaemonTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, result=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config = Config(submission_dir=tmpdir)
            super().run(result)

    async def asyncSetUp(self):
        await super().asyncSetUp()

        tx = await self.daemon.jsonrpc_channel_create(name="@Steve", bid="0.001")

        await self.generate(1)
        await self.ledger.wait(tx, self.blockchain.block_expected)

        await self.daemon.channel_load("@Steve")

        with aioresponses() as m:
            m.post(
                "http://reviewserver.org/api/channel/register",
                status=201,
                payload={
                    "name": "Test Review Server",
                    "channel_name": "@TestReviewServer",
                },
            )
            await self.daemon.papr_server_add("http://reviewserver.org")

    async def test_create_unencrypted_manuscript(self):
        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")
        hash_i = file_sha256(file_path)

        ret = await self.daemon.papr_article_create(
            base_claim_name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            authors="Steve Tremblay and Bob Roberts",
            tags=["test"],
            server_name="Test Review Server",
            encrypt=False,
        )

        await self.generate(1)
        await self.ledger.wait(ret["tx"], self.blockchain.block_expected)

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
            assert "server.json" in zipped_files

            pdf = z.read("Manuscript_test_preprint.pdf")
            hash_f = sha256(pdf)
            assert hash_f == hash_i

            server_data = json.loads(z.read("server.json"))
            self.assertEqual(server_data["name"], "Test Review Server")
            self.assertEqual(server_data["channel_name"], "@TestReviewServer")

    async def test_create_encrypted_manuscript(self):
        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")
        hash_i = file_sha256(file_path)

        ret = await self.daemon.papr_article_create(
            base_claim_name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            authors="Steve Tremblay and Bob Roberts",
            server_name="Test Review Server",
            tags=["test"],
            encrypt=True,
        )

        await self.generate(1)
        await self.ledger.wait(ret["tx"], self.blockchain.block_expected)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("test_preprint")

        if isinstance(res["test_preprint"], dict) and "error" in res["test_preprint"]:
            raise Exception("Manuscript was not found in claims")

        assert res["test_preprint"].permanent_url == pub.permanent_url

        await self.daemon.jsonrpc_file_save(
            "test_preprint.zip",
            self.daemon.conf.data_dir,
            claim_name="test_preprint",
        )

        assert os.path.isfile(
            os.path.join(self.daemon.conf.data_dir, "test_preprint.zip")
        )

        passphrase = ret["encryption_passphrase"]

        with ZipFile(os.path.join(self.daemon.conf.data_dir, "test_preprint.zip")) as z:
            zipped_files = z.namelist()

            assert len(zipped_files) == 2
            assert "Manuscript_test_preprint.pdf" in zipped_files
            assert "server.json" in zipped_files

            data_enc = z.read("Manuscript_test_preprint.pdf")
            hash_enc = sha256(data_enc)
            assert hash_enc != hash_i

            data_dec = better_aes_decrypt(passphrase, data_enc)
            hash_dec = sha256(data_dec)
            assert hash_dec == hash_i

            server_data = json.loads(z.read("server.json"))
            self.assertEqual(server_data["name"], "Test Review Server")
            self.assertEqual(server_data["channel_name"], "@TestReviewServer")

    async def test_create_duplicate_manuscript(self):
        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        ret = await self.daemon.papr_article_create(
            base_claim_name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            authors="Steve Tremblay and Bob Roberts",
            server_name="Test Review Server",
            tags=["test"],
            encrypt=True,
        )

        await self.generate(1)
        await self.ledger.wait(ret["tx"], self.blockchain.block_expected)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1

        file_path2 = os.path.join(TESTS_DIR, "data", "document2.pdf")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ret = await self.daemon.papr_article_create(
                base_claim_name="test",
                bid="0.001",
                file_path=file_path2,
                title="My other title",
                abstract="we did some more great stuff",
                authors="Steve Tremblay and Bob Roberts",
                server_name="Test Review Server",
                tags=["test"],
                encrypt=False,
            )

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1

        res = await self.daemon.jsonrpc_resolve("test_preprint")
        assert res["test_preprint"].claim.stream.title == "My title"

    async def test_create_revision(self):
        file_path = os.path.join(TESTS_DIR, "data", "document1.pdf")

        ret = await self.daemon.papr_article_create(
            base_claim_name="test",
            bid="0.001",
            file_path=file_path,
            title="My title",
            abstract="we did great stuff",
            authors="Steve Tremblay and Bob Roberts",
            server_name="Test Review Server",
            tags=["test"],
            encrypt=False,
        )

        await self.generate(1)
        await self.ledger.wait(ret["tx"], self.blockchain.block_expected)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1

        file_path2 = os.path.join(TESTS_DIR, "data", "document2.pdf")
        hash_i = file_sha256(file_path2)

        ret = await self.daemon.papr_article_revise(
            base_claim_name="test",
            bid="0.001",
            file_path=file_path2,
            title="My title",
            abstract="we did great stuff",
            authors="Steve Tremblay and Bob Roberts",
            tags=["test"],
            encrypt=False,
        )

        await self.generate(1)
        await self.ledger.wait(ret["tx"], self.blockchain.block_expected)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 2
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("test_r1")
        assert "test_r1" in res
        assert not isinstance(res["test_r1"], dict)
        assert res["test_r1"].permanent_url == pub.permanent_url

        await self.daemon.jsonrpc_file_save(
            "test_r1.zip", self.daemon.conf.data_dir, claim_name="test_r1"
        )

        assert os.path.isfile(os.path.join(self.daemon.conf.data_dir, "test_r1.zip"))

        with ZipFile(os.path.join(self.daemon.conf.data_dir, "test_r1.zip")) as z:
            zipped_files = z.namelist()

            assert len(zipped_files) == 2
            assert "Manuscript_test_r1.pdf" in zipped_files
            assert "server.json" in zipped_files

            pdf = z.read("Manuscript_test_r1.pdf")
            hash_f = sha256(pdf)
            assert hash_f == hash_i
