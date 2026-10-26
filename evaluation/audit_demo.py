"""Stage9 demo transport: missing real validator reads fail closed, never fabricated.

Only this test process installs the stricter RPC class. Original core files and
all authorization/state transitions stay unchanged. Existing bounded polling
handles CHAIN_UNAVAILABLE; no action, transaction or side effect is replayed here.
"""
from chainguard_gateway import chain_rpc
from chainguard_sandbox.protocol import ToolError

OriginalRPC=chain_rpc.RPC


def validator_read(method,value):
    if method=='qbft_getValidatorsByBlockNumber' and not isinstance(value,list):
        raise ToolError('CHAIN_UNAVAILABLE')
    return value


class DemoReadRPC(OriginalRPC):
    def call(self,method,params=None):
        return validator_read(method,super().call(method,params))


def main():
    chain_rpc.RPC=DemoReadRPC
    from evaluation.replay import main as original_demo
    original_demo()


if __name__=='__main__':main()
