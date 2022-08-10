import logging
import json

from papr.exceptions import UninitializedException

logger = logging.getLogger(__name__)

class User:
    def __init__(self, daemon):
        self.daemon = daemon
        self.channel = None

    async def channel_create(self, name, bid, **kwargs):
        tx = await self.daemon.jsonrpc_channel_create(name=name, bid=bid, **kwargs)
        logger.info(f"Initiated the creation of channel {name} with bid {bid}...")
        await self.daemon.ledger.wait(tx)

        self.channel_id = tx.outputs[0].claim_id
        self.channel_name = tx.outputs[0].claim_name

        self.channel = tx.outputs[0].claim.channel
        logger.info(f"Channel {self.channel_name} created with bid {bid}")

    @property
    def public_key(self):
        if not self.channel:
            raise UninitializedException(f"User has no channel")
        return self.channel.public_key

    @property
    def public_key_bytes(self):
        if not self.channel:
            raise UninitializedException(f"User has no channel")
        return self.channel.public_key_bytes

    ### Network interaction utilities
    async def verify_claim_free(self, name):
        hits = await self.daemon.jsonrpc_resolve(name)

        ll = len(hits[name])
        logger.warning(f"Found {ll} claims with name {name}")

        if ll > 0:
            return False
        return True
