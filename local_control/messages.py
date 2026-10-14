"""Ollama Messages qualification, independent of Responses API evidence."""
import json
import time
from scripts import audit
from .audit_store import Store
from .transport import connect


def identity(endpoint):
    return audit.identity([endpoint['node'],endpoint['model']])[:24]


def validate(body):
    allowed={'model','max_tokens','messages','system','stream','temperature','top_p','top_k','stop_sequences','tools','thinking','output_config','metadata'}
    if set(body)-allowed:raise ValueError('Unsupported Messages request fields; use the documented local subset')
    if type(body.get('max_tokens')) is not int or not 1<=body['max_tokens']<=131072:raise ValueError('Use bounded max_tokens')
    if not isinstance(body.get('messages'),list) or not body['messages'] or len(body['messages'])>2000:raise ValueError('Send bounded full message history')
    if 'stream' in body and type(body['stream']) is not bool:raise ValueError('stream must be boolean')
    if not isinstance(body.get('tools',[]),list) or len(body.get('tools',[]))>100:raise ValueError('Too many tools')
    if 'metadata' in body and (not isinstance(body['metadata'],dict) or set(body['metadata'])-{'user_id'}):raise ValueError('Unsupported metadata')


def current(control, endpoint, *, refresh=False):
    store=Store(control.root);record=store.get('messages-contract',identity(endpoint))
    if not record:return False
    if refresh:
        try:
            runtime=control.rpc(endpoint['node'],'/api/version',timeout=5).get('version')
            model=next((m for m in control.rpc(endpoint['node'],'/api/tags',timeout=5).get('models',[]) if m['name']==endpoint['model']),{})
            if runtime!=record['runtime_version'] or model.get('digest')!=record['model_digest']:
                record['checked_at']=0;store.put('messages-contract',record['id'],record);return False
            record['checked_at']=time.time();store.put('messages-contract',record['id'],record)
        except (ValueError,OSError):
            record['checked_at']=0;store.put('messages-contract',record['id'],record);return False
    return time.time()-record['checked_at']<300 and record['context']>=control.config['context']


def qualify(control, body, progress=lambda _:None):
    role=body.get('role','primary')
    if role not in ('primary','fallback'):raise ValueError('Choose primary or fallback')
    endpoint=control.config.get(role)
    if not endpoint:raise ValueError('Configure a route first')
    if control.config.get('driver_hold') or endpoint['node'] in control.config['maintenance']:raise ValueError('Resume this machine before qualification')
    if control.mode in ('gaming','draining') and not control.gaming_eligible(endpoint):raise ValueError('Gaming protects this GPU; qualify an eligible fallback or return to Work')
    if control.node(endpoint['node']).get('kind')=='worker':
        supported=control.rpc(endpoint['node'],'/version',timeout=5).get('inference_apis',[])
        if 'messages' not in supported:raise ValueError('Worker update required for Claude Messages')
    with control.operation,control.administer(endpoint['node']):
        progress('Checking Messages tool round trip and streaming')
        info=control.rpc(endpoint['node'],'/api/show',{'model':endpoint['model']})
        if info.get('remote_host') or info.get('remote_model'):raise ValueError('Cloud-backed Ollama models are outside local routing')
        runtime=control.rpc(endpoint['node'],'/api/version').get('version')
        model=next((m for m in control.rpc(endpoint['node'],'/api/tags').get('models',[]) if m['name']==endpoint['model']),{})
        resident=next((m for m in control.rpc(endpoint['node'],'/api/ps').get('models',[]) if m['name']==endpoint['model']),{})
        if not model.get('digest') or not runtime or resident.get('context_length',0)<control.config['context']:raise ValueError('Model/runtime/context evidence is incomplete')
        common={'model':endpoint['model'],'max_tokens':256,'tools':[{'name':'constitution_probe','description':'Return readiness value','input_schema':{'type':'object','properties':{'value':{'type':'string'}},'required':['value']}}]}
        history=[{'role':'user','content':'Call constitution_probe with value ready.'}]
        first=control.rpc(endpoint['node'],'/v1/messages',{**common,'messages':history})
        calls=[c for c in first.get('content',[]) if c.get('type')=='tool_use']
        if len(calls)!=1 or calls[0].get('name')!='constitution_probe' or calls[0].get('input')!={'value':'ready'} or not calls[0].get('id'):raise ValueError('Messages tool call failed qualification')
        history += [{'role':'assistant','content':first['content']},{'role':'user','content':[{'type':'tool_result','tool_use_id':calls[0]['id'],'content':'LOCAL_TOOL_OK'}]}]
        second=control.rpc(endpoint['node'],'/v1/messages',{'model':endpoint['model'],'max_tokens':256,'messages':history})
        if not any('LOCAL_TOOL_OK' in c.get('text','') for c in second.get('content',[])):raise ValueError('Messages full-history tool result failed')
        conn,response=connect(control.node(endpoint['node']),'/v1/messages',{'model':endpoint['model'],'max_tokens':32,'stream':True,'messages':[{'role':'user','content':'Reply OK'}]},timeout=60)
        try:stream=response.read(65537)
        finally:conn.close()
        events=[]
        try:
            for line in stream.decode('utf-8').splitlines():
                if line.startswith('data: '):events.append(json.loads(line[6:]))
        except (UnicodeError,ValueError):raise ValueError('Invalid Messages streaming frames') from None
        if len(stream)>65536 or not events or not all(isinstance(e,dict) for e in events) or events[0].get('type')!='message_start' or events[-1].get('type')!='message_stop':raise ValueError('Messages streaming failed qualification')
        record={'id':identity(endpoint),'api':'messages','level':'protocol-tested','coding_quality':'not-evaluated','model_digest':model['digest'],'runtime_version':runtime,'context':resident['context_length'],'checked_at':time.time()}
        Store(control.root).put('messages-contract',record['id'],record)
        return record


def readiness(control):
    from .routing import select
    for endpoint in [control.config.get('primary'),*control.fallback_candidates()]:
        if endpoint:current(control,endpoint,refresh=True)
    route=select(control,api='messages')
    return {'ready':True,'node':route['node'],'model':route['model'],'api':'messages','context':control.config['context']}
