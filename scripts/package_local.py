#!/usr/bin/env python3
"""Build an unsigned preview on its target OS, in an isolated build environment."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.absolute()
    output.mkdir(parents=True,exist_ok=True)
    inventory=[]
    licenses=output/'licenses'; licenses.mkdir(exist_ok=True)
    for dist in importlib.metadata.distributions():
        name=dist.metadata['Name']
        inventory.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression',dist.metadata.get('License','See distribution'))})
        for file in dist.files or []:
            if '.dist-info' in str(file) and ('license' in file.name.lower() or 'copying' in file.name.lower()):
                (licenses/(name+'-'+file.name)).write_bytes(dist.locate_file(file).read_bytes())
    (output/'dependencies.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--noupx','--name','ai-constitution-local',
             '--distpath',str(output/'app'),'--workpath',str(output/'build'),'--specpath',str(output),
             '--paths',str(ROOT),'--collect-submodules','local_control','--collect-submodules','pystray',
             '--hidden-import','cryptography','--add-data',str(ROOT/'local_control/web')+':local_control/web']
    if platform.system()=='Windows':command+=['--hide-console','hide-early']
    command+=[str(ROOT/'packaging/entrypoint.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    executable=output/'app/ai-constitution-local'/('ai-constitution-local.exe' if platform.system()=='Windows' else 'ai-constitution-local')
    smoke = subprocess.run([str(executable),'--help'],capture_output=True,text=True)
    if smoke.returncode:
        raise RuntimeError('Packaged entry point failed: ' + smoke.stderr[-4000:])
    checks={p.relative_to(output/'app').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (output/'app').rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps({'schema':1,'platform':platform.system(),'architecture':platform.machine(),
        'signing':'unsigned preview; no publisher identity certification','files':checks},indent=2),encoding='utf-8')
    print(json.dumps({'status':'built','executable':str(executable),'files':len(checks),'signing':'unsigned-preview'}))


if __name__=='__main__':main()
