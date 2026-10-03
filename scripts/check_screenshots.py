"""Offline screenshot integrity, freshness, coverage and publication-budget checks."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
ASSET_LIMIT = 16 * 1024 * 1024
IMAGE_LIMIT = 900 * 1024
RELEASE_LIMIT = 64 * 1024 * 1024


def png_dimensions(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    offset, dimensions = 8, None
    while offset < len(data):
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        checksum = data[offset + 8 + length:offset + 12 + length]
        if len(checksum) != 4 or zlib.crc32(kind + payload) != struct.unpack('>I', checksum)[0]:
            raise ValueError('invalid chunk checksum')
        if kind in {b'tEXt', b'iTXt', b'zTXt', b'eXIf'}:
            raise ValueError('unreviewed embedded text or EXIF metadata')
        if kind == b'IHDR':
            dimensions = struct.unpack('>II', payload[:8])
        offset += length + 12
        if kind == b'IEND':
            if offset != len(data) or not dimensions or not all(dimensions):
                raise ValueError('invalid PNG end or dimensions')
            return dimensions
    raise ValueError('missing PNG end')


def validate(root=ROOT, *, sources=True, release=True):
    failures = []
    folder = root / 'docs/assets/screenshots'
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return [f'Cannot read screenshot manifest: {exc}']
    if manifest.get('schema') != 1:
        failures.append('Unknown screenshot manifest schema')
    if manifest.get('ui_version') != (root / 'VERSION').read_text().strip():
        failures.append('Screenshot UI version is stale; run npm run screenshots')
    if sources:
        try:
            inputs = manifest['digest_inputs']
            allowed = ['local_control/web/' + a for a in ['index.html', 'style.css', 'app.js', 'center.js', 'studio.js', 'experience.js']] + ['VERSION', 'tests/fixtures/documentation.cjs', 'scripts/documentation_scenarios.cjs', 'scripts/documentation_cli.py', 'scripts/screenshots.cjs', 'templates/architecture-components.json'] + ['templates/architectures/' + a + '.json' for a in ['web-product', 'data-dashboard', 'python-api']] + ['constitution.md', 'engineering.md', 'research.md', 'routing.md', 'registry/routes.json']
            if inputs != allowed:
                raise ValueError('Screenshot digest inputs must match the capture harness')
            data = b''.join(name.encode() + b'\0' + (root / name).read_bytes().replace(b'\r\n', b'\n') + b'\0' for name in inputs)
            if hashlib.sha256(data).hexdigest() != manifest['source_digest']:
                failures.append('Screenshot sources changed; run npm run screenshots and review the images')
        except (OSError, KeyError, ValueError) as exc:
            failures.append(str(exc))
    entries = manifest.get('entries', [])
    ids = [v['id'] for v in entries]
    if len(set(ids)) != len(ids):
        failures.append('Duplicate screenshot IDs')
    nav = set(re.findall(r'class="nav[^"\n]*"[^>]*data-page="([a-z-]+)"', (root / 'local_control/web/index.html').read_text()))
    # Attribute order can vary without changing the UI.
    if not nav:
        nav = set(re.findall(r'data-page="([a-z-]+)"', (root / 'local_control/web/index.html').read_text()))
    covered = {v['page'] for v in entries if v.get('overview')}
    if nav != covered or nav != set(manifest.get('pages', {})):
        failures.append('Dashboard-page screenshot coverage is incomplete')
    if sources:
        scenario_text = (root / 'scripts/documentation_scenarios.cjs').read_text(encoding='utf-8')
        required = set(re.findall(r"add\('([a-z]+(?:-[a-z]+)*)'", scenario_text)) | nav | {'worker-windows', 'worker-macos', 'worker-linux'}
        if set(ids) != required:
            failures.append('Capture manifest does not cover every declared documentation journey')
    total = 0
    expected = set()
    for entry in entries:
        name = entry.get('path', '')
        canonical = f"docs/assets/screenshots/{entry['id']}.png"
        if not re.fullmatch(r'[a-z0-9-]+', entry['id']) or name != canonical or PurePosixPath(name).is_absolute():
            failures.append(f"Unsafe screenshot path: {entry['id']}")
            continue
        file = root / name
        expected.add(file.name)
        if file.is_symlink():
            failures.append(f'Screenshot must not be a link: {name}')
            continue
        try:
            data = file.read_bytes()
            total += len(data)
            if len(data) > IMAGE_LIMIT:
                failures.append(f'Screenshot exceeds 900 KiB: {name}')
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                failures.append(f'Screenshot checksum differs: {name}')
            if png_dimensions(data) != (entry['width'], entry['height']) or len(data) != entry['bytes']:
                failures.append(f'Screenshot dimensions or byte count differ: {name}')
            text = (root / f"docs/manual/{entry['chapter']}.md").read_text(encoding='utf-8')
            if f"../assets/screenshots/{entry['id']}.png" not in text or entry['caption'] not in text:
                failures.append(f"Manual image or caption missing: {entry['id']}")
        except (OSError, ValueError, KeyError, struct.error) as exc:
            failures.append(f'{name}: {exc}')
    if {p.name for p in folder.glob('*.png')} != expected:
        failures.append('Unlisted PNG assets or missing captures in screenshot directory')
    if total > ASSET_LIMIT:
        failures.append('Screenshots exceed the 16 MiB total asset budget')
    readme = (root / 'README.md').read_text(encoding='utf-8')
    for page in nav:
        if f'docs/assets/screenshots/{page}.png' not in readme:
            failures.append(f'README gallery is missing {page}')
    for external in manifest.get('external_captures', []):
        if external.get('status') != 'pending' or not external.get('reason'):
            failures.append('External captures require an explicit reviewed import before claiming completion')
        if not (root / external['guide']).is_file():
            failures.append(f"Missing external setup guide: {external['guide']}")
    if release:
        if __package__:
            from .releases import files
        else:
            from releases import files
        payload = files(root)
        # The updater counts the manifest as an archive entry too.
        size = sum(map(len, payload.values())) + len(json.dumps({'files': {n: '0'*64 for n in payload}}).encode())
        if size >= RELEASE_LIMIT or len(payload) + 1 > 1000:
            failures.append('Public release payload exceeds updater archive limits')
    return failures


if __name__ == '__main__':
    errors = validate()
    if errors:
        print('\n'.join(errors))
        sys.exit(1)
    print('Screenshot integrity, freshness, journey coverage, manual references and release budget passed.')
