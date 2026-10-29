"""Bounded local service resources, shared by initial deployment and upgrades."""
MIB = 1024 * 1024


def service_limits(kind, current_memory=0):
    # Gateway also hosts periodic chain workers and trusted stdio subprocesses.
    memory = max(current_memory, (1024 if kind == 'gateway' else 512) * MIB)
    return ['--memory', str(memory), '--restart', 'unless-stopped']
