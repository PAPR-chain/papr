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
    #data = json.dumps({"jsonrpc": "2.0", "method": method, "params": kwargs})
    data = {"jsonrpc": "2.0", "method": method, "params": kwargs}
    print(data)

    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    return requests.post("http://localhost:5279/", json=data, headers=headers)


@click.group()
def cli():
    pass

@cli.command()
def status():
    #d = run(get_daemon())
    #print(d)
    ret = call("status")
    print(ret.json())
    print("status")

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

    #r = call("lbry_channel_create", name=name, bid="0.1")
    #print(r)
    #print(r.content)
    print("Channel created!")

if __name__ == "__main__":
    cli()

