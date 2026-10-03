"""Fail closed before uploading public files. Never print credential values."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

try:
    from .releases import private_path
    from .paths import no_links
except ImportError:
    from releases import private_path
    from paths import no_links

VERSION = '8.30.1'
DOWNLOADS = {
    ('Linux', 'x86_64'): ('linux_x64.tar.gz', '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'),
    ('Linux', 'aarch64'): ('linux_arm64.tar.gz', 'e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080'),
    ('Darwin', 'arm64'): ('darwin_arm64.tar.gz', 'b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5'),
    ('Darwin', 'x86_64'): ('darwin_x64.tar.gz', 'dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709'),
    ('Windows', 'amd64'): ('windows_x64.zip', 'd29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e'),
}
MAX_MEMBERS = 100000
MAX_BYTES = 8 * 1024 ** 3
MAX_DEPTH = 3


class PublicationError(ValueError):
    """Only static, safe diagnostics belong in public CI output."""


def install(folder):
    key = (platform.system(), platform.machine().lower())
    if key not in DOWNLOADS:
        raise PublicationError('Unsupported scanner platform; supply a verified Gitleaks executable')
    suffix, expected = DOWNLOADS[key]
    url = f'https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{suffix}'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(32 * 1024 ** 2 + 1)
    if hashlib.sha256(data).hexdigest() != expected:
        raise PublicationError('Scanner download checksum mismatch')
    name = 'gitleaks.exe' if key[0] == 'Windows' else 'gitleaks'
    if suffix.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            executable = archive.read(name)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            executable = archive.extractfile(name).read()
    folder = Path(folder).absolute(); no_links(folder / name)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name; target.write_bytes(executable)
    target.chmod(0o700)
    return target


def inspect_archive(archive, budget, depth=1):
    if depth > MAX_DEPTH:
        raise PublicationError('Archive nesting exceeds the publication scan limit')
    seen = set()
    for entry in archive.infolist():
        name = entry.orig_filename.rstrip('/')
        p = PurePosixPath(name)
        if (not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name
                or str(p) != name or name.casefold() in seen
                or stat.S_ISLNK(entry.external_attr >> 16) or private_path(name)):
            raise PublicationError('Private filename, link, duplicate or unsafe archive path')
        seen.add(name.casefold())
        budget[0] += 1; budget[1] += entry.file_size
        if budget[0] > MAX_MEMBERS or budget[1] > MAX_BYTES:
            raise PublicationError('Publication exceeds archive inspection limits')
        if name.lower().endswith('.zip'):
            if entry.file_size > 1024 ** 3:
                raise PublicationError('Nested ZIP exceeds the inspection limit')
            with zipfile.ZipFile(io.BytesIO(archive.read(entry))) as nested:
                inspect_archive(nested, budget, depth + 1)


def inspect_sources(roots):
    budget = [0, 0]
    files = []
    for root in roots:
        root = Path(root).absolute(); no_links(root)
        if not root.exists():
            raise PublicationError('Publication input is missing')
        # Walk explicitly to reject links before descending into a directory.
        pending = [root]
        while pending:
            path = pending.pop(); no_links(path)
            if private_path(path.relative_to(root).as_posix() if path != root else path.name):
                raise PublicationError('Publication input contains a private filename')
            if path.is_dir():
                pending.extend(path.iterdir())
            elif path.is_file():
                files.append(path)
                if path.suffix.lower() == '.zip':
                    with zipfile.ZipFile(path) as archive:
                        inspect_archive(archive, budget)
            else:
                raise PublicationError('Publication input is not an ordinary file')
    if not files:
        raise PublicationError('Publication input contains no files')
    return files


def checksum_finding(finding):
    """Only suppress a checksum whose exact matched value and payload are verified."""
    if finding.get('RuleID') != 'generic-api-key' or finding.get('StartLine') != finding.get('EndLine'):
        return False
    chain = finding.get('File', '').split('!')
    member = chain[-1] if len(chain) > 1 else Path(chain[0]).name
    if len(chain) > MAX_DEPTH + 1 or member not in {'manifest.json', 'release-manifest.json'}:
        return False
    archive = None
    try:
        if len(chain) > 1:
            archive = zipfile.ZipFile(chain[0])
            for nested in chain[1:-1]:
                data = archive.read(nested); archive.close()
                archive = zipfile.ZipFile(io.BytesIO(data))
            raw = archive.read(member).decode('utf-8')
        else:
            source = Path(chain[0]); no_links(source)
            raw = source.read_text(encoding='utf-8')
        line = raw.splitlines()[finding['StartLine'] - 1]
        fragment = json.loads('{' + line.strip().rstrip(',') + '}')
        if len(fragment) != 1:
            return False
        path, value = next(iter(fragment.items()))
        if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
            return False
        # Check the entire matched span, so a secret in a filename cannot hide
        # behind an unrelated valid digest on the same line.
        # Columns differ across Gitleaks archive readers. Reconstruct its fully
        # redacted match and require one exact occurrence ending at this value.
        match = finding['Match']
        if finding.get('Secret') != 'REDACTED' or match.count('REDACTED') != 1:
            return False
        actual_match = match.replace('REDACTED', value)
        if (not actual_match.endswith(value + '"') or line.count(actual_match) != 1
                or not line.rstrip().rstrip(',').endswith(actual_match)):
            return False
        document = json.loads(raw)
        if document['files'].get(path) != value:
            return False
        p = PurePosixPath(path)
        if p.is_absolute() or '..' in p.parts or '\\' in path or ':' in path or str(p) != path:
            return False
        payload = path if member == 'release-manifest.json' else 'app/' + path
        if archive is not None:
            data = archive.read(payload)
        else:
            target = Path(chain[0]).parent / payload; no_links(target)
            data = target.read_bytes()
        return hashlib.sha256(data).hexdigest() == value
    except (OSError, ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile):
        return False
    finally:
        if archive is not None:
            archive.close()


def scan(roots, executable):
    files = inspect_sources(roots)
    findings = []
    with tempfile.TemporaryDirectory(prefix='publication-scan-') as temporary:
        config = Path(temporary) / 'rules.toml'
        config.write_text('[extend]\nuseDefault = true\n', encoding='utf-8')
        ignore = Path(temporary) / '.gitleaksignore'
        ignore.write_text('', encoding='utf-8')
        for index, root in enumerate(roots):
            report = Path(temporary) / f'{index}.json'
            command = [str(executable), 'dir', str(Path(root).absolute()), '--no-banner', '--redact=100',
                       '--log-level', 'error', '--report-format', 'json', '--report-path', str(report),
                       '--config', str(config), '--gitleaks-ignore-path', str(ignore), '--ignore-gitleaks-allow',
                       '--max-decode-depth', '3', '--max-archive-depth', str(MAX_DEPTH)]
            result = subprocess.run(command, capture_output=True, timeout=900)
            if result.returncode not in {0, 1} or not report.is_file():
                raise PublicationError('Secret scanner failed; no artifacts may be uploaded')
            rows = json.loads(report.read_text(encoding='utf-8'))
            if not isinstance(rows, list) or (result.returncode == 1 and not rows):
                raise PublicationError('Secret scanner returned an invalid report')
            findings.extend(rows)
    unresolved = [f for f in findings if not checksum_finding(f)]
    if unresolved:
        # Paths and rule IDs only. Never echo matches, secrets or scanner stderr.
        for finding in unresolved:
            print(json.dumps({k: finding.get(k) for k in ('RuleID', 'File', 'StartLine')}))
        raise PublicationError('Potential secrets remain; upload blocked')
    return {'status': 'passed', 'input_files': len(files), 'verified_checksum_flags': len(findings)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--gitleaks', type=Path, help='Previously verified executable (otherwise install a pinned release)')
    args = parser.parse_args()
    try:
        # Inspect first, so private filenames never require a scanner download.
        inspect_sources(args.paths)
        if args.gitleaks:
            result = scan(args.paths, args.gitleaks.absolute())
        else:
            with tempfile.TemporaryDirectory(prefix='verified-gitleaks-') as folder:
                result = scan(args.paths, install(folder))
        print(json.dumps(result))
    except PublicationError as error:
        raise SystemExit('Publication security check failed: ' + str(error) + '. Upload blocked.') from None
    except Exception:
        # Unexpected provider/tool errors can contain secrets, so withhold raw details.
        raise SystemExit('Publication security check failed. Review inputs privately; nothing may be uploaded.') from None


if __name__ == '__main__':
    main()
