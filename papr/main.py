async def do_stuff(daemon):
    addr = await daemon.jsonrpc_address_list()
    print(type(addr))
    print(addr)
    print(str(addr))
