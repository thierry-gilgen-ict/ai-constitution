"""Private acceptance receipts and optional fixed read-only GitHub checks."""
import json
import math
import re
import shutil
import subprocess
import time
import uuid
from .audit_store import Store
from .audit_review import SECRET
from scripts import audit


def receipt(root,body):
    allowed={'task','revision','artifact','account','states','evidence','actual_charge','currency','attempts','elapsed_seconds'}
    if not isinstance(body,dict) or set(body)-allowed or len(json.dumps(body))>16000 or SECRET.search(json.dumps(body)):raise ValueError('Invalid or sensitive acceptance receipt')
    if any(not isinstance(body.get(k,''),str) or len(body.get(k,''))>500 for k in ('task','revision','artifact','account','currency')) or not body.get('task'):raise ValueError('Receipt needs a bounded task ID')
    states=body.get('states',{})
    allowed_states={'implemented','reviewed','integrated','deployed','verified','business_accepted'}
    if not isinstance(states,dict) or set(states)-allowed_states or any(v not in ('observed','reported','not-applicable','unknown') for v in states.values()):raise ValueError('Use independently evidenced receipt states')
    for key in ('actual_charge','attempts','elapsed_seconds'):
        val=body.get(key)
        if val is not None and (type(val) not in (int,float) or not math.isfinite(val) or val<0):raise ValueError('Receipt measurements must be nonnegative or unknown')
    evidence=body.get('evidence',[])
    if not isinstance(evidence,list) or len(evidence)>30 or any(not isinstance(s,str) or len(s)>500 for s in evidence):raise ValueError('Use bounded evidence references')
    value={'schema':1,'id':uuid.uuid4().hex[:24],'created_at':time.time(),**body,'provenance':'explicit operator record; no invoice or subscription inference'}
    Store(root).put('receipt',value['id'],value);return value


def github(root,body,*,runner=subprocess.run):
    repository=body.get('repository','')
    if not re.fullmatch('[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',repository):raise ValueError('Choose an explicit owner/repository')
    executable=shutil.which('gh')
    if not executable:return {'status':'unknown','reason':'GitHub CLI unavailable'}
    def get(endpoint):
        result=runner([executable,'api','--method','GET',endpoint],capture_output=True,timeout=20)
        if result.returncode or len(result.stdout)>1024*1024:raise ValueError('GitHub read unavailable')
        return json.loads(result.stdout)
    try:
        repo=get('repos/'+repository);branch=repo['default_branch']
        if not re.fullmatch('[A-Za-z0-9_./-]{1,200}',branch):raise ValueError('Unsupported default branch')
        from urllib.parse import quote
        rules=get('repos/'+repository+'/rules/branches/'+quote(branch,safe=''))
        classic=None
        try:classic=get('repos/'+repository+'/branches/'+quote(branch,safe='')+'/protection')
        except (ValueError,OSError,subprocess.SubprocessError):pass
        pulls=get('repos/'+repository+'/pulls?state=open&per_page=100')
        reviews=[r.get('parameters',{}).get('required_approving_review_count',0) for r in rules if r.get('type')=='pull_request']
        checks=[c.get('context') for r in rules if r.get('type')=='required_status_checks' for c in r.get('parameters',{}).get('required_status_checks',[])]
        if classic:
            reviews.append((classic.get('required_pull_request_reviews') or {}).get('required_approving_review_count',0))
            checks.extend((classic.get('required_status_checks') or {}).get('contexts',[]))
        value={'schema':1,'id':repository,'observed_at':time.time(),'status':'observed','default_branch':branch,'required_reviews':max(reviews,default=0) if classic is not None else None,'ruleset_reviews':max(reviews,default=0),'classic_protection':'observed' if classic is not None else 'unknown',
               'required_checks':checks,'open_candidates':len(pulls),'truncated':len(pulls)==100,
               'candidates':[{'number':p['number'],'draft':p.get('draft'),'created_at':p.get('created_at'),'updated_at':p.get('updated_at'),'head':p.get('head',{}).get('sha')} for p in pulls],
               'note':'Read-only observable rules; unavailable inherited/classic controls and billing remain unknown.'}
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError):value={'schema':1,'id':repository,'observed_at':time.time(),'status':'unknown','reason':'Rules or repository access unavailable; no admin changes attempted'}
    project=body.get('project');expectations={}
    days=body.get('age_days',30)
    if type(days) is not int or not 1<=days<=3650:raise ValueError('Choose a bounded candidate age threshold')
    if project:
        from .auditing import current_scope
        path=audit.absolute(project)
        scope=current_scope(root)
        if str(path) not in scope['projects'] and not any(path.is_relative_to(__import__('pathlib').Path(r)) for r in scope['roots']):raise ValueError('Choose a project inside the selected audit scope')
        metadata=path/'.ai/governance.json'
        if metadata.is_file():expectations=audit.governance(audit.document(metadata))
        value['project']=str(path)
    value['findings']=compare_controls(value,expectations,age_days=days)
    Store(root).put('github',repository,value);return value


def compare_controls(value,expectations,*,age_days=30,now=None):
    """Compare documented expectations only with evidence actually returned."""
    from datetime import datetime,timezone
    now=time.time() if now is None else now
    findings=[]
    def add(code,detail,evidence='verified'):findings.append({'code':code,'detail':detail,'evidence':evidence})
    if value.get('status')!='observed':return [{'code':'github-coverage','detail':'Repository controls unavailable','evidence':'unknown'}]
    required=expectations.get('required_reviews')
    if required is not None:
        observed=value.get('required_reviews')
        if observed is None:add('review-enforcement-unknown','Classic or inherited review controls unavailable','unknown')
        elif observed<required:add('review-enforcement-gap','Observable review requirement is below the documented expectation')
    missing=set(expectations.get('required_checks',[]))-set(value.get('required_checks',[]))
    if missing:add('check-enforcement-gap','Expected checks not observed: '+', '.join(sorted(missing)),'unknown' if value.get('classic_protection')=='unknown' else 'verified')
    if 'wip_limit' in expectations and value.get('open_candidates',0)>expectations['wip_limit']:add('wip-threshold','Observed open candidates exceed the configured WIP threshold')
    aged=0
    for candidate in value.get('candidates',[]):
        try:
            if now-datetime.fromisoformat(candidate['created_at'].replace('Z','+00:00')).timestamp()>age_days*86400:aged+=1
        except (ValueError,KeyError,TypeError):add('candidate-age-unknown','Candidate creation time unavailable','unknown')
    if aged:add('aged-candidates',f'{aged} open candidates exceed the selected {age_days}-day age threshold')
    if value.get('truncated'):add('candidate-coverage','Candidate list truncated at one hundred','unknown')
    return findings
