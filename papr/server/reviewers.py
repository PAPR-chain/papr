import binascii

from lbry.wallet.bip32 import PublicKey

from papr.constants import REVIEW_APPENDIX_TXT


async def verify_identity(daemon, review, channel_name):
    """
    Verifies that a review has been signed by the expected channel.
    """

    # TODO: use channel_id to further verify the claim

    review_body, appendix = review.split(REVIEW_APPENDIX_TXT)
    signature, signing_ts = appendix.split("\n")
    signature = binascii.unhexlify(signature.encode())

    ext_reviewer_chan = await daemon.jsonrpc_resolve(channel_name)
    res = ext_reviewer_chan[channel_name]

    pubkey = PublicKey.from_compressed(res.claim.channel.public_key_bytes)
    digest = sha256(signing_ts.encode() + res.claim_hash + review_body.encode())

    return pubkey.verify(signature, digest)
