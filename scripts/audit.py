"""Read-only instruction inventory. Never execute project code or initialize installs."""
from __future__ import annotations
import configparser
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import time
import tomllib
if __package__:
    from . import clients, claude_audit
else:
    import clients, claude_audit
if __package__:
    from .paths import no_links, is_link
else:
    from paths import no_links, is_link

SCHEMA = 1
ENGINE = '1.1'
SKIP = {'.git', '.local', 'node_modules', '.venv', 'venv', 'vendor', 'dist', 'build', '__pycache__'}
NAMES = {'AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md', 'CLAUDE.local.md', '.cursorrules', 'ROUTING.md',
         'routing.md', 'STATE.md', 'CHECKLIST.md', 'constitution.md', 'engineering.md',
         'research.md', 'maintenance.md', 'governance.json', 'policy.json', 'VERSION'}
BEGIN, END = '<!-- ai-constitution:begin -->', '<!-- ai-constitution:end -->'
MAX_SAMPLE = 65536
SENSITIVE=re.compile(r'''(?:sk-[A-Za-z0-9_-]{15,}|(?:ghp_|github_pat_|xai-)[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{15,}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b[A-Za-z0-9_-]*(?:api[_-]?key|password|secret|token)[A-Za-z0-9_-]*["']?\s*[:=]\s*["']?[A-Za-z0-9_+/=.-]{12,})''',re.I)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def target_id(target):
    key=[target['root'],target['kind']]
    if target.get('claude_dir'):key.append(target['claude_dir'])
    return identity(key)[:24]


def absolute(value):
    if isinstance(value,str) and not value.strip():raise ValueError('Choose a non-empty path')
    path = Path(value).expanduser().absolute()
    no_links(path)
    path=Path(os.path.normpath(str(path)))
    no_links(path)
    return path


def document(path, limit=2 * 1024 * 1024):
    no_links(path)
    if not path.exists(): return {}
    if not path.is_file() or path.stat().st_size > limit: raise ValueError('Metadata exceeds its bound')
    return json.loads(path.read_text(encoding='utf-8'))


def fingerprint(path):
    no_links(path)
    if not path.exists(): return None
    if not path.is_file(): raise ValueError('Instruction must be an ordinary file')
    if path.stat().st_size>64*1024*1024:raise ValueError('Instruction exceeds the bounded hash size')
    hash_value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''): hash_value.update(block)
    return hash_value.hexdigest()


def sample(path):
    no_links(path)
    before = path.stat()
    if before.st_size>64*1024*1024:raise ValueError('Instruction exceeds the bounded hash size')
    hash_value, chunks, size = hashlib.sha256(), [], 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            hash_value.update(block)
            if size < MAX_SAMPLE: chunks.append(block[:MAX_SAMPLE-size])
            size += len(block)
    after = path.stat()
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError('Instruction changed during inspection')
    return hash_value.hexdigest(), size, b''.join(chunks).decode('utf-8', errors='replace')


def governance(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('Governance needs schema_version 1')
    allowed = {'schema_version', 'delivery_profile', 'risk', 'acceptance', 'owner_roles', 'wip_limit', 'exceptions', 'required_checks', 'required_reviews'}
    if set(value)-allowed: raise ValueError('Unknown governance setting')
    if value.get('delivery_profile', 'standard') not in ('lightweight', 'standard', 'high-risk'):
        raise ValueError('Unknown delivery profile')
    if value.get('risk', 'medium') not in ('low', 'medium', 'high', 'critical'): raise ValueError('Unknown risk')
    for key in ('acceptance', 'owner_roles', 'required_checks'):
        entries = value.get(key, [])
        if not isinstance(entries, list) or len(entries)>30 or any(not isinstance(x,str) or len(x)>500 for x in entries):
            raise ValueError('Governance lists must contain bounded text')
    for key in ('wip_limit', 'required_reviews'):
        if key in value and (type(value[key]) is not int or not 0 <= value[key] <= 100): raise ValueError('Invalid governance limit')
    entries=value.get('exceptions', [])
    if not isinstance(entries,list) or len(entries)>100: raise ValueError('Too many exceptions')
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)-{'id','reason','owner_role','scope','review_date','evidence'}:
            raise ValueError('Invalid exception')
        if any(not isinstance(entry.get(k),str) or not 1<=len(entry[k])<=500 for k in ('id','reason','owner_role','scope','review_date')):
            raise ValueError('Exception needs reason, owner, scope and review date')
        from datetime import date
        date.fromisoformat(entry['review_date'])
    return value


def default_profiles(home=None):
    base=Path(home or Path.home()).absolute()
    return [{'id':key,'client':key,'home':str(clients.directory(key, home))} for key in clients.CLIENTS]


def scope(value, *, home=None):
    if not isinstance(value,dict) or set(value)-{'roots','projects','profiles','canonical','state','files','max_directories','max_projects'}:
        raise ValueError('Unknown audit scope')
    result = dict(value)
    for key in ('roots','projects','files'):
        entries=result.get(key,[])
        if not isinstance(entries,list) or len(entries)>200 or any(not isinstance(v,str) for v in entries): raise ValueError('Invalid audit targets')
        result[key]=list(dict.fromkeys(str(absolute(v)) for v in entries))
    profiles=result.get('profiles')
    defaults=profiles is None
    if defaults:profiles=default_profiles(home)
    if not isinstance(profiles,list) or len(profiles)>20: raise ValueError('Choose up to twenty profiles')
    seen=set()
    for entry in profiles:
        if not isinstance(entry,dict) or set(entry)-{'id','client','home','cwd','account_rules','files','client_version'} or entry.get('client') not in clients.CLIENTS:
            raise ValueError('Invalid client profile')
        if not re.fullmatch('[a-zA-Z0-9_-]{1,64}',entry.get('id','')) or entry['id'] in seen: raise ValueError('Use unique profile IDs')
        seen.add(entry['id'])
        if 'client_version' in entry and (not isinstance(entry['client_version'],str) or len(entry['client_version'])>100):raise ValueError('Use a bounded client version')
        if not defaults:
            if not isinstance(entry.get('home'),str) or not entry['home']:raise ValueError('Choose a profile directory')
            entry['home']=os.path.normpath(str(Path(entry['home']).expanduser().absolute()))
        if entry.get('cwd'):entry['cwd']=str(absolute(entry['cwd']))
        if not isinstance(entry.get('files',[]),list) or len(entry.get('files',[]))>30: raise ValueError('Invalid profile file selection')
        for p in entry.get('files',[]):
            absolute(p)
            if Path(p).suffix not in ('.md','.mdc','.txt'):raise ValueError('Select instruction text files')
        entry['files']=[str(absolute(p)) for p in entry.get('files',[])]
        if entry.get('account_rules'):
            entry['account_rules']=str(absolute(entry['account_rules']))
            if Path(entry['account_rules']).suffix not in ('.md','.mdc','.txt'):raise ValueError('Account-rule imports must be instruction text')
    result['profiles']=profiles
    for key in ('canonical','state'):
        if result.get(key): result[key]=str(absolute(result[key]))
    for key,default,upper in [('max_directories',5000,50000),('max_projects',200,2000)]:
        count=result.get(key,default)
        if type(count) is not int or not 1<=count<=upper: raise ValueError('Invalid discovery limit')
        result[key]=count
    return result


def scan(request, *, home=None, now=None, progress=lambda _:None, ownership=None):
    cfg=scope(request,home=home); now=time.time() if now is None else now
    report={'schema':SCHEMA,'engine':ENGINE,'observed_at':now,'application_version':None,'canonical_release':None,
            'scope':cfg,'projects':[],'profiles':[],'sources':[],'chains':[],'findings':[],
            'coverage':{'complete':True,'gaps':[],'exclusions':[],'directories':0},'client_loading':'unverified'}
    source_map, contents, projects = {}, {}, set(cfg['projects'])
    def finding(code,detail,source=None,*,severity='warning',evidence='verified',target=None,related=None):
        signature=identity([code,(source or {}).get('id'),target,detail])[:24]
        report['findings'].append({'id':signature,'code':code,'detail':detail,'severity':severity,'evidence':evidence,
            'source':(source or {}).get('id'),'location':(source or {}).get('path'),'target':target,
            'fingerprint':identity([(source or {}).get('sha256'),detail,related]),'evidence_fingerprints':related or [],'disposition':'open'})
    def gap(path,reason):
        report['coverage']['complete']=False
        report['coverage']['gaps'].append({'path':str(path),'reason':reason})
        finding('coverage',reason,target=str(path),evidence='unknown')
    def walk(base, discovery=False):
        if not base.is_dir(): gap(base,'Folder unavailable');return
        def walk_error(error): gap(getattr(error,'filename',base),'Folder inaccessible')
        for folder,dirs,files in os.walk(base,followlinks=False,onerror=walk_error):
            if len(source_map)>=2000:gap(base,'Instruction source limit reached');return
            report['coverage']['directories']+=1
            if report['coverage']['directories']>cfg['max_directories']: gap(base,'Directory limit reached');return
            path=Path(folder)
            for name in sorted(set(dirs)&SKIP):
                if len(report['coverage']['exclusions'])<1000:report['coverage']['exclusions'].append({'path':str(path/name),'reason':'Dependency, metadata or build directory excluded'})
                elif not report['coverage'].get('exclusions_truncated'):
                    report['coverage']['exclusions_truncated']=True;gap(base,'Exclusion details truncated at one thousand entries')
            dirs[:]=sorted(d for d in dirs if d not in SKIP)
            for name in list(dirs):
                if is_link(path/name): dirs.remove(name);gap(path/name,'Linked directory excluded')
            if discovery:
                for d in dirs:
                    if len((path/d).relative_to(base).parts)>4:gap(path/d,'Search-root discovery depth limit excludes this directory')
                dirs[:]=[d for d in dirs if len((path/d).relative_to(base).parts)<=4]
                if '.git' in files or (path/'.git').is_dir() or (path/'.ai/project.md').is_file(): projects.add(str(path))
                if len(projects)>=cfg['max_projects']: gap(base,'Project limit reached');return
            else:
                for name in sorted(files):
                    p=path/name; relative=p.relative_to(base)
                    if name in NAMES or '.cursor' in relative.parts and p.suffix in ('.mdc','.md') or '.ai' in relative.parts and p.suffix=='.md' or '.claude' in relative.parts and 'rules' in relative.parts and p.suffix=='.md':
                        add(p,base,'project')
    def add(path,base,kind):
        key=str(path)
        if key in source_map:return source_map[key]
        if len(source_map)>=2000:return None
        progress('Inspecting an instruction source')
        try:
            if not path.exists():return None
            sha,size,body=sample(path)
        except (ValueError,OSError):gap(path,'File inaccessible, linked, changed or above the 64 MiB bound');return None
        name=path.name; classification='project-guidance' if kind=='project' else 'client-specific'
        if BEGIN in body:classification='managed-replica'
        if name in ('STATE.md','CHECKLIST.md'):classification='task-state'
        if any(v.casefold() in ('archive','archives','history') for v in path.parts):classification='historical'
        if kind=='canonical':classification='canonical'
        release=re.search(r'AI Constitution v([^\s]+)',body)
        source={'id':identity(key)[:24],'path':key,'name':name,'root':str(base),'kind':kind,'classification':classification,
                'sha256':sha,'bytes':size,'sampled':size>MAX_SAMPLE,'release':release.group(1) if release else None,'references':[]}
        source['sensitive']=bool(SENSITIVE.search(body))
        source_map[key]=source;contents[source['id']]='' if source['sensitive'] else body;report['sources'].append(source)
        if source['sensitive']:finding('sensitive-instructions','Potential credential material requires private local review; excerpts withheld',source,severity='warning')
        if size>24000:finding('large-instruction','Large instruction source; assess applicability before shortening',source,severity='review',evidence='suspected')
        if source['sampled']:gap(path,'Content sampled; size and fingerprint cover the full file')
        if name=='.cursorrules':finding('legacy-rule','Legacy Cursor entry point; review migration',source,severity='review')
        if '.cursor' in path.parts and 'rules' in path.parts and path.suffix=='.md':finding('unsupported-rule-format','Cursor project rules require .mdc; plain Markdown here is not automatically loaded',source)
        if path.suffix=='.mdc':
            front=re.match(r'^---\s*\n(.*?)\n---',body,re.S)
            if not front:finding('invalid-rule','Cursor rule needs supported frontmatter',source)
            else:
                fields={m[0]:m[1].strip().strip('"\'') for m in re.findall(r'^(description|globs|alwaysApply):\s*(.*?)$',front.group(1),re.M)}
                fields={k:v for k,v in fields.items() if not SENSITIVE.search(v)}
                source['rule']=fields
                if fields.get('alwaysApply','').lower() not in ('','true','false'):finding('invalid-rule','Invalid alwaysApply value',source)
        return source
    for root in cfg['roots']:walk(absolute(root),True)
    for p in sorted(projects)[:cfg['max_projects']]:
        progress('Inspecting a project instruction scope')
        path=absolute(p)
        record={'id':identity(p)[:24],'path':p,'name':path.name,'repository_id':identity(p)[:24],'git':False}
        repository=path
        if not (path/'.git').exists():
            for parent in list(path.parents)[:20]:
                try:no_links(parent)
                except (OSError,ValueError):gap(path,'Ancestor repository discovery unavailable');break
                if (parent/'.git').exists():
                    if any(parent.is_relative_to(Path(r)) for r in [*cfg['roots'],*cfg['projects']]):repository=parent
                    else:gap(path,'Ancestor repository instructions are outside selected scope')
                    break
        record['resolution_root']=str(repository)
        git=repository/'.git'
        try:
            if git.is_file():
                with git.open('r',encoding='utf-8') as stream:text=stream.read(4096)
                if not text.startswith('gitdir: '):raise ValueError()
                git=absolute(path/text[8:].strip())
            if git.is_dir():
                no_links(git);record['git']=True
                if not any(git.is_relative_to(Path(r)) for r in [*cfg['roots'],*cfg['projects']]):
                    gap(path,'Worktree metadata is outside selected roots')
                    raise ValueError()
                head=git/'HEAD';no_links(head)
                with head.open('r',encoding='utf-8') as stream:revision=stream.read(200).strip()
                record['revision']=revision if re.fullmatch(r'(?:[a-fA-F0-9]{40,64}|ref: refs/[a-zA-Z0-9_./-]{1,150})',revision) else 'unknown'
                common=git/'commondir';no_links(common)
                if common.exists():git=absolute(git/common.read_text()[:4096].strip())
                record['repository_id']=identity(str(git))[:24]
        except (OSError,ValueError):gap(path,'Git metadata unavailable')
        report['projects'].append(record);walk(path)
        gov=path/'.ai/governance.json'
        if gov.exists():
            try:
                value=governance(document(gov))
                if not SENSITIVE.search(json.dumps(value)):record['governance']=value
                from datetime import datetime,timezone
                today=datetime.fromtimestamp(now,timezone.utc).date().isoformat()
                for e in value.get('exceptions',[]):
                    if e['review_date']<today:finding('expired-exception','Governance exception needs review',source_map.get(str(gov)),target=record['id'])
                if not value.get('acceptance'):finding('acceptance-unspecified','No explicit acceptance criteria recorded',source_map.get(str(gov)),severity='review')
            except (ValueError,OSError):finding('invalid-governance','Governance metadata is invalid',target=record['id'])
    for filename in cfg['files']:add(absolute(filename),absolute(filename).parent,'canonical')
    if cfg.get('canonical'):
        base=absolute(cfg['canonical']); version=base/'VERSION'
        if version.is_file():
            release=version.read_text().strip()[:80]
            if re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?',release):report['canonical_release']=release
            else:gap(base,'Canonical release metadata is invalid')
        for name in ('constitution.md','engineering.md','research.md','maintenance.md','routing.md'):add(base/name,base,'canonical')
    for profile in cfg['profiles']:
        client=profile['client'];entry=dict(profile)
        try:base=absolute(profile['home'])
        except (OSError,ValueError):
            entry.update(configuration='unavailable',loading='unverified');report['profiles'].append(entry)
            gap(profile['home'],'Profile directory is unavailable or traverses a link');continue
        entry.update(configuration='available' if base.exists() else 'unavailable',loading='unverified')
        try:entry['configuration_fingerprint']=identity([profile,fingerprint(base/'config.toml') if client=='codex' and (base/'config.toml').is_file() else None])
        except (OSError,ValueError):entry['configuration_fingerprint']=None;gap(base,'Profile configuration is unavailable')
        report['profiles'].append(entry);fallbacks=[];cap=32768
        if client=='claude-code':
            claude_audit.resolve(profile, entry, cfg, report, add, gap, finding, contents, absolute, fingerprint, document, identity)
            continue
        if client=='codex':
            config=base/'config.toml'
            try:
                no_links(config)
                if config.exists():
                    if config.stat().st_size>2*1024*1024:raise ValueError()
                    options=tomllib.loads(config.read_text(encoding='utf-8'))
                    fallbacks=options.get('project_doc_fallback_filenames',[]);cap=options.get('project_doc_max_bytes',32768)
                    if not isinstance(fallbacks,list) or len(fallbacks)>30 or any(not isinstance(n,str) or Path(n).name!=n for n in fallbacks) or type(cap) is not int or not 1<=cap<=16*1024*1024:raise ValueError()
            except (ValueError,OSError):gap(config,'Codex configuration cannot be interpreted');fallbacks=[];cap=32768
            global_candidates=[add(base/name,base,'global') for name in ('AGENTS.override.md','AGENTS.md')]
        else:
            global_candidates=[]
            rules=base/'rules'
            if rules.is_dir():
                for path in sorted(rules.glob('*.mdc')):global_candidates.append(add(path,base,'global'))
            if profile.get('account_rules'):global_candidates.append(add(absolute(profile['account_rules']),base,'global'))
            else:gap(base,'Cursor account and team rules not independently collected')
        for filename in profile.get('files',[]):global_candidates.append(add(absolute(filename),base,'global'))
        for project in report['projects'] or [{'id':None,'path':str(base)}]:
            chain=[];used=0
            def include(src,status='expected'):
                nonlocal used
                if not src or not src['bytes']:return
                if client=='codex' and status=='expected' and used+src['bytes']>cap:
                    finding('loading-limit','Combined instruction chain exceeds configured byte limit',src,target=profile['id']+':'+str(project['id']))
                    status='truncated';used=cap
                elif status=='expected':used+=src['bytes']
                chain.append({'source':src['id'],'status':status,'bytes':src['bytes']})
            present=[s for s in global_candidates if s and s['bytes']]
            for i,s in enumerate(present):
                status='shadowed' if client=='codex' and i>0 else 'expected'
                if client=='cursor' and Path(s['path']).suffix=='.mdc':status='configuration-file; applicability unknown'
                include(s,status)
            root=absolute(project.get('resolution_root',project['path']));cwd=absolute(profile.get('cwd',project['path']))
            if not cwd.is_relative_to(root):gap(cwd,'Working directory is outside this project');continue
            if not cwd.is_dir():gap(cwd,'Working directory is unavailable');continue
            if client=='codex':
                parents=[root]
                for part in cwd.relative_to(root).parts:parents.append(parents[-1]/part)
                for directory in parents:
                    candidates=[add(directory/name,root,'project') for name in ['AGENTS.override.md','AGENTS.md',*fallbacks]]
                    present=[s for s in candidates if s and s['bytes']]
                    for i,s in enumerate(present):
                        include(s,'expected' if i==0 else 'shadowed')
                        if i:finding('shadowed-entry','An earlier entry point shadows this instruction file',s,target=profile['id'])
            else:
                for src in list(report['sources']):
                    path=Path(src['path'])
                    if src['kind']!='project' or not path.is_relative_to(root):continue
                    if src['name']=='AGENTS.md' and cwd.is_relative_to(path.parent):include(src)
                    elif src['name']=='CLAUDE.md' and cwd.is_relative_to(path.parent):include(src,'unsupported-entry')
                    elif src['name']=='.cursorrules' and path.parent==root:include(src,'legacy')
                    elif path.suffix=='.mdc':
                        parts=path.relative_to(root).parts
                        if '.cursor' not in parts or 'rules' not in parts:include(src,'unsupported-entry');continue
                        directory=root.joinpath(*parts[:parts.index('.cursor')])
                        include(src,'expected' if src.get('rule',{}).get('alwaysApply','').lower()=='true' and cwd.is_relative_to(directory) else 'conditional')
            report['chains'].append({'profile':profile['id'],'client':client,'project':project['id'],'cwd':str(cwd),'sources':chain,'expected_bytes':used,'limit':cap if client=='codex' else None,'configuration_fingerprint':entry['configuration_fingerprint'],'loading':'unverified'})
    for chain in report['chains']:
        seen={};duplicates=0;replicas=0;positive={};negative={}
        for item in chain['sources']:
            if item['status']!='expected':continue
            src=next(s for s in report['sources'] if s['id']==item['source'])
            if src['classification']=='historical':finding('history-active','Historical instructions appear in an expected active chain',src,evidence='suspected',severity='review')
            for line in contents[src['id']].splitlines()[:2000]:
                normalized=re.sub(r'\s+',' ',line.strip().lstrip('-* '))
                if len(normalized)<40:continue
                old=seen.get(normalized)
                if old and old!=src['id']:
                    prior=next(s for s in report['sources'] if s['id']==old)
                    if src['classification']==prior['classification']=='managed-replica' and src.get('release')==prior.get('release'):replicas+=1
                    else:duplicates+=1
                seen[normalized]=src['id']
                match=re.match(r'(Always|Never)\s+(.+)',normalized,re.I)
                if match:
                    destination=positive if match[1].casefold()=='always' else negative
                    destination[match[2].casefold()]=src
        chain['repeated_clauses']=duplicates
        chain['replicated_managed_clauses']=replicas
        if duplicates:finding('repeated-context',f'{duplicates} exact clauses repeat in this applicable chain; managed replicas may be intentional',target=chain['profile']+':'+str(chain['project']),evidence='suspected',severity='review',related=[s['sha256'] for s in report['sources'] if s['id'] in {c['source'] for c in chain['sources']}])
        for text in positive.keys() & negative.keys():finding('potential-conflict','Overlapping always/never statements need contextual review',negative[text],target=chain['profile']+':'+identity(text)[:16],evidence='suspected',severity='review',related=[positive[text]['sha256'],negative[text]['sha256']])
    if cfg.get('canonical'):
        try:
            models=document(Path(cfg['canonical'])/'registry/models.json').get('models',[])
            known={m['key']:m['surface'] for m in models}
            for project in report['projects']:
                path=Path(project['path'])/'.ai/policy.json'
                if not path.exists():continue
                value=document(path)
                if value.get('schema_version')!=1:raise ValueError()
                for route in value.get('routes',[]):
                    if route.get('task') not in ('small','implementation','deep','review','research','operational') or any(known.get(k)!=route.get('platform') for k in [route.get('preferred'),*route.get('fallbacks',[])] if k is not None):
                        finding('invalid-route','Project route references unsupported taxonomy or selector',source_map.get(str(path)))
        except (ValueError,OSError,TypeError,KeyError):gap(cfg['canonical'],'Routing validation unavailable')
    # References are metadata, never implicit permission to traverse or execute.
    for src in list(report['sources']):
        body=contents[src['id']]
        references=re.findall(r'\[[^\]]*\]\(([^)]+)\)',body)+re.findall(r'`([^`\n]+\.(?:md|mdc))`',body)
        for ref in list(dict.fromkeys(references))[:100]:
            ref=ref.strip('<>').split('#')[0]
            if not ref or '://' in ref or '*' in ref:continue
            path=Path(src['path']).parent/ref
            status='referenced'
            try:
                path=absolute(path)
                if not path.is_relative_to(Path(src['root'])):status='outside-scope'
                elif not path.exists():status='missing';finding('broken-reference','Referenced instruction is missing',src,target=ref)
            except (ValueError,OSError):status='unavailable'
            src['references'].append({'reference':ref,'status':status})
    supplied_ownership=ownership
    ownership={}
    if cfg.get('state') or supplied_ownership is not None:
        try:
            database=supplied_ownership if supplied_ownership is not None else document(absolute(cfg['state'])/'installations.json')
            if database and database.get('schema_version')!=1:raise ValueError()
            for target in database.get('targets',{}).values():
                base=absolute(target['root'])
                if target['kind']=='project' and str(base) not in projects:continue
                if target['kind'] in clients.CLIENTS and not any(p['client']==target['kind'] and (Path(p['home'])==Path(target.get('claude_dir') or clients.directory(target['kind'], base)) or target.get('cursor_dir') and Path(p['home'])==Path(target['cursor_dir'])) for p in cfg['profiles']):continue
                for relative,expected in target.get('files',{}).items():
                    path=absolute(base/relative)
                    if target.get('cursor_dir') and relative.startswith('.cursor/'):path=absolute(Path(target['cursor_dir'])/relative[8:])
                    if target.get('claude_dir') and relative.startswith('.claude/'):path=absolute(Path(target['claude_dir'])/relative[8:])
                    if not path.is_relative_to(base) and not target.get('cursor_dir') and not target.get('claude_dir'):raise ValueError()
                    src=add(path,base,'project' if target['kind']=='project' else 'global')
                    current=fingerprint(path)
                    if expected.get('managed') and current:
                        raw=path.read_bytes()
                        start,end=raw.find(BEGIN.encode()),raw.find(END.encode())
                        if raw.count(BEGIN.encode())!=1 or raw.count(END.encode())!=1 or end<start:current=None
                        else:current=hashlib.sha256(raw[start:end+len(END)].replace(b'\r\n',b'\n')).hexdigest()
                    state='missing' if not path.exists() else 'current' if current==expected['sha256'] else 'modified'
                    ownership[str(path)]={'target':target['root'],'kind':target['kind'],'pinned':target.get('pinned',False),'installed_release':target['version'],'integrity':state}
                    if src:src['ownership']=ownership[str(path)]
                    if state!='current':finding('installation-'+state,'Managed file is '+state,src,target=str(path),related=[expected['sha256']])
                if report['canonical_release'] and target['version']!=report['canonical_release']:
                    finding('release-difference','Installed release differs from canonical release'+(' (deliberate pin)' if target.get('pinned') else ''),target=target['root'],severity='review')
        except (ValueError,OSError,KeyError,TypeError):gap(cfg.get('state','local ownership'),'Ownership metadata unavailable or invalid')
    report['ownership']=ownership
    report['id']=identity([now,cfg,[s['sha256'] for s in report['sources']]])[:24]
    report['content_fingerprint']=identity([[(s['path'],s['sha256']) for s in report['sources']],[(p['id'],p.get('configuration_fingerprint')) for p in report['profiles']],cfg,report['ownership'],[(f['id'],f['fingerprint']) for f in report['findings']],report['coverage']])
    report['findings']=list({f['id']:f for f in report['findings']}.values())
    return report
