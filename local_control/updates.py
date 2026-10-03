"""Public GitHub releases, verified staging and guarded application replacement.

No checkout reset, shell installer, arbitrary download URL or background installation.
"""
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from scripts import constitution as kit, releases
from scripts.catalog import digest, json_bytes, atomic_bytes
from . import distribution, processes
from .storage import atomic, load, wait_lock
from .studio import bundled_source

REPOSITORY = 'https://github.com/thierry-gilgen-ict/ai-constitution'
API = 'https://api.github.com/repos/thierry-gilgen-ict/ai-constitution/releases/latest'
HOSTS = {'github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


def current():
    return (bundled_source() / 'VERSION').read_text().strip()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Choose a stable numbered release')
    return tuple(map(int, value.removeprefix('v').split('.')))


def fetch(url, limit):
    def verify(value):
        p = urllib.parse.urlsplit(value)
        if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password:
            raise ValueError('Unexpected release download location')
    verify(url)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            verify(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={'User-Agent': 'AI-Constitution-Updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(Redirect()).open(request, timeout=60) as response:
        body = response.read(limit + 1)
    if len(body) > limit: raise ValueError('Release download exceeds its size limit')
    return body


def read(root):
    path = Path(root) / 'updates.json'; kit.no_links(path)
    value = kit.read_json(path) if path.exists() else {'schema': 1, 'automatic_check': True}
    return {**value, 'current': current(), 'available': bool(value.get('latest') and version(value['latest']) > version(current()))}


def check(root, progress=lambda _: None):
    progress('Checking the public GitHub release; no account credentials are sent')
    try:
        record = json.loads(fetch(API, 2 * 1024**2)); tag = record.get('tag_name'); version(tag)
        if record.get('draft') or record.get('prerelease'): raise ValueError('Latest stable release unavailable')
        assets = {}
        for item in record.get('assets', []):
            name, url = item.get('name', ''), item.get('browser_download_url', '')
            if not re.fullmatch('[A-Za-z0-9_.-]+', name) or not url.startswith(REPOSITORY + '/releases/download/' + tag + '/'):
                continue
            assets[name] = url
        with wait_lock(Path(root) / 'update-operations'):
            value = read(root)
            value.update(latest=tag.removeprefix('v'), checked_at=time.time(), last_check=time.time(), error=None,
                url=REPOSITORY + '/releases/tag/' + tag, notes=str(record.get('body') or '')[:20000], assets=assets)
            atomic(Path(root) / 'updates.json', value)
        return {'status': 'checked', 'available': version(tag) > version(current()), 'version': tag}
    except (ValueError, OSError):
        with wait_lock(Path(root) / 'update-operations'):
            value = read(root); value.update(last_check=time.time(), error='Release check failed. Last successful result is retained; retry when GitHub is reachable.')
            atomic(Path(root) / 'updates.json', value)
        raise ValueError('Cannot check GitHub releases. Retry from Updates; no installation changed.') from None


def stage(root, expected, progress=lambda _: None):
    with wait_lock(Path(root) / 'update-operations'):
        value = read(root)
        if value.get('latest') != expected or not value['available']: raise ValueError('Check the latest release before downloading')
        assets = value.get('assets', {})
        frozen = bool(getattr(sys, 'frozen', False))
        archive = ('ai-constitution-worker-' + platform.system().lower() + '-' + platform.machine().lower() + '.zip') if frozen else 'ai-constitution-release.zip'
        checksum = archive + '.sha256' if frozen else 'ai-constitution-release.sha256'
        if archive not in assets or checksum not in assets: raise ValueError('This release has no matching package and checksum for this installation')
        progress('Downloading and verifying release ' + expected)
        sha = fetch(assets[checksum], 1024).decode().split()[0]
        if not re.fullmatch('[a-f0-9]{64}', sha): raise ValueError('Invalid release checksum')
        data = fetch(assets[archive], (1024 if frozen else 64) * 1024**2)
        if digest(data) != sha: raise ValueError('Release checksum verification failed')
        base = Path(root) / 'updates' / (expected + '-' + sha[:16]); kit.no_links(base)
        if base.exists():
            executable = base / 'app/ai-constitution-local' / ('ai-constitution-local.exe' if os.name == 'nt' else 'ai-constitution-local')
            record = {'version': expected, 'directory': str(base), 'sha256': sha,
                      'prefix': [str(executable)] if frozen else [sys.executable, str(base / 'scripts/local_control.py')]}
            verify_staged(record)
            value['staged'] = record
            if not value.get('active'): value['current_backup'] = capture_current(root)
            atomic(Path(root) / 'updates.json', value)
            return {'status': 'staged', 'version': expected, 'note': 'Previously verified download recovered. Review and restart when clients are idle.'}
        from .permissions import directory
        directory(base.parent)
        with tempfile.TemporaryDirectory(dir=base.parent, prefix='.stage-') as scratch:
            temp = Path(scratch).resolve()
            if frozen:
                zipped = temp / 'package.zip'; zipped.write_bytes(data)
                manifest = distribution.inspect_archive(zipped)
                if manifest.get('platform') != platform.system() or manifest.get('architecture', '').lower() != platform.machine().lower():
                    raise ValueError('Package platform does not match this computer')
                if manifest.get('version') != expected: raise ValueError('Package version must match the release')
                with zipfile.ZipFile(zipped) as bundle:
                    for name in manifest['files']:
                        atomic_bytes(kit.safe_path(temp, 'app/' + name), bundle.read('app/' + name))
                executable = temp / 'app/ai-constitution-local' / ('ai-constitution-local.exe' if os.name == 'nt' else 'ai-constitution-local')
                if os.name != 'nt': executable.chmod(0o700)
                relative_command = [str(executable.relative_to(temp))]
                checks = {'app/' + name: sha for name,sha in manifest['files'].items()}
                zipped.unlink()
            else:
                payload = releases.unpack(data, sha)
                if payload['VERSION'].decode().strip() != expected: raise ValueError('Source version does not match the release')
                for name, body in payload.items(): atomic_bytes(kit.safe_path(temp, name), body)
                relative_command = [sys.executable, 'scripts/local_control.py']
                checks = {name:digest(body) for name,body in payload.items()}
            atomic(temp / 'verified.json', {'version': expected, 'archive_sha256': sha, 'files': checks})
            temp.rename(base)
        prefix = [str(base / relative_command[0])] if frozen else [sys.executable, str(base / relative_command[1])]
        value['staged'] = {'version': expected, 'directory': str(base), 'prefix': prefix, 'sha256': sha}
        if not value.get('active'):
            value['current_backup'] = capture_current(root)
        atomic(Path(root) / 'updates.json', value)
        return {'status': 'staged', 'version': expected, 'note': 'Verified download ready. Review and restart from Updates when clients are idle.'}


def verify_staged(record):
    base = Path(record['directory']); kit.no_links(base)
    manifest = kit.read_json(base / 'verified.json')
    if manifest.get('version') != record['version']: raise ValueError('Staged release version changed')
    if manifest['archive_sha256'] != record['sha256']: raise ValueError('Staged release identity changed')
    for name, expected in manifest['files'].items():
        if digest(kit.safe_path(base, name).read_bytes()) != expected: raise ValueError('Staged application was modified; update refused')


def capture_current(root):
    """Retain the running code, even when its original Git checkout changes later."""
    frozen = bool(getattr(sys, 'frozen', False))
    if frozen:
        from .locations import tree
        source = Path(sys.executable).parent
        inventory = tree(source)
        if sum(size for size, _ in inventory.values()) > 3 * 1024**3:
            raise ValueError('Current application exceeds rollback-copy limit')
        payload = {name: kit.safe_path(source, name).read_bytes() for name in inventory}
    else:
        payload = releases.files(bundled_source())
    manifest = {name:digest(data) for name,data in payload.items()}
    identity = digest(json_bytes(manifest))
    base = Path(root) / 'updates' / ('rollback-' + current() + '-' + identity[:16])
    for name, data in payload.items():
        path = kit.safe_path(base, name)
        if path.exists() and digest(path.read_bytes()) != manifest[name]: raise ValueError('Rollback copy was modified')
        if not path.exists(): atomic_bytes(path, data)
    atomic(base / 'verified.json', {'version': current(), 'archive_sha256': identity, 'files': manifest})
    prefix = [str(base / Path(sys.executable).name)] if frozen else [sys.executable, str(base / 'scripts/local_control.py')]
    if frozen and os.name != 'nt': Path(prefix[0]).chmod(0o700)
    return {'version': current(), 'directory': str(base), 'prefix': prefix, 'sha256': identity}


def preview(control, rollback=False):
    value = read(control.root)
    target = value.get('previous') if rollback else value.get('staged')
    if not target: raise ValueError('No previous installation retained' if rollback else 'Download and verify the release first')
    if target.get('directory'): verify_staged(target)
    with control.lock:
        blockers = []
        if sum(control.active.values()) or control.queued: blockers.append('Active or queued model responses')
        if any(s['status'] != 'stale' for s in control.sessions()): blockers.append('Managed coding sessions')
        if any(j['status'] in ('queued','running') for j in control.jobs.values()): blockers.append('Background operations')
    result = {'version': target['version'], 'rollback': rollback, 'blockers': blockers,
        'note': 'Restart this service after external clients are idle. Configuration and model weights remain in their selected locations. The previous application is retained.'}
    result['plan'] = digest(json_bytes({'target': target, 'rollback': rollback, 'root': str(control.root)}))
    return result


def apply(server, body):
    control = server.control; rollback = body.get('rollback') is True
    with wait_lock(control.root / 'update-operations'):
        plan = preview(control, rollback)
        if body.get('plan') != plan['plan'] or plan['blockers']: raise ValueError('Update is blocked or changed; review the restart preview again')
        if body.get('acknowledge_external') is not True: raise ValueError('Confirm external model clients are idle before restarting')
        value = read(control.root); target = value['previous' if rollback else 'staged']
        from .launcher import command
        current_prefix = command()
        previous = value.get('active') or value.get('current_backup') or capture_current(control.root)
        if previous.get('directory'): verify_staged(previous)
        process = processes.identity(os.getpid())
        if not process: raise ValueError('Cannot establish process identity for a safe restart')
        address = urllib.parse.urlsplit(server.advertised)
        arguments = ['--state-dir', str(control.root), 'node' if server.worker else 'serve', '--port', str(address.port)]
        if server.worker: arguments += ['--address', address.hostname]
        elif getattr(server, 'no_background_services', False) is True: arguments += ['--no-background-services']
        ticket = uuid.uuid4().hex
        intent = {'process': process, 'target': target, 'previous': previous, 'args': arguments,
                  'url': server.advertised, 'worker': server.worker, 'status': 'waiting'}
        atomic(control.root / 'updates' / ('restart-' + ticket + '.json'), intent)
        control.stop_ready(True)
        try:
            subprocess.Popen([*current_prefix, '--state-dir', str(control.root), 'finish-update', '--ticket', ticket],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
        except Exception:
            control.stopping = False
            raise
        return {'status': 'restarting', 'version': target['version'], 'note': 'Restart scheduled. The page will reconnect automatically.'}


def finish(root, ticket):
    if not re.fullmatch('[a-f0-9]{32}', ticket): raise ValueError('Invalid restart ticket')
    path = Path(root) / 'updates' / ('restart-' + ticket + '.json'); kit.no_links(path)
    intent = kit.read_json(path)
    if intent.get('status') != 'waiting': raise ValueError('Restart ticket has already been used')
    deadline = time.monotonic() + 90
    while processes.matches(intent):
        if time.monotonic() > deadline:
            intent['status'] = 'blocked'; atomic(path, intent)
            with wait_lock(Path(root) / 'update-operations'):
                value = read(root); value.update(restart_status='blocked', error='Previous service did not exit. Review its active work before trying the update again.')
                atomic(Path(root) / 'updates.json', value)
            return
        time.sleep(.25)
    target = intent['target']
    if target.get('directory'): verify_staged(target)
    intent['status'] = 'starting'; atomic(path, intent)
    with open(Path(root) / 'update.log', 'ab') as log:
        child = subprocess.Popen([*target['prefix'], *intent['args']], stdout=log, stderr=log, env=dict(os.environ, AI_CONSTITUTION_UPDATE_BOOT='1'),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
    config = load(Path(root))
    endpoint = {'url': intent['url'], 'kind': 'worker' if intent['worker'] else 'ollama', 'token': config['token']}
    if intent['worker']:
        from .setup import certificate
        _, _, endpoint['fingerprint'] = certificate(Path(root), urllib.parse.urlsplit(intent['url']).hostname)
    from .transport import request
    healthy = False
    for _ in range(60):
        if child.poll() is not None: break
        try:
            result = request(endpoint, '/admin/version' if intent['worker'] else '/api/version', timeout=1)
            if result.get('version') == target['version']: healthy = True; break
        except (ValueError, OSError): pass
        time.sleep(.5)
    changes = {'previous': intent['previous']}
    if healthy:
        changes.update(active=target, previous=intent['previous'], staged=None, restart_status='verified', error=None)
        intent['status'] = 'verified'
        atomic(Path(root) / 'active-application.json', target)
    elif child.poll() is not None:
        subprocess.Popen([*intent['previous']['prefix'], *intent['args']], stdin=subprocess.DEVNULL, env=dict(os.environ, AI_CONSTITUTION_UPDATE_BOOT='1'),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
        changes.update(restart_status='rolled-back', error='New application exited during startup. Previous application restarted; inspect the private update log.')
        intent['status'] = 'rolled-back'
    else:
        # Never kill an unverified service: it may already have accepted client work.
        changes.update(restart_status='needs-attention', error='Startup health could not be confirmed. Inspect the service and update log before rollback.')
        intent['status'] = 'needs-attention'
    with wait_lock(Path(root) / 'update-operations'):
        value = read(root); value.update(changes)
        atomic(Path(root) / 'updates.json', value)
    atomic(path, intent)


def redirect(root, args):
    path = Path(root) / 'active-application.json'; kit.no_links(path)
    if not path.exists(): return None
    record = kit.read_json(path)
    actual = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/local_control.py')]
    if record['prefix'] == actual: return None
    if record.get('directory'): verify_staged(record)
    return subprocess.call([*record['prefix'], *args])
