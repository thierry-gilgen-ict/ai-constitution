"""Project inventory and bounded, reviewable batch onboarding. No project execution."""
import copy
import os
from pathlib import Path
from scripts import constitution as kit
from scripts.adoption import project_record
from scripts.catalog import digest, json_bytes
from . import synchronization, project_vault, monitoring
from .studio import Studio, difference

SKIP = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'vendor', '__pycache__'}


def overview(control):
    studio = Studio(control.root)
    sync = synchronization.status(control.root)
    vault = project_vault.read(control.root)
    accounts = monitoring.load(control.root)['accounts']
    path = studio.state / 'architectures.json'; kit.no_links(path)
    baselines = kit.read_json(path).get('projects', {}) if path.exists() else {}
    for project in sync['projects']:
        name = project['project']; baseline = baselines.get(name)
        mappings = [dict(id=k, **v) for k,v in vault['projects'].items() if v.get('project') == name]
        project.update(machine='This computer', architecture=({k:v for k,v in baseline.items()
            if k in ('id','version','policy','template_sha256')} if baseline else None), configurations=mappings,
            accounts=[{k:v for k,v in a.items() if k in ('id','label','login','provider','application','machine')}
                      for a in accounts.values() if name in a.get('projects', [])],
            backup={'last_success': vault.get('last_success') if mappings else None,
                    'error': vault.get('last_error') if mappings else None, 'configured': bool(mappings)},
            route={'alias': 'constitution-local', 'mode': control.mode, 'primary': control.config.get('primary'),
                   'fallback': control.config.get('fallback'), 'applies': 'Only sessions launched through Local Control'})
    return sync


def discover(root, body):
    roots = body.get('roots')
    if not isinstance(roots, list) or not 1 <= len(roots) <= 10:
        raise ValueError('Choose one to ten search roots')
    projects, visited, seen = [], 0, set()
    enrolled = kit.state_load(Studio(root).state)['targets']
    truncated = False
    for entry in roots:
        base = Path(entry).expanduser().absolute(); kit.no_links(base)
        if not base.is_dir(): raise ValueError('Choose an existing search root')
        for folder, dirs, files in os.walk(base, followlinks=False):
            path = Path(folder); kit.no_links(path)
            visited += 1
            if visited > 5000 or len(projects) >= 200:
                truncated = True; break
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.')
                             and len((path / d).relative_to(base).parts) <= 4)
            for d in list(dirs):
                try: kit.no_links(path / d)
                except ValueError: dirs.remove(d)
            if '.git' not in files and not (path / '.git').is_dir(): continue
            name = str(path)
            if name in seen: continue
            seen.add(name)
            lock = path / '.ai/constitution.lock.json'; kit.no_links(lock)
            projects.append({'project': name, 'name': path.name, 'enrolled': 'project:' + name in enrolled,
                'portable_bundle': lock.is_file(), 'has_instructions': (path / 'AGENTS.md').is_file()})
    return {'projects': projects, 'truncated': truncated, 'directories_inspected': min(visited, 5000),
            'note': 'Discovery reads names only, to depth four. Select projects to preview; no source or environment values are collected.'}


def plan(studio, body):
    entries = body.get('projects')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 50:
        raise ValueError('Select one to fifty projects')
    database = kit.state_load(studio.state)
    vault = project_vault.read(studio.root)
    writes, results, seen = {}, [], set()
    for entry in entries:
        project = Path(entry.get('project', '')).expanduser()
        if not project.is_absolute() or not project.is_dir(): raise ValueError('Select an existing absolute project path')
        kit.no_links(project); project = project.absolute()
        if str(project) in seen: raise ValueError('Project selected more than once')
        seen.add(str(project)); identity = 'project:' + str(project)
        before = copy.deepcopy(database); draft = {}
        try:
            if identity not in database['targets'] and (project / '.ai/constitution.lock.json').exists():
                if entry.get('adopt') is not True: raise ValueError('Select adoption to verify the existing portable bundle')
                database['targets'][identity] = project_record(project, modules=kit.MODULES, safe_path=kit.safe_path,
                    managed_hash=kit.managed_hash, digest=digest)
            if not database['targets'].get(identity, {}).get('pinned'):
                kit._install(studio.draft, studio.state, project=project, planned=draft, database=database)
            config_id = entry.get('configuration')
            if config_id:
                if config_id not in vault['projects']: raise ValueError('Choose an existing configuration mapping')
                mapping = vault['projects'][config_id]
                if mapping.get('project') and mapping['project'] != str(project):
                    raise ValueError('This configuration folder belongs to another project')
                mapping['project'] = str(project)
            writes.update(draft)
            results.append({'project': str(project), 'status': 'ready', 'changes': [difference(p.relative_to(project).as_posix(),
                p.read_bytes() if p.exists() else None, data) for p,data in draft.items() if p.is_relative_to(project)
                and (not p.exists() or p.read_bytes() != data)]})
        except (OSError, ValueError) as error:
            database = before
            results.append({'project': str(project), 'status': 'conflict', 'detail': str(error) if isinstance(error, ValueError) else 'Folder unavailable'})
    project_vault.validate(studio.root, vault)
    writes[studio.state / 'installations.json'] = json_bytes(database)
    writes[studio.root / 'project-vault.json'] = json_bytes(vault)
    signature = {str(p): {'before': digest(p.read_bytes()) if p.exists() else None, 'after': digest(b)} for p,b in writes.items()}
    return {'plan': digest(json_bytes(signature)), 'projects': results, 'ready': sum(v['status'] == 'ready' for v in results),
            'note': 'Only ready projects will be enrolled. Existing instructions and private configuration files are preserved.'}, writes


def onboard(root, body, apply=False):
    studio = Studio(root)
    from .storage import wait_lock
    with wait_lock(studio.guard), wait_lock(studio.state), wait_lock(Path(root) / 'vault-operations'):
        studio.initialize()
        preview, writes = plan(studio, body)
        if not apply: return preview
        if body.get('plan') != preview['plan']: raise ValueError('Projects changed since preview; review again')
        if not preview['ready']: raise ValueError('Resolve a conflict before onboarding')
        return {**kit.transaction(studio.state, writes), 'projects': preview['projects']}
