"""Fetch the official Docker Hub image using the host's network, verifying every digest.

No mirror, Java replacement, or runtime package modification. Docker's WSL network
may differ from Windows' configured proxy. Private keys are never involved here.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.local' / 'besu-download'
REPO = 'hyperledger/besu'
VERSION = '25.10.0'
REGISTRY = 'https://registry-1.docker.io/v2/' + REPO
ACCEPT = ', '.join([
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
])


def request(url, token=None):
    headers = {'Accept': ACCEPT, 'User-Agent': 'ChainGuard-phase4/1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90)


def verify(data, digest):
    if 'sha256:' + hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Official registry content digest mismatch')


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    with request('https://auth.docker.io/token?service=registry.docker.io&scope=repository:hyperledger/besu:pull') as response:
        token = json.load(response)['token']
    with request(REGISTRY + '/manifests/' + VERSION, token) as response:
        data = response.read()
        digest = response.headers['Docker-Content-Digest']
    verify(data, digest)
    index_digest = digest
    manifest = json.loads(data)
    if 'manifests' in manifest:
        entry, = [x for x in manifest['manifests'] if x.get('platform', {}).get('os') == 'linux' and x.get('platform', {}).get('architecture') == 'amd64']
        digest = entry['digest']
        with request(REGISTRY + '/manifests/' + digest, token) as response:
            data = response.read()
        verify(data, digest)
        manifest = json.loads(data)
    (CACHE / 'manifest.json').write_bytes(data)
    for entry in [manifest['config'], *manifest['layers']]:
        target = CACHE / entry['digest'].split(':')[1]
        if target.exists() and target.stat().st_size == entry['size']:
            with target.open('rb') as stream:
                if 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() == entry['digest']:
                    continue
        print('Downloading verified official blob ' + entry['digest'] + ' bytes=' + str(entry['size']), flush=True)
        with request(REGISTRY + '/blobs/' + entry['digest'], token) as response, target.open('wb') as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        with target.open('rb') as stream:
            actual = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != entry['digest'] or target.stat().st_size != entry['size']:
            raise ValueError('Official blob digest or size mismatch')
    # A standard docker-save archive allows offline docker load on the WSL Engine.
    archive = CACHE / 'besu.docker.tar'
    config_name = manifest['config']['digest'].split(':')[1] + '.json'
    layer_names = []
    with tarfile.open(archive, 'w') as tar:
        tar.add(CACHE / manifest['config']['digest'].split(':')[1], arcname=config_name)
        for entry in manifest['layers']:
            blob = CACHE / entry['digest'].split(':')[1]
            layer = CACHE / (blob.name + '.tar')
            with blob.open('rb') as source:
                compressed = source.read(2) == b'\x1f\x8b'
            if compressed:
                with gzip.open(blob, 'rb') as source, layer.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            else:
                layer = blob
            name = blob.name + '/layer.tar'
            layer_names.append(name)
            tar.add(layer, arcname=name)
        saved = json.dumps([{'Config': config_name, 'RepoTags': [REPO + ':' + VERSION], 'Layers': layer_names}]).encode()
        info = tarfile.TarInfo('manifest.json')
        info.size = len(saved)
        tar.addfile(info, io.BytesIO(saved))
    lock = {
        'besu_version': VERSION, 'official_repository': 'docker.io/' + REPO,
        'source': REGISTRY + '/manifests/' + VERSION, 'index_digest': index_digest,
        'platform': 'linux/amd64', 'manifest_digest': digest,
        'image_id': manifest['config']['digest'],
        'compose_image': manifest['config']['digest'],
        'distribution': 'official Docker Hub bytes; host download plus offline docker load',
    }
    lock_path = ROOT / 'chain' / 'image.lock.json'
    lock_path.parent.mkdir(exist_ok=True)
    if lock_path.exists():
        existing = json.loads(lock_path.read_text())
        for field in ['besu_version', 'manifest_digest', 'index_digest', 'official_repository']:
            if existing[field] != lock[field]:
                raise ValueError('Image lock drift: explicit review required; refusing overwrite')
        lock = existing  # Keep the separately verified local containerd identity.
    else:
        lock_path.write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(lock))
    print('Ready for Docker load: .local/besu-download/besu.docker.tar')


if __name__ == '__main__':
    main()
