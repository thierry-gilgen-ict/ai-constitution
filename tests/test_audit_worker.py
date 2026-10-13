"""Loopback worker acceptance; no actual computer, model, or account access."""
import json
import threading
import time
import urllib.request
import urllib.error
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_workspace_workflows import Fixture
from local_control import auditing,credentials
from local_control.server import Server


class Worker(Fixture):
    def setUp(self):
        super().setUp();self.control_value=self.control()
        code=credentials.create_pairing(self.control_value.config)
        # The one-use value is intentionally confined to fixture memory.
        self.control_value.config['pairing']=None
        record={'name':'Fixture controller','management_hash':credentials.hashed('fixture-management'),
                'inference_hash':credentials.hashed('fixture-inference'),'created':time.time()}
        self.control_value.config['controllers']['fixture']=record
        self.control_value.config['legacy_worker_token']=True
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':[]}})
        self.server=Server(('127.0.0.1',0),self.control_value,worker=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])
    def invoke(self,operation,body=None,token='fixture-management'):
        data=json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(self.url+'/node/audit/'+operation,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=10) as result:return result.status,json.load(result)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def allow(self,permissions):
        auditing.grant(self.root,{'controller':'fixture','roots':[str(self.project)],'profiles':[],'permissions':permissions},self.control_value.config)
    def wait(self,job):
        for _ in range(100):
            status,value=self.invoke('job',{'id':job})
            if value.get('status') in ('done','failed'):return value
            time.sleep(.05)
        self.fail('Fixture audit operation did not finish')
    def test_tokens_and_local_grants_are_separate(self):
        self.assertNotEqual(self.invoke('overview',token='fixture-inference')[0],200)
        self.assertNotEqual(self.invoke('overview',token=self.control_value.config['token'])[0],200)
        self.assertNotEqual(self.invoke('overview')[0],200)
        self.allow(['report'])
        status,value=self.invoke('overview');self.assertEqual(status,200)
        self.assertNotIn('settings',value);self.assertNotIn('profile_defaults',value)
        self.assertNotEqual(self.invoke('scan',{})[0],200)
    def test_worker_scan_preview_apply_verify_and_rollback(self):
        self.allow(['scan','report','preview','apply','excerpts'])
        status,job=self.invoke('scan',{});self.assertEqual(status,200);self.assertEqual(self.wait(job['job'])['status'],'done')
        status,overview=self.invoke('overview');self.assertEqual(len(overview['latest']['projects']),1)
        target=overview['targets'][0]['id'];missing=self.project/'.ai/shared/research.md';missing.unlink()
        status,proposal=self.invoke('preview',{'target':target});self.assertEqual(status,200)
        request={'proposal':proposal['id'],'plan':proposal['plan'],'request':'a'*32}
        status,job=self.invoke('apply',request);self.assertEqual(status,200);result=self.wait(job['job'])
        self.assertEqual(result['status'],'done');self.assertTrue(missing.exists())
        self.assertEqual(self.invoke('request',{'id':'a'*32})[1]['status'],'completed')
        status,job=self.invoke('rollback',{'id':proposal['id'],'request':'b'*32});self.assertEqual(status,200)
        self.assertEqual(self.wait(job['job'])['status'],'done');self.assertFalse(missing.exists())
        status,job=self.invoke('rollback',{'id':proposal['id'],'request':'b'*32});self.assertEqual(self.wait(job['job'])['status'],'done')
    def test_grant_revocation_and_foreign_jobs_fail_closed(self):
        self.allow(['scan','report'])
        self.assertNotEqual(self.invoke('job',{'id':'unknown'})[0],200)
        cfg=auditing.settings(self.root);cfg['grants']={}
        from local_control.storage import atomic
        atomic(self.root/'audit-settings.json',cfg)
        self.assertNotEqual(self.invoke('overview')[0],200)

    def test_controller_tracks_remote_jobs_and_retains_completed_receipts(self):
        from local_control.core import Control
        from local_control.audit_store import Store
        self.allow(['scan','report','preview','apply','excerpts'])
        def rpc(node,path,body=None,**kwargs):
            if path=='/version':return {'capabilities':['constitution-audit-v1']}
            status,result=self.invoke(path.removeprefix('/audit/'),body)
            if status!=200:raise ValueError('Fixture worker rejected request')
            return result
        controller=Control(self.base/'controller-two',rpc);self.addCleanup(controller.pool.shutdown)
        controller.config['nodes']['fixture']={'kind':'worker','name':'Fixture worker'}
        operation=auditing.remote(controller,{'node':'fixture','operation':'scan'})
        for _ in range(100):
            job=controller.jobs[operation['job']]
            if job['status'] in ('done','failed'):break
            time.sleep(.05)
        self.assertEqual(job['status'],'done')
        self.assertEqual(Store(controller.root).get('remote-operation',operation['remote_operation'])['status'],'completed')
        self.assertEqual(len(auditing.overview(controller.root)['remote']),1)
