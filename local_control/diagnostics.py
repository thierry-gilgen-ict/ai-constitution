"""Support exports use an allowlist, never generic redaction of private payloads."""
import platform
from . import VERSION


def report(control):
    statuses = {'done', 'failed', 'interrupted', 'cancelled', 'queued', 'running'}
    operations = {'pull', 'configure', 'switch', 'lifecycle', 'health_check', 'remove_node', 'benchmark', 'setup_component', 'maintain'}
    evidence = control.config['primary'].get('contract', {}).get('level', 'unverified') if control.config['primary'] else 'unconfigured'
    return {'schema_version': 1, 'version': VERSION, 'platform': platform.system(),
            'mode': control.mode if control.mode in ('work', 'gaming', 'draining') else 'unknown',
            'active_requests': sum(control.active.values()), 'node_count': len(control.config['nodes']),
            'session_count': len(control.sessions()),
            'jobs': [{'status': j['status'] if j.get('status') in statuses else 'unknown',
                      'operation': j.get('operation') if j.get('operation') in operations else 'other'} for j in list(control.jobs.values())[-15:]],
            'primary_evidence': evidence if evidence in ('unverified', 'unconfigured', 'protocol-tested', 'coding-tested') else 'unverified',
            'excluded': ['credentials', 'prompts', 'responses', 'project contents', 'paths', 'hostnames', 'addresses', 'model names', 'event text']}
