"""Assemble and verify a release directory before publication."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import constitution as kit, releases
from local_control.distribution import inspect_archive
from scripts.paths import no_links


def assemble(root, output):
    kit.validate(root);kit.build(root,check=True)
    no_links(output)
    output.mkdir(parents=True,exist_ok=True)
    # Only the exact native inputs belong in this staging directory. Refuse
    # leftovers rather than signing or uploading arbitrary files with a wildcard.
    expected = {f'ai-constitution-worker-{platform}{suffix}'
                for platform in ('windows-amd64', 'darwin-arm64', 'linux-x86_64')
                for suffix in ('.zip', '.zip.sha256', '.cdx.json')}
    if {p.name for p in output.iterdir()} != expected:
        raise ValueError('Release staging must contain only the three native ZIPs, checksums and SBOMs; use a fresh directory')
    for path in output.iterdir():
        no_links(path)
        if not path.is_file(): raise ValueError('Release staging inputs must be ordinary files')
    result=releases.export(root,output/'ai-constitution-release.zip')
    (output/'ai-constitution-release.sha256').write_text(result['sha256']+'  ai-constitution-release.zip\n',encoding='utf-8')
    releases.unpack((output/'ai-constitution-release.zip').read_bytes(),result['sha256'])
    kit.export_bundle(root,output/'grok-bot.zip')
    native=list(output.glob('ai-constitution-worker-*.zip'))
    if len(native) != 3: raise ValueError('Assemble exactly the three supported native platform builds')
    systems=set()
    for path in native:
        checksum=path.with_suffix('.zip.sha256')
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if not checksum.exists() or checksum.read_text().split()[0] != actual: raise ValueError('Native package checksum failed')
        manifest=inspect_archive(path)
        if manifest.get('version') != (root/'VERSION').read_text().strip(): raise ValueError('Native package version differs from the toolkit')
        systems.add(manifest['platform'])
    if systems != {'Windows','Darwin','Linux'}: raise ValueError('Missing supported platform build')
    sums=[]
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != 'SHA256SUMS.txt': sums.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
    (output/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    return {'version':(root/'VERSION').read_text().strip(),'verified_files':len(sums)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(assemble(Path(__file__).resolve().parents[1],args.output)))
