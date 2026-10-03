"""Private project configuration mappings and verified, non-destructive backups."""
import datetime as dt
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from scripts import constitution as kit
from scripts.catalog import digest, json_bytes
from . import locations
from .storage import atomic
from scripts.paths import is_link
from .permissions import protect


def read(root):
    path = Path(root) / 'project-vault.json'; kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'schema': 1, 'config_root': os.environ.get('AI_CONSTITUTION_CONFIG_HOME', str(Path.home() / '.config')),
        'backup_root': str(Path.home() / '.local/share/ai-constitution/backups'), 'projects': {},
        'schedule': {'enabled': False, 'hours': 24}, 'last_attempt': None, 'last_success': None}


def slug(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value):
        raise ValueError('Use a short project ID with lowercase letters, digits and hyphens')
    return value


def separate(a, b):
    return not (a == b or a.is_relative_to(b) or b.is_relative_to(a))


def validate(root, value):
    base = locations.destination(value['config_root'])
    backup = locations.destination(value['backup_root'])
    value['config_root'], value['backup_root'] = str(base), str(backup)
    if not separate(base, backup) or not separate(Path(root), backup):
        raise ValueError('Backups must be outside the configuration root and Local Control state')
    paths = []
    for identity, entry in value['projects'].items():
        slug(identity)
        path = locations.destination(entry['folder'])
        entry['folder'] = str(path)
        if not path.is_relative_to(base) or path == base:
            raise ValueError('Each project needs its own folder under the private configuration root')
        if not separate(path, Path(root)) or any(not separate(path, old) for old in paths):
            raise ValueError('Project configuration folders must not overlap one another or Local Control state')
        paths.append(path)
        if entry.get('project'):
            project = Path(entry['project'])
            if not project.is_absolute() or not project.is_dir(): raise ValueError('Choose an existing project checkout')
            kit.no_links(project)
            if not separate(project, path) or not separate(project, backup):
                raise ValueError('Private configuration and backups must be outside project checkouts')
    schedule = value['schedule']
    if type(schedule.get('enabled')) is not bool or type(schedule.get('hours')) is not int or not 1 <= schedule['hours'] <= 720:
        raise ValueError('Choose a backup interval from 1 to 720 hours')
    return value


def configure(root, body):
    with kit.state_lock(Path(root) / 'vault-operations'):
        value = read(root)
        for key in ('config_root', 'backup_root', 'schedule'):
            if key in body: value[key] = body[key]
        if 'entry' in body:
            entry = body['entry']; identity = slug(entry.get('id'))
            label = entry.get('name', identity)
            if not isinstance(label, str) or not 1 <= len(label) <= 100: raise ValueError('Enter a project name')
            value['projects'][identity] = {'name': label, 'folder': entry.get('folder') or str(Path(value['config_root']) / identity),
                                          'project': entry.get('project', '')}
        if 'remove' in body: value['projects'].pop(slug(body['remove']), None)
        validate(root, value)
        atomic(Path(root) / 'project-vault.json', value)
        return {'status': 'saved', 'note': 'Mapping saved. Existing files stay in place; only selected project folders are backed up.'}


def overview(root):
    value = read(root)
    folders, warnings = [], []
    try:
        base = locations.destination(value['config_root'])
        children = sorted(base.iterdir()) if base.is_dir() else []
    except OSError:
        children = []; warnings.append('The configuration root is unavailable. Choose an accessible private directory below.')
    for path in children:
        try:
            if is_link(path): continue
            if path.is_dir() and separate(path, Path(root)): folders.append({'name': path.name, 'path': str(path)})
        except OSError: continue
    snapshots = []
    try:
        backup = locations.destination(value['backup_root'])
        candidates = sorted(backup.glob('snapshot-*'), reverse=True)[:100] if backup.exists() else []
    except OSError:
        candidates = []; warnings.append('Backup storage is unavailable; snapshot inventory could not be read.')
    for path in candidates:
        try:
            kit.no_links(path)
            kit.no_links(path / 'manifest.json')
            record = kit.read_json(path / 'manifest.json')
            if record.get('schema') == 1:
                snapshots.append({'id': path.name, 'created': record['created'], 'projects': record['projects'],
                                  'files': len(record['files']), 'bytes': record['bytes']})
        except (OSError, ValueError, KeyError): continue
    from .encrypted_backup import settings
    encrypted = settings(root)['enabled']
    return {**value, 'available_folders': folders, 'snapshots': snapshots, 'warnings': warnings,
            'next_due': (value.get('pending_until') or value.get('retry_after') or ((value.get('last_success') or 0) + value['schedule']['hours'] * 3600)) if value['schedule']['enabled'] else None,
            'note': ('New backups use the configured encrypted restic repository. Existing local snapshots remain available below. ' if encrypted else 'Local snapshots contain secrets; choose private encrypted storage or enable restic below. ') + 'Schedules run in Local Control or through an optional OS task. Originals are preserved; retention requires review.'}


def plan(root):
    value = validate(root, read(root))
    if not value['projects']: raise ValueError('Select at least one project configuration folder first')
    inventories, total = {}, 0
    for identity, entry in value['projects'].items():
        path = Path(entry['folder'])
        if not path.is_dir(): raise ValueError('A selected configuration folder is missing; create it or update its mapping')
        inventory = locations.tree(path)
        if any(size > 1024**3 for size, _ in inventory.values()): raise ValueError('A configuration file exceeds the 1 GiB backup limit')
        total += sum(v[0] for v in inventory.values())
        if total > 5 * 1024**3: raise ValueError('Configuration backup exceeds 5 GiB; use a dedicated backup tool for large artifacts')
        inventories[identity] = inventory
    from .encrypted_backup import settings
    encryption = settings(root)
    backend = encryption if encryption['enabled'] else {'enabled': False}
    destination = encryption['repository'] if encryption['enabled'] else value['backup_root']
    if not encryption['enabled'] and locations.space(destination)['free_bytes'] < total + 16 * 1024**2: raise ValueError('Not enough backup space')
    return {'plan': digest(json_bytes({'settings': value, 'files': inventories, 'backend': backend})), 'backend': 'restic' if encryption['enabled'] else 'local', 'projects': list(value['projects']),
            'files': sum(len(v) for v in inventories.values()), 'bytes': total, 'destination': destination}


def backup(root, expected=None, progress=lambda _: None):
    with kit.state_lock(Path(root) / 'vault-operations'):
        preview = plan(root)
        if preview['backend'] != 'local': raise ValueError('Backup backend changed; preview again')
        if expected is not None and expected != preview['plan']: raise ValueError('Configuration files changed. Preview backup again.')
        value = validate(root, read(root)); parent = Path(value['backup_root'])
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        identity = 'snapshot-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        final = parent / identity
        with tempfile.TemporaryDirectory(prefix='.backup-', dir=parent) as scratch:
            staging = Path(scratch).resolve(); protect(staging)
            files = {}
            for key, entry in value['projects'].items():
                source = Path(entry['folder']); target = staging / 'projects' / key
                copy = locations.copy_plan(source, target)
                locations.copy_verified(source, target, copy['fingerprint'], progress=progress)
                for name in locations.tree(target): files['projects/' + key + '/' + name] = locations.file_hash(kit.safe_path(target, name))
            # A snapshot describes one stable source state, including all selected projects.
            if plan(root)['plan'] != preview['plan']: raise ValueError('Configuration changed during backup; retry to capture a stable snapshot')
            manifest = {'schema': 1, 'created': time.time(), 'projects': list(value['projects']), 'files': files, 'bytes': preview['bytes']}
            atomic(staging / 'manifest.json', manifest)
            kit.no_links(final)
            if staging.parent != parent.resolve() or final.exists(): raise ValueError('Backup destination changed')
            staging.rename(final)
        value['last_success'] = time.time(); value['last_attempt'] = value['last_success']; value['last_error'] = None
        value.update(schedule_status='succeeded', pending_until=None, retry_after=None, schedule_failures=0)
        atomic(Path(root) / 'project-vault.json', value)
        return {'status': 'verified', 'snapshot': identity, 'files': len(files), 'bytes': preview['bytes']}


def restore_plan(root, identity, project, destination):
    if not isinstance(identity, str) or not re.fullmatch(r'snapshot-\d{8}T\d{6}Z-[a-f0-9]{8}', identity): raise ValueError('Choose a listed snapshot')
    slug(project)
    source = locations.destination(read(root)['backup_root']) / identity; kit.no_links(source)
    kit.no_links(source / 'manifest.json')
    document = kit.read_json(source / 'manifest.json')
    if document.get('schema') != 1 or project not in document['projects']: raise ValueError('Project is absent from this snapshot')
    prefix = 'projects/' + project + '/'
    expected = {n[len(prefix):]: h for n,h in document['files'].items() if n.startswith(prefix)}
    base = source / 'projects' / project
    inventory = locations.tree(base)
    if set(inventory) != set(expected): raise ValueError('Snapshot inventory changed; restore refused')
    for name, sha in expected.items():
        if locations.file_hash(kit.safe_path(base, name)) != sha: raise ValueError('Snapshot integrity check failed')
    target = locations.destination(destination)
    if not separate(target, Path(root)) or not separate(target, source.parent): raise ValueError('Restore outside Local Control state and backup storage')
    copy = locations.copy_plan(base, target)
    if copy.get('unchanged'): raise ValueError('Restore into a new directory')
    return {**copy, 'plan': digest(json_bytes({'copy': {k:v for k,v in copy.items() if k != 'free_bytes'}, 'manifest': document, 'project': project})),
            'note': 'Restores into a new folder. Active environment files and existing folders are never overwritten.'}


def restore(root, identity, project, target, expected, progress=lambda _: None):
    with kit.state_lock(Path(root) / 'vault-operations'):
        preview = restore_plan(root, identity, project, target)
        if preview['plan'] != expected: raise ValueError('Restore source changed. Preview again.')
        # Parent exists only for the selected new destination; private permissions follow below.
        result = locations.copy_verified(Path(preview['source']), Path(preview['destination']), preview['fingerprint'], progress=progress, prepare=protect)
        return {**result, 'status': 'restored', 'note': 'Verified restoration is ready. Update the project mapping explicitly when you want to use it.'}


def scheduled(root, progress=lambda _: None):
    schedule_state(root, 'started')
    try:
        from . import encrypted_backup
        return (encrypted_backup.backup if encrypted_backup.settings(root)['enabled'] else backup)(root, progress=progress)
    except Exception:
        schedule_state(root, 'failed')
        raise


def schedule_state(root, status, now=None):
    now = time.time() if now is None else now
    with kit.state_lock(Path(root) / 'vault-operations'):
        value = read(root)
        value['schedule_status'] = status
        value['pending_until'] = None
        if status == 'started':
            value['last_attempt'] = now
            value['pending_until'] = now + 7200
        elif status in ('rejected', 'failed'):
            failures = min(value.get('schedule_failures', 0) + 1, 7)
            value.update(schedule_failures=failures, retry_after=now + min(3600, 60 * 2**(failures-1)),
                last_error='Backup could not start or finish. Check Activity and backup settings. An automatic retry is scheduled.')
        atomic(Path(root) / 'project-vault.json', value)


def claim_due(root, now=None):
    now = time.time() if now is None else now
    # Read a durable lease before contending with a long-running backup lock.
    if now < (read(root).get('pending_until') or 0): return False
    with kit.state_lock(Path(root) / 'vault-operations'):
        value = read(root)
        if not value['schedule']['enabled'] or not value['projects']: return False
        if now < (value.get('pending_until') or 0) or now < (value.get('retry_after') or 0): return False
        if now - (value.get('last_success') or 0) < value['schedule']['hours'] * 3600: return False
        # Durable, short reservation. A rejected queue or interrupted process never
        # advances the backup interval. A stale reservation recovers after 5 minutes.
        value.update(pending_until=now + 300, schedule_status='pending')
        atomic(Path(root) / 'project-vault.json', value)
        return True
