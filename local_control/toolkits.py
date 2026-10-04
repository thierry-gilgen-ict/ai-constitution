"""Portable agent assets with explicit client adapters and conservative ownership."""
import copy
import json
import re
import tomllib
import base64
import io
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
from scripts import constitution as kit, architecture
from scripts.catalog import digest, json_bytes
from . import plans

ID = re.compile(r'[a-z][a-z0-9-]{0,47}')
ENV = re.compile(r'[A-Z][A-Z0-9_]{0,79}')
DEFAULT = {'schema':1,'kits':{},'projects':{}}
START, END = '# ai-constitution:toolkits:begin', '# ai-constitution:toolkits:end'


def validate(value):
    value = copy.deepcopy(value)
    if not isinstance(value,dict) or set(value)-{'schema','id','name','version','rules','skills','commands','mcp'}:
        raise ValueError('Unsupported toolkit fields')
    if value.get('schema')!=1 or not ID.fullmatch(value.get('id','')):
        raise ValueError('Toolkit needs schema 1 and a portable ID')
    if not isinstance(value.get('name'),str) or not 1<=len(value['name'])<=120:
        raise ValueError('Choose a toolkit name')
    if not re.fullmatch(r'\d+\.\d+\.\d+',value.get('version','')): raise ValueError('Use a semantic toolkit version')
    for group in ('rules','skills','commands'):
        entries=value.setdefault(group,[])
        if not isinstance(entries,list) or len(entries)>30:raise ValueError('Too many toolkit assets')
        seen=set()
        for entry in entries:
            if not isinstance(entry,dict) or set(entry)!={'id','description','content'}:raise ValueError('Asset needs ID, description and content')
            if not ID.fullmatch(entry['id']) or entry['id'] in seen:raise ValueError('Asset IDs must be unique and portable')
            seen.add(entry['id'])
            if not isinstance(entry['description'],str) or not 1<=len(entry['description'])<=240:raise ValueError('Asset needs a short description')
            if not isinstance(entry['content'],str) or len(entry['content'].encode())>32768:raise ValueError('Asset exceeds text limit')
    entries=value.setdefault('mcp',[])
    if not isinstance(entries,list) or len(entries)>20:raise ValueError('Too many MCP servers')
    seen=set()
    for server in entries:
        if not isinstance(server,dict) or set(server)-{'id','command','args','environment','url','bearer_env'}:raise ValueError('Unsupported MCP settings')
        if not ID.fullmatch(server.get('id','')) or server['id'] in seen:raise ValueError('MCP IDs must be unique')
        seen.add(server['id'])
        if ('command' in server)==('url' in server):raise ValueError('Choose stdio or HTTP for each MCP')
        if 'url' in server:
            parsed=urlsplit(server['url'])
            if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1')):raise ValueError('MCP needs HTTPS or loopback HTTP')
            if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Keep credentials out of MCP URLs')
            if set(server)-{'id','url','bearer_env'}:raise ValueError('HTTP MCP accepts only URL and bearer environment reference')
        else:
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}',server['command']) or server['command'].lower() in ('cmd','powershell','pwsh','sh','bash'):raise ValueError('MCP command must be a runtime executable name')
            args=server.setdefault('args',[])
            if not isinstance(args,list) or len(args)>30 or any(not isinstance(a,str) or len(a)>1000 or any(ord(c)<32 for c in a) for a in args):raise ValueError('MCP arguments exceed limits')
            if set(server)-{'id','command','args','environment'}:raise ValueError('Stdio MCP accepts argument lists and environment names')
        names=server.get('environment',[])+([server['bearer_env']] if server.get('bearer_env') else [])
        if not isinstance(names,list) or len(names)>30 or any(not isinstance(n,str) or not ENV.fullmatch(n) for n in names):raise ValueError('MCP credentials must be environment variable names')
    architecture.clean_text(json.dumps(value))
    if len(json_bytes(value))>256*1024:raise ValueError('Toolkit exceeds size limit')
    return value


def overview(root):
    return {**plans.read(root,'toolkits.json',DEFAULT),'note':'Installing files does not verify client loading. MCP commands execute only when you enable them in a trusted client.'}


def save(root,value):
    value=validate(value)
    with kit.state_lock(Path(root)/'toolkit-lock'):
        data=plans.read(root,'toolkits.json',DEFAULT)
        if value['id'] not in data['kits'] and len(data['kits'])>=100:raise ValueError('Toolkit library is full')
        data['kits'][value['id']]=value;plans.write(root,'toolkits.json',data)
    return {'status':'saved','id':value['id']}


def export(value,format):
    value=validate(value); servers={}
    for s in value['mcp']:
        row={'url':s['url']} if 'url' in s else {'command':s['command'],'args':s['args'],'env':{n:'${env:'+n+'}' for n in s.get('environment',[])}}
        if s.get('bearer_env'):row['headers']={'Authorization':'Bearer ${env:'+s['bearer_env']+'}'}
        servers[s['id']]=row
    if format=='native':return {'format':format,'document':value,'losses':[]}
    if format=='rulesync':
        files={'.rulesync/mcp.jsonc':json.dumps({'mcpServers':servers},indent=2)+'\n'}
        for group in ('rules','skills','commands'):
            for a in value[group]:
                path=f'.rulesync/{group}/{a["id"]}'+('/SKILL.md' if group=='skills' else '.md')
                header='---\n'+('name: '+a['id']+'\n' if group=='skills' else '')+'description: '+json.dumps(a['description'])+'\n'+('targets: ["*"]\n' if group!='skills' else '')+'---\n\n'
                files[path]=header+a['content']+'\n'
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
            for name,text in sorted(files.items()):bundle.writestr(name,text)
        return {'format':format,'files':files,'archive_base64':base64.b64encode(archive.getvalue()).decode(),'losses':['Client-specific metadata and hooks are outside this portable subset.']}
    if format=='continue':
        rows=[]
        for name,s in servers.items():
            row={'name':name,**s}
            if 'env' in row:row['env']={n:'${{ secrets.'+n+' }}' for n in row['env']}
            if 'headers' in row:row['requestOptions']={'headers':{'Authorization':'Bearer ${{ secrets.'+next(v['bearer_env'] for v in value['mcp'] if v['id']==name)+' }}'}};del row['headers']
            rows.append(row)
        return {'format':format,'document':{'name':value['name'],'version':value['version'],'schema':'v1','rules':[a['content'] for a in value['rules']],'mcpServers':rows},'losses':['Skills and commands require their separate Markdown assets; model definitions are not included.','JSON output is valid YAML. General YAML import requires conversion to JSON.']}
    raise ValueError('Choose native, rulesync or continue')


def import_document(body):
    fmt=body.get('format');doc=body.get('document')
    if fmt=='native':return {'toolkit':validate(doc),'losses':[]}
    if not isinstance(doc,dict):raise ValueError('Import a JSON object; comments and general YAML need conversion first')
    servers=doc.get('mcpServers',{} if fmt=='rulesync' else [])
    if fmt not in ('rulesync','continue'):raise ValueError('Choose a supported import format')
    if fmt=='continue':
        if not isinstance(servers,list):raise ValueError('Continue MCP servers must be a list')
        servers={s.get('name'): {k:v for k,v in s.items() if k!='name'} for s in servers if isinstance(s,dict)}
    if not isinstance(servers,dict):raise ValueError('MCP servers must be an object')
    rows=[];losses=[]
    for name,s in servers.items():
        if not isinstance(s,dict):raise ValueError('Invalid MCP server')
        row={'id':name}
        if 'url' in s:row['url']=s['url']
        else:
            row.update(command=s.get('command'),args=s.get('args',[]),environment=[])
            for key,v in s.get('env',{}).items():
                if v not in ('${env:'+key+'}','${{ secrets.'+key+' }}'):raise ValueError('Literal MCP environment values cannot be imported')
                row['environment'].append(key)
        headers=s.get('headers',s.get('requestOptions',{}).get('headers',{}))
        for key,v in headers.items():
            match=re.fullmatch(r'Bearer (?:\$\{env:([A-Z][A-Z0-9_]*)\}|\$\{\{ secrets\.([A-Z][A-Z0-9_]*) \}\})',str(v))
            if key!='Authorization' or not match:raise ValueError('Only bearer environment references can be imported')
            row['bearer_env']=match.group(1) or match.group(2)
        if set(s)-{'command','args','env','url','headers','requestOptions','type','transport'}:losses.append('Unsupported server metadata omitted: '+str(name))
        rows.append(row)
    value={'schema':1,'id':body.get('id','imported'),'name':body.get('name','Imported toolkit'),'version':'1.0.0','mcp':rows,'rules':[]}
    for i,text in enumerate(doc.get('rules',[]) if fmt=='continue' else []):
        if not isinstance(text,str):raise ValueError('External rule references require manual review')
        value['rules'].append({'id':'rule-'+str(i+1),'description':'Imported rule','content':text})
    return {'toolkit':validate(value),'losses':losses+['Only inline rules and MCP are imported; review separate skills, commands and client metadata.']}


def _writes(root,body):
    project=plans.project(root,body.get('project'));db=plans.read(root,'toolkits.json',DEFAULT)
    ids=body.get('kits',[])
    if not isinstance(ids,list) or len(ids)>20 or len(set(ids))!=len(ids) or any(i not in db['kits'] for i in ids):raise ValueError('Select existing toolkits')
    chosen=[validate(db['kits'][i]) for i in ids];old=db['projects'].get(str(project),{'files':{},'mcp':{}});writes={};owned={}
    def file(relative,text):
        path=kit.safe_path(project,relative);before=plans.fingerprint(path)
        if before is not None and before!=old['files'].get(relative):raise ValueError('Toolkit file has local edits or another owner')
        data=text.encode();writes[path]=data;owned[relative]=digest(data)
    servers={};codex=[];rules=[]
    for value in chosen:
        for group in ('rules','skills','commands'):
            for a in value[group]:
                name='constitution-'+value['id']+'-'+a['id'];header='---\nname: '+name+'\ndescription: '+json.dumps(a['description'])+'\n---\n\n'
                if group=='rules':
                    rules.append(a['content']);file('.cursor/rules/'+name+'.mdc','---\ndescription: '+json.dumps(a['description'])+'\nalwaysApply: true\n---\n\n'+a['content']+'\n')
                if group in ('skills','commands'):
                    file('.agents/skills/'+name+'/SKILL.md',header+a['content']+'\n')
                    if group=='commands':file('.cursor/commands/'+name+'.md',header+a['content']+'\n')
        for s in value['mcp']:
            name='ai_constitution__'+value['id'].replace('-','_')+'__'+s['id'].replace('-','_')
            codex.append('[mcp_servers.'+name+']')
            if 'url' in s:
                servers[name]={'url':s['url']};codex.append('url = '+json.dumps(s['url']))
                if s.get('bearer_env'):
                    servers[name]['headers']={'Authorization':'Bearer ${env:'+s['bearer_env']+'}'};codex.append('bearer_token_env_var = '+json.dumps(s['bearer_env']))
            else:
                servers[name]={'command':s['command'],'args':s['args'],'env':{n:'${env:'+n+'}' for n in s.get('environment',[])}}
                codex += ['command = '+json.dumps(s['command']),'args = '+json.dumps(s['args']),'env_vars = '+json.dumps(s.get('environment',[]))]
            codex.append('')
    for relative in set(old['files'])-set(owned):
        path=kit.safe_path(project,relative)
        if plans.fingerprint(path)!=old['files'][relative]:raise ValueError('Removed toolkit asset has local edits')
        writes[path]=None
    for relative,text,begin,end in [('.codex/config.toml','\n'.join(codex),START,END),('AGENTS.md','\n\n'.join(rules),'<!-- ai-constitution:toolkits:begin -->','<!-- ai-constitution:toolkits:end -->')]:
        path=kit.safe_path(project,relative);plans.fingerprint(path);before=path.read_text(encoding='utf-8') if path.exists() else '';marker=old.get('blocks',{}).get(relative)
        if before.count(begin)!=before.count(end) or before.count(begin)>1:raise ValueError('Malformed toolkit managed block')
        if begin in before:
            start=before.index(begin);finish=before.index(end)+len(end);block=before[start:finish]
            if digest(block.encode())!=marker:raise ValueError('Toolkit block has local edits or another owner')
            outside=before[:start]+before[finish:]
        else:
            if marker:raise ValueError('Managed toolkit block was removed')
            outside=before
        if relative.endswith('.toml'):
            unmanaged=tomllib.loads(outside)
            if any(n in unmanaged.get('mcp_servers',{}) for n in servers):raise ValueError('MCP name already owned by client configuration')
        block=begin+'\n'+text+'\n'+end
        if begin in before:after=before[:start]+block+before[finish:]
        else:after=before+('\n' if before and not before.endswith('\n') else '')+'\n'+block+'\n'
        if relative.endswith('.toml'):tomllib.loads(after)
        writes[path]=after.encode();old.setdefault('blocks',{})[relative]=digest(block.encode())
    path=kit.safe_path(project,'.cursor/mcp.json');plans.fingerprint(path);cursor=kit.read_json(path) if path.exists() else {'mcpServers':{}}
    if not isinstance(cursor,dict) or not isinstance(cursor.get('mcpServers'),dict):raise ValueError('Invalid existing Cursor MCP configuration')
    for name,hashvalue in old['mcp'].items():
        if digest(json_bytes(cursor['mcpServers'].get(name)))!=hashvalue:raise ValueError('Cursor MCP server has local edits')
        del cursor['mcpServers'][name]
    if set(servers)&set(cursor['mcpServers']):raise ValueError('Cursor MCP server name already in use')
    cursor['mcpServers'].update(servers);writes[path]=json_bytes(cursor)
    db['projects'][str(project)]={'kits':ids,'versions':{v['id']:v['version'] for v in chosen},'files':owned,'blocks':old['blocks'],'mcp':{n:digest(json_bytes(s)) for n,s in servers.items()}}
    writes[Path(root)/'workspace/toolkits.json']=json_bytes(db)
    return project,writes


def preview(root,body):
    project,writes=_writes(root,body)
    # Existing MCP files may contain secrets: expose only hashes, never their text.
    return plans.seal({'schema':1,'project':str(project),'kits':body.get('kits',[]),'changes':[{'path':str(p.relative_to(project)) if p.is_relative_to(project) else 'private ownership journal','before':plans.fingerprint(p),'after':digest(v) if v is not None else None} for p,v in writes.items()],
                       'note':'Review toolkit content and MCP commands before trusting the project. Restart the client to verify loading; no server is started by this operation.'})


def apply(root,body,progress=lambda _:None):
    with kit.state_lock(Path(root)/'toolkit-lock'):
        value=preview(root,body);plans.verify(value,body.get('plan'));_,writes=_writes(root,body)
        return {**kit.transaction(Path(root)/'workspace/transactions',writes),'status':'installed','loading':'unverified'}


def synchronize_toolkits(control,progress=lambda _:None):
    from .studio import Studio
    from . import synchronization
    db=overview(control.root);targets=kit.state_load(Studio(control.root).state)['targets'];paused=synchronization.settings(control.root)['paused_projects'];rows=[]
    for project,value in db['projects'].items():
        target=targets.get('project:'+project)
        if not target or target['pinned'] or project in paused:continue
        try:
            body={'project':project,'kits':value['kits']};previewed=preview(control.root,body)
            changed=any(c['before']!=c['after'] for c in previewed['changes'])
            if changed:
                progress('Synchronizing owned project toolkit assets');result=apply(control.root,{**body,'plan':previewed['plan']})
                rows.append({'project':project,**result})
        except (ValueError,OSError):rows.append({'project':project,'status':'conflict','detail':'Toolkit drift or unavailable project; review its ownership and preview again.'})
    return {'projects':rows}
