import os
import logging
import json

from papr.exceptions import UninitializedException
from papr.network import Network
from papr.settings import USERDATA_DIR

logger = logging.getLogger(__name__)

class User:
    def __init__(self, daemon, identifier=None, network=None):
        self.daemon = daemon
        self.identifier = identifier # Name of the user profile, used when storing userdata to disk
        if identifier:
            self.userdata_load()

        self.channel = None
        if network:
            self.network = network
        else:
            self.network = Network(daemon)

    def userdata_load(self):
        d = os.path.join(USERDATA_DIR, self.identifier)
        if not os.path.isdir(d):
            #os.makedirs(d, exist_ok=True)
            return

        # TODO: load data

    async def channel_load(self, name):
        tx = await self.daemon.jsonrpc_channel_list()
        for res in tx['items']:
            if res.claim_name == name:
                self.channel_id = res.claim_id
                self.channel_name = res.claim_name
                self.channel = res.claim.channel
                break
        else:
            raise Exception(f"Could not find channel {name}")

    async def channel_create(self, name, bid, **kwargs):
        tx = await self.daemon.jsonrpc_channel_create(name=name, bid=bid, **kwargs)
        logger.info(f"Initiated the creation of channel {name} with bid {bid}...")

        await self.daemon.ledger.wait(tx)

        self.channel_id = tx.outputs[0].claim_id
        self.channel_name = tx.outputs[0].claim_name

        self.channel = tx.outputs[0].claim.channel
        logger.info(f"Channel {self.channel_name} created with bid {bid}")
        print("done")

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


