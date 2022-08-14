import os
import json
import typing
import asyncio
import signal
from aiohttp.web import GracefulExit
import logging

from lbry.extras.daemon.daemon import Daemon, JSONRPCServerType
from lbry.extras.cli import ensure_directory_exists
from lbry.conf import Config, Setting, NOT_SET
from lbry.extras.daemon.componentmanager import ComponentManager

class PAPRJSONRPCServerType(JSONRPCServerType):
    def __new__(mcs, name, bases, newattrs):
        klass = type.__new__(mcs, name, bases, newattrs)
        klass.callable_methods = {}
        klass.deprecated_methods = {}

        for methodname in dir(klass):
            name = ""
            if methodname.startswith("jsonrpc_"):
                name = methodname.split("jsonrpc_")[1]
            elif methodname.startswith("papr_"):
                name = methodname
            else:
                continue

            method = getattr(klass, methodname)
            if not hasattr(method, '_deprecated'):
                klass.callable_methods.update({name: method})
            else:
                klass.deprecated_methods.update({name: method})
        return klass

class PaprDaemon(Daemon,metaclass=PAPRJSONRPCServerType):
    def __init__(self, conf: Config, component_manager: typing.Optional[ComponentManager] = None):
        super().__init__(conf, component_manager)

        self.users = {}

    async def papr_channel_create(self, name, bid):
        pass

def run_daemon(daemon):
    loop = asyncio.get_event_loop()

    def __exit():
        raise GracefulExit()

    try:
        loop.add_signal_handler(signal.SIGINT, __exit)
        loop.add_signal_handler(signal.SIGTERM, __exit)
    except NotImplementedError:
        pass  # Not implemented on Windows

    try:
        loop.run_until_complete(daemon.start())
        loop.run_forever()
    except (GracefulExit, KeyboardInterrupt, asyncio.exceptions.CancelledError):
        pass
    finally:
        loop.run_until_complete(daemon.stop())

    if hasattr(loop, 'shutdown_asyncgens'):
        loop.run_until_complete(loop.shutdown_asyncgens())

def run_from_args(args):
    conf = Config.create_from_arguments(args)
    for directory in (conf.data_dir, conf.download_dir, conf.wallet_dir):
        ensure_directory_exists(directory)

    pd = PaprDaemon(conf)
    run_daemon(pd)
    print("PAPR daemon closing")

if __name__ == "__main__":
    if os.path.isfile("papr.json"):
        with open("papr.json") as f:
            args = json.load(f)
    run_from_args(args)
