"""Independent, fail-closed repository admission against two actual Besu nodes.

Public configuration only. This domain is separate from frozen ActionIntent/Receipt.
"""
import json
from eth_utils import keccak
from .chain_rpc import Chain, Contract
from .github_read import resource, GitHubFailure
from chainguard_sandbox.protocol import ToolError

RULE_TYPES = {'RepositoryRuleChange': [
    {'name': 'repositoryHash', 'type': 'bytes32'}, {'name': 'enabled', 'type': 'bool'},
    {'name': 'nonce', 'type': 'uint64'}, {'name': 'epoch', 'type': 'uint64'},
    {'name': 'issuedAt', 'type': 'uint64'}, {'name': 'expiresAt', 'type': 'uint64'}]}

def repository_hash(query):
    repo, _ = resource(query)
    return '0x' + keccak(text='ChainGuard/github/repository/' + repo).hex()

def view(name, inputs, outputs):
    return {'type': 'function', 'name': name, 'stateMutability': 'view',
            'inputs': [{'name': str(i), 'type': t} for i, t in enumerate(inputs)],
            'outputs': [{'name': str(i), 'type': t} for i, t in enumerate(outputs)]}

ABI = [view('policyRegistry', [], ['address']), view('epoch', [], ['uint64']),
       view('repositoryAllowed', ['bytes32'], ['bool']), view('requireRepository', ['bytes32'], ['uint64'])]

class RepositoryPolicy:
    def __init__(self, config, urls):
        self.config, self.chain = config, Chain(config['deployment'], urls)

    def check(self, query):
        repo, _ = resource(query)
        try:
            snapshot = self.chain.healthy()
            item = self.config['contract']; block = hex(int(snapshot['number']))
            answers = []
            for node in self.chain.nodes:
                raw = node.call('eth_getCode', [item['address'], block])
                if raw == '0x' or '0x' + keccak(bytes.fromhex(raw[2:])).hex() != item['codeHash']:
                    raise ToolError('CHAIN_UNAVAILABLE')
                contract = Contract('RepositoryReadPolicy', item['address'], node, abi=ABI)
                if contract.call('policyRegistry', block=block) != self.chain.policy.address:
                    raise ToolError('CHAIN_UNAVAILABLE')
                answers.append((contract.call('repositoryAllowed', [repository_hash(query)], block),
                                contract.call('epoch', block=block), Contract('PolicyRegistry',self.chain.policy.address,node).call('paused',block=block)))
                if answers[-1][0] and not answers[-1][2]:
                    if contract.call('requireRepository', [repository_hash(query)], block) != answers[-1][1]:
                        raise ToolError('CHAIN_UNAVAILABLE')
            if len(set(answers)) != 1:
                raise ToolError('CHAIN_UNAVAILABLE')
            allowed, epoch, paused = answers[0]
            return dict(chain_id=str(self.config['deployment']['chainId']), contract=item['address'].lower(),
                        code_hash=item['codeHash'], repository=repo, repository_hash=repository_hash(query),
                        allowed=allowed and not paused, epoch=str(epoch), block_number=snapshot['number'],
                        block_hash=snapshot['hash'], checked_nodes=len(answers), enforcement='ON_CHAIN_REPOSITORY_POLICY')
        except (ToolError, KeyError, ValueError, TypeError):
            raise GitHubFailure('GITHUB_POLICY_UNAVAILABLE') from None

def configured_check(store, query):
    try:
        config = json.loads(store.private_read('github-policy.json'))
        return RepositoryPolicy(config, ['http://node2:8545', 'http://node4:8545']).check(query)
    except (OSError, ValueError, KeyError, ToolError):
        raise GitHubFailure('GITHUB_POLICY_UNAVAILABLE') from None
