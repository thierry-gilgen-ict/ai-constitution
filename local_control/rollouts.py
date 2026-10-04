"""Preview and apply recoverable per-project instruction/template rollouts."""
from pathlib import Path
from contextlib import nullcontext
from scripts import constitution as kit, architecture, releases
from scripts.catalog import digest, json_bytes
from . import plans, synchronization
from .studio import Studio, difference


def _target(studio, project, database, baselines, source):
    writes = {}; old = baselines.get(str(project))
    if old:
        value = old['snapshot'] if old.get('policy') == 'pinned' else kit.read_json(
            kit.safe_path(studio.draft, 'templates/architectures/' + old['id'] + '.json'))
        _, writes = architecture.plan(kit, studio.draft, studio.state, project,
                                     architecture.validate(value), old['project_name'], old.get('policy', 'latest'))
    kit._install(studio.draft, studio.state, project=project, planned=writes,
                 source_reference=source, database=database)
    return writes


def preview(root, selected=None, *, _locked=False):
    studio = Studio(root)
    with (nullcontext() if _locked else kit.state_lock(studio.guard)), (nullcontext() if _locked else kit.state_lock(studio.state)):
        studio.initialize(); kit.validate(studio.draft); kit.build(studio.draft, check=True)
        db = kit.state_load(studio.state); preferences = synchronization.settings(root)
        if selected is not None and (not isinstance(selected,list) or len(selected)>200 or not all(isinstance(s,str) for s in selected)):
            raise ValueError('Select up to 200 enrolled projects')
        if selected is not None and any('project:' + s not in db['targets'] for s in selected):
            raise ValueError('Choose enrolled projects')
        path = studio.state / 'architectures.json'; kit.no_links(path)
        baselines = kit.read_json(path).get('projects', {}) if path.exists() else {}
        identity, source = releases.prepare(studio.payload(), studio.state, preview=True)
        rows = []; signatures = {}
        for target in db['targets'].values():
            if target['kind'] != 'project' or selected is not None and target['root'] not in selected: continue
            project = Path(target['root']); row = {'project': str(project), 'changes': []}
            if target['pinned'] or str(project) in preferences['paused_projects']:
                row['status'] = 'pinned' if target['pinned'] else 'paused'
            else:
                try:
                    writes = _target(studio, project, __import__('copy').deepcopy(db), baselines, source)
                    signature = {}
                    for name, after in writes.items():
                        before = name.read_bytes() if plans.fingerprint(name) is not None else None
                        signature[str(name)] = [digest(before) if before is not None else None, digest(after)]
                        try: relative = name.relative_to(project).as_posix()
                        except ValueError: continue  # Private ownership journals stay private.
                        if before != after: row['changes'].append(difference(relative, before, after))
                    signatures[str(project)] = signature
                    row['status'] = 'ready' if row['changes'] else 'current'
                except (OSError, ValueError):
                    row.update(status='conflict', detail='Project unavailable or locally changed. Inspect its setup before retrying.')
            rows.append(row)
        return plans.seal({'schema': 1, 'release': identity, 'projects': rows,
                           'signatures': signatures, 'enrollment': digest(json_bytes(db)),
                           'note': 'Each project has its own recoverable transaction. Pins and pauses remain effective; reload client instructions afterwards.'})


def apply(root, body, progress=lambda _: None):
    selected = body.get('projects')
    studio = Studio(root)
    with kit.state_lock(studio.guard), kit.state_lock(studio.state):
        reviewed = preview(root, selected, _locked=True); plans.verify(reviewed, body.get('plan'))
        db = kit.state_load(studio.state)
        path = studio.state / 'architectures.json'
        baselines = kit.read_json(path).get('projects', {}) if path.exists() else {}
        _, source = releases.prepare(studio.payload(), studio.state)
        results = []
        for row in reviewed['projects']:
            if row['status'] != 'ready': results.append(row); continue
            progress('Updating one reviewed project')
            project = Path(row['project'])
            try:
                writes = _target(studio, project, kit.state_load(studio.state), baselines, source)
                # Earlier commits legitimately change private enrollment journals.
                # Recheck each project's actual files immediately before its commit.
                for name, after in writes.items():
                    try: name.relative_to(project)
                    except ValueError: continue
                    expected = reviewed['signatures'][str(project)].get(str(name))
                    if expected != [plans.fingerprint(name), digest(after)]:
                        raise ValueError('Project changed during rollout')
                result = kit.transaction(studio.state, writes)
                results.append({'project': str(project), **result, 'status': 'applied'})
            except (OSError, ValueError):
                results.append({'project': str(project), 'status': 'needs-review',
                                'detail': 'Target changed or became unavailable; preview this project again'})
        return {'projects': results, 'release': reviewed['release']}
