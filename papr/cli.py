import os
import click
import json
import functools
import requests

from papr.user import User

DEFAULT_CONFIG = {
            "blockchain_name": "lbrycrd_testnet",
            "lbryum_servers": [('127.0.0.1', 50001)],
}


def call(method, **kwargs):
    data = {"jsonrpc": "2.0", "method": method, "params": kwargs}
    url = "http://localhost:5279/"
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

    return requests.post(url, json=data, headers=headers)


@click.group()
def cli():
    pass

@cli.command()
def status():
    resp = call("status")
    print(resp)

    return resp

@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--encrypt', default=False, help="Publish as an encrypted file for private review")
def publish(path, encrypt):
    pass

@cli.command()
@click.argument('name')
@click.option('--yes', '-y', is_flag=True, help="Do not ask for confirmation")
def create_channel(name, yes):
    if name[0] != "@":
        name = "@" + name

    if not yes:
        ans = input(f"Your channel name will be '{name}', create this channel? (Y/N)")
        if ans.lower().strip() != 'y':
            print("Channel creation aborted!")
            return

    # Actually create the channel 

    print("Channel created!")
    return

if __name__ == "__main__":
    cli()

