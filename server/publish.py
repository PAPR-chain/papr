import asyncio
import random

from papr.server.formatting import format_formal_review
from papr.utilities import rsa_encrypt_text

class FormalReview:
    def __init__(self, config):
        self.config = config

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
        title = f"Review 1 of {sub_name} by {sub_channel_id}"
        author = "PAPR server - Sherbrooke" # Server identifier (must match with channel id...)
        description = f"Peer review of the manuscript {sub_name} by {sub_channel_id}. The content is encrypted for objectivity during the peer review process. The decryption key will be published once the manuscript reaches the official publication stage." # TODO: better
        tags = ["PAPR", "PAPR-review"]
        tx = await self.server.daemon.jsonrpc_stream_create(name, "0.0001", file_path=review_path, title=title, author=author, tags=tags, channel_id=self.server.channel['claim_id'], channel_name=self.server.channel['name'], description=description)

        return tx
