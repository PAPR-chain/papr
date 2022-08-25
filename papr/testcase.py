import os
from functools import partial

from lbry.testcase import CommandTestCase, ExchangeRateManagerComponent
from lbry.extras.daemon.components import Component, WalletComponent
from lbry.extras.daemon.componentmanager import ComponentManager
from lbry.wallet.orchstr8.node import LBCWalletNode, WalletNode
from lbry.extras.daemon.components import (
    DHT_COMPONENT,
    HASH_ANNOUNCER_COMPONENT,
    PEER_PROTOCOL_SERVER_COMPONENT,
    UPNP_COMPONENT,
    EXCHANGE_RATE_MANAGER_COMPONENT,
    LIBTORRENT_COMPONENT,
)
from lbry.extras.daemon.exchange_rate_manager import (
    ExchangeRateManager,
    ExchangeRate,
    BittrexBTCFeed,
    BittrexUSDFeed,
)

from papr.config import Config
from papr.daemon import PaprDaemon


class PaprDaemonTestCase(CommandTestCase):
    async def add_daemon(self, wallet_node=None, seed=None):
        start_wallet_node = False
        if wallet_node is None:
            wallet_node = WalletNode(
                self.wallet_node.manager_class,
                self.wallet_node.ledger_class,
                port=self.extra_wallet_node_port,
            )
            self.extra_wallet_node_port += 1
            start_wallet_node = True

        upload_dir = os.path.join(wallet_node.data_path, "uploads")
        os.mkdir(upload_dir)

        conf = Config(
            # needed during instantiation to access known_hubs path
            data_dir=wallet_node.data_path,
            wallet_dir=wallet_node.data_path,
            save_files=True,
            download_dir=wallet_node.data_path,
            submission_dir=wallet_node.data_path,
            review_dir=wallet_node.data_path,
        )
        conf.upload_dir = upload_dir  # not a real conf setting
        conf.share_usage_data = False
        conf.use_upnp = False
        conf.reflect_streams = True
        conf.blockchain_name = "lbrycrd_regtest"
        conf.lbryum_servers = [
            (self.conductor.spv_node.hostname, self.conductor.spv_node.port)
        ]
        conf.reflector_servers = [("127.0.0.1", 5566)]
        conf.fixed_peers = [("127.0.0.1", 5567)]
        conf.known_dht_nodes = []
        conf.blob_lru_cache_size = self.blob_lru_cache_size
        conf.transaction_cache_size = 10000
        conf.components_to_skip = [
            DHT_COMPONENT,
            UPNP_COMPONENT,
            HASH_ANNOUNCER_COMPONENT,
            PEER_PROTOCOL_SERVER_COMPONENT,
        ]
        if self.skip_libtorrent:
            conf.components_to_skip.append(LIBTORRENT_COMPONENT)

        if start_wallet_node:
            await wallet_node.start(self.conductor.spv_node, seed=seed, config=conf)
            self.extra_wallet_nodes.append(wallet_node)
        else:
            wallet_node.manager.config = conf
            wallet_node.manager.ledger.config["known_hubs"] = conf.known_hubs

        def wallet_maker(component_manager):
            wallet_component = WalletComponent(component_manager)
            wallet_component.wallet_manager = wallet_node.manager
            wallet_component._running = True
            return wallet_component

        daemon = PaprDaemon(
            conf,
            ComponentManager(
                conf,
                skip_components=conf.components_to_skip,
                wallet=wallet_maker,
                exchange_rate_manager=partial(
                    ExchangeRateManagerComponent, rates={"BTCLBC": 1.0, "USDLBC": 2.0}
                ),
            ),
        )
        await daemon.initialize()
        self.daemons.append(daemon)
        wallet_node.manager.old_db = daemon.storage
        return daemon
