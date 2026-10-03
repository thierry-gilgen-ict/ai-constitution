"""Select a ready endpoint before dispatch. Never replay an accepted generation."""
import copy
import time
from . import insights


def select(control):
    gaming = control.mode in ('gaming', 'draining')
    primary = control.config.get('fallback' if gaming else 'primary')
    if not primary: raise ValueError('Configure a working route in the dashboard first')
    candidates = [primary]
    if control.config.get('automatic_fallback', True): candidates += control.fallback_candidates()
    if not gaming and control.config.get('task_profile') == 'fast':
        preferred = control.config.get('fast_route')
        if preferred: candidates.sort(key=lambda e: (e['node'], e['model']) != (preferred['node'], preferred['model']))
    for endpoint in candidates:
        node = endpoint['node']
        if node in control.config['maintenance'] or (node in control.admin_nodes and endpoint != primary): continue
        if gaming and not control.gaming_eligible(endpoint): continue
        health = control.health.get(node, {})
        if health.get('status') == 'offline': continue
        if 'ready_models' in health and time.time() - health.get('checked_at', 0) < 180 and endpoint['model'] not in health['ready_models']: continue
        if endpoint != primary:
            # Alternate endpoints must have actual compatibility evidence and a fresh
            # successful health check. Unknown/stale state is never called ready.
            if endpoint.get('contract', {}).get('level') not in ('protocol-tested','coding-tested'): continue
            if health.get('status') != 'online' or time.time() - health.get('checked_at', 0) > 180: continue
        return copy.deepcopy(endpoint)
    raise ValueError('No tested route is ready: machines may be offline, in maintenance or missing aliases; this request was not sent.')


def configure(control, body, progress=lambda _: None):
    profile = body.get('profile', control.config.get('task_profile', 'deep'))
    if profile not in ('fast','deep','gaming'): raise ValueError('Choose fast, deep or gaming')
    automatic = body.get('automatic_fallback', control.config.get('automatic_fallback', True))
    if type(automatic) is not bool: raise ValueError('Choose whether to enable pre-dispatch fallback')
    if profile == 'gaming':
        result = control.switch('gaming', progress=progress)
        return {**result, 'profile': 'gaming'}
    fast = None
    if profile == 'fast':
        advice = insights.suggestion(control)
        match = next((p for p in advice['profiles'] if p['id'] == advice['fast_candidate']), None)
        if not match: raise ValueError('Evaluate a configured route first so Fast can use measured evidence')
        fast = {k:match[k] for k in ('node','model')}
    with control.operation, control.lock:
        old = copy.deepcopy(control.config)
        control.config.update(task_profile=profile, fast_route=fast, automatic_fallback=automatic)
        try: control.save()
        except Exception: control.config = old; raise
    return {'profile': profile, 'note': 'Next-request preference saved. Work/Gaming mode remains a separate GPU safety control; active responses retain their route.'}
