"""Operate the real local four-validator Besu network. No business contracts."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local' / 'phase4'
NETWORK = LOCAL / 'network'
EVIDENCE = ROOT / 'results' / 'phase4'
CHAIN_ID = 20261026
PORTS = [8545, 8546, 8547, 8548]
NODES = ['node1', 'node2', 'node3', 'node4']
FUNDING = 10**24


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o600
            info.uid = info.gid = 1000
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class RpcError(RuntimeError):
    def __init__(self, error):
        self.error = error
        super().__init__(json.dumps(error))


class RPC:
    def __init__(self, port):
        self.url = f'http://127.0.0.1:{port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method, params=None):
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or []}).encode()
        request = urllib.request.Request(self.url, data=body, headers={'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=6) as response:
            value = json.load(response)
        if value.get('jsonrpc') != '2.0' or value.get('id') != 1:
            raise ValueError('Invalid JSON-RPC envelope')
        if 'error' in value:
            raise RpcError(value['error'])
        return value['result']


def validate_receipt(receipt, tx_hash, sender, receiver, block):
    if not receipt or receipt['transactionHash'].lower() != tx_hash.lower():
        raise ValueError('Wrong or missing transaction receipt')
    if receipt['status'] != '0x1' or int(receipt['gasUsed'], 16) != 21000:
        raise ValueError('Transfer did not succeed with expected intrinsic gas')
    if receipt['from'].lower() != sender.lower() or receipt['to'].lower() != receiver.lower():
        raise ValueError('Receipt account mismatch')
    if receipt['blockHash'] != block['hash'] or receipt['blockNumber'] != block['number']:
        raise ValueError('Receipt does not belong to retrieved committed block')
    if tx_hash.lower() not in [x.lower() for x in block['transactions']]:
        raise ValueError('Transaction not in retrieved committed block')


class Chain:
    def __init__(self, args):
        self.prefix = ['wsl.exe', '-d', args.wsl_distro, '-u', args.wsl_user, '--', 'docker'] if args.wsl_distro else ['docker']
        self.wsl = bool(args.wsl_distro)
        self.lock = load(ROOT / 'chain/image.lock.json')
        EVIDENCE.mkdir(parents=True, exist_ok=True)

    def wsl_session(self, stop=False):
        if not self.wsl:
            return
        # systemd services alone do not keep a WSL distribution alive. Keep one
        # explicit user session while this deployed network is up, without
        # changing global WSL, proxy, firewall or systemd settings.
        probe = ('read -r chg_pid < /tmp/chainguard-phase4-session.pid 2>/dev/null || exit 1; '
                 'case "$chg_pid" in ""|*[!0-9]*) exit 1;; esac; '
                 '[ -r /proc/$chg_pid/cmdline ] || exit 1; '
                 '[ "$(tr "\\000" " " < /proc/$chg_pid/cmdline)" = "chainguard-phase4-session infinity " ] || exit 1; ')
        # --exec avoids an extra default-shell expansion of $$/$chg_pid.
        prefix = self.prefix[:-2] + ['--exec']
        status = subprocess.run(prefix + ['/bin/bash', '-c', probe + ('kill "$chg_pid"' if stop else 'exit 0')], capture_output=True, timeout=30)
        if stop or status.returncode == 0:
            return
        command = 'echo $$ > /tmp/chainguard-phase4-session.pid; exec -a chainguard-phase4-session /usr/bin/sleep infinity'
        LOCAL.mkdir(parents=True, exist_ok=True)
        with (LOCAL / 'wsl-session.log').open('ab') as log:
            child = subprocess.Popen(prefix + ['/bin/bash', '-c', command], stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        for attempt in range(10):
            time.sleep(1)
            status = subprocess.run(prefix + ['/bin/bash', '-c', probe + 'exit 0'], capture_output=True, timeout=30)
            if status.returncode == 0:
                break
            if child.poll() is not None:
                break
        if status.returncode:
            diagnostic = subprocess.run(prefix + ['/bin/bash', '-c', 'cat /tmp/chainguard-phase4-session.pid; ps -eo pid,args | grep "[c]hainguard-phase4-session"'], capture_output=True, timeout=30)
            (LOCAL / 'session-diagnostics.txt').write_bytes(status.stdout + status.stderr + diagnostic.stdout + diagnostic.stderr)
            raise RuntimeError('Could not maintain explicit WSL session; see private session diagnostics; child exit=' + str(child.poll()))
        write(LOCAL / 'wsl-session.json', {'windows_pid': child.pid, 'purpose': 'Keep the deployed local ChainGuard QBFT WSL session alive; chain down releases it.'})
        print('Explicit hidden WSL runtime session active; chain down releases it.', flush=True)

    def docker(self, *args, data=None, timeout=180, check=True):
        result = subprocess.run(self.prefix + list(args), input=data, capture_output=True, timeout=timeout, cwd=ROOT)
        if result.returncode and check:
            # Keep WSL's mixed-encoding stderr intact without decoding it as GBK.
            (LOCAL / 'last-command.stderr.bin').parent.mkdir(parents=True, exist_ok=True)
            (LOCAL / 'last-command.stderr.bin').write_bytes(result.stderr)
            raise RuntimeError(f'Docker {args[0]} failed ({result.returncode}); see .local/phase4/last-command.stderr.bin')
        return result

    def path(self, path):
        path = str(Path(path).resolve())
        if self.wsl:
            return '/mnt/' + path[0].lower() + '/' + path[3:].replace('\\', '/')
        return path

    def compose(self, *args, timeout=240):
        return self.docker('compose', '--project-directory', self.path(ROOT / 'chain'), '--env-file', self.path(LOCAL / 'compose.env'),
            '-f', self.path(ROOT / 'chain/compose.yaml'), '-f', self.path(ROOT / 'chain/compose.audit-history.yaml'), *args, timeout=timeout)

    def preflight(self):
        info = json.loads(self.docker('info', '--format', '{{json .}}').stdout)
        # Docker 29's containerd import identifies a docker-save image by an
        # imported manifest, while older Engines identify it by config digest.
        # Verify the official config and uncompressed layers before pinning it.
        ref = self.lock.get('runtime_image_id', 'hyperledger/besu:' + self.lock['besu_version'])
        image = json.loads(self.docker('image', 'inspect', ref).stdout)[0]
        config_digest = self.lock.get('config_digest', self.lock['image_id'])
        config_bytes = (ROOT / '.local/besu-download' / config_digest.split(':')[1]).read_bytes()
        if 'sha256:' + hashlib.sha256(config_bytes).hexdigest() != config_digest:
            raise ValueError('Official image config digest mismatch')
        official = json.loads(config_bytes)
        if image['RootFS']['Layers'] != official['rootfs']['diff_ids'] or any(image['Config'].get(k) != v for k, v in official['config'].items() if k in ['Env', 'Entrypoint', 'Cmd', 'User', 'WorkingDir', 'Labels']) or image['Architecture'] != 'amd64':
            raise ValueError('Loaded image differs from verified official config/layers')
        if 'runtime_image_id' not in self.lock:
            self.lock.update(config_digest=config_digest, runtime_image_id=image['Id'], image_id=image['Id'], compose_image=image['Id'])
            write(ROOT / 'chain/image.lock.json', self.lock)
        if image['Id'] != self.lock['image_id']:
            raise ValueError('Installed image differs from verified lock')
        version = self.docker('run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp', self.lock['image_id'], '--version').stdout.decode('utf-8').strip()
        if '/v' + self.lock['besu_version'] not in version:
            raise ValueError('Unexpected Besu version: ' + version)
        tools = self.docker('run', '--rm', '--network', 'none', '--read-only', '--user', '1000:1000', '--entrypoint', '/bin/sh', self.lock['image_id'], '-c', 'id; command -v bash; command -v tar; command -v head; command -v grep').stdout.decode().strip()
        if info['MemTotal'] < 6 * 1024**3:
            raise RuntimeError('Four-node profile needs at least 6 GiB Docker memory')
        report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'engine': info['ServerVersion'], 'cpus': info['NCPU'], 'memory_bytes': info['MemTotal'], 'os': info['OperatingSystem'], 'kernel': info['KernelVersion'], 'architecture': info['Architecture'], 'compose': self.docker('compose', 'version', '--short').stdout.decode().strip(), 'image': self.lock, 'besu_version_output': version, 'image_user_tools': tools}
        write(EVIDENCE / 'environment.json', report)
        print(json.dumps(report), flush=True)

    def init(self):
        LOCAL.mkdir(parents=True, exist_ok=True)
        if (NETWORK / 'deployment.json').exists():
            self.verify_config()
            print('Existing network preserved; init is idempotent.')
            return
        # Refuse to put fresh keys into existing data volumes, even after .local loss.
        volumes = self.docker('volume', 'ls', '--format', '{{.Name}}').stdout.decode().splitlines()
        if any('chainguard_chain_node' + str(i) in volumes for i in range(1, 5)):
            raise RuntimeError('Existing chain volumes found without local manifest; restore .local, do not regenerate keys.')
        NETWORK.mkdir(parents=True, exist_ok=True)
        account_path = LOCAL / 'accounts.private.json'
        if account_path.exists():
            private = load(account_path)
            sender, receiver = Account.from_key(private['sender']), Account.from_key(private['receiver'])
        else:
            sender, receiver = Account.create(), Account.create()
            private = {'sender': sender.key.hex(), 'receiver': receiver.key.hex()}
            # Private account material is never passed as command-line arguments or logged.
            fd = os.open(account_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(private, stream)
        template = load(ROOT / 'chain/genesis-template.json')
        template['genesis']['alloc'] = {sender.address[2:].lower(): {'balance': hex(FUNDING)}}
        result = self.docker('run', '--rm', '-i', '--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,size=64m,uid=1000,gid=1000', '--entrypoint', '/bin/sh', self.lock['image_id'], '-c', 'tar -xf - -C /tmp && /opt/besu/bin/besu operator generate-blockchain-config --config-file=/tmp/operator.json --to=/tmp/generated --private-key-file-name=key >&2 && tar -cf - -C /tmp generated', data=archive({'operator.json': json.dumps(template).encode()}))
        (LOCAL / 'keygen.stderr.bin').write_bytes(result.stderr)
        generated = result.stdout
        fd = os.open(LOCAL / 'generated.private.tar', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(generated)
        # Never extract archive paths to the host; read only recognized generated files.
        with tarfile.open(fileobj=io.BytesIO(generated)) as tar:
            members = [m for m in tar.getmembers() if m.isfile()]
            genesis, = [tar.extractfile(m).read() for m in members if m.name.endswith('/genesis.json')]
            keys = sorted([(m.name, tar.extractfile(m).read()) for m in members if m.name.endswith('/key')])
        if len(keys) != 4:
            raise ValueError('Official generator did not produce four distinct private keys')
        validators = []
        enodes = []
        for i, (_, key) in enumerate(keys, 1):
            account = Account.from_key(key.decode().strip())
            public_key = account._key_obj.public_key.to_hex()[2:]
            validators.append(account.address)
            enodes.append(f'enode://{public_key}@172.30.44.{10+i}:30303')
            volume = 'chainguard_chain_node' + str(i)
            self.docker('run', '--rm', '-i', '--network', 'none', '--read-only', '--user', '0:0', '--cap-drop', 'ALL', '--cap-add', 'CHOWN', '-v', volume + ':/data', '--entrypoint', '/bin/sh', self.lock['image_id'], '-c', 'tar --no-same-owner -xf - -C /data && chmod 700 /data && chmod 600 /data/key && chown 1000:1000 /data/key /data', data=archive({'key': key}))
        (NETWORK / 'genesis.json').write_bytes(genesis)
        (NETWORK / 'node.toml').write_bytes((ROOT / 'chain/node.toml').read_bytes())
        write(NETWORK / 'static-nodes.json', enodes)
        (LOCAL / 'compose.env').write_text('CHG_BESU_IMAGE=' + self.lock['compose_image'] + '\n', encoding='utf-8')
        deployment = {'chain_id': CHAIN_ID, 'validators': validators, 'enodes': enodes, 'sender': sender.address, 'receiver': receiver.address, 'funding_wei': str(FUNDING), 'genesis_sha256': hashlib.sha256(genesis).hexdigest(), 'node_config_sha256': hashlib.sha256((NETWORK / 'node.toml').read_bytes()).hexdigest(), 'image_id': self.lock['image_id'], 'rpc_urls': [f'http://127.0.0.1:{port}' for port in PORTS]}
        write(NETWORK / 'deployment.json', deployment)
        write(EVIDENCE / 'deployment.json', deployment)
        (EVIDENCE / 'genesis.json').write_bytes(genesis)
        self.verify_config()
        print('Official Besu QBFT genesis, four private node volumes and two local test accounts created.', flush=True)

    def verify_config(self):
        manifest = load(NETWORK / 'deployment.json')
        genesis = load(NETWORK / 'genesis.json')
        if manifest['chain_id'] != CHAIN_ID or genesis['config']['chainId'] != CHAIN_ID:
            raise ValueError('Chain ID drift')
        if hashlib.sha256((NETWORK / 'genesis.json').read_bytes()).hexdigest() != manifest['genesis_sha256']:
            raise ValueError('Genesis drift')
        if (NETWORK / 'node.toml').read_bytes() != (ROOT / 'chain/node.toml').read_bytes():
            raise ValueError('Node config drift; explicit migration/review required')
        if len(set(x.lower() for x in manifest['validators'])) != 4:
            raise ValueError('Expected four distinct validators')
        if load(NETWORK / 'static-nodes.json') != manifest['enodes']:
            raise ValueError('Static peer configuration drift')
        if manifest['image_id'] != self.lock['image_id']:
            raise ValueError('Deployment image drift')
        self.compose('config', '--quiet')

    def health(self, nodes=NODES):
        manifest = load(NETWORK / 'deployment.json')
        expected = sorted(x.lower() for x in manifest['validators'])
        rows = []
        for name in nodes:
            port = PORTS[NODES.index(name)]
            rpc = RPC(port)
            row = {'node': name, 'rpc': rpc.url, 'chain_id': int(rpc.call('eth_chainId'), 16), 'client_version': rpc.call('web3_clientVersion'), 'height': int(rpc.call('eth_blockNumber'), 16), 'peer_count': int(rpc.call('net_peerCount'), 16), 'validators': rpc.call('qbft_getValidatorsByBlockNumber', ['latest']), 'enode': rpc.call('net_enode'), 'genesis_hash': rpc.call('eth_getBlockByNumber', ['0x0', False])['hash'], 'syncing': rpc.call('eth_syncing')}
            if row['chain_id'] != CHAIN_ID or row['height'] < 1 or row['syncing'] is not False:
                raise ValueError('Chain not ready: ' + name)
            if '/v' + self.lock['besu_version'] not in row['client_version']:
                raise ValueError('Unexpected RPC client version')
            if sorted(x.lower() for x in row['validators']) != expected:
                raise ValueError('Validator set mismatch: ' + name)
            if row['enode'].split('?')[0] != manifest['enodes'][NODES.index(name)]:
                raise ValueError('Running node private identity mismatch: ' + name)
            if row['peer_count'] != len(nodes)-1:
                raise ValueError('Insufficient/full unexpected peer count: ' + name)
            rows.append(row)
        height = min(row['height'] for row in rows)
        hashes = [RPC(PORTS[NODES.index(name)]).call('eth_getBlockByNumber', [hex(height), False])['hash'] for name in nodes]
        if len(set(hashes)) != 1 or len(set(row['genesis_hash'] for row in rows)) != 1:
            raise ValueError('Nodes disagree about committed history')
        return {'nodes': rows, 'common_height': height, 'common_hash': hashes[0]}

    def wait_healthy(self, nodes=NODES, seconds=120):
        deadline = time.monotonic() + seconds
        while True:
            try:
                return self.health(nodes)
            except (OSError, RpcError, ValueError, KeyError) as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Network health timeout: ' + str(error)) from error
                time.sleep(2)

    def growth(self, nodes=NODES):
        before = self.wait_healthy(nodes)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            time.sleep(2)
            after = self.wait_healthy(nodes)
            if after['common_height'] >= before['common_height'] + 2:
                return {'before': before, 'after': after}
        raise RuntimeError('QBFT network did not commit two new blocks')

    def transfer(self):
        manifest = load(NETWORK / 'deployment.json')
        key = load(LOCAL / 'accounts.private.json')['sender']
        sender, receiver = manifest['sender'], manifest['receiver']
        if Account.from_key(key).address != sender:
            raise ValueError('Private test account does not match chain allocation')
        rpc = RPC(PORTS[0])
        before_block = rpc.call('eth_getBlockByNumber', ['latest', False])['number']
        before = {'block': before_block, 'sender': int(rpc.call('eth_getBalance', [sender, before_block]), 16), 'receiver': int(rpc.call('eth_getBalance', [receiver, before_block]), 16), 'nonce': int(rpc.call('eth_getTransactionCount', [sender, before_block]), 16)}
        tx = {'chainId': CHAIN_ID, 'nonce': before['nonce'], 'to': receiver, 'value': 10**15, 'gas': 21000, 'gasPrice': 0}
        signed = Account.sign_transaction(tx, key)
        expected_hash = '0x' + signed.hash.hex().removeprefix('0x')
        # A wrong-chain signature is a real negative RPC test, before a valid send.
        bad = Account.sign_transaction({**tx, 'chainId': CHAIN_ID + 1}, key)
        negative = {}
        try:
            rpc.call('eth_sendRawTransaction', ['0x' + bad.raw_transaction.hex().removeprefix('0x')])
        except RpcError as error:
            negative['wrong_chain_id'] = error.error
        else:
            raise ValueError('RPC accepted a wrong-chain signature')
        try:
            rpc.call('eth_sendTransaction', [{'from': sender, 'to': receiver, 'value': '0x1'}])
        except RpcError as error:
            negative['no_unlocked_accounts'] = error.error
        else:
            raise ValueError('RPC unexpectedly unlocked an account')
        tx_hash = rpc.call('eth_sendRawTransaction', ['0x' + signed.raw_transaction.hex().removeprefix('0x')])
        if tx_hash != expected_hash:
            raise ValueError('RPC returned wrong transaction hash')
        deadline = time.monotonic() + 60
        receipt = None
        while time.monotonic() < deadline:
            receipt = rpc.call('eth_getTransactionReceipt', [tx_hash])
            if receipt:
                break
            time.sleep(1)
        if not receipt:
            raise RuntimeError('Broadcast succeeded but transaction has no committed receipt')
        per_node = []
        for port in PORTS:
            node = RPC(port)
            # Committed block can be learned slightly later by the next validator.
            while True:
                observed = node.call('eth_getTransactionReceipt', [tx_hash])
                if observed or time.monotonic() >= deadline:
                    break
                time.sleep(1)
            block = node.call('eth_getBlockByHash', [receipt['blockHash'], False])
            validate_receipt(observed, tx_hash, sender, receiver, block)
            if observed != receipt:
                raise ValueError('Validators returned differing transaction receipts')
            balances = {who: int(node.call('eth_getBalance', [address, receipt['blockNumber']]), 16) for who, address in [('sender', sender), ('receiver', receiver)]}
            nonce = int(node.call('eth_getTransactionCount', [sender, receipt['blockNumber']]), 16)
            if balances != {'sender': before['sender'] - tx['value'], 'receiver': before['receiver'] + tx['value']} or nonce != before['nonce'] + 1:
                raise ValueError('Real transfer did not produce exact balances/nonce')
            per_node.append({'rpc': node.url, 'receipt': observed, 'block': block, 'balances_wei': {k: str(v) for k, v in balances.items()}, 'sender_nonce': nonce})
        return {'transaction_hash': tx_hash, 'transaction': {**tx, 'value': str(tx['value'])}, 'sender': sender, 'receiver': receiver, 'before': {**before, 'sender': str(before['sender']), 'receiver': str(before['receiver'])}, 'negative_rpc': negative, 'nodes': per_node}

    def acceptance(self):
        previous = EVIDENCE / 'network-acceptance.json'
        if previous.exists():
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            (EVIDENCE / ('network-acceptance.previous.' + stamp + '.json')).write_bytes(previous.read_bytes())
        report = {'status': 'FAIL', 'recorded_at_utc': datetime.now(timezone.utc).isoformat()}
        try:
            self.verify_config()
            report['growth'] = self.growth()
            report['transfer'] = self.transfer()
            # Restart one actual JVM against its existing key and database.
            old_id = self.compose('ps', '--quiet', 'node4').stdout.decode().strip()
            before = json.loads(self.docker('inspect', old_id).stdout)[0]
            self.compose('restart', 'node4')
            report['restart_health'] = self.wait_healthy()
            report['receipt_after_restart'] = RPC(PORTS[3]).call('eth_getTransactionReceipt', [report['transfer']['transaction_hash']])
            if report['receipt_after_restart'] != report['transfer']['nodes'][0]['receipt']:
                raise ValueError('Committed transaction missing or changed after node restart')
            after = json.loads(self.docker('inspect', old_id).stdout)[0]
            if before['State']['StartedAt'] == after['State']['StartedAt']:
                raise ValueError('Node did not actually restart')
            report['restart'] = {'container': old_id, 'before_started_at': before['State']['StartedAt'], 'after_started_at': after['State']['StartedAt'], 'same_persistent_mounts': before['Mounts'] == after['Mounts']}
            # Remove exactly one validator from availability, then restore in finally.
            self.compose('stop', 'node4')
            try:
                stopped = json.loads(self.docker('inspect', old_id).stdout)[0]
                if stopped['State']['Running']:
                    raise ValueError('Fourth validator did not stop')
                report['three_node_growth'] = self.growth(NODES[:3])
                report['stopped_validator'] = {'node': 'node4', 'running': stopped['State']['Running'], 'exit_code': stopped['State']['ExitCode']}
            finally:
                self.compose('start', 'node4')
            report['restored'] = self.wait_healthy()
            containers = json.loads(self.docker('inspect', *[self.compose('ps', '--quiet', name).stdout.decode().strip() for name in NODES]).stdout)
            report['containers'] = [{'name': row['Name'], 'id': row['Id'], 'image_id': row['Image'], 'started_at': row['State']['StartedAt'], 'health': row['State']['Health']['Status'], 'running': row['State']['Running'], 'readonly_rootfs': row['HostConfig']['ReadonlyRootfs'], 'user': row['Config']['User'], 'ports': row['NetworkSettings']['Ports'], 'mounts': row['Mounts'], 'memory_limit': row['HostConfig']['Memory']} for row in containers]
            if len(set(row['id'] for row in report['containers'])) != 4 or any(row['health'] != 'healthy' or row['image_id'] != self.lock['image_id'] for row in report['containers']):
                raise ValueError('Four distinct healthy locked Besu containers required')
            report['status'] = 'PASS'
        except BaseException as error:
            report['error'] = str(error)
            raise
        finally:
            write(EVIDENCE / 'network-acceptance.json', report)
            logs = self.compose('logs', '--no-color', '--tail', '150')
            (EVIDENCE / 'besu-logs.txt').write_bytes(logs.stdout)
        print('Real four-validator QBFT acceptance PASS; hash=' + report['transfer']['transaction_hash'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'init', 'validate', 'up', 'down', 'status', 'logs', 'health', 'acceptance'])
    parser.add_argument('--wsl-distro')
    parser.add_argument('--wsl-user', default='root')
    args = parser.parse_args()
    chain = Chain(args)
    if args.action == 'preflight':
        chain.preflight()
    elif args.action == 'init':
        chain.init()
    elif args.action == 'validate':
        chain.verify_config()
        print('Public configuration integrity and Compose validation PASS')
    elif args.action == 'up':
        chain.verify_config()
        chain.wsl_session()
        result = chain.compose('up', '--no-build', '--wait', '--wait-timeout', '180', timeout=240)
        (EVIDENCE / 'compose-up.txt').write_bytes(result.stdout)
        write(EVIDENCE / 'startup-health.json', chain.wait_healthy())
        print('Four real Besu validators healthy; localhost RPC ports 8545-8548')
    elif args.action == 'down':
        chain.compose('down')  # No --volumes: preserve all private identities/history.
        chain.wsl_session(stop=True)
        print('Network stopped; private keys and chain data volumes preserved')
    elif args.action == 'status':
        print(chain.compose('ps', '--format', 'json').stdout.decode())
    elif args.action == 'logs':
        content = chain.compose('logs', '--no-color', '--tail', '100').stdout
        (EVIDENCE / 'latest-besu-logs.txt').write_bytes(content)
        sys.stdout.buffer.write(content)
    elif args.action == 'health':
        print(json.dumps(chain.wait_healthy(), indent=2))
    elif args.action == 'acceptance':
        chain.acceptance()


if __name__ == '__main__':
    main()
