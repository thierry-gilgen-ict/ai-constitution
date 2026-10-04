"""Opt-in time/application triggers with manual priority and deferred transitions."""
import csv
import io
import os
from pathlib import Path
import re
import subprocess
import time
from scripts import constitution as kit
from . import plans, routing

DEFAULT={'schema':1,'enabled':False,'rules':[],'manual_until':0,'last_transition':0,'last_result':None,'cooldown_seconds':300}


def overview(root):return plans.read(root,'profiles.json',DEFAULT)


def configure(root,body):
    with kit.state_lock(Path(root)/'profile-lock'):
        value=overview(root);rules=body.get('rules',value['rules'])
        if not isinstance(rules,list) or len(rules)>20:raise ValueError('Choose at most 20 resource rules')
        for r in rules:
            if not isinstance(r,dict) or set(r)-{'profile','applications','days','start','end'} or r.get('profile') not in ('work','gaming','fast','deep'):raise ValueError('Choose work, gaming, fast or deep')
            apps=r.get('applications',[])
            if not isinstance(apps,list) or len(apps)>20 or any(not isinstance(a,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',a) for a in apps):raise ValueError('Application triggers use executable basenames only')
            days=r.get('days',list(range(7)))
            if not isinstance(days,list) or any(type(d) is not int or not 0<=d<=6 for d in days):raise ValueError('Days range from Monday 0 through Sunday 6')
            for k in ('start','end'):
                if k in r and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',r[k]):raise ValueError('Use local 24-hour HH:MM')
            if ('start' in r)!=('end' in r):raise ValueError('Set both schedule times')
            if not apps and 'start' not in r:raise ValueError('Each rule needs a schedule or application trigger')
        enabled=body.get('enabled',value['enabled']);cooldown=body.get('cooldown_seconds',value['cooldown_seconds'])
        if type(enabled) is not bool or type(cooldown) is not int or not 60<=cooldown<=3600:raise ValueError('Choose enabled and cooldown 60–3600 seconds')
        value.update(enabled=enabled,rules=rules,cooldown_seconds=cooldown)
        if body.get('resume') is True:value['manual_until']=0
        plans.write(root,'profiles.json',value)
    return {'status':'saved','note':'Automation applies while this controller runs. First matching rule wins; outside matching rules the current profile stays active.'}


def manual(root,hours=24):
    with kit.state_lock(Path(root)/'profile-lock'):
        value=overview(root);value['manual_until']=time.time()+hours*3600;plans.write(root,'profiles.json',value)


def applications():
    try:
        if os.name=='nt':
            out=subprocess.run(['tasklist.exe','/FO','CSV','/NH'],capture_output=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout
            if len(out)>1024*1024:return None
            return {row[0].casefold() for row in csv.reader(io.StringIO(out.decode(errors='replace'))) if row}
        out=subprocess.run(['ps','-axo','comm='],capture_output=True,timeout=5).stdout
        if len(out)>1024*1024:return None
        return {Path(s).name.casefold() for s in out.decode(errors='replace').splitlines()}
    except (OSError,subprocess.TimeoutExpired):return None


def desired(value,clock,apps):
    for r in value['rules']:
        if clock.tm_wday not in r.get('days',range(7)):continue
        if r.get('applications') and (apps is None or not {a.casefold() for a in r['applications']}&apps):continue
        if 'start' in r:
            now=time.strftime('%H:%M',clock);start,end=r['start'],r['end']
            if not (start<=now<end if start<end else now>=start or now<end):continue
        return r['profile']
    return None


def apply_profile(control,profile,progress=lambda _:None):
    if profile in ('work','gaming'):return control.switch(profile,progress=progress)
    return routing.configure(control,{'profile':profile},progress=progress)


def automatic_profile(control,progress=lambda _:None):
    with kit.state_lock(control.root/'profile-lock'):
        value=overview(control.root);now=time.time()
        if not value['enabled'] or now<value['manual_until'] or now-value['last_transition']<value['cooldown_seconds']:return {'status':'held'}
        target=desired(value,time.localtime(),applications() if any(r.get('applications') for r in value['rules']) else set())
        current=control.mode if target in ('work','gaming') else control.config.get('task_profile','deep')
        if not target or current==target:return {'status':'current'}
        # Avoid blocking maintenance threads behind active leases or administration.
        with control.lock:
            if control.active and any(control.active.values()) or control.queued or control.admin_nodes:
                result={'status':'deferred','profile':target,'note':'Active work retains its route; retry on a later maintenance tick.'}
                value['last_result']=result;plans.write(control.root,'profiles.json',value);return result
        result=apply_profile(control,target,progress);value.update(last_transition=now,last_result=result);plans.write(control.root,'profiles.json',value)
        return result
