import asyncio
import os
import tempfile
import logging
import aiohttp
from zipfile import ZipFile
from unittest.mock import patch
from click.testing import CliRunner
from functools import partial
from syncer import sync

from lbry.testcase import CommandTestCase


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

    def call(self, args):
        runner = CliRunner()
        result = runner.invoke(cli.cli, args, catch_exceptions=False, standalone_mode=False)

        '''
        if result.output:
            print(result.output)
        if result.exception:
            print(result.exception)
        '''

        return result

    async def test_create_channel(self):
        await self.daemon.start()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.call, ["status"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.return_value.status_code, 200)
        self.assertIn('jsonrpc', result.return_value.json())
