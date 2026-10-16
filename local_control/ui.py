"""Private presentation state; reads never launch clients or collect accounts."""
import copy
import os
import platform
import shutil
import sys
import time
from pathlib import Path

from scripts import constitution as kit
from scripts.catalog import digest, json_bytes
from . import plans, workspace, locations
from .storage import wait_lock
from .studio import Studio


def preferences(root):
    return plans.read(root, 'ui.json', {'schema': 1, 'favorites': [], 'recent': [], 'onboarding': {}, 'environment': 'production' if getattr(sys, 'frozen', False) else 'development'})


def save_preferences(root, body):
    if not isinstance(body, dict) or set(body) - {'schema', 'favorites', 'recent', 'onboarding', 'environment'} or body.get('schema', 1) != 1:
        raise ValueError('Unsupported interface preferences')
    with wait_lock(Path(root) / 'ui-preferences'):
        value = preferences(root)
        for key in ('favorites', 'recent'):
            if key in body:
                rows = body[key]
                if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(s, str) or len(s) > 160 for s in rows):
                    raise ValueError('Choose at most 100 valid destinations')
                value[key] = list(dict.fromkeys(rows))
        if 'environment' in body:
            if body['environment'] not in ('production', 'development'): raise ValueError('Choose production or development')
            value['environment'] = body['environment']
        if 'onboarding' in body:
            progress = body['onboarding']
            if not isinstance(progress, dict) or set(progress) - {'goal', 'project', 'clients', 'step', 'dismissed', 'worker_platform', 'worker_kind', 'template', 'configuration'}:
                raise ValueError('Invalid onboarding progress')
            if len(json_bytes(progress)) > 8000: raise ValueError('Onboarding progress is too large')
            if progress.get('goal', 'project') not in ('project', 'models', 'worker'): raise ValueError('Choose a setup goal')
            if 'clients' in progress and (not isinstance(progress['clients'], list) or any(c not in ('codex', 'cursor', 'claude-code') for c in progress['clients'])):
                raise ValueError('Choose supported coding applications')
            if 'project' in progress and (not isinstance(progress['project'], str) or len(progress['project']) > 1000): raise ValueError('Invalid project location')
            for choice in ('template','configuration'):
                if choice in progress and (not isinstance(progress[choice],str) or len(progress[choice])>120): raise ValueError('Invalid setup selection')
            if 'step' in progress and (type(progress['step']) is not int or not 0 <= progress['step'] <= 6): raise ValueError('Invalid setup step')
            if 'dismissed' in progress and type(progress['dismissed']) is not bool: raise ValueError('Invalid dismissal setting')
            if 'worker_platform' in progress and progress['worker_platform'] not in ('windows-amd64', 'macos-arm64', 'macos-amd64', 'linux-amd64', 'linux-arm64'): raise ValueError('Choose a supported worker platform')
            if 'worker_kind' in progress and progress['worker_kind'] not in ('source','portable'): raise ValueError('Choose source or portable installation')
            value['onboarding'] = copy.deepcopy(progress)
        plans.write(root, 'ui.json', value)
        return value


def project_id(path):
    # Checkout-specific, stable, opaque; never put a private filesystem path in a URL.
    return digest(os.path.normcase(str(Path(path).absolute())).encode())[:24]


def projects(control):
    result = workspace.overview(control)
    rows = [{**p, 'id': project_id(p['project']), 'name': Path(p['project']).name, 'local': True} for p in result['projects']]
    from .fleet import DEFAULT
    for peer in plans.read(control.root,'fleet.json',DEFAULT)['peers'].values():
        if 'inventory' not in peer.get('scopes',[]): continue
        cached=plans.read(control.root,'peer-'+peer['id']+'.json',{'schema':1})
        for item in cached.get('snapshot',{}).get('projects',[])[:200]:
            if not isinstance(item.get('id'),str) or not isinstance(item.get('name'),str): continue
            identity=digest((peer['id']+':'+item['id']).encode())[:24]
            rows.append({'id':identity,'name':item['name'],'machine':peer['name'],'local':False,
                         'project':'Owner-local checkout; path not shared','status':'Cached remote observation',
                         'observed_at':cached.get('received_at'), 'accounts':[], 'configurations':[],
                         'architecture':item.get('architecture'),'backup':{'configured':False},
                         'route':{'mode':'Owner-local'},'owner_status':item.get('status')})
    return rows


def bootstrap(control):
    from scripts.clients import CLIENTS
    from .updates import current
    return {'schema': 1, 'version': current(), 'ui_protocol': 1,
            'controller': platform.node(), 'preferences': preferences(control.root),
            'launch_kind': 'packaged' if getattr(sys, 'frozen', False) else 'source',
            'clients': [{'id': key, 'name': value['name'], 'detected': bool(shutil.which(value['executable'])),
                         'note': 'Detection on PATH only; native sign-in and loading require separate verification.'} for key, value in CLIENTS.items()]}


def operations(control, body=None):
    body=body or {}
    offset=body.get('offset',0)
    if type(offset) is not int or not 0<=offset<=100000: raise ValueError('Invalid history offset')
    fields=('id','label','operation','status','detail','created_at','updated_at','started_at','finished_at','target','acknowledged')
    # Results can contain large reports; presentation does not copy or expose them.
    with control.lock: jobs=[{k:copy.deepcopy(j[k]) for k in fields if k in j} for j in control.jobs.values()]
    if body.get('project'):
        project=plans.project(control.root,body['project'])
        jobs=[j for j in jobs if j.get('target')==str(project)]
    jobs.sort(key=lambda j:j.get('created_at',0),reverse=True)
    rows=[]
    for job in jobs[offset:offset+100]:
        pending=job['status'] in ('queued','running')
        cancel=job['status']=='queued' or job['status']=='running' and job.get('operation') in ('pull','run_lab','audit_scan_job')
        rows.append({**{k:job.get(k) for k in ('id','label','operation','status','detail','created_at','updated_at','started_at','finished_at','target','acknowledged')},
            'stage':job.get('detail') or 'Stage not recorded',
            'elapsed_seconds':max(0,(job.get('finished_at') or time.time())-(job.get('started_at') or job.get('created_at',time.time()))) if pending or job.get('finished_at') else None,
            'actions':(['cancel'] if cancel else [])+([] if pending else ['inspect'])+(['acknowledge'] if job['status'] in ('failed','interrupted') and not job.get('acknowledged') else []),
            'recovery':'Inspect actual state before retrying interrupted work. No operation is replayed automatically.'})
    return {'schema':1,'jobs':rows,'total':len(jobs),'next':offset+100 if offset+100<len(jobs) else None,
            'retention':'The most recent 50 completed or acknowledged operations are retained, alongside unresolved and active work.'}


def operation_detail(control, identity):
    if not isinstance(identity,str): raise ValueError('Choose an operation ID')
    with control.lock:
        if identity not in control.jobs: raise ValueError('Operation is no longer retained')
    offset=0
    while True:
        page=operations(control,{'offset':offset})
        row=next((j for j in page['jobs'] if j['id']==identity),None)
        if row: return {'schema':1,'operation':row}
        if page['next'] is None: raise ValueError('Operation is no longer retained')
        offset=page['next']


def home(control):
    value = control.status()
    issues=list(value['service_errors'])
    stale=False
    try:
        rows=projects(control)
        control.ui_projects_cache=copy.deepcopy(rows)
    except (OSError,ValueError):
        rows=copy.deepcopy(getattr(control,'ui_projects_cache',[]));stale=True
        issues.append({'service':'Project inventory','message':'Inventory unavailable; any previous observations are stale. Inspect configuration and retry.'})
    return {'schema': 1, 'projects': rows, 'projects_stale':stale, 'preferences': preferences(control.root),
            'issues': issues, 'operations': operations(control)['jobs'],
            'sessions': value['sessions'], 'observed_at': time.time()}


def detail(control, identity):
    row = next((p for p in projects(control) if p['id'] == identity), None)
    if row is None: raise ValueError('Project is unavailable or no longer enrolled')
    cached=plans.read(control.root,'project-inspections.json',{'schema':1,'projects':{}})['projects'].get(identity)
    inspection=cached['inspection'] if cached and row.get('local') else {'evidence':{'client_loading':{'value':'Not checked'}},'findings':[]}
    return {'schema':1,'project':row,'inspection':inspection,'inspected_at':cached.get('observed_at') if cached else None,
            'note':'Retained observation only. Request a fresh inspection to check current instruction files.'}


def inspect_project(control, identity):
    row=next((p for p in projects(control) if p['id']==identity),None)
    if not row or not row['local']: raise ValueError('Inspect this project on its owning computer')
    from .inspector import inspect
    result=inspect(control,row['project'])
    summary={k:result[k] for k in ('evidence','findings','installation','modules','release','effective_sha256')}
    with wait_lock(Path(control.root)/'ui-inspections'):
        record=plans.read(control.root,'project-inspections.json',{'schema':1,'projects':{}})
        record['projects'][identity]={'observed_at':time.time(),'inspection':summary}
        record['projects']=dict(sorted(record['projects'].items(),key=lambda item:item[1]['observed_at'],reverse=True)[:100])
        plans.write(control.root,'project-inspections.json',record)
    return detail(control,identity)


def editor_draft(root, body, save=False, discard=False):
    kind=body.get('kind');context=body.get('context','library')
    if kind not in ('toolkit','preparation'): raise ValueError('Unsupported draft editor')
    if kind=='preparation': context=project_id(plans.project(root,context))
    elif context!='library': raise ValueError('Unsupported toolkit context')
    key=kind+':'+context
    with wait_lock(Path(root)/'ui-editor-drafts'):
        store=plans.read(root,'editor-drafts.json',{'schema':1,'items':{}})
        previous=store['items'].get(key)
        revision=digest(json_bytes(previous)) if previous else None
        if save or discard:
            if body.get('revision')!=revision: raise ValueError('Draft changed in another editor; restore and compare before saving')
        if discard:
            store['items'].pop(key,None); plans.write(root,'editor-drafts.json',store)
            return {'schema':1,'draft':None,'revision':None,'note':'Saved candidate deleted; active configuration is unchanged.'}
        if save:
            value=copy.deepcopy(body.get('document'))
            from . import toolkits,project_setup
            value=(toolkits.validate if kind=='toolkit' else project_setup.validate)(value)
            previous={'document':value,'saved_at':time.time()}
            store['items'][key]=previous
            if len(store['items'])>100: raise ValueError('Editor draft limit reached; remove unused drafts first')
            plans.write(root,'editor-drafts.json',store)
            revision=digest(json_bytes(previous))
        return {'schema':1,'draft':previous,'revision':revision,'note':'Private candidate only; explicit save or reviewed application in the owning workflow is still required.'}


def drafts(root):
    return plans.read(root, 'ui-drafts.json', {'schema': 1, 'files': {}})


def draft_view(root):
    record = drafts(root)
    return {**record, 'files': {name: {**item, 'revision': digest(json_bytes(item))} for name, item in record['files'].items()}}


def draft_save(root, body):
    studio = Studio(root)
    with wait_lock(studio.guard):
        studio.initialize()
        name, content = body.get('path'), body.get('content')
        # Existing validation includes ownership, file allowlists and secret checks.
        studio.file_plan(name, content, body.get('sha256'))
        record = drafts(root)
        previous = record['files'].get(name)
        if body.get('revision') != (digest(json_bytes(previous)) if previous else None):
            raise ValueError('Another editor changed this draft. Reload and compare before saving.')
        record['files'][name] = {'content': content, 'before': body.get('sha256'), 'saved_at': time.time()}
        plans.write(root, 'ui-drafts.json', record)
        return {'schema': 1, 'status': 'draft-saved', 'revision': digest(json_bytes(record['files'][name])), 'note': 'Private draft saved. No active instructions or following projects changed.'}


def draft_plan(studio, record):
    current = studio.payload()
    edits = {}
    for name, item in record['files'].items():
        if not studio.editable(name, len(item['content'].encode())): raise ValueError('Draft target is no longer editable')
        if item['before'] != (digest(current[name]) if name in current else None):
            raise ValueError('Published library changed. Compare and save a fresh draft before publishing.')
        edits[name] = item['content'].encode()
    payload = studio.staged(edits)
    from .studio import difference
    changes = [difference(n, current.get(n), b) for n, b in payload.items() if current.get(n) != b]
    from .synchronization import status
    targets = status(studio.root)
    signature = {'before': {n: digest(b) for n, b in current.items()}, 'drafts': record, 'targets': [{k:p.get(k) for k in ('project','pinned','paused')} for p in targets['projects']], 'enabled': targets['enabled']}
    return {'schema': 1, 'plan': digest(json_bytes(signature)), 'changes': changes,
            'targets': signature['targets'], 'synchronization_enabled': targets['enabled'],
            'scope': 'Shared instruction library and eligible following projects; global client activation is separate',
            'effect': 'The library changes on publication. Existing following projects synchronize only when their policies allow it.',
            'note': 'Publish to the shared library. Following projects synchronize according to existing policies; global client activation remains separate.',
            'verification': 'Validate and rebuild generated files before publishing. Verify instruction loading in a fresh client session.',
            'rollback': 'A transaction snapshot preserves previous library contents; later edits are protected.'}, {studio.file_path(n): b for n, b in payload.items() if current.get(n) != b}


def draft_action(root, operation, body):
    studio = Studio(root)
    with wait_lock(Path(root) / 'sync-operations'), wait_lock(studio.guard), wait_lock(studio.state):
        record = drafts(root)
        if operation == 'discard':
            path = body.get('path')
            if path not in record['files']: raise ValueError('Choose an existing draft')
            if body.get('sha256') != digest(json_bytes(record['files'][path])): raise ValueError('Draft changed; reload before discarding')
            del record['files'][path]; plans.write(root, 'ui-drafts.json', record)
            return {'status': 'discarded'}
        preview, writes = draft_plan(studio, record)
        if operation == 'preview': return preview
        if operation != 'publish' or not record['files']: raise ValueError('Save a draft before publishing')
        plans.verify(preview, body.get('plan'))
        from . import template_versions
        import json
        for name, item in record['files'].items():
            if name.startswith('templates/architectures/') and name.endswith('.json'):
                previous=studio.file_path(name)
                if previous.exists(): template_versions.archive(studio,kit.read_json(previous))
                template_versions.archive(studio,json.loads(item['content']))
        # Commit candidate removal and library writes together, including interruption recovery.
        writes[Path(root) / 'workspace/ui-drafts.json'] = json_bytes({'schema': 1, 'files': {}})
        return {'schema':1, **kit.transaction(studio.history, writes), 'note': preview['note']}


def dispatch(control, operation, body=None):
    body = body or {}
    if not isinstance(body,dict) or body.get('schema',1)!=1: raise ValueError('Unsupported interface request schema')
    if operation == 'bootstrap': return bootstrap(control)
    if operation == 'home': return home(control)
    if operation == 'projects': return {'schema': 1, 'projects': projects(control)}
    if operation == 'project': return detail(control, body.get('id'))
    if operation == 'preferences': return save_preferences(control.root, body)
    if operation == 'operations': return operations(control,body)
    if operation == 'project-operations': return operations(control,body)
    if operation == 'operation': return operation_detail(control,body.get('id'))
    if operation == 'inspect-project': return inspect_project(control,body.get('id'))
    if operation in ('editor-draft','editor-save','editor-discard'): return editor_draft(control.root,body,operation=='editor-save',operation=='editor-discard')
    if operation == 'drafts': return draft_view(control.root)
    if operation == 'draft-save': return draft_save(control.root, body)
    if operation.startswith('draft-'): return draft_action(control.root, operation[6:], body)
    raise ValueError('Unknown interface operation')
