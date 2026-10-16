"""Account-wide quota evidence assists launch; it never signs in or moves a session."""
import time
from . import plans, monitoring, launcher


def advice(control,project):
    project=plans.project(control.root,project);data=monitoring.load(control.root);rows=[];seen=set()
    for a in data.get('accounts',{}).values():
        if str(project) not in a.get('projects',[]):continue
        key=a.get('subscription_key',a['id'])
        if key in seen:continue
        seen.add(key);obs=data.get('observations',{}).get(a.get('application','').lower(),{})
        current=obs.get('status')=='available' and obs.get('login','').casefold()==a.get('login','').casefold() and 0<=time.time()-obs.get('observed_at',0)<300
        samples=[w.get('used_percent') for w in obs.get('windows',[]) if w.get('used_percent') is not None and (w.get('resets_at') is None or w['resets_at']>time.time())] if current else []
        manual=next((s for s in a.get('usage',[]) if 0<=time.time()-s.get('observed_at',0)<300),None)
        source='provider observation' if samples else 'unavailable'
        if not samples and manual and manual.get('limit'):
            samples=[manual['used']/manual['limit']*100];source='manual/import'
        used=max(samples) if samples else None
        rows.append({'id':a['id'],'label':a.get('label'),'login':a.get('login'),'application':a.get('application'),
                     'subscription_key':key,'quota':'exhausted' if used is not None and used>=100 else 'available' if used is not None else 'unknown',
                     'used_percent':used,'observed_at':obs.get('observed_at') if source=='provider observation' else manual.get('observed_at') if source=='manual/import' else None,
                     'identity_verified':bool(obs.get('login') and current and obs.get('login','').casefold()==a.get('login','').casefold()),'source':source})
    from . import auditing
    profiles = [{'id':p['id'], 'home':p['home']} for p in auditing.current_scope(control.root)['profiles'] if p['client']=='claude-code']
    return plans.seal({'schema':1,'project':str(project),'accounts':rows,'claude_profiles':profiles,'local':{'mode':control.mode,'route':control.config.get('fallback' if control.mode in ('gaming','draining') else 'primary')},
        'note':'Quota is shared across machines. Unknown is not free capacity. Launch uses the client’s existing login; verify its account there. Existing tasks keep their session and route.'})


def launch(control,body):
    value=advice(control,body.get('project'));plans.verify(value,body.get('plan'))
    client=body.get('client');mode=body.get('mode','local')
    if client not in ('codex','cursor','claude-code') or mode not in ('local','hosted'):raise ValueError('Choose a supported coding application and local or hosted')
    selected=next((a for a in value['accounts'] if a['id']==body.get('account')),None)
    if body.get('account') and selected is None: raise ValueError('Account mapping is unavailable; review the current project assignments')
    if selected and selected['application'].lower().replace(' ', '-')!=client:raise ValueError('Account mapping belongs to another application')
    if selected and selected['quota']=='exhausted':raise ValueError('Selected account’s latest observed window is exhausted; review usage before launching')
    if client=='claude-code':return launcher.open_claude(control.root,value['project'],body.get('profile'),mode)
    if mode=='local':return launcher.open_project(control.root,value['project'],client)
    return launcher.open_hosted(control.root,value['project'],client)
