"""Portable setup recipes and explicit non-destructive new-machine mappings."""
from pathlib import Path
import tempfile
from scripts import constitution as kit, releases, architecture
from scripts.catalog import digest,json_bytes
from . import plans,fleet,toolkits,project_vault
from .studio import Studio


def export(control):
    studio=Studio(control.root);targets=kit.state_load(studio.state)['targets'];vault=project_vault.read(control.root)
    path=studio.state/'architectures.json';kit.no_links(path);baselines=kit.read_json(path).get('projects',{}) if path.exists() else {};kits=toolkits.overview(control.root)['projects']
    projects=[]
    for v in targets.values():
        if v['kind']!='project':continue
        baseline=baselines.get(v['root'],{})
        projects.append({'id':digest(v['root'].encode())[:12],'name':Path(v['root']).name,'pinned':v['pinned'],
            'architecture':{k:baseline[k] for k in ('id','policy','project_name','snapshot') if k in baseline},'toolkits':kits.get(v['root'],{}).get('kits',[])})
    return {'schema':1,'library':fleet.portable(control.root),'projects':projects,
        'configurations':[{'id':i,'name':v['name']} for i,v in vault['projects'].items()],
        'models':[{'role':r,'model':control.config[r].get('source_model',control.config[r]['model']),'cpu':control.config[r].get('cpu',False)} for r in ('primary','fallback') if control.config.get(r)],
        'context':control.config['context'],'note':'Recipe only. Host paths, account logins, credentials, worker tokens, weights and configuration contents are excluded. Review custom instruction text before sharing.'}


def preview(root,body,*,_locked=False):
    manifest=body.get('manifest');studio=Studio(root);studio.initialize()
    if not isinstance(manifest,dict) or manifest.get('schema')!=1 or set(manifest)-{'schema','library','projects','configurations','models','context','note'}:raise ValueError('Import a portable recovery recipe')
    fleet.validate_bundle(manifest.get('library'),studio);projects=manifest.get('projects',[])
    if not isinstance(projects,list) or len(projects)>200 or any(not isinstance(p,dict) or set(p)-{'id','name','pinned','architecture','toolkits'} or not isinstance(p.get('id'),str) or not isinstance(p.get('name'),str) or type(p.get('pinned')) is not bool for p in projects):raise ValueError('Invalid portable project inventory')
    for p in projects:
        selected=p.get('toolkits',[])
        if not isinstance(selected,list) or len(selected)>20 or any(i not in manifest['library']['toolkits'] for i in selected):raise ValueError('Recovery references a missing toolkit')
        baseline=p.get('architecture',{})
        if not isinstance(baseline,dict) or set(baseline)-{'id','policy','project_name','snapshot'}:raise ValueError('Invalid architecture recovery reference')
        if baseline:
            architecture.identifier(baseline.get('id'));architecture.validate(baseline.get('snapshot') or __import__('json').loads(manifest['library']['files'].get('templates/architectures/'+baseline['id']+'.json','null')))
    mapping=body.get('mapping',{})
    if not isinstance(mapping,dict) or set(mapping)-{p['id'] for p in projects}:raise ValueError('Map portable project IDs to local checkouts')
    rows=[];seen=set();db=kit.state_load(studio.state)
    for p in projects:
        path=mapping.get(p['id'])
        if not path:rows.append({**p,'status':'unmapped'});continue
        if not isinstance(path,str) or not Path(path).expanduser().is_absolute():raise ValueError('Use an absolute checkout path')
        target=Path(path).expanduser().absolute();kit.no_links(target)
        if str(target).casefold() in seen:raise ValueError('Each checkout may only be mapped once')
        seen.add(str(target).casefold())
        if not target.is_dir():raise ValueError('Clone or open the existing repository first; recovery does not execute URLs')
        status='already-enrolled' if 'project:'+str(target) in db['targets'] else 'adoption-required' if (target/'.ai/constitution.lock.json').exists() else 'ready'
        rows.append({**p,'project':str(target),'status':status,'agents_hash':plans.fingerprint(target/'AGENTS.md'),'project_hash':plans.fingerprint(target/'.ai/project.md')})
    return plans.seal({'schema':1,'manifest_hash':digest(json_bytes(manifest)),'local_hash':digest(json_bytes(fleet.portable(root,_locked=_locked))),
        'enrollment':digest(json_bytes(db)),'projects':rows,'replacements':[{'path':n,'before':plans.fingerprint(kit.safe_path(studio.draft,n)),'after':digest(t.encode())} for n,t in manifest['library']['files'].items()],
        'note':'Replaces the reviewed editable library and enrolls mapped fresh checkouts. Existing bundles require verified adoption. Restore secrets from encrypted backup to a new private folder; re-pair workers and re-test hardware and model routes.'})


def recover_workspace(control,body,progress=lambda _:None):
    root=control.root;studio=Studio(root)
    with kit.state_lock(root/'recovery-lock'),kit.state_lock(studio.guard),kit.state_lock(studio.state),kit.state_lock(root/'toolkit-lock'):
        value=preview(root,body,_locked=True);plans.verify(value,body.get('plan'));manifest=body['manifest'];writes={}
        with tempfile.TemporaryDirectory(prefix='constitution-recovery-') as folder:
            target=Path(folder).resolve(strict=True)
            for name,data in studio.payload().items():kit.atomic_bytes(kit.safe_path(target,name),data)
            for name,text in manifest['library']['files'].items():kit.atomic_bytes(kit.safe_path(target,name),text.encode())
            kit.validate(target);kit.build(target)
            current=studio.payload()
            for name,data in releases.files(target).items():
                existing=kit.safe_path(studio.draft,name)
                if current.get(name)!=data:writes[existing]=data
        db=plans.read(root,'toolkits.json',toolkits.DEFAULT);db['kits'].update(manifest['library']['toolkits']);writes[root/'workspace/toolkits.json']=json_bytes(db)
        stage=kit.transaction(studio.history,writes);results=[]
        for p in value['projects']:
            if p['status']!='ready':results.append(p);continue
            progress('Enrolling mapped recovery project');path=Path(p['project'])
            if plans.fingerprint(path/'AGENTS.md')!=p['agents_hash'] or plans.fingerprint(path/'.ai/project.md')!=p['project_hash']:results.append({**p,'status':'needs-review'});continue
            try:
                planned={};baseline=p.get('architecture',{})
                if baseline:
                    template=baseline.get('snapshot') or kit.read_json(kit.safe_path(studio.draft,'templates/architectures/'+baseline['id']+'.json'))
                    _,planned=architecture.plan(kit,studio.draft,studio.state,path,architecture.validate(template),baseline.get('project_name',p['name']),baseline.get('policy','latest'))
                kit._install(studio.draft,studio.state,project=path,pin=p['pinned'],planned=planned)
                installed=kit.transaction(studio.state,planned)
                if p.get('toolkits'):
                    _,assets=toolkits._writes(root,{'project':str(path),'kits':p['toolkits']});kit.transaction(root/'workspace/transactions',assets)
                results.append({**p,**installed,'status':'enrolled'})
            except (ValueError,OSError):results.append({**p,'status':'needs-review'})
    return {'library':stage,'projects':results,'note':'Library and fresh mappings restored. Secrets, logins, runtimes and routes need separate verification.'}
