import asyncio
import os
import tempfile
from zipfile import ZipFile

from lbry.testcase import CommandTestCase
from lbry.crypto.hash import sha256, double_sha256
from lbry.crypto.crypt import better_aes_decrypt

from papr.manuscript import Manuscript
from papr.network import Network
from papr.review import Review
from papr.server.reviewround import ReviewRound
from papr.server.server import Server
from papr.server.reviewers import verify_identity
from papr.config import Config
from papr.utilities import generate_rsa_keys, rsa_decrypt_text, read_all_bytes

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class ServerTestCase(CommandTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, result=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config = Config(review_dir=tmpdir)
            super(ServerTestCase, self).run(result)

    async def test_publish_anonymized_reviews(self):
        # Apparently, awaiting both at once changes the required bid, which goes over the available funds (???)
        chan = await self.channel_create(name="@Server", bid="0.001")
        sub_chan = await self.channel_create(name="@CorrespondingAuthor", bid="0.001")

        network = Network(self.daemon)
        server = Server("Test PAPR server", "@Server", network)

        rev = ReviewRound(self.config, server, "perfect, just cite me a lot more")

        reviews = [
            "pretty groundbreaking stuff, 2/10",
            "perfect, just cite me a lot more",
        ]
        privkey, pubkey = generate_rsa_keys(
            "testpassword"
        )  # Hypothetical author RSA keys

        rev.author_pub_key = pubkey

        rev.set_reviews(reviews)

        tx = await rev.publish(
            sub_name="tremblay-test-manuscript",
            sub_channel_id=sub_chan["outputs"][0]["claim_id"],
        )

        await self.generate(5)

        ll = await self.daemon.jsonrpc_stream_list()
        assert len(ll["items"]) == 1
        pub = ll["items"][0]

        res = await self.daemon.jsonrpc_resolve("tremblay-test-manuscript_review1")
        assert (
            res["tremblay-test-manuscript_review1"].permanent_url == pub.permanent_url
        )

        await self.daemon.jsonrpc_file_save(
            "review",
            self.daemon.conf.data_dir,
            claim_name="tremblay-test-manuscript_review1",
        )

        assert os.path.isfile(os.path.join(self.daemon.conf.data_dir, "review"))

        enc_review = read_all_bytes(os.path.join(self.daemon.conf.data_dir, "review"))

        try:
            pseudo_dec_review = enc_review.decode("UTF-8")
        except UnicodeDecodeError:
            pass
        else:
            for r in reviews:
                assert r not in pseudo_dec_review

        dec_review = rsa_decrypt_text(enc_review, privkey, "testpassword")

        for r in reviews:
            assert r in dec_review

    async def test_verify_reviewer_identity(self):
        rev_daemon = await self.add_daemon()
        rev_addr = (
            await rev_daemon.wallet_manager.default_account.receiving.get_or_create_usable_address()
        )
        await self.send_to_address_and_wait(rev_addr, 2, 1, ledger=rev_daemon.ledger)
        reviewer = await rev_daemon.jsonrpc_channel_create(
            name="@Reviewer2", bid="0.001"
        )

        await self.generate(10)

        review = Review("submission-name", rev_daemon, "@Reviewer2")
        await review.generate("Everything about this work is bad")

        assert verify_identity(self.daemon, review.review, "@Reviewer2")
