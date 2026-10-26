"""Local lab provisioning and distinct gateway/tool service processes."""
import argparse
import base64
import json
import os
from pathlib import Path
import ssl
import sys

import uvicorn

from .canonical import canonical
from .chain_rpc import Chain
from .chain_store import ChainStore
from .chain_service import ChainService
from .chain_api import create_chain_app,create_tool_app
from .chain_transport import TLSClient,PeerCertificateProtocol
from chainguard_sandbox.storage import Store,require_container
from chainguard_sandbox.chain_mail import ChainMailTool


def private_write(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream: stream.write(data)


def initialize(kind):
    require_container()
    value=json.load(sys.stdin)
    if kind=='gateway':
        store=ChainStore.create('/sandbox/gateway')
        (store.root/'jwt.key').write_bytes(bytes.fromhex(value.pop('jwt_key')))
        private_write(store.root/'relay.key',bytes.fromhex(value.pop('relay_key').removeprefix('0x')))
        for actor in value.pop('actors'): store.register_actor(store.private('admin.key'),actor)
        root=store.root
    elif kind=='tool':
        store=Store.create()
        root=store.root
        private_write(root/'signing.key',bytes.fromhex(value.pop('tool_key').removeprefix('0x')))
        private_write(root/'data.key',bytes.fromhex(value.pop('data_key')))
    else:
        root=Path('/sandbox/qa')
        root.mkdir(mode=0o700)
    for name,data in value.pop('files').items():
        if Path(name).name!=name: raise ValueError('Unsafe private file name')
        private_write(root/name,base64.b64decode(data,validate=True))
    private_write(root/'runtime.json',canonical(value))
    private_write(Path('/sandbox/root.json'),canonical({'root':str(root)}))
    print(json.dumps({'initialized':kind}))


def load():
    root=Path(json.loads(Path('/sandbox/root.json').read_text())['root'])
    return root,json.loads((root/'runtime.json').read_text())


def client(root,config):
    return TLSClient(config['url'],root/'ca.pem',root/config['certificate'],root/config['key'],config['token'])


def serve(kind):
    require_container()
    root,config=load()
    chain=Chain(config['deployment'],config['rpc_urls'])
    if kind=='gateway':
        store=ChainStore(root)
        service=ChainService(store,chain,client(root,config['tool_client']),(root/'relay.key').read_bytes(),config['tool_signer'])
        app=create_chain_app(service,config['authority_fingerprint'],config['authority_token'])
    else:
        tool=ChainMailTool(Store(root),chain,client(root,config['authority_client']),(root/'signing.key').read_bytes(),(root/'data.key').read_bytes())
        app=create_tool_app(tool,config['gateway_fingerprint'],config['gateway_token'])
    uvicorn.run(app,host='0.0.0.0',port=8443,http=PeerCertificateProtocol,access_log=False,log_level='warning',
        ssl_keyfile=str(root/'server.key'),ssl_certfile=str(root/'server.pem'),ssl_ca_certs=str(root/'ca.pem'),ssl_cert_reqs=ssl.CERT_REQUIRED)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['init','serve'])
    parser.add_argument('kind',choices=['gateway','tool','qa'])
    args=parser.parse_args()
    initialize(args.kind) if args.operation=='init' else serve(args.kind)
