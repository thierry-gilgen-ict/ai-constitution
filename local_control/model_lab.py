"""Repeated, fingerprinted local evaluations; no paid provider calls or arbitrary code."""
import statistics
import time
import uuid
from scripts import constitution as kit
from scripts.catalog import digest, json_bytes
from . import plans, compatibility


def overview(control):
    value=plans.read(control.root,'lab.json',{'schema':1,'runs':[]})
    return {**value,'fixtures':['clamp correctness (8 cases)','function-call protocol and full-history tool results'],
            'note':'Repeated fixture results are evidence for this hardware and context, not a universal ranking. Local inference only; no paid calls. Project source and generated code are never executed.'}


def preview(control,body):
    roles=body.get('roles',['primary','fallback']);repeats=body.get('repeats',3);minutes=body.get('minutes',30)
    if not isinstance(roles,list) or not roles or len(set(roles))!=len(roles) or any(r not in ('primary','fallback') for r in roles):raise ValueError('Choose configured primary/fallback routes')
    if type(repeats) is not int or not 1<=repeats<=5 or type(minutes) is not int or not 1<=minutes<=120:raise ValueError('Use 1–5 repetitions and a 1–120 minute start budget')
    routes={r:control.config.get(r) for r in roles}
    if any(not v for v in routes.values()):raise ValueError('Configure the selected routes first')
    if any(control.node(v['node'])['kind'] not in ('ollama','worker') for v in routes.values()):raise ValueError('Lab permits local/paired inference only')
    return plans.seal({'schema':1,'routes':routes,'node_fingerprints':{v['node']:digest(json_bytes(control.node(v['node']))) for v in routes.values()},'repeats':repeats,'minutes':minutes,'context':control.config['context'],'fixture_version':1,'max_trials':len(roles)*repeats,'max_output_tokens_per_coding_trial':1024,'paid_budget':0,
                       'note':'Budget stops new trials at the deadline. Each already-started bounded protocol/coding trial finishes; cancellation happens between trials. Close managed sessions before evaluating.'})


def run_lab(control,body,progress=lambda _:None):
    value=preview(control,body);plans.verify(value,body.get('plan'));start=time.monotonic();rows=[]
    for i in range(value['repeats']):
        for role in value['routes']:
            if time.monotonic()-start>=value['minutes']*60:break
            progress('Evaluating '+role+' · repetition '+str(i+1))
            # Revalidate configured endpoint before each trial; never redirect a
            # trial to a newly configured model under the old preview.
            if control.config.get(role)!=value['routes'][role]:raise ValueError('Lab route changed; preview a new experiment')
            result=control.benchmark(role,progress=progress)
            rows.append({'role':role,'trial':i+1,**result})
        else:continue
        break
    summary=[]
    for role in value['routes']:
        samples=[r for r in rows if r['role']==role];times=[r['elapsed_seconds'] for r in samples if r.get('elapsed_seconds') is not None]
        summary.append({'role':role,'trials':len(samples),'passed':sum(r['status']=='passed' for r in samples),
                        'median_seconds':statistics.median(times) if times else None,'spread_seconds':max(times)-min(times) if times else None,
                        'fingerprint':digest(json_bytes({'route':value['routes'][role],'context':value['context'],'hardware':sorted({digest(json_bytes(r.get('hardware'))) for r in samples}),'fixture':1}))})
    with kit.state_lock(control.root/'lab-lock'):
        data=plans.read(control.root,'lab.json',{'schema':1,'runs':[]});previous=data['runs'][0] if data['runs'] else None
        for s in summary:
            baseline=next((p for p in previous.get('summary',[]) if p['fingerprint']==s['fingerprint']),None) if previous else None
            s['regression']='unmatched baseline' if not baseline else 'correctness decreased' if s['trials'] and baseline['trials'] and s['passed']/s['trials']<baseline['passed']/baseline['trials'] else 'no correctness decrease observed'
        record={'id':uuid.uuid4().hex[:12],'created_at':time.time(),'plan':value,'summary':summary,'trials':rows}
        data['runs'].insert(0,record);del data['runs'][20:];plans.write(control.root,'lab.json',data)
    return record
