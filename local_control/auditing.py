"""Scoped constitution health, proposals and durable correction receipts."""
import copy
import difflib
import json
from pathlib import Path
import re
import time
import uuid
from scripts import clients
from scripts import audit, constitution as kit, releases
from scripts.catalog import digest, json_bytes
from . import locations, synchronization
from .storage import atomic, wait_lock
from .studio import bundled_source
from .audit_store import Store

CORRECTIONS={'restore-missing','managed-update','generated-refresh','reference-migration'}
PERMISSIONS={'scan','report','preview','apply','review','excerpts'}
DEFAULT={'schema':1,'scope':{},'mode':'notify','corrections':[],'approved_source':None,
         'schedule':{'enabled':False,'hours':24,'changes':False,'paused':False,'window_start':None,'window_end':None},
         'semantic':{'enabled':False,'client':'codex','profile':None,'execution':'handoff','hours':168,'minutes':10,'max_projects':3},
         'notifications':True,'native_notifications':False,'retention_days':90,'grants':{},'overrides':{},'mcp_projects':[]}


def settings(root):
    for parent in (Path(root),*Path(root).parents):
        if (parent/'.git').exists():raise ValueError('Private audit state must stay outside Git repositories')
    path=Path(root)/'audit-settings.json';kit.no_links(path)
    value=kit.read_json(path) if path.exists() else copy.deepcopy(DEFAULT)
    if value.get('schema')!=1:raise ValueError('Unknown audit settings schema')
    return value


def source(root):
    draft=locations.folder(root,'studio')/'library'
    return draft if (draft/'VERSION').is_file() else bundled_source()


def source_signature(root):
    base=source(root);kit.validate(base);kit.build(base,check=True)
    return digest(json_bytes(releases.manifest(releases.files(base))))


def configure(root, body):
    allowed={'scope','mode','corrections','approve_source','schedule','semantic','notifications','native_notifications','retention_days','target','mcp_projects'}
    if not isinstance(body,dict) or set(body)-allowed:raise ValueError('Unknown health setting')
    with wait_lock(Path(root)/'audit-policy'):
        value=settings(root)
        if body.get('target'):
            identity=body['target'];db=kit.state_load(locations.folder(root,'constitution_state'))
            if not any(audit.target_id(t)==identity for t in db['targets'].values()):raise ValueError('Choose an enrolled policy target')
            if set(body)-{'target','mode','corrections'}:raise ValueError('Target policies accept mode and correction types')
            mode=body.get('mode','notify');types=body.get('corrections',[])
            if mode not in ('notify','propose','automatic') or not isinstance(types,list) or set(types)-CORRECTIONS:raise ValueError('Invalid target correction policy')
            value.setdefault('overrides',{})[identity]={'mode':mode,'corrections':sorted(set(types))}
            atomic(Path(root)/'audit-settings.json',value);return value
        if 'scope' in body:value['scope']=audit.scope(body['scope'])
        if 'mcp_projects' in body:
            entries=body['mcp_projects']
            if not isinstance(entries,list) or len(entries)>200:raise ValueError('Choose up to two hundred MCP projects')
            selected=[]
            for entry in entries:
                if not isinstance(entry,dict) or set(entry)!={'project','profiles'} or not isinstance(entry['profiles'],list) or any(not isinstance(p,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}',p) for p in entry['profiles']):raise ValueError('MCP grants need project and selected profile IDs')
                path=audit.absolute(entry['project'])
                if not path.is_dir():raise ValueError('Choose an existing MCP project')
                selected.append({'project':str(path),'profiles':sorted(set(entry['profiles']))})
            value['mcp_projects']=selected
        if 'mode' in body:
            if body['mode'] not in ('notify','propose','automatic'):raise ValueError('Choose notify, propose or automatic')
            value['mode']=body['mode']
        if 'corrections' in body:
            if not isinstance(body['corrections'],list) or set(body['corrections'])-CORRECTIONS:raise ValueError('Unknown correction type')
            value['corrections']=sorted(set(body['corrections']))
        if body.get('approve_source') is True:value['approved_source']=source_signature(root)
        for key in ('schedule','semantic'):
            if key not in body:continue
            entry=body[key]
            if not isinstance(entry,dict) or set(entry)-set(DEFAULT[key]):raise ValueError('Unknown schedule setting')
            candidate={**value[key],**entry}
            for flag in ('enabled','changes','paused'):
                if flag in candidate and type(candidate[flag]) is not bool:raise ValueError('Schedule switches must be booleans')
            if type(candidate['hours']) is not int or not 1<=candidate['hours']<=720:raise ValueError('Use an interval from 1 to 720 hours')
            if key=='schedule':
                start,end=candidate.get('window_start'),candidate.get('window_end')
                if (start is None)!=(end is None) or start is not None and (type(start) is not int or type(end) is not int or not 0<=start<=23 or not 0<=end<=23 or start==end):raise ValueError('Choose distinct maintenance-window hours from 0 to 23, or leave both empty')
            if key=='semantic':
                if candidate.get('execution','handoff') not in ('handoff','api','local') or candidate.get('execution','handoff')!='handoff' and candidate['client']!='claude-code':raise ValueError('Only Claude supports isolated execution; other clients use handoffs')
                if candidate['client'] not in tuple(clients.CLIENTS) or type(candidate['minutes']) is not int or not 1<=candidate['minutes']<=10 or type(candidate['max_projects']) is not int or not 1<=candidate['max_projects']<=3:raise ValueError('Invalid bounded review settings')
                profiles=[p for p in audit.scope(value['scope'])['profiles'] if p['client']==candidate['client']]
                profile=candidate.get('profile')
                if profile is not None and not any(p['id']==profile for p in profiles):raise ValueError('Choose a review profile in the selected scope')
                if candidate['enabled'] and len(profiles)>1 and profile is None:raise ValueError('Select a review profile when several client profiles exist')
            value[key]=candidate
        for key in ('notifications','native_notifications'):
            if key in body:
                if type(body[key]) is not bool:raise ValueError('Notification switch must be a boolean')
                value[key]=body[key]
        if 'retention_days' in body:
            days=body['retention_days']
            if type(days) is not int or not 1<=days<=3650:raise ValueError('Choose retention from 1 to 3650 days')
            value['retention_days']=days
        atomic(Path(root)/'audit-settings.json',value)
    return value


def policy_for(root, target):
    value=settings(root)
    return {**value,**value.get('overrides',{}).get(target,{})}


def grant(root, body, config):
    identity=body.get('controller')
    if identity not in config.get('controllers',{}):raise ValueError('Choose a paired controller on this worker')
    operations=body.get('permissions',[])
    if not isinstance(operations,list) or set(operations)-PERMISSIONS:raise ValueError('Choose supported audit permissions')
    roots=body.get('roots',[])
    if not isinstance(roots,list) or not roots or len(roots)>20:raise ValueError('Choose locally approved instruction roots')
    roots=[str(audit.absolute(p)) for p in roots]
    profiles=body.get('profiles',[])
    if not isinstance(profiles,list) or len(profiles)>20 or any(not isinstance(p,str) for p in profiles):raise ValueError('Invalid profiles')
    with wait_lock(Path(root)/'audit-policy'):
        value=settings(root)
        value['grants'][identity]={'permissions':sorted(set(operations)),'roots':roots,'profiles':profiles,'created_at':time.time()}
        atomic(Path(root)/'audit-settings.json',value)
    return {'status':'granted','controller':identity,'permissions':operations}


def authorize(root, principal, operation):
    allowed=settings(root)['grants'].get(principal)
    if not principal or not allowed or operation not in allowed['permissions']:raise ValueError('Constitution audit permission is not granted locally')
    return allowed


def target_allowed(target, granted, *, root=None):
    if not granted:return True
    kind=target['kind'];path=audit.absolute(target['root'])
    if kind=='codex':path=path/'.codex'
    if kind=='claude-code':path=Path(target.get('claude_dir') or clients.directory(kind,path))
    if kind=='cursor':path=Path(target.get('cursor_dir') or path/'.cursor')
    profiles={kind}
    if root is not None and kind in clients.CLIENTS:
        profiles={p['id'] for p in current_scope(root)['profiles'] if p['client']==kind and Path(p['home'])==path}
    if not (kind=='project' or profiles.intersection(granted['profiles'])) or not any(path.is_relative_to(Path(p)) for p in granted['roots']):return False
    for relative in target.get('files',{}):
        candidate=audit.absolute(kit.installed_path(Path(target['root']),relative,target.get('cursor_dir'),target.get('claude_dir')))
        if not any(candidate.is_relative_to(Path(p)) for p in granted['roots']):return False
    return True


def current_scope(root, granted=None):
    cfg=copy.deepcopy(settings(root)['scope']);state=locations.folder(root,'constitution_state')
    if not cfg.get('projects') and not cfg.get('roots'):
        cfg['projects']=[v['root'] for v in kit.state_load(state)['targets'].values() if v['kind']=='project']
    cfg['canonical']=str(source(root));cfg['state']=str(state)
    cfg=audit.scope(cfg)
    if granted:
        permitted=[Path(p) for p in granted['roots']]
        for key in ('projects','roots','files'):
            cfg[key]=[p for p in cfg[key] if any(Path(p).is_relative_to(r) for r in permitted)]
        cfg['profiles']=[p for p in cfg['profiles'] if p['id'] in granted['profiles'] and any(Path(p['home']).is_relative_to(r) for r in permitted)]
        for profile in cfg['profiles']:
            profile['files']=[p for p in profile.get('files',[]) if any(Path(p).is_relative_to(r) for r in permitted)]
            if profile.get('account_rules') and not any(Path(profile['account_rules']).is_relative_to(r) for r in permitted):profile.pop('account_rules')
        # Ownership state may include unrelated targets; filter a read-only copy below.
        cfg.pop('state',None);cfg.pop('canonical',None)
    return cfg


def annotated(root, report):
    store=Store(root)
    for finding in report['findings']:
        finding['disposition']='open'
        saved=store.get('disposition',finding['id'])
        if saved and saved['fingerprint']==finding['fingerprint'] and (not saved.get('until') or saved['until']>time.time()):finding['disposition']=saved['status']
    for chain in report['chains']:
        key=audit.identity([chain['profile'],chain['project']])[:24];proof=store.get('loading',key)
        if proof:
            relevant=[(v['source'],next((s['sha256'] for s in report['sources'] if s['id']==v['source']),None)) for v in chain['sources']]
            chain['loading_evidence']=proof
            chain['loading']=proof['level'] if proof['fingerprint']==audit.identity([relevant,chain.get('configuration_fingerprint')]) and time.time()-proof['observed_at']<30*86400 else 'stale'
    return report


def scan(root, progress=lambda _:None, *, granted=None, record_unchanged=True):
    with wait_lock(Path(root)/'audit-scan',timeout=1):
        progress('Inspecting selected instruction sources')
        owned=None
        if granted:
            db=kit.state_load(locations.folder(root,'constitution_state'))
            owned={'schema_version':1,'targets':{k:t for k,t in db['targets'].items() if target_allowed(t,granted,root=root)}}
        report=audit.scan(current_scope(root,granted),progress=progress,ownership=owned)
        report['application_version']=__import__('local_control',fromlist=['VERSION']).VERSION
        report['machine_id']=audit.identity([__import__('platform').node(),str(Path.home())])[:24]
        report=annotated(root,report);store=Store(root);last=store.list('report',1)
        if not record_unchanged and last and last[0]['content_fingerprint']==report['content_fingerprint']:
            return {**report,'id':last[0]['id'],'unchanged':True}
        new=[f for f in report['findings'] if store.get('notice-finding',f['id'],{}).get('fingerprint')!=f['fingerprint'] and f['disposition']=='open']
        store.put('report',report['id'],report)
        if new and settings(root)['notifications']:
            for finding in new:store.put('notice-finding',finding['id'],{'fingerprint':finding['fingerprint']})
            store.put('notification',report['id'],{'id':report['id'],'created_at':time.time(),'message':f'{len(new)} new constitution findings','report':report['id'],'acknowledged':False})
            if settings(root)['native_notifications']:
                from .audit_notifications import notify
                notify()
        store.prune(settings(root)['retention_days'])
        return report


def disposition(root, body):
    report=Store(root).get('report',body.get('report'))
    finding=next((f for f in (report or {}).get('findings',[]) if f['id']==body.get('finding')),None)
    if not finding or body.get('status') not in ('acknowledged','deferred','exception','open'):raise ValueError('Choose an existing finding and disposition')
    reason=body.get('reason','')
    if not isinstance(reason,str) or not 1<=len(reason)<=500:raise ValueError('Record a bounded reason')
    until=body.get('until')
    if until is not None and (type(until) not in (float,int) or not time.time()<until<time.time()+3650*86400):raise ValueError('Invalid review deadline')
    return Store(root).put('disposition',finding['id'],{'id':finding['id'],'fingerprint':finding['fingerprint'],'status':body['status'],'reason':reason,'until':until})


def loading(root, body):
    report=Store(root).get('report',body.get('report'))
    chain=next((c for c in (report or {}).get('chains',[]) if c['profile']==body.get('profile') and c['project']==body.get('project')),None)
    if not chain or body.get('level') not in ('agent-reported','operator-observed'):raise ValueError('Choose a chain and evidence level')
    if not isinstance(body.get('client_version'),str) or not 1<=len(body['client_version'])<=100:raise ValueError('Record the observed client version')
    relevant=[(v['source'],next(s['sha256'] for s in report['sources'] if s['id']==v['source'])) for v in chain['sources']]
    key=audit.identity([chain['profile'],chain['project']])[:24]
    return Store(root).put('loading',key,{'id':key,'fingerprint':audit.identity([relevant,chain.get('configuration_fingerprint')]),'level':body['level'],'client_version':body['client_version'],'observed_at':time.time(),'note':'Session evidence; not universal compliance'})


def preview(root, body, *, granted=None):
    canonical=source(root);state=locations.folder(root,'constitution_state');cfg=policy_for(root,body.get('target'))
    requested=body.get('target');db=kit.state_load(state)
    candidates=[(k,t) for k,t in db['targets'].items() if audit.target_id(t)==requested]
    if len(candidates)!=1:raise ValueError('Choose an enrolled installation target')
    key,target=candidates[0];path=audit.absolute(target['root'])
    if not target_allowed(target,granted,root=root):raise ValueError('Target is outside the local grant')
    if target.get('pinned') or str(path) in synchronization.settings(root)['paused_projects']:raise ValueError('Pinned or paused target requires its owner to change that policy')
    with wait_lock(Path(root)/'sync-operations'),wait_lock(Path(root)/'studio-operations'),wait_lock(state):
        signature=source_signature(root)
        _,immutable=releases.prepare(releases.files(canonical),state,preview=True)
        writes={};database=copy.deepcopy(db)
        kwargs={'project':path} if target['kind']=='project' else {'platform':target['kind'],'home':path,'cursor_dir':Path(target['cursor_dir']) if target.get('cursor_dir') else None,'claude_dir':Path(target['claude_dir']) if target.get('claude_dir') else None}
        kit._install(canonical,state,**kwargs,planned=writes,database=database,source_reference=immutable)
        changes=[]
        for name,data in writes.items():
            if not name.is_relative_to(path) and not any(target.get(k) and name.is_relative_to(Path(target[k])) for k in ('cursor_dir','claude_dir')):continue
            before=name.read_bytes() if name.exists() else None
            if before==data:continue
            correction='restore-missing' if before is None else 'generated-refresh' if name.name=='routing.md' else 'managed-update'
            changes.append({'path':str(name),'before':audit.fingerprint(name),'after':digest(data),'correction':correction,
                'diff':''.join(difflib.unified_diff((before or b'').decode().splitlines(True),data.decode().splitlines(True),fromfile='before/'+name.name,tofile='after/'+name.name))[:60000]})
        reports=Store(root).list('report',1)
        proposal={'schema':1,'target':requested,'kind':'managed','installation':key,'source_signature':signature,'changes':changes,'report':reports[0]['id'] if reports else None,
                  'enrollment':digest(json_bytes(db)),'status':'proposed','automatic_eligible':signature==cfg['approved_source'] and all(c['correction'] in cfg['corrections'] for c in changes),
                  'note':'Files change through a recoverable transaction; client instructions require a fresh session.'}
        proposal['plan']=digest(json_bytes({k:v for k,v in proposal.items() if k!='report'}));proposal['id']=proposal['plan'][:24]
        Store(root).put('proposal',proposal['id'],proposal)
        if granted and 'excerpts' not in granted['permissions']:
            proposal=copy.deepcopy(proposal)
            for change in proposal['changes']:change['diff']='Source sharing is not granted on the worker.'
        return proposal


def apply(root, body, *, granted=None, automatic=False, principal=None):
    if not re.fullmatch('[a-f0-9]{24}',body.get('proposal','')):raise ValueError('Choose a reviewed proposal')
    store=Store(root);proposal=store.get('proposal',body['proposal'])
    if not proposal or proposal['kind']!='managed':raise ValueError('Choose a managed correction proposal')
    request_id=body.get('request') or uuid.uuid4().hex
    if not re.fullmatch('[a-f0-9]{32}',request_id):raise ValueError('Invalid durable request ID')
    if body.get('plan')!=proposal['plan']:raise ValueError('Review the exact proposal before applying')
    state=locations.folder(root,'constitution_state')
    with wait_lock(Path(root)/'audit-policy'),wait_lock(Path(root)/'sync-operations'),wait_lock(Path(root)/'studio-operations'),wait_lock(state):
        if principal:granted=authorize(root,principal,'apply')
        cfg=policy_for(root,proposal['target']);db=kit.state_load(state);target=db['targets'].get(proposal['installation'])
        if not target or not target_allowed(target,granted,root=root):raise ValueError('Target outside the current grant')
        prior=store.get('request',request_id)
        if prior:
            if prior['signature']!=proposal['plan'] or principal and prior.get('principal')!=principal:raise ValueError('Request belongs to another proposal or controller')
            return prior.get('result',{'status':'needs-review','request':request_id,'note':'Earlier request may have completed; inspect its journal before retrying.'})
        if not target or digest(json_bytes(db))!=proposal['enrollment'] or source_signature(root)!=proposal['source_signature']:raise ValueError('Source or enrollment changed; preview again')
        path=audit.absolute(target['root'])
        if target.get('pinned') or str(path) in synchronization.settings(root)['paused_projects']:raise ValueError('Target was pinned or paused after preview')
        if not target_allowed(target,granted,root=root):raise ValueError('Target outside local grant')
        if automatic and (cfg['mode']!='automatic' or cfg['approved_source']!=proposal['source_signature'] or any(c['correction'] not in cfg['corrections'] for c in proposal['changes'])):raise ValueError('This correction is not preauthorized')
        for change in proposal['changes']:
            if audit.fingerprint(Path(change['path']))!=change['before']:raise ValueError('Target changed; preview again')
        existing=store.begin(request_id,proposal['plan'],principal)
        if existing:return {'status':'needs-review','request':request_id}
        writes={};canonical=source(root)
        _,immutable=releases.prepare(releases.files(canonical),state)
        kwargs={'project':path} if target['kind']=='project' else {'platform':target['kind'],'home':path,'cursor_dir':Path(target['cursor_dir']) if target.get('cursor_dir') else None,'claude_dir':Path(target['claude_dir']) if target.get('claude_dir') else None}
        kit._install(canonical,state,**kwargs,planned=writes,database=copy.deepcopy(db),source_reference=immutable)
        for change in proposal['changes']:
            if digest(writes[Path(change['path'])])!=change['after']:raise ValueError('Rendered correction changed')
        result={**kit.transaction(state,writes),'request':request_id,'status':'applied','verification':'pending fresh scan','proposal':proposal['id']}
        store.put('request',request_id,{'id':request_id,'signature':proposal['plan'],'principal':principal,'status':'completed','result':result})
        proposal.update(status='applied',snapshot=result.get('snapshot'));store.put('proposal',proposal['id'],proposal)
    verification=scan(root,granted=granted)
    if principal:store.put('remote-report',principal,verification)
    result['report']=verification['id'];result['verification']='structural scan completed; client loading remains unverified'
    store.put('request',request_id,{'id':request_id,'signature':proposal['plan'],'principal':principal,'status':'completed','result':result})
    return result


def rollback(root,body,*,granted=None,principal=None):
    store=Store(root);proposal=store.get('proposal',body.get('id'));state=locations.folder(root,'constitution_state')
    if not proposal or not proposal.get('snapshot'):raise ValueError('No retained correction snapshot')
    request=body.get('request') or uuid.uuid4().hex
    if not re.fullmatch('[a-f0-9]{32}',request):raise ValueError('Invalid durable rollback request')
    signature=digest(json_bytes(['rollback',proposal['id'],proposal['snapshot']]))
    with wait_lock(Path(root)/'audit-policy'),wait_lock(Path(root)/'sync-operations'),wait_lock(state):
        if principal:
            granted=authorize(root,principal,'apply')
            target=kit.state_load(state)['targets'].get(proposal.get('installation'))
            if not target or not target_allowed(target,granted,root=root):raise ValueError('Rollback target outside current grant')
        prior=store.get('request',request)
        if prior:
            if prior['signature']!=signature or principal and prior.get('principal')!=principal:raise ValueError('Request belongs to another correction or controller')
            return prior.get('result',{'status':'needs-review','request':request})
        store.begin(request,signature,principal)
        result={**kit._rollback(state,proposal['snapshot']),'request':request}
        proposal['status']='rolled-back';store.put('proposal',proposal['id'],proposal)
        store.put('request',request,{'signature':signature,'principal':principal,'status':'completed','result':result})
    report=scan(root,granted=granted)
    if principal:store.put('remote-report',principal,report)
    return {**result,'report':report['id']}


def overview(root):
    cfg=settings(root);store=Store(root);reports=store.list('report',10);state=locations.folder(root,'constitution_state')
    targets=[{'id':audit.target_id(t),'name':Path(t['root']).name,'kind':t['kind'],'release':t['version'],'pinned':t.get('pinned',False)} for t in kit.state_load(state)['targets'].values()]
    from . import schedules,plans
    machines={}
    for remote in store.list('remote'):
        r=(remote.get('overview') or {}).get('latest') or {}
        key=r.get('machine_id') or remote['id']
        item=machines.setdefault(key,{'id':key,'connections':[],'observed_at':r.get('observed_at'),'status':remote.get('status','unknown')})
        item['connections'].append({'id':remote['id'],'kind':'worker'})
    workspace=Path(root)/'workspace';kit.no_links(workspace)
    for path in sorted(workspace.glob('peer-*.json'))[:50]:
        if not re.fullmatch(r'peer-[a-f0-9]{12}\.json',path.name):continue
        peer=plans.read(root,path.name,{'schema':1});summary=peer.get('snapshot',{}).get('audit',{})
        if summary.get('machine_id'):
            item=machines.setdefault(summary['machine_id'],{'id':summary['machine_id'],'connections':[],'observed_at':summary.get('observed_at'),'status':'controller-snapshot'})
            item['connections'].append({'id':path.stem[5:],'kind':'controller'});item['summary']=summary
    return {'schema':1,'client_capabilities':clients.capabilities(),'settings':cfg,'os_schedule':schedules.read(root,'audit'),'profile_defaults':audit.default_profiles(),'targets':targets,'latest':annotated(root,reports[0]) if reports else None,
            'history':[{'id':r['id'],'observed_at':r['observed_at'],'findings':len(r['findings']),'complete':r['coverage']['complete']} for r in reports],
            'proposals':store.list('proposal'),'notifications':store.list('notification'),'remote':store.list('remote'),
            'reviews':[{'id':r['id'],'client':r['client'],'created_at':r['created_at'],'status':'handoff'} for r in store.list('review')],
            'receipts':store.list('receipt'),'github':store.list('github'),
            'fleet':list(machines.values()),
            'remote_operations':store.list('remote-operation'),'evidence_usage':store.usage(),
            'versions':{'application':__import__('local_control',fromlist=['VERSION']).VERSION,'canonical':(source(root)/'VERSION').read_text().strip()},
            'note':'Expected instruction chains, installation integrity and client loading are separate evidence.'}


def remote(control, body, progress=lambda _:None):
    node_id=body.get('node');node=control.node(node_id)
    if node['kind']!='worker':raise ValueError('Choose a connected worker')
    operation=body.get('operation','overview')
    if operation not in ('overview','scan','preview','apply','rollback','request','job','review'):raise ValueError('Unsupported remote audit action')
    store=Store(control.root)
    try:
        version=control.rpc(node,'/version',timeout=5)
        if 'constitution-audit-v1' not in version.get('capabilities',[]):raise ValueError('Worker update required for constitution health')
        payload=body.get('body',{})
        if not isinstance(payload,dict):raise ValueError('Use a bounded operation request')
        if operation=='review' and payload.get('client')=='claude-code' and 'claude-code' not in version.get('audit_clients',[]):raise ValueError('Worker update required for Claude instruction reviews')
        if operation in ('scan','apply','rollback'):
            payload=copy.deepcopy(payload)
            if operation!='scan':payload.setdefault('request',uuid.uuid4().hex)
            durable=uuid.uuid4().hex
            store.put('remote-operation',durable,{'id':durable,'node':node_id,'operation':operation,'request':payload.get('request'),'status':'started'})
            def run(progress=lambda _:None):
                record=store.get('remote-operation',durable)
                try:
                    start=control.rpc(node,'/audit/'+operation,payload,timeout=30)
                    record.update(job=start['job'],status='running');store.put('remote-operation',durable,record)
                    deadline=time.monotonic()+900
                    while time.monotonic()<deadline:
                        job=control.rpc(node,'/audit/job',{'id':start['job']},timeout=10)
                        progress('Worker constitution operation: '+job.get('status','unknown'))
                        if job.get('status')=='failed':raise ValueError('Worker operation failed; inspect its local journal before retrying')
                        if job.get('status')=='done':
                            record.update(status='completed',result=job.get('result'));store.put('remote-operation',durable,record)
                            summary=control.rpc(node,'/audit/overview',timeout=10)
                            store.put('remote',node_id,{'id':node_id,'status':'online','received_at':time.time(),'overview':summary})
                            return {**(job.get('result') or {}),'remote_operation':durable}
                        time.sleep(.5)
                    raise ValueError('Worker status wait timed out; retrieve the durable operation status before retrying')
                except (OSError,ValueError,KeyError):
                    record['status']='uncertain';store.put('remote-operation',durable,record)
                    raise ValueError('Worker outcome needs inspection; no correction was automatically replayed') from None
            return {**control.submit('Worker constitution '+operation,run),'remote_operation':durable}
        result=control.rpc(node,'/audit/'+operation,None if operation=='overview' else payload,timeout=30)
        if operation=='overview':store.put('remote',node_id,{'id':node_id,'status':'online','received_at':time.time(),'overview':result})
        return result
    except (OSError,ValueError):
        cached=store.get('remote',node_id,{'id':node_id})
        cached.update(status='unavailable',checked_at=time.time());store.put('remote',node_id,cached)
        raise


def schedule_targets(root,report):
    projects={Path(p['path']) for p in report['projects']}
    selected=set()
    for target in kit.state_load(locations.folder(root,'constitution_state'))['targets'].values():
        path=Path(target['root']);kind=target['kind']
        eligible=kind=='project' and path in projects and path.is_dir()
        if kind in tuple(clients.CLIENTS):
            home=Path(target.get('cursor_dir') or target.get('claude_dir') or clients.directory(kind, path))
            eligible=any(p['client']==kind and Path(p['home'])==home and p.get('configuration')=='available' for p in report['profiles'])
        if eligible:selected.add(audit.target_id(target))
    return selected


def scheduled(root, progress=lambda _:None, *, controller=None):
    with wait_lock(Path(root)/'audit-due',timeout=1):
        cfg=settings(root);schedule=cfg['schedule'];store=Store(root)
        if (not schedule['enabled'] and not cfg['semantic']['enabled']) or schedule['paused']:return {'status':'disabled'}
        start,end=schedule.get('window_start'),schedule.get('window_end')
        if start is not None:
            from datetime import datetime
            hour=datetime.now().hour
            if not (start<=hour<end if start<end else hour>=start or hour<end):return {'status':'outside-maintenance-window'}
        latest=store.list('report',1);last=store.get('schedule','last',{})
        semantic=cfg['semantic'];last_review=store.get('schedule','semantic',{})
        due=schedule['enabled'] and time.time()-last.get('at',0)>=schedule['hours']*3600
        review_due=semantic['enabled'] and time.time()-last_review.get('at',0)>=semantic['hours']*3600
        change_due=schedule['enabled'] and schedule['changes'] and time.time()-last.get('checked_at',0)>=300
        if not due and not review_due and not change_due:return {'status':'not-due'}
        report=scan(root,progress,record_unchanged=bool(due or review_due))
        if not due and not review_due and latest and latest[0]['content_fingerprint']==report['content_fingerprint']:
            store.put('schedule','last',{**last,'checked_at':time.time()})
            return {'status':'unchanged'}
        store.put('schedule','last',{'at':time.time() if due or change_due else last.get('at',0),'checked_at':time.time(),'report':report['id']})
        corrections=[]
        if due or change_due:
            permitted=schedule_targets(root,report)
            for target in overview(root)['targets']:
                if target['id'] not in permitted:continue
                target_policy=policy_for(root,target['id'])
                if target_policy['mode']=='notify':continue
                try:
                    proposal=preview(root,{'target':target['id']})
                    if proposal['changes']:
                        corrections.append(apply(root,{'proposal':proposal['id'],'plan':proposal['plan']},automatic=True) if target_policy['mode']=='automatic' and proposal['automatic_eligible'] else {'proposal':proposal['id'],'status':'awaiting-review'})
                except (ValueError,OSError):corrections.append({'target':target['id'],'status':'needs-review'})
        reviews=[]
        if review_due:
            from .audit_review import prepare
            for project in report['projects'][:semantic['max_projects']]:
                try:
                    body={'report':report['id'],'project':project['path'],'client':semantic['client'],'profile':semantic.get('profile')}
                    if semantic.get('execution','handoff')!='handoff':
                        from . import claude
                        if controller is None and semantic['execution']=='local':raise ValueError('Local review requires the owning controller')
                        from types import SimpleNamespace
                        candidate=claude.review(controller or SimpleNamespace(root=Path(root)),{**body,'execution':semantic['execution'],'minutes':semantic['minutes']})
                        reviews.append({'id':candidate['id'],'status':'needs-review'})
                    else:reviews.append(prepare(root,body))
                except (ValueError,OSError,__import__('subprocess').SubprocessError):
                    notice='review-failed-'+audit.identity([project['id'],report['id']])[:24]
                    store.put('notification',notice,{'id':notice,'created_at':time.time(),'message':'Scheduled Claude review unavailable; inspect profile, credentials and execution prerequisites.','acknowledged':False})
            store.put('schedule','semantic',{'at':time.time(),'reviews':[r['id'] for r in reviews]})
            notice='review-'+audit.identity([r['id'] for r in reviews])[:24]
            if reviews and cfg['notifications'] and not store.get('notification',notice):
                store.put('notification',notice,{'id':notice,'created_at':time.time(),'message':f'{len(reviews)} constitution review handoffs ready','acknowledged':False})
        return {'status':'scanned','report':report['id'],'corrections':corrections,'reviews':[{'id':r['id'],'status':r['status']} for r in reviews]}


def run_scheduled(control, progress=lambda _:None):
    return scheduled(control.root,progress,controller=control)


def dispatch(control, operation, body=None, *, principal=None):
    body=body or {};root=control.root
    granted=authorize(root,principal,{'overview':'report','scan':'scan','preview':'preview','apply':'apply','rollback':'apply','review':'review','request':'report','job':'report'}.get(operation,operation)) if principal else None
    if operation=='overview':
        value=overview(root)
        if granted:
            for private in ('settings','profile_defaults','os_schedule','reviews','receipts','github','fleet','remote_operations','evidence_usage'):value.pop(private,None)
            db=kit.state_load(locations.folder(root,'constitution_state'))
            value['targets']=[t for t in value['targets'] if any(audit.target_id(v)==t['id'] and target_allowed(v,granted,root=root) for v in db['targets'].values())]
            value['proposals']=[p for p in value['proposals'] if p['kind']=='managed' and p['target'] in {t['id'] for t in value['targets']}]
            if 'excerpts' not in granted['permissions']:
                for p in value['proposals']:
                    for change in p['changes']:change['diff']='Source sharing is not granted on the worker.'
            value['latest']=Store(root).get('remote-report',principal)
            value['history']=[];value['remote']=[];value['notifications']=[]
        return value
    if operation=='scan':
        def run(progress=lambda _:None):
            current_grant=authorize(root,principal,'scan') if principal else None
            result=scan(root,progress,granted=current_grant)
            if principal:Store(root).put('remote-report',principal,result)
            return result
        run.__name__='audit_scan_job'
        result=control.submit('Scan constitution health',run)
        if principal:Store(root).put('remote-job',result['job'],{'principal':principal,'job':result['job']})
        return result
    if operation=='preview':return preview(root,body,granted=granted)
    if operation in ('apply','rollback'):
        def run(progress=lambda _:None):
            if principal:authorize(root,principal,'apply')
            progress('Applying a reviewed correction')
            current=authorize(root,principal,'apply') if principal else None
            return rollback(root,body,granted=current,principal=principal) if operation=='rollback' else apply(root,body,granted=current,principal=principal)
        result=control.submit('Apply reviewed constitution correction',run)
        if principal:Store(root).put('remote-job',result['job'],{'principal':principal,'job':result['job']})
        return result
    if operation=='job':
        owner=Store(root).get('remote-job',body.get('id'))
        if principal and (not owner or owner['principal']!=principal):raise ValueError('Job is outside this grant')
        with control.lock:return copy.deepcopy(control.jobs.get(body.get('id'),{'status':'unknown'}))
    if operation=='request':
        result=Store(root).get('request',body.get('id'),{'status':'unknown'})
        if principal and result.get('principal')!=principal:raise ValueError('Request is outside this controller grant')
        return result
    if operation=='review':
        if principal and 'excerpts' not in granted['permissions']:raise ValueError('Review excerpts must be granted locally')
        from .audit_review import prepare
        return prepare(root,body,granted=granted)
    if principal:raise ValueError('Operation is not exposed to worker controllers')
    if operation=='review-snapshot':
        from .audit_review import handoff
        return handoff(root,body.get('id'))
    if operation=='remote':return remote(control,body)
    if operation=='remote-status':
        store=Store(root);record=store.get('remote-operation',body.get('id'))
        if not record:raise ValueError('Choose a recorded remote operation')
        node=control.node(record['node'])
        path='/audit/request' if record.get('request') else '/audit/job'
        result=control.rpc(node,path,{'id':record.get('request') or record.get('job')},timeout=10)
        if result.get('status') in ('completed','done'):record.update(status='completed',result=result.get('result'));store.put('remote-operation',record['id'],record)
        return {'id':record['id'],'status':result.get('status','unknown'),'note':'No correction was replayed.'}
    if operation=='settings':return configure(root,body)
    if operation=='mcp-recipe':
        from .launcher import command
        from .audit_mcp import Access
        Access(root,body.get('project'),body.get('profile'))
        # Global arguments precede the subcommand in the native CLI.
        argv=command('--state-dir',root,'audit-mcp','--project',body['project'],'--profile',body['profile'])
        return {'command':argv[0],'args':argv[1:],'claude_config':{'mcpServers':{'ai-constitution-health':{'type':'stdio','command':argv[0],'args':argv[1:]}}},'note':'Use a runtime with requirements-mcp.txt installed. Install this server through the client’s MCP settings; start a fresh session and test a tool.'}
    if operation=='review-import':
        from .audit_review import import_result
        return import_result(root,body)
    if operation=='semantic-apply':
        from .audit_review import apply_reviewed
        return apply_reviewed(root,body)
    if operation=='receipt':
        from .audit_governance import receipt
        return receipt(root,body)
    if operation=='github':
        from .audit_governance import github
        return github(root,body)
    if operation=='os-schedule':
        from . import schedules
        return schedules.configure(root,body.get('enabled'),1,kind='audit')
    if operation=='disposition':return disposition(root,body)
    if operation=='loading':return loading(root,body)
    if operation=='notification':
        store=Store(root);value=store.get('notification',body.get('id'))
        if not value:raise ValueError('Unknown notification')
        value['acknowledged']=True;return store.put('notification',value['id'],value)
    if operation=='backup':return Store(root).backup(body.get('destination'))
    if operation=='restore':return Store(root).restore(body.get('source'))
    raise ValueError('Unknown constitution health operation')
