import logging

from lbry.wallet.transaction import Output

logger = logging.getLogger(__name__)

class Network:
    def __init__(self, daemon):
        self.daemon = daemon

    async def verify_claim_free(self, name):
        hits = await self.daemon.jsonrpc_resolve(name)

        if not isinstance(hits[name], Output):
            logger.info(f"Found no claim with name {name}")
            return True

        logger.warning(f"Found claim(s) with name {name}")

        return False

