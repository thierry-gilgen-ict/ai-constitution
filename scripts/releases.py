"""Immutable, content-verified release libraries; no Git worktree mutation."""
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import urllib.request
import urllib.parse
import zipfile
if __package__:
    from .paths import is_link, no_links
else:
    from paths import is_link, no_links

if __package__:
    from .catalog import atomic_bytes, digest, json_bytes
else:
    from catalog import atomic_bytes, digest, json_bytes

TOP = {"VERSION", "LICENSE", "README.md", "AGENTS.md", "CHANGELOG.md", "constitution.md", "engineering.md", "research.md", "maintenance.md", "routing.md", "requirements-local-node.txt", "requirements-desktop.txt", "requirements-build.txt", "THIRD_PARTY_NOTICES.md"}
DIRS = {"scripts", "registry", "adapters", "skills", "templates", "onboarding", "checks", "docs", "local_control", "packaging"}
SUFFIXES = {".py", ".ps1", ".json", ".md", ".mdc", ".html", ".js", ".css", ".txt", ".png"}
INVENTORY = 'checks/release-files.json'


def private_path(name):
    """Shared publication guard; source that manages credentials is not a key file."""
    parts = PurePosixPath(name).parts
    for part in parts:
        lower = part.casefold()
        if (lower in {'auth.json', 'config.json', 'runtime.json', 'pairing.json',
                      'drivers.json', 'server.log', '.local', '.config', '.ssh',
                      'transactions', 'configurations', 'local-worker', 'pki', 'secrets'}
                or lower.startswith(('.env', 'credentials'))
                or PurePosixPath(lower).suffix in {'.pem', '.key', '.p12', '.pfx'}):
            if part == 'credentials.py' and parts[-2:] == ('local_control', 'credentials.py'):
                continue
            return True
    return False


def allowed(name):
    if not isinstance(name, str) or private_path(name):
        return False
    path = PurePosixPath(name)
    return ('\\' not in name and ':' not in name
            and not path.is_absolute() and '..' not in path.parts and str(path) == name
            and (name in TOP or (len(path.parts) > 1 and path.parts[0] in DIRS
                 and not any(p.startswith('.') or p == '__pycache__' for p in path.parts)
                 and path.suffix in SUFFIXES)))


def files(root):
    result = {}
    # Never traverse unrelated trees such as Git, local build outputs or private
    # state merely to discard their names later.
    candidates = [root / name for name in TOP]
    for directory in sorted(DIRS):
        path = root / directory
        if is_link(path):
            raise ValueError('Release sources must not traverse links')
        if path.is_dir(): candidates.extend(path.rglob('*'))
    for path in sorted(candidates):
        name = path.relative_to(root).as_posix()
        if allowed(name) and path.is_file():
            if path.is_symlink() or any(is_link(p) for p in (path, *path.parents)):
                raise ValueError('Release sources must not traverse links')
            result[name] = path.read_bytes()
    return result


def public_files(root):
    """Export exactly the reviewed inventory, independently of Git ignore rules."""
    root = Path(root)
    no_links(root / INVENTORY)
    try:
        document = json.loads((root / INVENTORY).read_text(encoding='utf-8'))
        names = document['files']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('Public release inventory is missing or invalid') from exc
    if (set(document) != {'schema_version', 'files'} or document['schema_version'] != 1
            or not isinstance(names, list) or not names or len(names) > 1000
            or any(not allowed(name) for name in names)
            or len({name.casefold() for name in names}) != len(names)
            or names != sorted(names) or not {'VERSION', INVENTORY}.issubset(names)):
        raise ValueError('Public release inventory contains unsafe or duplicate paths')
    payload = {}
    for name in names:
        path = root / name
        no_links(path)
        if not path.is_file():
            raise ValueError('Public release inventory has a missing file: ' + name)
        payload[name] = path.read_bytes()
    return payload


def manifest(payload):
    version = payload.get('VERSION', b'').decode().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Release VERSION must be numeric')
    return {'schema_version': 1, 'version': version, 'source': 'https://github.com/thierry-gilgen-ict/ai-constitution',
            'files': {name: digest(body) for name, body in sorted(payload.items())}}


def export(root, output):
    payload = public_files(root)
    document = manifest(payload)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
        archive.writestr('release-manifest.json', json_bytes(document))
    atomic_bytes(output, stream.getvalue())
    return {'output': str(output), 'sha256': digest(stream.getvalue()), 'version': document['version']}


def unpack(data, expected):
    if not re.fullmatch(r'[a-f0-9]{64}', expected) or digest(data) != expected:
        raise ValueError('Release archive checksum mismatch')
    payload = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(i.file_size for i in entries) > 64 * 1024 * 1024:
            raise ValueError('Release archive exceeds limits')
        for item in entries:
            name = item.filename
            if name in payload or (name != 'release-manifest.json' and not allowed(name)) or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Unsafe or duplicate release archive entry')
            payload[name] = archive.read(item)
    declared = json.loads(payload.pop('release-manifest.json'))
    if declared != manifest(payload):
        raise ValueError('Release manifest does not match archive contents')
    return payload


def prepare(payload, state, *, preview=False):
    document = manifest(payload)
    identity = document['version'] + '-' + digest(json_bytes(document))[:16]
    destination = state.parent / 'releases' / identity
    if not preview:
        for name, data in payload.items():
            path = destination / name
            if path.exists() and path.read_bytes() != data:
                raise ValueError('Immutable release content was modified; preserve it before repair')
        for name, data in payload.items():
            atomic_bytes(destination / name, data)
        atomic_bytes(destination / 'release-manifest.json', json_bytes(document))
    return identity, destination


def selected(state, default):
    pointer = state / 'active-release.json'
    if not pointer.exists():
        return default
    identity = json.loads(pointer.read_text(encoding='utf-8'))['identity']
    if not re.fullmatch(r'\d+\.\d+\.\d+-[a-f0-9]{16}', identity):
        raise ValueError('Invalid installed release identity')
    root = state.parent / 'releases' / identity
    document = json.loads((root / 'release-manifest.json').read_text(encoding='utf-8'))
    if manifest(files(root)) != document or identity != document['version'] + '-' + digest(json_bytes(document))[:16]:
        raise ValueError('Installed release integrity check failed')
    return root


def latest():
    """Only the named public project's release assets; never arbitrary remote code URLs."""
    def fetch(url, limit):
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                parsed = urllib.parse.urlsplit(newurl)
                if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'} or parsed.username or parsed.password:
                    raise ValueError('Unexpected release download redirect')
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        request = urllib.request.Request(url, headers={'User-Agent': 'AI-Constitution', 'Accept': 'application/vnd.github+json'})
        with urllib.request.build_opener(Redirect()).open(request, timeout=30) as response:
            body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError('Release download exceeds limit')
        return body
    record = json.loads(fetch('https://api.github.com/repos/thierry-gilgen-ict/ai-constitution/releases/latest', 1024 * 1024))
    assets = record.get('assets', [])
    archive = next((a for a in assets if a['name'] == 'ai-constitution-release.zip'), None)
    checksum = next((a for a in assets if a['name'] == 'ai-constitution-release.sha256'), None)
    if not archive or not checksum:
        raise ValueError('The latest release has no managed-upgrade archive yet; use upgrade --source with a reviewed checkout')
    for item in (archive, checksum):
        if not item['browser_download_url'].startswith('https://github.com/thierry-gilgen-ict/ai-constitution/releases/download/'):
            raise ValueError('Unexpected release asset URL')
    expected = fetch(checksum['browser_download_url'], 512).decode().strip().split()[0]
    return unpack(fetch(archive['browser_download_url'], 64 * 1024 * 1024), expected)
