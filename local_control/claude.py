"""Explicit Claude profiles, launches and bounded private monitoring."""
import copy
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
import uuid
from scripts import clients, audit, constitution as kit
from . import auditing, locations, processes
from .storage import atomic, wait_lock
from .transport import request

DEFAULT = {'schema':1,'monitoring':False,'telemetry':False,'share':False,'automated_reviews':False,'api_key_env':None}


def bounded_run(argv, *, input='', timeout=600, cwd=None, env=None, cancelled=lambda:False, **ignored):
    """Stop a native client before oversized output can exhaust memory."""
    import threading
    from types import SimpleNamespace
    process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=cwd,env=env)
    chunks=[];oversized=[]
    def read():
        size=0
        while True:
            block=process.stdout.read(8192)
            if not block:break
            size+=len(block)
            if size>512*1024:
                oversized.append(True);process.kill();break
            chunks.append(block)
    def write():
        try:process.stdin.write(input.encode('utf-8'));process.stdin.close()
        except (BrokenPipeError,OSError):pass
    reader=threading.Thread(target=read,daemon=True);writer=threading.Thread(target=write,daemon=True)
    reader.start();writer.start()
    try:
        deadline=time.monotonic()+timeout
        while process.poll() is None:
            if cancelled():process.kill();process.wait();raise ValueError('Isolated review cancelled')
            if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(argv,timeout)
            time.sleep(.1)
    except subprocess.TimeoutExpired:
        process.kill();process.wait();raise
    finally:
        reader.join(timeout=5);writer.join(timeout=5)
        process.stdout.close()
    if oversized:raise ValueError('Native output exceeded its bound')
    return SimpleNamespace(returncode=process.returncode,stdout=b''.join(chunks).decode('utf-8',errors='replace'))


def settings(root):
    path=Path(root)/'claude-client.json';kit.no_links(path)
    value=kit.read_json(path) if path.exists() else copy.deepcopy(DEFAULT)
    if value.get('schema')!=1:raise ValueError('Unsupported Claude client settings')
    return value


def configure(root, body):
    if set(body)-(set(DEFAULT)-{'schema'}):
        raise ValueError('Unknown Claude client setting')
    with wait_lock(Path(root)/'claude-policy'):
        value=settings(root)
        for key in ('monitoring','telemetry','share','automated_reviews'):
            if key in body:
                if type(body[key]) is not bool:raise ValueError('Choose a boolean Claude setting')
                value[key]=body[key]
        if 'api_key_env' in body:
            name=body['api_key_env']
            if name is not None and (not isinstance(name,str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,79}',name)):raise ValueError('Use an environment variable name, never a key')
            value['api_key_env']=name
        atomic(Path(root)/'claude-client.json',value)
        if value['telemetry']:
            path=Path(root)/'claude-telemetry-token.json';kit.no_links(path)
            if not path.exists():atomic(path,{'token':secrets.token_urlsafe(32)})
    return {'status':'saved'}


def profile(root, identity):
    candidates=[p for p in auditing.current_scope(root)['profiles'] if p['client']=='claude-code' and (identity is None or p['id']==identity)]
    if len(candidates)!=1:raise ValueError('Choose one enrolled Claude profile')
    return candidates[0]


def project(root, value):
    path=audit.absolute(value)
    db=kit.state_load(locations.folder(root,'constitution_state'))
    target=db['targets'].get('project:'+str(path))
    if not target or 'claude-code' not in target.get('clients',[]):raise ValueError('Enable Claude for this enrolled project first')
    return path


def overview(root):
    value=settings(root)
    return {'client':clients.probe('claude-code'),'settings':value,
            'profiles':[p for p in auditing.current_scope(root)['profiles'] if p['client']=='claude-code'],
            'usage':read_observation(root),'capabilities':clients.capabilities(),
            'note':'Subscription allowances are unknown unless imported. Local launches require Messages qualification; desktop/IDE local launch is not qualified.'}


def read_observation(root):
    path=Path(root)/'claude-observation.json';kit.no_links(path)
    return kit.read_json(path) if path.exists() else {'status':'not-collected','allowance':None,'cost_basis':'estimated; not subscription billing'}


def collect(root, identity=None, runner=bounded_run):
    cfg=settings(root)
    if not cfg['monitoring']:return {'status':'disabled'}
    selected=profile(root,identity);binary=shutil.which('claude')
    if not binary:return {'status':'not-found-on-path'}
    env=os.environ.copy();env['CLAUDE_CONFIG_DIR']=selected['home']
    try:
        result=runner([binary,'auth','status'],capture_output=True,text=True,timeout=10,env=env)
        if len(result.stdout)>65536:raise ValueError()
        data=json.loads(result.stdout)
        allowed={k:data[k] for k in ('loggedIn','authMethod','email','subscriptionType') if k in data and isinstance(data[k],(str,bool))}
        if any(audit.SENSITIVE.search(str(v)) for v in allowed.values()):raise ValueError()
        value={'status':'available','profile':selected['id'],'observed_at':time.time(),'account':allowed,'allowance':None,'cost_basis':'subscription usage unknown'}
    except (OSError,ValueError,subprocess.TimeoutExpired):value={'status':'unavailable','profile':selected['id'],'observed_at':time.time(),'allowance':None}
    if not settings(root)['monitoring']:return {'status':'disabled'}
    atomic(Path(root)/'claude-observation.json',value)
    with wait_lock(Path(root)/'claude-observations'):
        path=Path(root)/'claude-observations.json';kit.no_links(path)
        records=kit.read_json(path) if path.exists() else {}
        records[selected['id']]=value;atomic(path,records)
    return value


def collect_all(root):
    if not settings(root)['monitoring']:return {}
    result={}
    for p in auditing.current_scope(root)['profiles']:
        if p['client']!='claude-code':continue
        try:result[p['id']]=collect(root,p['id'])
        except (ValueError,OSError):result[p['id']]={'status':'unavailable','profile':p['id'],'allowance':None}
    return result


def telemetry(root, body):
    if not settings(root)['telemetry']:raise ValueError('Claude telemetry is disabled')
    # Accept only numeric aggregate metrics, never log/span bodies or attributes.
    if len(json.dumps(body))>256*1024:raise ValueError('Telemetry batch exceeds bound')
    allowed={'claude_code.token.usage','claude_code.cost.usage','claude_code.session.count','claude_code.active_time.total'}
    batch=[]
    def items(value,key,limit):
        if not isinstance(value,dict) or not isinstance(value.get(key,[]),list):raise ValueError('Malformed telemetry structure')
        return value.get(key,[])[:limit]
    for resource in items(body,'resourceMetrics',20):
        for scope in items(resource,'scopeMetrics',20):
            for metric in items(scope,'metrics',100):
                if not isinstance(metric,dict) or not isinstance(metric.get('name'),str):raise ValueError('Malformed telemetry metric')
                if metric.get('name') not in allowed:continue
                total=metric.get('sum',{})
                for point in items(total,'dataPoints',100):
                    if not isinstance(point,dict):raise ValueError('Malformed telemetry point')
                    number=point.get('asDouble',point.get('asInt'))
                    if isinstance(number,str) and re.fullmatch(r'\d{1,16}',number):number=int(number)
                    if type(number) not in (int,float) or not 0<=number<1e15:continue
                    end=str(point.get('timeUnixNano',''));start=str(point.get('startTimeUnixNano','0'))
                    if not re.fullmatch('[0-9]{1,30}',end) or not re.fullmatch('[0-9]{1,30}',start):continue
                    # Attributes are hashed only for series identity, never persisted.
                    series=audit.identity(point.get('attributes',[]))
                    temporality=total.get('aggregationTemporality',1)
                    if temporality=='AGGREGATION_TEMPORALITY_DELTA':temporality=1
                    if temporality=='AGGREGATION_TEMPORALITY_CUMULATIVE':temporality=2
                    if temporality not in (1,2):continue
                    batch.append({'name':metric['name'],'series':series,'end':end,
                                  'start':start,'value':number,'temporality':temporality})
    with wait_lock(Path(root)/'claude-telemetry'):
        path=Path(root)/'claude-metrics.json';kit.no_links(path)
        value=kit.read_json(path) if path.exists() else {'schema':1,'series':{},'totals':{}}
        for point in batch:
            key=point['name']+':'+point['series'];old=value['series'].get(key)
            if old and int(point['end'])<=int(old['end']):continue
            amount=point['value']
            if point['temporality']==2 and old and point['start']==old['start']:amount=max(0,amount-old['value'])
            if key not in value['series'] and len(value['series'])>=1000:continue
            value['totals'][point['name']]=value['totals'].get(point['name'],0)+amount;value['series'][key]=point
        value['observed_at']=time.time();atomic(path,value)
    return {'partialSuccess':{}}


def enroll(root, body, *, apply=False):
    """Explicit, fingerprint-bound enrollment; ordinary sync never adds clients."""
    from . import plans
    from .studio import difference
    state=locations.folder(root,'constitution_state');cwd=audit.absolute(body.get('project',''))
    with wait_lock(Path(root)/'sync-operations'),wait_lock(Path(root)/'studio-operations'),kit.state_lock(state):
        db=kit.state_load(state);target=db['targets'].get('project:'+str(cwd))
        if target and target.get('pinned'):raise ValueError('Change the project pin before enabling Claude')
        from . import synchronization
        if str(cwd) in synchronization.settings(root)['paused_projects']:raise ValueError('Resume project synchronization before enabling Claude')
        source=auditing.source(root);writes={}
        kit._install(source,state,project=cwd,selected_clients=['claude-code'],planned=writes,database=copy.deepcopy(db))
        preview=plans.seal({'project':str(cwd),'changes':[
            {'path':str(p),'before':plans.fingerprint(p),'after':kit.digest(data)} for p,data in writes.items()],
            'diffs':[difference(p.relative_to(cwd).as_posix(),p.read_bytes() if p.exists() else None,data)
                     for p,data in writes.items() if p.is_relative_to(cwd)]})
        if not apply:return preview
        if body.get('plan')!=preview['plan']:raise ValueError('Enrollment preview changed; review again')
        return kit.transaction(state,writes)


def review(control, body, runner=bounded_run):
    """Explicit isolated inference; native tools cannot write active instructions."""
    import tempfile
    from . import audit_review, messages
    cfg=settings(control.root)
    if not cfg['automated_reviews']:raise ValueError('Enable isolated Claude reviews locally first')
    managed=clients.claude_managed_directory()
    if any((managed/name).exists() for name in ('managed-settings.json','managed-mcp.json','managed-settings.d')):
        raise ValueError('Managed Claude execution policies require an interactive handoff until their isolation boundary is qualified')
    info=clients.probe('claude-code')
    if clients.version_tuple(info.get('version'))<(2,1,286):raise ValueError('Isolated reviews require qualified Claude Code 2.1.286 or later')
    if body.get('snapshot'):
        from .audit_store import Store
        saved=Store(control.root).get('review',body['snapshot'])
        if not saved or saved['client']!='claude-code':raise ValueError('Choose an existing Claude snapshot')
        body={**body,'report':saved['report'],'profile':saved['profile'],'sources':[s['id'] for s in saved['sources']]}
    handoff=audit_review.prepare(control.root,{**body,'client':'claude-code'})
    mode=body.get('execution','api')
    env={k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','SYSTEMROOT','TEMP','TMP','HOME','USERPROFILE','APPDATA','LOCALAPPDATA')}
    if mode=='api':
        key=os.environ.get(cfg.get('api_key_env') or '')
        if not key:raise ValueError('Configure an available API key environment variable; subscription credentials are not used')
        env['ANTHROPIC_API_KEY']=key
        model=body.get('model','sonnet')
        if not isinstance(model,str) or not re.fullmatch('[a-zA-Z0-9_.:-]{1,100}',model):raise ValueError('Use a bounded explicit model identifier')
    elif mode=='local':
        messages.readiness(control)
        runtime=kit.read_json(control.root/'runtime.json')
        env.update(ANTHROPIC_BASE_URL=runtime['url'],ANTHROPIC_API_KEY=control.config['gateway_token']);model='constitution-local'
    else:raise ValueError('Isolated review supports API or qualified local models, not subscription login')
    schema={'type':'object','required':['schema','snapshot','findings','edits'],'properties':{'schema':{'const':1},'snapshot':{'const':handoff['id']},'findings':{'type':'array'},'edits':{'type':'array'}},'additionalProperties':False}
    argv=[shutil.which('claude'),'--bare','-p','--tools','','--disallowedTools','mcp__*','--strict-mcp-config',
          '--mcp-config','{"mcpServers":{}}','--settings','{"disableAllHooks":true}','--model',model,'--output-format','json','--json-schema',json.dumps(schema)]
    from .audit_store import Store
    with wait_lock(control.root/'claude-review-active',timeout=1),tempfile.TemporaryDirectory(prefix='constitution-review-') as directory:
        cache=audit.identity([handoff['id'],mode,model,info['version'],1])
        cached=Store(control.root).get('claude-review-cache',cache)
        if cached:
            proposal=Store(control.root).get('proposal',cached['proposal'])
            if proposal:return {**proposal,'cached':True}
        cancellation=control.root/'claude-review-cancel.json'
        before=audit.fingerprint(cancellation)
        minutes=body.get('minutes',10)
        if type(minutes) is not int or not 1<=minutes<=10:raise ValueError('Choose one to ten review minutes')
        result=runner(argv,input=handoff['prompt'],capture_output=True,text=True,timeout=minutes*60,cwd=directory,env=env,cancelled=lambda:audit.fingerprint(cancellation)!=before)
        if result.returncode or len(result.stdout.encode())>512*1024:raise ValueError('Claude review failed or exceeded its output bound; private stderr was withheld')
        value=json.loads(result.stdout);output=value.get('structured_output')
        if output is None:
            candidate=value.get('result')
            output=json.loads(candidate) if isinstance(candidate,str) else candidate
        proposal=audit_review.import_result(control.root,{'snapshot':handoff['id'],'result':output})
        Store(control.root).put('claude-review',handoff['id'],{'id':handoff['id'],'execution':mode,'model':model,'at':time.time(),'usage':None})
        Store(control.root).put('claude-review-cache',cache,{'id':cache,'proposal':proposal['id']})
        return proposal


def cancel_review(root):
    atomic(Path(root)/'claude-review-cancel.json',{'request':uuid.uuid4().hex})
    return {'status':'cancellation-requested','note':'Only the isolated Claude review is affected; interactive tasks are preserved.'}


def launch_command(root, body):
    from .launcher import command
    cwd=project(root,body.get('project',''));selected=profile(root,body.get('profile'))
    mode=body.get('mode','hosted')
    if mode not in ('hosted','local'):raise ValueError('Choose hosted or local')
    argv=command('--state-dir',root,'claude','--project',cwd,'--profile',selected['id'],'--mode',mode)
    if os.name=='nt':value='& '+' '.join("'"+str(a).replace("'","''")+"'" for a in argv)
    else:
        import shlex
        value=shlex.join(map(str,argv))
    return {'command':value,'mode':mode}


def launch(root, runtime, body, runner=subprocess.Popen):
    selected=profile(root,body.get('profile'));cwd=project(root,body['project'])
    binary=shutil.which('claude')
    if not binary:raise ValueError('Install Claude Code using the documented platform installer')
    mode=body.get('mode','hosted')
    if mode not in ('hosted','local'):raise ValueError('Choose hosted or local')
    args=body.get('args',[])
    if not isinstance(args,list) or len(args)>30 or any(not isinstance(a,str) or len(a)>1000 for a in args):raise ValueError('Use bounded native arguments')
    if any(a.startswith(('--dangerously','--mcp-config','--settings','--plugin','--add-dir','--model')) for a in args):raise ValueError('Managed launch overrides require a separate native session')
    env=os.environ.copy();env['CLAUDE_CONFIG_DIR']=selected['home'];command=[binary]
    cfg=settings(root);identity=uuid.uuid4().hex
    if mode=='local':
        ready=request(runtime,'/api/claude/readiness',{})
        env.update(ANTHROPIC_BASE_URL=runtime['url'],ANTHROPIC_AUTH_TOKEN=runtime['gateway_token'],ANTHROPIC_API_KEY='')
        for tier in ('HAIKU','SONNET','OPUS'):env['ANTHROPIC_DEFAULT_'+tier+'_MODEL']='constitution-local'
        env['CLAUDE_CODE_MAX_CONTEXT_TOKENS']=str(ready['context'])
        # Native profile env settings can override shell values. Refuse conflicts
        # instead of accidentally sending a local credential to another backend.
        for config in (Path(selected['home'])/'settings.json',cwd/'.claude/settings.json',cwd/'.claude/settings.local.json'):
            settings_env=audit.document(config).get('env',{})
            if not isinstance(settings_env,dict):raise ValueError('Invalid profile environment settings')
            for key in ('ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY'):
                if key in settings_env and settings_env[key]!=env[key]:raise ValueError('Claude profile overrides the managed local backend; reconcile it before launch')
        command+=['--model','constitution-local']
    if cfg['telemetry']:
        token=kit.read_json(Path(root)/'claude-telemetry-token.json')['token']
        env.update(CLAUDE_CODE_ENABLE_TELEMETRY='1',OTEL_METRICS_EXPORTER='otlp',OTEL_LOGS_EXPORTER='none',
                   OTEL_EXPORTER_OTLP_METRICS_PROTOCOL='http/json',OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=runtime['url']+'/api/claude/telemetry',
                   OTEL_EXPORTER_OTLP_METRICS_HEADERS='Authorization=Bearer '+token,OTEL_LOG_USER_PROMPTS='0',OTEL_LOG_TOOL_DETAILS='0',OTEL_LOG_TOOL_CONTENT='0')
    process=processes.identity(os.getpid())
    if not process:raise ValueError('Cannot establish session owner')
    request(runtime,'/api/session',{'action':'open','id':identity,'process':process})
    child=None
    try:
        child=runner([*command,*args],cwd=cwd,env=env)
        owner=processes.identity(child.pid)
        if owner:request(runtime,'/api/session',{'action':'open','id':identity,'process':owner})
        return child.wait()
    finally:
        if child is None or child.poll() is not None:request(runtime,'/api/session',{'action':'close','id':identity},timeout=3)
