"""Reviewed worker bundles served only through the authenticated controller."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from scripts import constitution as kit, releases
from scripts.catalog import digest, json_bytes
from . import locations
from .storage import atomic
from .studio import bundled_source

PROJECT = 'https://github.com/thierry-gilgen-ict/ai-constitution'
PLATFORMS = {'Windows': 'windows', 'Darwin': 'macos', 'Linux': 'linux'}


def index(root):
    path = Path(root) / 'worker-packages.json'
    kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'schema': 1, 'packages': {}}


def inspect_archive(path):
    kit.no_links(path)
    if path.stat().st_size > 1024 ** 3: raise ValueError('Worker archive exceeds 1 GiB')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(v.file_size for v in infos) > 3 * 1024 ** 3:
            raise ValueError('Worker archive exceeds extraction limits')
        seen = set()
        for item in infos:
            p = PurePosixPath(item.filename)
            if (p.is_absolute() or '..' in p.parts or '\\' in item.filename or ':' in item.filename
                    or str(p) != item.filename or item.filename.casefold() in seen or stat.S_ISLNK(item.external_attr >> 16)
                    or p.name.lower() in {'config.json','runtime.json','auth.json','drivers.json','server.log','.env'}
                    or p.suffix.lower() in {'.pem','.key','.pfx','.p12'}):
                raise ValueError('Archive contains private state, a duplicate, or an unsafe path')
            seen.add(item.filename.casefold())
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('platform') not in PLATFORMS or not isinstance(manifest.get('files'), dict):
            raise ValueError('Choose an AI Constitution portable archive with its build manifest')
        for name, expected in manifest['files'].items():
            if 'app/' + name not in archive.namelist() or digest(archive.read('app/' + name)) != expected:
                raise ValueError('Worker package file does not match its manifest')
        if any(n.startswith('app/') and n[4:] not in manifest['files'] for n in archive.namelist()):
            raise ValueError('Worker package has unlisted application files')
        for name in archive.namelist():
            if not name.startswith(('app/','licenses/')) and name not in {'manifest.json','dependencies.json','LICENSE','THIRD_PARTY_NOTICES.md','README.txt'}:
                raise ValueError('Unexpected package entry; review the archive before registering it')
    return manifest


def register(root, path):
    with kit.state_lock(Path(root) / 'studio-operations'):
        return _register(root, path)


def _register(root, path):
    path = Path(path).absolute()
    manifest = inspect_archive(path)
    sha = locations.file_hash(path)
    system = PLATFORMS[manifest['platform']]
    arch = re.sub('[^a-z0-9-]', '-', str(manifest.get('architecture', 'unknown')).lower())[:30]
    name = f'ai-constitution-worker-{system}-{arch}-{sha[:12]}.zip'
    target = locations.folder(root, 'downloads') / 'workers' / name
    kit.no_links(target); target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copyfile(path, temporary)
            if locations.file_hash(temporary) != sha: raise ValueError('Source package changed while copying')
            temporary.replace(target)
        finally: temporary.unlink(missing_ok=True)
    if locations.file_hash(target) != sha: raise ValueError('Registered package checksum mismatch')
    value = index(root)
    value['packages'][sha] = {'id': sha, 'filename': name, 'platform': system, 'architecture': arch,
                              'bytes': target.stat().st_size, 'sha256': sha, 'kind': 'portable',
                              'signing': 'Unsigned preview; checksums verify integrity, not publisher identity'}
    atomic(Path(root) / 'worker-packages.json', value)
    return value['packages'][sha]


def source_bundle(root):
    with kit.state_lock(Path(root) / 'studio-operations'):
        return _source_bundle(root)


def _source_bundle(root):
    payload = releases.files(bundled_source())
    identity = digest(json_bytes(releases.manifest(payload)))
    name = 'ai-constitution-worker-source-' + identity[:12] + '.zip'
    path = locations.folder(root, 'downloads') / 'workers' / name
    if path.exists():
        releases.unpack(path.read_bytes(), locations.file_hash(path))
        result = {'sha256': locations.file_hash(path)}
    else: result = releases.export(bundled_source(), path)
    value = index(root)
    value['packages'][result['sha256']] = {'id': result['sha256'], 'filename': name, 'platform': 'all',
        'architecture': 'Python 3.11+', 'bytes': path.stat().st_size, 'sha256': result['sha256'], 'kind': 'source',
        'signing': 'Source bundle from this controller version; review before running'}
    atomic(Path(root) / 'worker-packages.json', value)
    return value['packages'][result['sha256']]


def catalog(root):
    result = []
    for record in index(root)['packages'].values():
        path = locations.folder(root, 'downloads') / 'workers' / record['filename']
        kit.no_links(path)
        if path.is_file(): result.append({**record, 'download': '/api/worker-package?id=' + record['id']})
    return {'packages': result, 'builds_url': PROJECT + '/actions/workflows/package-preview.yml',
            'docs_url': PROJECT + '/blob/main/docs/windows-worker.md',
            'note': 'Download here, then transfer the whole archive to the worker. The dashboard stays on loopback; it is not exposed on your LAN.'}


def download(root, identity):
    if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{64}', identity): raise ValueError('Choose a listed worker package')
    record = index(root)['packages'].get(identity)
    if not record: raise ValueError('Worker package is no longer available')
    name = record['filename']
    if Path(name).name != name or not re.fullmatch('[a-z0-9.-]+', name): raise ValueError('Invalid worker package filename')
    path = locations.folder(root, 'downloads') / 'workers' / name
    kit.no_links(path)
    if not path.is_file() or locations.file_hash(path) != identity: raise ValueError('Package integrity check failed; register a verified package again')
    return path, record


def fetch_release(root, target, progress=lambda _: None):
    """Download a named native release package; registration never runs it."""
    from . import updates
    supported = {'windows-amd64': ('Windows','AMD64'), 'darwin-arm64': ('Darwin','arm64'), 'linux-x86_64': ('Linux','x86_64')}
    if target not in supported: raise ValueError('Choose a supported native build; use the source package on other architectures')
    value = updates.read(root)
    if not value.get('assets'): updates.check(root, progress=progress); value=updates.read(root)
    name='ai-constitution-worker-'+target+'.zip'
    assets=value.get('assets',{})
    if name not in assets or name+'.sha256' not in assets: raise ValueError('The latest release has no matching native package yet; use the source package')
    progress('Downloading the official release package; nothing will be executed')
    checksum=updates.fetch(assets[name+'.sha256'],1024).decode().split()[0]
    data=updates.fetch(assets[name],1024**3)
    if not re.fullmatch('[a-f0-9]{64}',checksum) or digest(data)!=checksum: raise ValueError('Worker package checksum failed')
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder).resolve()/name;path.write_bytes(data)
        manifest=inspect_archive(path); system,arch=supported[target]
        if manifest['platform']!=system or manifest.get('architecture','').lower()!=arch.lower(): raise ValueError('Worker package platform mismatch')
        result=register(root,path)
    return {**result,'note':'Verified worker package is ready to download from Set up a worker.'}
