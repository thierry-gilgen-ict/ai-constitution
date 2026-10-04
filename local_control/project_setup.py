"""Reviewed project preparation with private environment references and durable checkpoints."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit
import http.client

from scripts import constitution as kit, architecture
from scripts.catalog import digest, json_bytes
from . import plans, project_vault, processes

INPUTS = ('package.json','package-lock.json','requirements.txt','pyproject.toml','uv.lock',
          'compose.yaml','compose.yml','docker-compose.yml')
KINDS = {'venv','python-install','npm-install','compose-up','command','http'}
BINARIES = {'python','node','npm','docker','git','uv','pytest','ruff','cargo','go','dotnet','java','mvn'}


def validate(recipe):
    if not isinstance(recipe, dict) or set(recipe) - {'schema','id','name','steps','environment'} or recipe.get('schema') != 1:
        raise ValueError('Unsupported preparation recipe')
    architecture.identifier(recipe.get('id'))
    if not isinstance(recipe.get('name'),str) or not 1 <= len(recipe['name']) <= 120:
        raise ValueError('Give the recipe a short name')
    steps = recipe.get('steps')
    if not isinstance(steps,list) or not 1 <= len(steps) <= 20:
        raise ValueError('Choose one to twenty preparation steps')
    seen = set()
    for step in steps:
        if not isinstance(step,dict) or set(step) - {'id','kind','argv','url','timeout'} or step.get('kind') not in KINDS:
            raise ValueError('Unsupported preparation step')
        identity = architecture.identifier(step.get('id'))
        if identity in seen: raise ValueError('Preparation step identifiers must be unique')
        seen.add(identity)
        timeout = step.get('timeout',300)
        if type(timeout) is not int or not 1 <= timeout <= 1800: raise ValueError('Step timeout must be between 1 and 1800 seconds')
        if step['kind'] == 'command':
            argv = step.get('argv')
            if (not isinstance(argv,list) or not 1 <= len(argv) <= 30 or argv[0] not in BINARIES
                    or any(not isinstance(v,str) or not 1 <= len(v) <= 2000 or any(ord(c)<32 for c in v) for v in argv)):
                raise ValueError('Use a bounded runtime argument list, not a shell command')
        elif 'argv' in step: raise ValueError('Only command steps accept arguments')
        if step['kind'] == 'http':
            parsed = urlsplit(step.get('url',''))
            if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1')
                    or parsed.username or parsed.password or parsed.fragment or parsed.query or not parsed.port):
                raise ValueError('Health checks use an explicit loopback HTTP URL without credentials')
        elif 'url' in step: raise ValueError('Only HTTP health checks accept a URL')
    variables = recipe.get('environment',[])
    if not isinstance(variables,list) or len(variables)>50 or any(not isinstance(v,str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,79}',v) for v in variables):
        raise ValueError('Environment references must be variable names')
    # Child process controls and lookup paths are owned by the runner.
    if any(v in {'PATH','HOME','USERPROFILE','SYSTEMROOT','COMSPEC','PYTHONPATH','NODE_OPTIONS','LD_PRELOAD','DYLD_INSERT_LIBRARIES'} for v in variables):
        raise ValueError('Recipe cannot override runtime process controls')
    architecture.clean_text(json.dumps(recipe))
    return recipe


def recipes(root, name):
    project = plans.project(root,name)
    steps = []
    if (project/'requirements.txt').is_file():
        steps += [{'id':'environment','kind':'venv'},{'id':'dependencies','kind':'python-install'}]
    if (project/'package-lock.json').is_file(): steps.append({'id':'dependencies','kind':'npm-install'})
    compose = next((n for n in INPUTS if n.startswith(('compose','docker-compose')) and (project/n).is_file()),None)
    if compose: steps.append({'id':'services','kind':'compose-up'})
    if not steps: steps = [{'id':'runtime','kind':'command','argv':['python','--version']}]
    stored = plans.read(root,'recipes.json',{'schema':1,'projects':{}})['projects'].get(str(project))
    return {'recipe': stored or {'schema':1,'id':'project-preparation','name':'Prepare this project','steps':steps,'environment':[]},
            'step_kinds':sorted(KINDS), 'note':'Review all commands. Project scripts and dependency installers can execute code; captured templates never authorize execution.'}


def save_recipe(root, name, value):
    project=plans.project(root,name); validate(value)
    with kit.state_lock(Path(root)/'workspace-recipe-lock'):
        db=plans.read(root,'recipes.json',{'schema':1,'projects':{}})
        db['projects'][str(project)]=value;plans.write(root,'recipes.json',db)
    return {'status':'saved','project':str(project)}


def environment(root, project, variables):
    values = {name: os.environ[name] for name in variables if os.environ.get(name)}
    references = {}
    for entry in project_vault.read(root)['projects'].values():
        if entry.get('project') != str(project): continue
        folder = Path(entry['folder']); kit.no_links(folder)
        file = folder / '.env'; signature = plans.fingerprint(file)
        if signature is None: continue
        references[str(file)] = signature
        for line in file.read_text(encoding='utf-8').splitlines():
            match = re.fullmatch(r'(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*)',line.strip())
            if match and match[1] in variables and match[2]:
                value = match[2]
                if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"): value=value[1:-1]
                values.setdefault(match[1],value)
    # Presence and digests bind review without returning variable values.
    return values, references


def executable(name, project):
    if name=='python': return [sys.executable]
    if name in ('pytest','ruff'):
        binary = project / '.venv' / ('Scripts' if os.name=='nt' else 'bin') / ('python.exe' if os.name=='nt' else 'python')
        kit.no_links(binary)
        return [str(binary),'-m',name] if binary.is_file() else [sys.executable,'-m',name]
    binary = shutil.which(name)
    if not binary: return None
    if name == 'npm' and os.name == 'nt':
        cli = Path(binary).parent/'node_modules/npm/bin/npm-cli.js'
        node=shutil.which('node');kit.no_links(cli)
        return [node,str(cli)] if node and cli.is_file() else None
    if os.name=='nt' and Path(binary).suffix.lower() in ('.cmd','.bat','.ps1'):
        return None  # No implicit command interpreter.
    return [binary]


def commands(project, recipe):
    result=[]; blockers=[]
    venv = project/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    compose=next((n for n in INPUTS if n.startswith(('compose','docker-compose')) and (project/n).is_file()),None)
    for step in recipe['steps']:
        kind=step['kind']; binary=None; args=[]
        if kind=='venv': binary=executable('python',project);args=['-m','venv','--copies',str(project/'.venv')]
        if kind=='python-install':
            binary=[str(venv)];args=['-m','pip','install','--requirement','requirements.txt','--disable-pip-version-check','--no-input','--no-cache-dir']
            if not (project/'requirements.txt').is_file(): blockers.append('Python installation needs requirements.txt')
            if not venv.is_file() and not any(s['kind']=='venv' for s in recipe['steps'][:recipe['steps'].index(step)]): blockers.append('Create the project environment before installing Python dependencies')
        if kind=='npm-install':
            binary=executable('npm',project);args=['ci','--ignore-scripts','--no-audit','--no-fund']
            if not (project/'package-lock.json').is_file(): blockers.append('Node installation needs package-lock.json')
        if kind=='compose-up':
            binary=executable('docker',project);args=['compose','--project-name','constitution-'+digest(str(project).encode())[:12],'-f',compose or 'compose.yaml','up','-d']
            if not compose: blockers.append('Choose a project with a Compose file')
        if kind=='command':
            name=step['argv'][0];binary=executable(name,project);args=step['argv'][1:]
            if name in ('python','pytest','ruff') and any(s['kind']=='venv' for s in recipe['steps'][:recipe['steps'].index(step)]):
                binary=[str(venv)]+(['-m',name] if name!='python' else [])
        if kind!='http' and not binary: blockers.append('Install the runtime for step '+step['id']+' through its native installer')
        result.append({**step,'command':(binary or [])+args})
    return result, sorted(set(blockers))


def preview(root, body):
    project=plans.project(root,body.get('project'));recipe=validate(body.get('recipe') or recipes(root,str(project))['recipe'])
    steps,blockers=commands(project,recipe)
    values,references=environment(root,project,recipe.get('environment',[]))
    inputs={n:plans.fingerprint(project/n) for n in INPUTS}
    for n in INPUTS:
        if inputs[n] is not None:
            # Reject obvious embedded credentials without returning manifest contents.
            architecture.clean_text((project/n).read_text(encoding='utf-8'))
    missing=[n for n in recipe.get('environment',[]) if not values.get(n)]
    if missing: blockers.append('Missing selected environment references: '+', '.join(missing))
    # Hash selected process values as well as mapped files; no literal values are persisted.
    env_hash={k:digest(v.encode()) for k,v in values.items()}
    return plans.seal({'schema':1,'project':str(project),'recipe':recipe,'steps':steps,'inputs':inputs,
                       'environment_files':references,'environment_fingerprints':env_hash,'blockers':blockers,
                       'note':'Reviewed commands run in this project under your OS account. Dependencies may use the network. Health checks only contact loopback; logs omit child output.'})


def run_command(argv, project, root, variables, timeout):
    if not argv: raise ValueError('Runtime unavailable')
    env = {k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','LANG','LC_ALL')}
    child_home=Path(root)/'workspace/child-home'
    from .permissions import directory
    directory(child_home)
    env.update(HOME=str(child_home),USERPROFILE=str(child_home),PIP_NO_INPUT='1',PYTHONDONTWRITEBYTECODE='1',
               npm_config_cache=str(child_home/'npm-cache'),**variables)
    # Output can include secrets from project scripts, so never store or return it.
    try:
        result=subprocess.run(argv,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired: raise ValueError('Preparation step exceeded its reviewed timeout; inspect actual project state before retrying') from None
    except OSError: raise ValueError('Preparation runtime could not start; inspect installation and permissions') from None
    if result.returncode: raise ValueError('Preparation command failed. Review the project and its native runtime before retrying.')
    return {'exit_code':0}


def health(url, timeout):
    parsed=urlsplit(url);conn=http.client.HTTPConnection(parsed.hostname,parsed.port,timeout=min(timeout,10))
    try:
        conn.request('GET',parsed.path or '/',headers={'Connection':'close'})
        response=conn.getresponse();response.read(65536)
        if not 200<=response.status<300: raise ValueError('Loopback health check failed; redirects are not followed')
        return {'status':response.status}
    finally:conn.close()


def apply(control, body, progress=lambda _: None):
    with kit.state_lock(control.root/'workspace-prepare-lock'):
        value=preview(control.root,body);plans.verify(value,body.get('plan'))
        if value['blockers']:raise ValueError('Resolve preparation prerequisites before starting')
        project=Path(value['project']);identity=body.get('run') or uuid.uuid4().hex[:12]
        journal=plans.Checkpoints(control.root,identity,value['plan'])
        variables,_=environment(control.root,project,value['recipe'].get('environment',[]))
        results=[]
        for step in value['steps']:
            progress('Preparing project: '+step['id'])
            if step['kind']=='venv':
                kit.no_links(project/'.venv')
                # Existing environments are never adopted merely because a folder exists.
                owned=journal.value['steps'].get(step['id'],{})
                if (project/'.venv').exists() and not owned:
                    raise ValueError('A project environment already exists. Remove the create-environment step or inspect it before adoption.')
            perform=(lambda s=step:health(s['url'],s.get('timeout',300))) if step['kind']=='http' else (
                lambda s=step:run_command(s['command'],project,control.root,variables,s.get('timeout',300)))
            def verified(previous, s=step):
                if s['kind']=='http': return health(s['url'],s.get('timeout',300)) == previous
                if s['kind']=='venv':
                    return (project/'.venv/pyvenv.cfg').is_file()
                return True  # Exit evidence; not a claim of ongoing service readiness.
            result=journal.step(step['id'],perform,verified,retry_uncertain=body.get('retry_uncertain') is True)
            results.append({'step':step['id'],**result})
        return {'run':identity,'status':'prepared','steps':results,
                'note':'Reviewed steps completed. Client instruction loading and a model request still need separate verification.'}
