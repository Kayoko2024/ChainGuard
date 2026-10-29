"""Explicit deployment profile; legacy frozen deployments keep their 120s limit."""
DAY = 24 * 60 * 60


def mail_lifetime(deployment):
    profile = deployment.get('mailApprovalWindow')
    if profile is None:
        return 120
    source = deployment['contracts'].get('SourcePolicyRegistry', {}).get('address')
    if (profile != {'version': 1, 'seconds': DAY, 'source_policy': source} or
            not source or source.lower() == deployment['contracts']['PolicyRegistry']['address'].lower()):
        raise ValueError('Invalid 24h mail deployment profile')
    return DAY


def action_expiry(issued, task_expiry, rule_lifetime, deployment):
    return min(issued + min(rule_lifetime, mail_lifetime(deployment)), int(task_expiry))


def chain_for_action(chain, action):
    """Only trusted configured deployments may select a historical signing domain."""
    reserve = action.get('reservation_evidence')
    if not reserve or not hasattr(chain, 'config'):
        return chain
    registry = reserve['registry'].lower()
    if registry == chain.execution.address:
        return chain
    for deployment in chain.config.get('legacyDeployments', []):
        if deployment['contracts']['ExecutionRegistry']['address'].lower() == registry:
            from .audit_verify import make_chain
            return make_chain(deployment, [n.url for n in chain.nodes])
    raise ValueError('Untrusted reservation registry')
