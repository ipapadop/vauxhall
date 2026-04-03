from pyloid.rpc import PyloidRPC, RPCContext

rpc = PyloidRPC()

@rpc.method()
async def copy_to_clipboard(ctx: RPCContext, text: str) -> bool:
    """Handled in a later task."""
    print(f"RPC received: {text}")
    return True
