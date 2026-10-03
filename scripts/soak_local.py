"""Read-only acceptance monitor. Run explicitly against your own controller.

Never switches routes, unloads models or submits inference; records counts only.
"""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_control.storage import load, atomic, private_root
from local_control import locations
from local_control.transport import request


def sample(root):
    config=load(root); runtime=json.loads((root/'runtime.json').read_text(encoding='utf-8'))
    endpoint={'url':runtime['url'],'kind':'ollama','token':config['token']}
    status=request(endpoint,'/api/status',timeout=5)
    workers=[]
    for node in config['nodes'].values():
        if node['kind']!='worker':continue
        try:
            value=request(node,'/diagnostics',timeout=5)
            workers.append({'status':'online','version':value.get('version'),'platform':value.get('platform'),
                'active_requests':value.get('active_requests')})
        except (OSError,ValueError):workers.append({'status':'unavailable'})
    return {'time':time.time(),'controller':'online','active_requests':status['active_requests'],
        'queued_requests':status['queued_requests'],'open_sessions':sum(s['status']=='open' for s in status['sessions']),
        'unresolved_operations':len(status.get('notifications',[])),'workers':workers}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,default=private_root())
    parser.add_argument('--hours',type=float,default=48)
    parser.add_argument('--interval',type=int,default=60)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 0 < args.hours <= 168 or not 10 <= args.interval <= 3600: parser.error('Use up to 168 hours and a 10–3600 second interval')
    root=locations.resolve_root(args.state_dir)
    deadline=time.monotonic()+args.hours*3600
    report={'schema':1,'started':time.time(),'requested_hours':args.hours,'samples':[],
        'scope':'Read-only availability observations. Does not certify GPU stability, model quality or uninterrupted client work.'}
    while True:
        try: value=sample(root)
        except (OSError,ValueError):value={'time':time.time(),'controller':'unavailable'}
        report['samples'].append(value);report['updated']=time.time()
        report['complete']=time.monotonic()>=deadline
        atomic(args.output.absolute(),report)
        if report['complete']:break
        time.sleep(min(args.interval,max(.1,deadline-time.monotonic())))
    print(json.dumps({'status':'complete','samples':len(report['samples']),
        'controller_unavailable':sum(v['controller']!='online' for v in report['samples'])}))


if __name__=='__main__':main()
