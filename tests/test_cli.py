import asyncio
import os
import tempfile
import logging
from zipfile import ZipFile
from click.testing import CliRunner
from functools import partial
from syncer import sync

from lbry.testcase import CommandTestCase
from lbry.schema.claim import Channel


from papr.user import User
from papr.testcase import PaprDaemonTestCase
from papr.manuscript import Manuscript
from papr.review import sign_review
from papr.server.publish import FormalReview
from papr.server.coordination_server import Server
from papr.server.reviewers import verify_identity
from papr.settings import Config
from papr.utilities import generate_rsa_keys, rsa_decrypt_text, read_all_bytes
from papr.daemon import run_daemon
from papr import cli

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class CliTestCase(CommandTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, result=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config = Config(review_dir=tmpdir)
            super().run(result)

    def _call(self, args):
        runner = CliRunner()
        result = runner.invoke(
            cli.cli, args, catch_exceptions=False, standalone_mode=False
        )

        return result

    async def call(self, cmd):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call, cmd.split())

    async def test_status(self):
        await self.daemon.start()

        result = await self.call("status")

        self.assertEqual(result.return_value, "Success")

    async def test_create_channel_success(self):
        await self.daemon.start()

        result = await self.call("create-channel @Steve --yes")

        self.assertEqual(result.return_value, "Success")

        await self.generate(5)

        user = User(self.daemon)
        await user.channel_load("@Steve")

        self.assertTrue(isinstance(user.channel, Channel))

    async def test_create_channel_success_custom_bid(self):
        await self.daemon.start()

        result = await self.call("create-channel @Steve --yes -b 0.1234")

        self.assertEqual(result.return_value, "Success")

        await self.generate(10)

        user = User(self.daemon)
        await user.channel_load("@Steve")

        self.assertTrue(isinstance(user.channel, Channel))

        channels = await self.daemon.jsonrpc_channel_list()

        self.assertEqual(channels["items"][0].amount, 12340000)

    async def test_create_channel_insufficient_funds(self):
        daemon2 = await self.add_daemon()
        await daemon2.start()

        result = await self.call("create-channel @Steve --yes")

        self.assertEqual(result.return_value, "Insufficient Funds")

        user = User(daemon2)
        with self.assertRaises(Exception):
            await user.channel_load("@Steve")

        self.assertIsNone(user.channel)
