"""Explain effective project setup without treating installed files as loaded instructions."""
import time
from scripts import constitution as kit, policy
from . import plans, workspace
from .studio import Studio


def inspect(control, name):
    project = plans.project(control.root, name)
    studio = Studio(control.root)
    with kit.state_lock(studio.guard):
        studio.initialize()
        plans.fingerprint(project / '.ai/policy.json')
        plans.fingerprint(studio.state.parent / 'overrides/policy.json')
        resolved = policy.resolve(studio.draft, studio.state, project)
        installation = kit.doctor(studio.draft, studio.state, project)
    overview = workspace.overview(control)
    item = next(p for p in overview['projects'] if p['project'] == str(project))
    findings = []
    for report in installation:
        findings += [{'severity': 'warning', 'code': 'installation-drift', 'detail': p,
                      'page': 'constitution'} for p in report.get('problems', [])]
    modules = []
    for name, content in sorted(resolved['instructions'].items()):
        size = len(content.encode('utf-8'))
        modules.append({'path': name, 'bytes': size, 'estimated_tokens': (size + 3) // 4,
                        'estimate': 'UTF-8 bytes / 4; actual client tokenization differs', 'page': 'constitution'})
        if size > 24000:
            findings.append({'severity': 'review', 'code': 'large-module',
                             'detail': name + ' is large; consider scoped instructions', 'page': 'constitution'})
    if not item['accounts']:
        findings.append({'severity': 'review', 'code': 'account-unassigned',
                         'detail': 'No application subscription is assigned', 'page': 'accounts'})
    if not item['configurations']:
        findings.append({'severity': 'review', 'code': 'configuration-unmapped',
                         'detail': 'No private configuration folder is associated', 'page': 'vault'})
    route = item['route']; selected = control.config.get('fallback' if control.mode in ('gaming','draining') else 'primary')
    health = control.health.get((selected or {}).get('node'), {})
    fresh = time.time() - health.get('checked_at', 0) < 180
    access = 'observed-ready' if selected and fresh and health.get('status') == 'online' and selected['model'] in health.get('ready_models',[]) else 'unverified'
    return {'schema': 1, 'project': str(project), 'release': (studio.draft / 'VERSION').read_text().strip(),
            'effective_sha256': resolved['effective_sha256'], 'layers': resolved['layer_hashes'],
            'routes': resolved['routes']['routes'], 'route_sources': resolved['provenance'],
            'modules': modules, 'installation': installation, 'architecture': item['architecture'],
            'accounts': item['accounts'], 'configurations': item['configurations'], 'route': route,
            'evidence': {'files': plans.evidence(installation, 'managed ownership checks', level='tested'),
                         'client_loading': plans.evidence('unverified', 'No reliable client loading evidence'),
                         'model_access': plans.evidence(access, 'machine readiness observation', observed_at=health.get('checked_at')),
                         'performance': plans.evidence((selected or {}).get('contract', {}).get('level','unverified'), 'configured route evaluation')},
            'findings': findings, 'note': 'File checks, client loading, access and evaluated behavior are separate evidence. Semantic contradictions need review.'}
