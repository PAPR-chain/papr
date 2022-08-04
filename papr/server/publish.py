import os
import asyncio
import random

from papr.server.formatting import format_formal_review
from papr.utilities import rsa_encrypt_text

class FormalReview:
    def __init__(self, config, server):
        self.config = config
        self.server = server

    async def publish_review(self, sub_name, sub_channel_id, author_pubkey, reviews, encrypt=True):
        """
            Publishes the reviews on the LBRY blockchain using the identity of the server.
            The authenticity of the reviews is assumed to have been verified already.
            The reviews must be in the desired order (reviewer number).
        """

        cleartext_review = format_formal_review(reviews)
        encrypted_review = rsa_encrypt_text(cleartext_review, author_pubkey)

        # get server info through self.server
        name = sub_name + '_review1' ##

        review_path = os.path.join(self.config.review_dir, name + '_encrypted')
        with open(review_path, 'wb') as out:
            out.write(encrypted_review)

        title = f"Review 1 of {sub_name} by {sub_channel_id}"
        description = f"Peer review of the manuscript {sub_name} by {sub_channel_id}. The content is encrypted for objectivity during the peer review process. The decryption key will be published once the manuscript reaches the official publication stage." # TODO: better
        tags = ["PAPR", "PAPR-review"]
        tx = await self.server.daemon.jsonrpc_stream_create(name, "0.0001", file_path=review_path, title=title, author=self.server.name, tags=tags, channel_id=self.server.channel['claim_id'], channel_name=self.server.channel['name'], description=description)

        return tx
