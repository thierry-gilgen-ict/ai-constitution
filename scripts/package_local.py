#!/usr/bin/env python3
"""Build a portable preview on its target OS, in an isolated build environment."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def prepare_output(output):
    if __package__:
        from .paths import no_links
        from .releases import DIRS
    else:
        from paths import no_links
        from releases import DIRS
    output = Path(output).absolute()
    no_links(output)
    output = output.resolve()
    if output == ROOT or any(output.is_relative_to(ROOT / name) for name in DIRS):
        raise ValueError('Build output must be outside public source folders')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Build output must be empty; choose a fresh directory. Existing files were preserved.')
    output.mkdir(parents=True, exist_ok=True)
    return output


def application_files(root):
    """Resolve PyInstaller's internal POSIX aliases into a closed regular-file ZIP."""
    root = Path(root).resolve()
    result = {}
    pending = [(root, frozenset())]
    while pending:
        path, parents = pending.pop()
        target = path.resolve(strict=True)
        if not target.is_relative_to(root):
            raise ValueError('Native application link escapes the build directory')
        if target.is_dir():
            if target in parents:
                raise ValueError('Native application directory link contains a cycle')
            pending.extend((child, parents | {target}) for child in path.iterdir())
        elif target.is_file():
            result[path.relative_to(root).as_posix()] = path
        else:
            raise ValueError('Native application contains a non-file entry')
        if len(result) + len(pending) > 10000:
            raise ValueError('Native application exceeds file limits')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=prepare_output(args.output)
    inventory=[]
    licenses=output/'licenses'; licenses.mkdir(exist_ok=True)
    for dist in importlib.metadata.distributions():
        name=dist.metadata['Name']
        inventory.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression',dist.metadata.get('License','See distribution'))})
        for file in dist.files or []:
            if '.dist-info' in str(file) and ('license' in file.name.lower() or 'copying' in file.name.lower()):
                (licenses/(name+'-'+file.name)).write_bytes(dist.locate_file(file).read_bytes())
    (output/'dependencies.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    from releases import public_files
    library = output / 'library'
    for name, data in public_files(ROOT).items():
        path = library / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--noupx','--name','ai-constitution-local',
             '--distpath',str(output/'app'),'--workpath',str(output/'build'),'--specpath',str(output),
             '--paths',str(library),'--collect-submodules','local_control','--collect-submodules','pystray',
             '--hidden-import','cryptography','--add-data',str(library/'local_control/web')+':local_control/web',
             '--add-data',str(library)+':library']
    if platform.system()=='Windows':command+=['--hide-console','hide-early']
    command+=[str(library/'packaging/entrypoint.py')]
    subprocess.run(command,cwd=library,check=True)
    executable=output/'app/ai-constitution-local'/('ai-constitution-local.exe' if platform.system()=='Windows' else 'ai-constitution-local')
    from sign_package import sign, notarize
    signing = sign(output/'app', executable)
    smoke = subprocess.run([str(executable),'--help'],capture_output=True,text=True)
    if smoke.returncode:
        raise RuntimeError('Packaged entry point failed: ' + smoke.stderr[-4000:])
    from smoke_local_package import smoke as check_package
    smoke_result = check_package(executable)
    application = application_files(output/'app')
    checks={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in application.items()}
    (output/'manifest.json').write_text(json.dumps({'schema':1,'version':(ROOT/'VERSION').read_text().strip(),'platform':platform.system(),'architecture':platform.machine(),
        'signing':signing,'files':checks},indent=2),encoding='utf-8')
    public = output / 'public'; public.mkdir()
    archive = public / ('ai-constitution-worker-' + platform.system().lower() + '-' + platform.machine().lower() + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name,path in sorted(application.items()): bundle.write(path, 'app/' + name)
        for path in sorted(licenses.rglob('*')):
            if path.is_file(): bundle.write(path, path.relative_to(output).as_posix())
        for name in ('manifest.json','dependencies.json'): bundle.write(output / name, name)
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md'): bundle.write(ROOT / name, name)
        bundle.writestr('README.txt', 'AI Constitution portable worker preview. See manifest.json for publisher signing status. Extract the complete archive.\nSetup and upgrade instructions are in the controller dashboard: Set up a worker.\nKeep private worker state outside this package. Never delete it during upgrades.\n')
    # Exercise the distributed bytes too; checking the build tree alone would
    # miss alias files or executable permissions lost during ZIP construction.
    with tempfile.TemporaryDirectory(prefix='packaged-worker-smoke-') as folder:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(folder)
            for entry in bundle.infolist():
                (Path(folder)/entry.filename).chmod((entry.external_attr >> 16) & 0o777)
        packaged = Path(folder)/'app/ai-constitution-local'/executable.name
        check_package(packaged)
    notarization = notarize(archive)
    sbom = {'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'metadata':{'component':{'type':'application','name':'ai-constitution','version':(ROOT/'VERSION').read_text().strip()}},
        'components':[{'type':'library','name':v['name'],'version':v['version'],'purl':'pkg:pypi/'+v['name'].lower()+'@'+v['version']} for v in inventory]}
    archive.with_suffix('.cdx.json').write_text(json.dumps(sbom,indent=2),encoding='utf-8')
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps({'status':'built','executable':str(executable),'archive':str(archive),'files':len(checks),'signing':signing,'notarization':notarization,'smoke':smoke_result}))


if __name__=='__main__':main()
