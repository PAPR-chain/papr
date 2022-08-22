import logging

from papr.localdata import PaprObject

logger = logging.getLogger(__name__)


class Server(PaprObject):
    SAVED_FIELDS = ["name", "channel_name", "url", "port", "public_key"]

    def __init__(
        self,
        name,
        channel_name,
        url="localhost",
        port=80,
        public_key=None,
        network=None,
    ):
        self.name = name
        self.channel_name = channel_name
        self.url = url
        self.port = port
        self.public_key = public_key

        # If created by user, it is only for storing information and not network interaction
        self.network = network

    @classmethod
    def from_json(self, **kwargs):
        if "network" in kwargs:
            self.network = kwargs["network"]
            del kwargs["network"]
        return super().from_json(**kwargs)

    async def load_public_key(self):
        pub_key = await self.network.get_public_key(self.channel_name)

        if not pub_key:
            logger.error(
                f"Could not load the public key of server {self.name} ({self.channel_name})"
            )
            return

        self.public_key = pub_key
