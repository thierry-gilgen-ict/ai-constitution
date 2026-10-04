"""Controller-only workflow APIs and metadata search; never indexes secret contents."""
from pathlib import Path
from . import inspector,rollouts,project_setup,toolkits,launch_advice,fleet,recovery,model_lab,resource_profiles,plans,monitoring

PAGES={'overview':'Overview','setup':'Get started','projects':'Projects','architectures':'Project templates','constitution':'Constitution files','models':'Model library','machines':'Your machines','accounts':'Apps & subscriptions','workers':'Set up a worker','storage':'Storage & locations','vault':'Configs & backups','updates':'Updates & model inbox','insights':'Measured performance','workflows':'Workspace workflows'}


def search(control,query):
    from .workspace import overview
    text=str(query).casefold().strip()[:160];items=[{'label':label,'kind':'page','page':p} for p,label in PAGES.items()]
    items.extend({'label':Path(p['project']).name,'detail':p['project'],'kind':'project','project':p['project'],'page':'workflows'} for p in overview(control)['projects'])
    items.extend({'label':v['name'],'detail':v['id']+' · '+v['version'],'kind':'toolkit','page':'workflows'} for v in toolkits.overview(control.root)['kits'].values())
    from .studio import Studio
    studio=Studio(control.root);studio.initialize();items.extend({'label':n,'kind':'file','page':'constitution'} for n in studio.payload())
    items.extend({'label':a.get('label') or a.get('login') or a['id'],'detail':a.get('application',''),'kind':'account','page':'accounts'} for a in monitoring.load(control.root)['accounts'].values())
    from scripts import constitution as kit
    catalog=studio.draft/'registry/catalog.json';kit.no_links(catalog)
    signature=(catalog.stat().st_mtime_ns,catalog.stat().st_size)
    if signature[1]>16*1024*1024:raise ValueError('Search catalog exceeds its metadata limit')
    cached=getattr(control,'search_catalog',None)
    if not cached or cached[0]!=signature:
        metadata=kit.read_json(catalog)
        models=[{'label':m.get('name') or m['id'],'detail':p.get('name',pid)+' · '+mid,'kind':'model definition','page':'constitution'} for pid,p in metadata['providers'].items() for mid,m in p['models'].items()]
        control.search_catalog=(signature,models)
    items.extend(control.search_catalog[1])
    items.extend({'label':m,'detail':control.config['nodes'].get(node,{}).get('name',node),'kind':'managed local model','page':'models'} for node,models in control.config['managed'].items() for m in models)
    for path in list((studio.draft/'templates/architectures').glob('*.json'))[:200]:
        value=kit.read_json(kit.safe_path(studio.draft,path.relative_to(studio.draft).as_posix()))
        items.append({'label':value.get('name',path.stem),'detail':path.stem,'kind':'architecture','page':'architectures'})
    matches=[i for i in items if all(word in (i['label']+' '+i.get('detail','')).casefold() for word in text.split())]
    return {'items':matches[:60],'truncated':len(matches)>60,'note':'Searches project, model, architecture, account and toolkit metadata plus library filenames. Secret contents and conversations are excluded.'}


def dispatch(control,operation,body):
    root=control.root
    if operation=='overview':
        from .workspace import overview
        return {'projects':overview(control)['projects'],'toolkits':toolkits.overview(root),'fleet':fleet.overview(root),'lab':model_lab.overview(control),'profiles':resource_profiles.overview(root)}
    if operation=='search':return search(control,body.get('query',''))
    if operation=='inspect':return inspector.inspect(control,body.get('project'))
    if operation=='rollout-preview':return rollouts.preview(root,body.get('projects'))
    if operation=='rollout-apply':return control.submit('Apply reviewed workspace rollout',rollouts.apply,root,body)
    if operation=='prepare-recipe':return project_setup.recipes(root,body.get('project'))
    if operation=='prepare-save':return project_setup.save_recipe(root,body.get('project'),body.get('recipe'))
    if operation=='prepare-preview':return project_setup.preview(root,body)
    if operation=='prepare-apply':return control.submit('Prepare reviewed project',project_setup.apply,control,body)
    if operation=='prepare-history':
        from scripts import constitution as kit
        path=Path(root)/'workspace';kit.no_links(path)
        return {'runs':[{'id':p.stem[4:],**plans.read(root,p.name,{'schema':1})} for p in sorted(path.glob('run-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]]}
    if operation=='toolkit-save':return toolkits.save(root,body.get('toolkit'))
    if operation=='toolkit-import':return toolkits.import_document(body)
    if operation=='toolkit-export':return toolkits.export(body.get('toolkit'),body.get('format'))
    if operation=='toolkit-preview':return toolkits.preview(root,body)
    if operation=='toolkit-apply':return control.submit('Install reviewed agent toolkits',toolkits.apply,root,body)
    if operation=='launch-preview':return launch_advice.advice(control,body.get('project'))
    if operation=='launch':return launch_advice.launch(control,body)
    if operation=='fleet-pairing':
        if not getattr(control,'peer_listener',None):raise ValueError('Enable this session’s controller listener first')
        return fleet.pairing(root,body)
    if operation=='fleet-listener':
        if getattr(control,'peer_listener',None):raise ValueError('A controller listener is already running; restart safely to change its address')
        from .fleet_server import start
        port=body.get('port',8768)
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('Choose a port from 1024 to 65535')
        control.peer_listener=start(control,body.get('address'),port)
        return {'status':'listening','note':'Controller TLS listener enabled for this session. Create a scoped invitation; private-network firewall configuration may still be required.'}
    if operation=='fleet-connect':return fleet.connect_peer(root,body)
    if operation=='fleet-revoke':return fleet.revoke(root,body)
    if operation=='fleet-pull':return control.submit('Fetch scoped controller library',fleet.pull,control,body)
    if operation=='fleet-preview':return fleet.stage_preview(root,body)
    if operation=='fleet-resolve':return fleet.resolve(root,body)
    if operation=='fleet-apply':return control.submit('Stage reviewed controller changes',fleet.stage_apply,root,body)
    if operation=='fleet-snapshot':return plans.read(root,'peer-'+str(body.get('id'))+'.json',{'schema':1})
    if operation=='recovery-export':return recovery.export(control)
    if operation=='recovery-preview':return recovery.preview(root,body)
    if operation=='recovery-apply':return control.submit('Recover reviewed workspace',recovery.recover_workspace,control,body)
    if operation=='lab-preview':return model_lab.preview(control,body)
    if operation=='lab-run':return control.submit('Run bounded model comparison',model_lab.run_lab,control,body)
    if operation=='profiles-save':return resource_profiles.configure(root,body)
    if operation=='profile-manual':
        if body.get('profile') not in ('work','gaming','fast','deep'):raise ValueError('Choose a supported resource profile')
        resource_profiles.manual(root);return control.submit('Choose resource profile',resource_profiles.apply_profile,control,body.get('profile'))
    raise ValueError('Unsupported workspace workflow')
