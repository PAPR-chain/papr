import os
import asyncio
import random

from papr.server.formatting import format_formal_review
from papr.utilities import rsa_encrypt_text
from papr.localdata import PaprObject


class ReviewRound(PaprObject):
    def __init__(
        self,
        config,
        server,
        submission_name,
        publication_time=None,
        author_pub_key=None,
    ):
        self.config = config
        self.server = server

        self.submission_name = submission_name
        self.publication_time = publication_time
        self.author_pub_key = author_pub_key

        self.reviews = []
        self.enc_review_path = b""

    async def retrieve_author_pub_key(self):
        # From the channel name, get the key from the network
        pass

    def set_reviews(self, reviews):
        if not self.author_pub_key:
            raise Exception(
                f"No author public key for review round of submission {submission_name}"
            )

        self.reviews = reviews  # Should be objects?

        cleartext_reviews = format_formal_review(reviews)
        encrypted_reviews = rsa_encrypt_text(cleartext_reviews, self.author_pub_key)

        # get server info through self.server
        name = sub_name + "_review1"  ##

        self.enc_review_path = os.path.join(
            self.config.review_dir, self.submission_namename + "_encrypted"
        )
        with open(self.enc_review_path, "wb") as out:
            out.write(encrypted_reviews)

    async def publish(self, sub_name, sub_channel_id, encrypt=True):
        """
        Publishes the reviews on the LBRY blockchain using the identity of the server.
        The authenticity of the reviews is assumed to have been verified already.
        The reviews must be in the desired order (reviewer number).
        """

        title = f"Review 1 of {sub_name} by {sub_channel_id}"
        description = f"Peer review of the manuscript {sub_name} by {sub_channel_id}. The content is encrypted for objectivity during the peer review process. The decryption key will be published once the manuscript reaches the official publication stage."  # TODO: better
        tags = ["PAPR", "PAPR-review"]
        tx = await self.server.daemon.jsonrpc_stream_create(
            name,
            "0.0001",
            file_path=self.enc_review_path,
            title=title,
            author=self.server.name,
            tags=tags,
            channel_id=self.server.channel["claim_id"],
            channel_name=self.server.channel["name"],
            description=description,
        )

        return tx
