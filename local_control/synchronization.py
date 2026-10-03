"""Reconcile enrolled projects independently, preserving pins and local edits."""
from pathlib import Path
import time

from scripts import constitution as kit, architecture, releases
from scripts.catalog import digest, json_bytes
from . import locations
from .storage import atomic
from .studio import Studio


def settings(root):
    path = Path(root) / 'synchronization.json'
    kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'schema': 1, 'enabled': True, 'paused_projects': []}


def configure(root, body):
    with kit.state_lock(Path(root) / 'sync-operations'):
        value = settings(root)
        if 'enabled' in body:
            if type(body['enabled']) is not bool: raise ValueError('Choose automatic synchronization on or off')
            value['enabled'] = body['enabled']
        if 'project' in body:
            project = body['project']
            db = kit.state_load(locations.folder(root, 'constitution_state'))
            if 'project:' + str(project) not in db['targets']: raise ValueError('Choose an enrolled project')
            if type(body.get('paused')) is not bool: raise ValueError('Choose follow or pause')
            paused = set(value['paused_projects'])
            if body['paused']: paused.add(project)
            else: paused.discard(project)
            value['paused_projects'] = sorted(paused)
        atomic(Path(root) / 'synchronization.json', value)
        return value


def status(root):
    config = settings(root)
    path = Path(root) / 'sync-status.json'; kit.no_links(path)
    last = kit.read_json(path) if path.exists() else {'projects': [], 'checked_at': None}
    error_path = Path(root) / 'sync-error.json'; kit.no_links(error_path)
    if error_path.exists(): last['error'] = kit.read_json(error_path)
    known = {v['project']: v for v in last['projects']}
    db = kit.state_load(locations.folder(root, 'constitution_state'))
    projects = []
    for target in db['targets'].values():
        if target['kind'] != 'project': continue
        record = known.get(target['root'], {'project': target['root'], 'status': 'pending'})
        projects.append({**record, 'pinned': target['pinned'], 'paused': target['root'] in config['paused_projects']})
    return {**last, **config, 'projects': projects,
            'scope': 'Projects enrolled on this computer. Runs every minute while Local Control is running; catches up after restart. Global client installations remain explicitly activated.',
            'runtime': 'Local sessions using constitution-local follow gateway routes on their next request. Instructions require client reload; direct-provider sessions keep their selected model.'}


def reconcile(root, config=None, progress=lambda _: None):
    root = Path(root)
    with kit.state_lock(root / 'sync-operations'):
        preferences = settings(root)
        if not preferences['enabled']: return status(root)
        studio = Studio(root)
        with kit.state_lock(studio.guard):
            studio.initialize()
            upstream, writes = studio.refresh_plan()
            if upstream['conflicts']:
                raise ValueError('Library edits conflict with an application update; review Constitution files')
            kit.transaction(studio.history, writes)
            # Validation precedes any target writes; executable draft code is never run.
            kit.validate(studio.draft); kit.build(studio.draft, check=True)
            payload = studio.payload()
            with kit.state_lock(studio.state):
                release, source = releases.prepare(payload, studio.state, preview=True)
                if not (source / 'release-manifest.json').exists():
                    releases.prepare(payload, studio.state)
                elif kit.read_json(source / 'release-manifest.json') != releases.manifest(releases.files(source)):
                    raise ValueError('Prepared instruction release integrity changed')
                db = kit.state_load(studio.state)
                ownership = studio.state / 'architectures.json'
                kit.no_links(ownership)
                baselines = kit.read_json(ownership).get('projects', {}) if ownership.exists() else {}
                records = []
                for target in list(db['targets'].values()):
                    if target['kind'] != 'project': continue
                    project = Path(target['root'])
                    record = {'project': str(project), 'release': release, 'checked_at': time.time()}
                    if target['pinned'] or str(project) in preferences['paused_projects']:
                        records.append({**record, 'status': 'pinned' if target['pinned'] else 'paused'})
                        continue
                    try:
                        writes = {}
                        old = baselines.get(str(project))
                        if old:
                            template = kit.safe_path(studio.draft, 'templates/architectures/' + old['id'] + '.json')
                            if old.get('policy') == 'pinned':
                                value = architecture.validate(old['snapshot'])
                            else:
                                if not template.is_file(): raise ValueError('The project template is missing; choose a replacement explicitly')
                                value = architecture.validate(kit.read_json(template))
                            _, writes = architecture.plan(kit, studio.draft, studio.state, project, value, old['project_name'], old.get('policy', 'latest'))
                            record['template'] = old['id']
                        # Replace the staged installer portion with an immutable source reference.
                        kit._install(studio.draft, studio.state, project=project, planned=writes, source_reference=source)
                        result = kit.transaction(studio.state, writes)
                        records.append({**record, 'status': 'current', 'snapshot': result.get('snapshot')})
                    except (OSError, ValueError) as error:
                        records.append({**record, 'status': 'conflict', 'detail': str(error) if isinstance(error, ValueError) else 'Project unavailable; check its drive and permissions'})
                    progress('Checked an enrolled project')
                # A digest detects routing changes without publishing machine inventories.
                runtime = {k: (config or {}).get(k) for k in ('nodes','primary','fallback','fallbacks','context','routing_policy')}
                result = {'projects': records, 'checked_at': time.time(), 'release': release,
                          'runtime_revision': digest(json_bytes(runtime))[:16]}
                atomic(root / 'sync-status.json', result)
                (root / 'sync-error.json').unlink(missing_ok=True)
                return result
