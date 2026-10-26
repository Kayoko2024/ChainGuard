"""Start an explicitly provisioned local A/B gateway; never create credentials."""

import argparse

import uvicorn

from .central_service import CentralService
from .central_store import CentralStore
from .main import create_app


def application_from_root(root):
    from chainguard_sandbox.central_adapter import CentralToolAdapter
    from chainguard_sandbox.storage import Store
    store = CentralStore(root)
    with store.connect() as db:
        tool_root = store.meta(db, "tool_root")
    tools = Store(tool_root)
    return create_app(central_service=CentralService(store, CentralToolAdapter(tools, store)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Operator-provisioned private central state directory")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(application_from_root(args.root), host="127.0.0.1", port=args.port, access_log=False)
