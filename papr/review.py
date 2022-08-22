import binascii
import time
import logging

from papr.constants import REVIEW_APPENDIX_TXT

logger = logging.getLogger(__name__)


class Review:
    def __init__(self, sub_name, daemon, channel_name, review_time=None):
        self.sub_name = sub_name
        self.daemon = daemon
        self.channel_name = channel_name
        self.review_time = review_time

        self.review = ""  # TODO: load

    async def generate(self, review):
        # verify that it exists and stuff

        self.review_time = time.time()
        full_review = (
            f"Review for submission {self.sub_name} signed at {self.review_time:.2f}"
        )
        review_hex = binascii.hexlify(full_review.encode("UTF-8")).decode("UTF-8")

        signed = await self.daemon.jsonrpc_channel_sign(
            channel_name=channel_name, hexdata=review_hex
        )

        # TODO: encrypt for server?
        signed_review = f"{full_review}{REVIEW_APPENDIX_TXT}{signed['signature']}\n{signed['signing_ts']}"

        self.review = signed_review

        logger.info("Review created!")

    def submit(self, server):
        # post request to server...
        pass
