import binascii

from papr.constants import REVIEW_APPENDIX_TXT

async def sign_review(sub_name, sub_url, review, daemon, channel_name): # channel_name?
    # verify that it exists and stuff
    # include reference to paper in review for server

    review_hex = binascii.hexlify(review.strip().encode('UTF-8')).decode('UTF-8')

    signed = await daemon.jsonrpc_channel_sign(channel_name=channel_name, hexdata=review_hex)

    # TODO: encrypt for server?
    signed_review = f"{review.strip()}{REVIEW_APPENDIX_TXT}{signed['signature']}\n{signed['signing_ts']}" # channel_name?

    return signed_review


def submit_review(signed_review, server):
    # post request to server...
    pass
