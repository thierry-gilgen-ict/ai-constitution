"""Opt-in controller peers. Independent TLS identity, credentials and read scopes."""
import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import tempfile
import time
from contextlib import nullcontext
from scripts import constitution as kit, releases
from scripts.catalog import digest, json_bytes
from . import plans, toolkits, monitoring
from .studio import Studio
from .transport import request, validate_url

DEFAULT={'schema':1,'peers':{},'grants':{},'pairings':{}}
SCOPES={'library','inventory','accounts'}


def overview(root):
    data=plans.read(root,'fleet.json',DEFAULT)
    return {'peers':[{k:v for k,v in p.items() if k not in ('token','fingerprint','base')} for p in data['peers'].values()],
            'grants':[{k:v for k,v in p.items() if k!='token_hash'} for p in data['grants'].values()],
            'listener':plans.read(root,'fleet-listener.json',{'schema':1}),
            'note':'Controller pairing is separate from inference workers. Library pulls are staged locally for review. Inventory and account sharing require explicit separate scopes; credentials, configuration files and conversations are never shared.'}


def pairing(root,body):
    scopes=body.get('scopes',['library']);name=monitoring.text(body.get('name','Trusted controller'),80)
    if not isinstance(scopes,list) or not scopes or set(scopes)-SCOPES:raise ValueError('Choose library, inventory or accounts scopes')
    listener=plans.read(root,'fleet-listener.json',{'schema':1})
    if not listener.get('url') or time.time()-listener.get('heartbeat',0)>120:raise ValueError('Start the controller with --fleet-address before creating a pairing code')
    nonce=secrets.token_urlsafe(32);key=hashlib.sha256(nonce.encode()).hexdigest();expires=time.time()+300
    with kit.state_lock(Path(root)/'fleet-lock'):
        value=plans.read(root,'fleet.json',DEFAULT);value['pairings']={k:v for k,v in value['pairings'].items() if v['expires']>time.time()}
        if len(value['pairings'])>=10:raise ValueError('Too many outstanding pairing invitations')
        value['pairings'][key]={'name':name,'scopes':sorted(set(scopes)),'expires':expires};plans.write(root,'fleet.json',value)
    code=base64.urlsafe_b64encode(json_bytes({'schema':1,'role':'controller','url':listener['url'],'fingerprint':listener['fingerprint'],'nonce':nonce})).decode()
    return {'code':code,'expires_at':expires,'note':'Private one-use invitation, valid five minutes. Share only with the intended controller.'}


def redeem(root,body):
    nonce=body.get('nonce','')
    if not isinstance(nonce,str) or len(nonce)>100:raise ValueError('Invalid controller invitation')
    with kit.state_lock(Path(root)/'fleet-lock'):
        value=plans.read(root,'fleet.json',DEFAULT);key=hashlib.sha256(nonce.encode()).hexdigest();invite=value['pairings'].get(key)
        if not invite or invite['expires']<time.time():raise ValueError('Controller invitation expired or already used')
        if len(value['grants'])>=50:raise ValueError('Controller grant limit reached')
        identity=secrets.token_hex(6);token=secrets.token_urlsafe(48)
        value['grants'][identity]={'id':identity,'name':invite['name'],'scopes':invite['scopes'],'token_hash':hashlib.sha256(token.encode()).hexdigest(),'created_at':time.time()}
        del value['pairings'][key];plans.write(root,'fleet.json',value)
    return {'id':identity,'token':token,'scopes':invite['scopes'],'protocol':1}


def principal(root,token):
    hashed=hashlib.sha256(token.encode()).hexdigest()
    return next((g for g in plans.read(root,'fleet.json',DEFAULT)['grants'].values() if hmac.compare_digest(hashed,g['token_hash'])),None)


def connect_peer(root,body):
    try:
        if not isinstance(body.get('code'),str) or len(body['code'])>5000:raise ValueError()
        record=json.loads(base64.urlsafe_b64decode(body['code']))
        if record.get('schema')!=1 or record.get('role')!='controller' or not re.fullmatch('[a-f0-9]{64}',record.get('fingerprint','')):raise ValueError()
        parsed=validate_url(record['url'],worker=True)
        if parsed.scheme!='https':raise ValueError()
    except (ValueError,KeyError,TypeError):raise ValueError('Use a controller pairing code from the other computer, not a worker code') from None
    endpoint={'kind':'worker','url':record['url'],'fingerprint':record['fingerprint']}
    result=request(endpoint,'/fleet/pair',{'nonce':record['nonce']},timeout=10)
    if result.get('protocol')!=1 or not isinstance(result.get('scopes'),list) or set(result['scopes'])-SCOPES or not re.fullmatch('[a-f0-9]{12}',result.get('id','')) or not isinstance(result.get('token'),str) or not 32<=len(result['token'])<=200:raise ValueError('Unsupported controller pairing response')
    with kit.state_lock(Path(root)/'fleet-lock'):
        value=plans.read(root,'fleet.json',DEFAULT)
        if len(value['peers'])>=50:raise ValueError('Controller peer limit reached; revoke the remote grant if local pairing could not be saved')
        value['peers'][result['id']]={**endpoint,**result,'name':monitoring.text(body.get('name','Controller'),80),'base':{},'status':'paired','paired_at':time.time()};plans.write(root,'fleet.json',value)
    return {'status':'paired','id':result['id'],'note':'Read scopes paired. Pull and review its library; no local project was changed.'}


def revoke(root,body):
    with kit.state_lock(Path(root)/'fleet-lock'):
        value=plans.read(root,'fleet.json',DEFAULT)
        if body.get('id') not in value['grants']:raise ValueError('Choose an incoming controller grant')
        del value['grants'][body['id']];plans.write(root,'fleet.json',value)
    return {'status':'revoked'}


def portable(root,*,_locked=False):
    studio=Studio(root)
    with (nullcontext() if _locked else kit.state_lock(studio.guard)):
        studio.initialize();files={}
        for name in releases.files(studio.draft):
            if shareable(studio,name):
                path=kit.safe_path(studio.draft,name);plans.fingerprint(path);files[name]=path.read_text(encoding='utf-8')
        kits=plans.read(root,'toolkits.json',toolkits.DEFAULT)['kits']
    value={'schema':1,'files':files,'toolkits':kits}
    if len(json_bytes(value))>4*1024*1024:raise ValueError('Shared library exceeds portable limit')
    return value


def shareable(studio,name):
    return studio.editable(name) and not name.startswith(('checks/','tests/')) and name not in ('AGENTS.md','registry/imported.json','registry/catalog.json','package.json','package-lock.json')


def snapshot(control,grant):
    value={'schema':1,'observed_at':time.time()}
    if 'library' in grant['scopes']:value['library']=portable(control.root)
    if 'inventory' in grant['scopes']:
        from .workspace import overview as projects
        value['projects']=[{'name':Path(p['project']).name,'id':digest(p['project'].encode())[:12],'status':p['status'],'architecture':p.get('architecture')} for p in projects(control)['projects']]
        value['machines']={k:{'name':v['name'],'kind':v['kind']} for k,v in control.status()['nodes'].items()}
    if 'accounts' in grant['scopes']:
        data=monitoring.load(control.root)
        value['accounts']=[{k:a.get(k) for k in ('label','login','application','provider','plan','subscription_key','usage')} for a in data['accounts'].values()]
    return value


def validate_bundle(bundle,studio):
    if not isinstance(bundle,dict) or set(bundle)!={'schema','files','toolkits'} or bundle.get('schema')!=1 or len(json_bytes(bundle))>4*1024*1024:raise ValueError('Unsupported portable library')
    if not isinstance(bundle['files'],dict) or len(bundle['files'])>1000 or not isinstance(bundle['toolkits'],dict) or len(bundle['toolkits'])>100:raise ValueError('Portable library exceeds limits')
    for name,text in bundle['files'].items():
        kit.safe_path(studio.draft,name)
        if not shareable(studio,name) or not isinstance(text,str) or len(text.encode())>2*1024*1024:raise ValueError('Portable library contains an unsupported asset')
        from scripts.architecture import clean_text
        clean_text(text)
    for name,value in bundle['toolkits'].items():
        if toolkits.validate(value)['id']!=name:raise ValueError('Toolkit identity mismatch')
    return bundle


def pull(control,body,progress=lambda _:None):
    identity=body.get('id');data=plans.read(control.root,'fleet.json',DEFAULT);peer=data['peers'].get(identity)
    if not peer:raise ValueError('Choose a controller peer')
    progress('Fetching scoped controller metadata through pinned TLS')
    observed=request(peer,'/fleet/snapshot',timeout=20)
    if not isinstance(observed,dict) or observed.get('schema')!=1 or len(json_bytes(observed))>4*1024*1024:raise ValueError('Unsupported peer snapshot')
    if 'library' in observed:validate_bundle(observed['library'],Studio(control.root))
    with kit.state_lock(control.root/'fleet-lock'):
        data=plans.read(control.root,'fleet.json',DEFAULT)
        if identity not in data['peers']:raise ValueError('Peer was removed during fetch')
        plans.write(control.root,'peer-'+identity+'.json',{'schema':1,'snapshot':observed,'received_at':time.time()})
        data['peers'][identity].update(status='fetched',last_success=time.time());plans.write(control.root,'fleet.json',data)
    return {'status':'fetched','note':'Snapshot saved privately. Preview its library changes before applying; offline fetches never overwrite the last successful snapshot.'}


def stage_preview(root,body):
    identity=body.get('id');data=plans.read(root,'fleet.json',DEFAULT);peer=data['peers'].get(identity)
    if not peer:raise ValueError('Choose a paired controller')
    cached=plans.read(root,'peer-'+identity+'.json',{'schema':1});bundle=cached.get('snapshot',{}).get('library')
    studio=Studio(root);studio.initialize();bundle=validate_bundle(bundle,studio);changes=[]
    for name,text in bundle['files'].items():
        before=plans.fingerprint(kit.safe_path(studio.draft,name));after=digest(text.encode());base=peer['base'].get(name)
        status='current' if before==after else 'ready' if before==base or name not in peer['base'] and before is None else 'conflict'
        changes.append({'path':name,'before':before,'after':after,'status':status})
    for name,toolkit in bundle['toolkits'].items():
        local=toolkits.overview(root)['kits'].get(name);before=digest(json_bytes(local)) if local else None;after=digest(json_bytes(toolkit));base=peer['base'].get('toolkit:'+name)
        changes.append({'path':'toolkit:'+name,'before':before,'after':after,'status':'current' if before==after else 'ready' if before==base or before is None else 'conflict'})
    return plans.seal({'schema':1,'id':identity,'received_at':cached['received_at'],'changes':changes,'bundle_hash':digest(json_bytes(bundle)),
                       'note':'First pull reports existing differing files as conflicts. Resolve deliberately; subsequent pulls use three-way fingerprints. Nothing is pushed back automatically.'})


def stage_apply(root,body,progress=lambda _:None):
    studio=Studio(root)
    with kit.state_lock(root/'fleet-lock'),kit.state_lock(studio.guard),kit.state_lock(root/'toolkit-lock'):
        value=stage_preview(root,body);plans.verify(value,body.get('plan'))
        if any(v['status']=='conflict' for v in value['changes']):raise ValueError('Resolve peer conflicts before staging; local work is preserved')
        bundle=plans.read(root,'peer-'+body['id']+'.json',{'schema':1})['snapshot']['library'];writes={}
        # Validate the entire resulting library in a disposable copy, including
        # regenerated adapters, before touching the editable draft.
        with tempfile.TemporaryDirectory(prefix='constitution-peer-') as folder:
            target=Path(folder).resolve(strict=True)
            for name,data in studio.payload().items():kit.atomic_bytes(kit.safe_path(target,name),data)
            for name,text in bundle['files'].items():kit.atomic_bytes(kit.safe_path(target,name),text.encode())
            kit.validate(target);kit.build(target)
            for name in releases.files(target):
                data=kit.safe_path(target,name).read_bytes()
                if kit.safe_path(studio.draft,name).read_bytes()!=data:writes[kit.safe_path(studio.draft,name)]=data
        db=plans.read(root,'toolkits.json',toolkits.DEFAULT);db['kits'].update(bundle['toolkits']);writes[root/'workspace/toolkits.json']=json_bytes(db)
        peers=plans.read(root,'fleet.json',DEFAULT);peers['peers'][body['id']]['base']={r['path']:r['after'] for r in value['changes']};writes[root/'workspace/fleet.json']=json_bytes(peers)
        result=kit.transaction(studio.history,writes)
    return {**result,'note':'Peer assets staged and validated. Use workspace rollout preview to update enrolled projects. No remote account or path is adopted.'}


def resolve(root,body):
    """Explicitly choose remote content by pinning the current local base first."""
    identity=body.get('id');value=stage_preview(root,body);plans.verify(value,body.get('plan'))
    selected=body.get('paths',[])
    if not isinstance(selected,list) or any(p not in [r['path'] for r in value['changes'] if r['status']=='conflict'] for p in selected):raise ValueError('Choose conflicted paths to replace with remote content')
    with kit.state_lock(Path(root)/'fleet-lock'):
        data=plans.read(root,'fleet.json',DEFAULT)
        for r in value['changes']:
            if r['path'] in selected:data['peers'][identity]['base'][r['path']]=r['before']
        plans.write(root,'fleet.json',data)
    return {'status':'reviewed','note':'Preview again before replacing the selected draft assets. Project files remain unchanged.'}
