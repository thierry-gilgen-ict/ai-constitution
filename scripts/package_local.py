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
    checks={p.relative_to(output/'app').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (output/'app').rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps({'schema':1,'version':(ROOT/'VERSION').read_text().strip(),'platform':platform.system(),'architecture':platform.machine(),
        'signing':signing,'files':checks},indent=2),encoding='utf-8')
    archive = output / ('ai-constitution-worker-' + platform.system().lower() + '-' + platform.machine().lower() + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for directory in ('app','licenses'):
            for path in sorted((output / directory).rglob('*')):
                if path.is_file(): bundle.write(path, path.relative_to(output).as_posix())
        for name in ('manifest.json','dependencies.json'): bundle.write(output / name, name)
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md'): bundle.write(ROOT / name, name)
        bundle.writestr('README.txt', 'AI Constitution portable worker preview. See manifest.json for publisher signing status. Extract the complete archive.\nSetup and upgrade instructions are in the controller dashboard: Set up a worker.\nKeep private worker state outside this package. Never delete it during upgrades.\n')
    notarization = notarize(archive)
    sbom = {'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'metadata':{'component':{'type':'application','name':'ai-constitution','version':(ROOT/'VERSION').read_text().strip()}},
        'components':[{'type':'library','name':v['name'],'version':v['version'],'purl':'pkg:pypi/'+v['name'].lower()+'@'+v['version']} for v in inventory]}
    archive.with_suffix('.cdx.json').write_text(json.dumps(sbom,indent=2),encoding='utf-8')
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps({'status':'built','executable':str(executable),'archive':str(archive),'files':len(checks),'signing':signing,'notarization':notarization,'smoke':smoke_result}))


if __name__=='__main__':main()
