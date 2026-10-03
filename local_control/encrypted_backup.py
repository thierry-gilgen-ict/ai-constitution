"""Optional restic adapter. Keys stay in OS environment or a private password file."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from scripts import constitution as kit
from scripts.catalog import digest, json_bytes
from . import locations, project_vault
from .permissions import directory
from .storage import atomic, wait_lock


def settings(root):
    path = Path(root) / 'restic.json'; kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'schema': 1, 'repository': '', 'password_file': '',
        'password_env': 'RESTIC_PASSWORD', 'tag': 'ai-constitution-' + digest(str(Path(root)).encode())[:12],
        'keep_last': 10, 'enabled': False}


def configure(root, body):
    with wait_lock(Path(root) / 'vault-operations'):
        value = settings(root)
        repository = body.get('repository', value['repository'])
        if not isinstance(repository, str) or not repository or len(repository) > 2000 or any(ord(c) < 32 for c in repository):
            raise ValueError('Enter a restic repository path or local/SFTP/S3/backend location')
        # Credentials belong in environment variables or files, never URLs saved in settings.
        if re.search(r'://[^/]*:[^/@]+@|[?&](?:token|key|secret|password)=', repository, re.I):
            raise ValueError('Repository locations must not contain credentials')
        if Path(repository).is_absolute() or repository.startswith('~'):
            repository = str(locations.destination(repository))
            vault = project_vault.read(root)
            for folder in [Path(root), locations.destination(vault['config_root'])]:
                if not project_vault.separate(Path(repository), folder): raise ValueError('Keep the encrypted repository outside state and source configuration')
        password_file = body.get('password_file', value['password_file'])
        if password_file:
            path = Path(password_file).expanduser(); kit.no_links(path)
            if not path.is_absolute() or not path.is_file(): raise ValueError('Choose an existing private password file')
            if any((p / '.git').exists() for p in path.parents): raise ValueError('Keep the password file outside Git checkouts')
            password_file = str(path)
        env = body.get('password_env', value['password_env'])
        if not isinstance(env, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', env): raise ValueError('Enter an environment-variable name, not its value')
        count = body.get('keep_last', value['keep_last'])
        if type(count) is not int or not 1 <= count <= 1000: raise ValueError('Retain from 1 to 1000 snapshots')
        enabled = body.get('enabled', value['enabled'])
        if type(enabled) is not bool: raise ValueError('Choose whether scheduled backups use encryption')
        value.update(repository=repository, password_file=password_file, password_env=env, keep_last=count, enabled=enabled)
        atomic(Path(root) / 'restic.json', value)
    return {'status': 'saved', 'note': 'Credentials were not read. Initialize or check the repository before enabling scheduled backups.'}


def run(root, args, *, timeout=900, progress=lambda _: None):
    executable = shutil.which('restic')
    if not executable: raise ValueError('Install restic first using the official instructions shown in Backups')
    value = settings(root)
    if not value['repository']: raise ValueError('Configure an encrypted backup repository first')
    env = {k:v for k,v in os.environ.items() if not k.startswith('RESTIC_')}
    env.update(RESTIC_REPOSITORY=value['repository'], RESTIC_CACHE_DIR=str(Path(root) / 'restic-cache'))
    if value['password_file']:
        kit.no_links(Path(value['password_file'])); env['RESTIC_PASSWORD_FILE'] = value['password_file']
    elif os.environ.get(value['password_env']): env['RESTIC_PASSWORD'] = os.environ[value['password_env']]
    else: raise ValueError('Backup password unavailable to this process. Set its environment variable or private password file.')
    progress('Running encrypted backup operation; credentials and file contents stay private')
    # Capture to a bounded-on-read private scratch file; never return raw stderr, paths or credentials.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run([executable, '--json', *args], env=env, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.DEVNULL, timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode: raise ValueError('Restic operation failed (exit ' + str(result.returncode) + '). Check repository access, password, locks and available space.')
        if output.tell() > 8 * 1024**2: raise ValueError('Restic report exceeds the 8 MiB limit; inspect it with the CLI')
        output.seek(0); raw = output.read().decode('utf-8')
    try: return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def snapshots(root):
    value = run(root, ['snapshots', '--tag', settings(root)['tag']])
    if not isinstance(value, list): raise ValueError('Unsupported snapshot report')
    return [{'id': v['id'], 'time': v.get('time'), 'tags': v.get('tags', [])} for v in value
            if isinstance(v, dict) and re.fullmatch('[a-f0-9]{64}', v.get('id', ''))][-1000:]


def overview(root):
    return {**settings(root), 'installed': bool(shutil.which('restic')),
            'docs': 'https://restic.readthedocs.io/en/stable/020_installation.html',
            'note': 'Restic encrypts data and supports local, SFTP, S3 and other backends. Keep the password separately; losing it prevents recovery. Retention deletion always requires a reviewed preview.'}


def backup(root, expected=None, progress=lambda _: None):
    with wait_lock(Path(root) / 'vault-operations'):
        preview = project_vault.plan(root)
        if preview['backend'] != 'restic': raise ValueError('Enable encrypted backups and preview again')
        if expected and expected != preview['plan']: raise ValueError('Configuration changed; preview backup again')
        value = project_vault.validate(root, project_vault.read(root)); config = settings(root)
        run(root, ['backup', '--tag', config['tag'], '--host', config['tag'], '--',
            *[v['folder'] for v in value['projects'].values()]], progress=progress)
        run(root, ['check'], progress=progress)
        value.update(last_success=time.time(), last_attempt=time.time(), last_error=None, schedule_status='succeeded',
                     pending_until=None, retry_after=None, schedule_failures=0, last_backend='restic')
        atomic(Path(root) / 'project-vault.json', value)
        return {'status': 'verified', 'backend': 'restic', 'note': 'Encrypted snapshot completed; repository metadata integrity checked. Use a restore drill to verify recoverability.'}


def retention(root, expected=None):
    with wait_lock(Path(root) / 'vault-operations'):
        return _retention(root, expected)


def _retention(root, expected=None):
    value = settings(root); current = snapshots(root)
    args = ['forget', '--tag', value['tag'], '--group-by', 'tags', '--keep-last', str(value['keep_last'])]
    report = run(root, [*args, '--dry-run'])
    plan = digest(json_bytes({'settings': value, 'snapshots': current, 'report': report}))
    removed = [v['id'] for group in report for v in (group.get('remove') or [])] if isinstance(report, list) else []
    if any(identity not in {v['id'] for v in current} for identity in removed): raise ValueError('Retention report contains snapshots outside the reviewed scope')
    result = {'plan': plan, 'remove': removed, 'keep_last': value['keep_last'], 'note': 'Deletes only the reviewed snapshots in this controller’s tag group. Other hosts and tags remain untouched.'}
    if expected is not None:
        if expected != plan: raise ValueError('Snapshot inventory changed; preview retention again')
        if removed: run(root, ['forget', *removed])
        return {'status': 'retained', 'removed': len(removed), 'note': 'Unused repository data remains until a separate restic prune.'}
    return result


def restore_plan(root, body):
    snapshot = body.get('snapshot')
    if snapshot not in {v['id'] for v in snapshots(root)}: raise ValueError('Choose a snapshot from this controller')
    destination = locations.destination(body.get('destination'))
    if destination.exists(): raise ValueError('Restore into a new directory')
    vault = project_vault.read(root)
    protected = [Path(root), locations.destination(vault['config_root'])]
    repository = settings(root)['repository']
    if Path(repository).is_absolute(): protected.append(Path(repository))
    for base in protected:
        if not project_vault.separate(destination, base): raise ValueError('Restore outside active configuration, state and backup storage')
    signature = {'snapshot': snapshot, 'destination': str(destination), 'settings': settings(root)}
    return {'snapshot': snapshot, 'destination': str(destination), 'plan': digest(json_bytes(signature)),
            'note': 'Restore the whole snapshot to a new private folder and verify restored file contents. Active files are never replaced.'}


def restore(root, body, progress=lambda _: None):
    with wait_lock(Path(root) / 'vault-operations'):
        plan = restore_plan(root, body)
        if body.get('plan') != plan['plan']: raise ValueError('Restore destination changed; preview again')
        destination = Path(plan['destination']); destination.parent.mkdir(parents=True, exist_ok=True)
        staging = directory(destination.parent / ('.restore-' + uuid.uuid4().hex))
        try:
            run(root, ['restore', plan['snapshot'], '--target', str(staging), '--verify'], progress=progress)
            kit.no_links(destination)
            if destination.exists(): raise ValueError('Restore destination was created meanwhile; verified files retained in recovery folder')
            staging.rename(destination)
        except Exception:
            # Preserve partial recovery instead of recursively deleting potentially valuable files.
            raise ValueError('Restore incomplete. Review the private .restore folder beside the selected destination before retrying.') from None
        return {'status': 'restored', 'destination': str(destination), 'verified': True}
