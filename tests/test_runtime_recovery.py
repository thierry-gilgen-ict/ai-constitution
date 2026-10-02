"""Recovery, pairing scope, bounded requests and session-aware service controls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from test_local_control import FakeOllama, ALIAS
from local_control.core import Control
from local_control import compatibility, credentials, operations, processes
from local_control.storage import atomic, load


class Recovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.rpc = FakeOllama()
        self.control = Control(self.root, self.rpc)
        self.addCleanup(self.control.pool.shutdown)
        self.control.config.update(primary={'node':'local','model':'gpu:latest','cpu':False},
                                   fallback={'node':'local','model':'cpu:latest','cpu':True},
                                   managed={'local':['gpu:latest','cpu:latest']})

    def test_interrupted_operations_are_visible_and_never_replayed(self):
        operations.save(self.root, {'job': {'id':'job', 'status':'running', 'label':'Pull'}}, [])
        recovered = Control(self.root, self.rpc)
        self.addCleanup(recovered.pool.shutdown)
        self.assertEqual(recovered.jobs['job']['status'], 'interrupted')
        self.assertEqual(self.rpc.calls, [])

    def test_schema_migration_backups_original_and_preserves_gaming(self):
        old = copy.deepcopy(self.control.config)
        old.update(schema=1, mode='gaming')
        atomic(self.root/'config.json', old)
        value = load(self.root, migrate=True)
        self.assertEqual(value['schema'], 2)
        self.assertEqual(value['mode'], 'gaming')
        self.assertEqual(json.loads((self.root/'migrations/config-v1.json').read_text()), old)

    def test_session_between_inference_calls_blocks_stop(self):
        record={'id':'a'*32, 'process':processes.identity(os.getpid())}
        self.assertIsNotNone(record['process'])
        self.control.session('open',record)
        self.assertEqual(self.control.status()['active_requests'],0)
        with self.assertRaisesRegex(ValueError,'managed sessions'):
            self.control.stop_ready(True)
        self.control.session('close',record)
        with self.assertRaisesRegex(ValueError,'external clients'):
            self.control.stop_ready(False)
        self.assertEqual(self.control.stop_ready(True)['status'],'stopping')
        with self.assertRaisesRegex(ValueError,'stopping'):
            with self.control.lease({'model':ALIAS}): pass

    def test_reused_pid_is_not_a_live_managed_session(self):
        value=processes.identity(os.getpid())
        value['started']='different-start'
        self.assertFalse(processes.matches({'process':value}))

    def test_queue_times_out_without_starting_inference(self):
        self.control.config['limits']['wait_seconds']=.02
        with self.control.lease({'model':ALIAS}):
            with self.assertRaisesRegex(ValueError,'timed out before inference'):
                with self.control.lease({'model':ALIAS}): pass
        self.assertEqual(self.control.queued,0)
        self.assertEqual(self.rpc.calls,[])

    def test_queued_request_reselects_route_after_mode_change(self):
        result=[]
        self.control.config['nodes']['cpu']={'url':'http://127.0.0.1:11435','kind':'ollama','name':'CPU'}
        self.control.config['fallback']['node']='cpu'
        with self.control.lease({'model':ALIAS}):
            def waiting():
                with self.control.lease({'model':ALIAS}) as (_,body):result.append(body['model'])
            thread=threading.Thread(target=waiting); thread.start()
            deadline=time.monotonic()+2
            while not self.control.queued and time.monotonic()<deadline: time.sleep(.005)
            with self.control.changed:
                self.control.mode='gaming'; self.control.changed.notify_all()
            thread.join(2)
            self.assertEqual(result,['cpu:latest'])

    def test_probe_records_tool_roundtrip_and_invalid_model_fails(self):
        evidence=compatibility.qualify(self.control,self.control.config['fallback'])
        self.assertTrue(evidence['function_tools'] and evidence['full_history'])
        self.assertEqual(evidence['coding_quality'],'not evaluated')
        real=self.control.rpc
        def bad(node,path,payload=None,**kwargs):
            if path=='/v1/responses' and payload.get('tools'):return {'output':[{'type':'message'}]}
            return real(node,path,payload,**kwargs)
        self.control.rpc=bad
        with self.assertRaisesRegex(ValueError,'function-call'):
            self.control.switch('gaming')
        self.assertEqual(self.control.mode,'work')

    def test_status_never_exposes_worker_credentials(self):
        self.control.config['nodes']['worker']={'name':'Worker','token':'MANAGEMENT','inference_token':'INFERENCE','fingerprint':'PIN'}
        rendered=json.dumps(self.control.status())
        for secret in ('MANAGEMENT','INFERENCE','PIN'):self.assertNotIn(secret,rendered)

    def test_maintenance_drains_existing_request_and_routes_new_work_away(self):
        self.control.config['nodes']['cpu']={'url':'http://127.0.0.1:11435','kind':'ollama','name':'CPU'}
        self.control.config['fallback']['node']='cpu'
        result=[]
        with self.control.lease({'model':ALIAS}):
            thread=threading.Thread(target=lambda:result.append(self.control.maintenance('local',True)))
            thread.start()
            deadline=time.monotonic()+2
            while self.control.mode!='gaming' and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(thread.is_alive())
            self.assertEqual(self.control.route()['node'],'cpu')
            self.assertIn('local',load(self.root)['maintenance'])
        thread.join(2)
        self.assertEqual(result[0]['status'],'maintenance')
        with self.assertRaisesRegex(ValueError,'Leave maintenance'):
            self.control.switch('work')
        self.control.maintenance('local',False)
        self.assertNotIn('local',self.control.config['maintenance'])

    def test_maintenance_failure_preserves_route_and_upgrade_requires_remote(self):
        with self.assertRaisesRegex(ValueError,'compatible route'):
            self.control.maintenance('local',True)
        self.assertEqual(self.control.mode,'work')
        self.assertEqual(self.control.config['maintenance'],[])
        with self.assertRaisesRegex(ValueError,'Drain both'):
            self.control.upgrade_runtime()

    def test_macos_startup_does_not_replace_foreign_entry(self):
        import plistlib
        from local_control.desktop import startup, LABEL
        home=self.root/'home'
        startup(self.root,True,home=home,system='Darwin')
        path=home/'Library/LaunchAgents'/(LABEL+'.plist')
        self.assertTrue(plistlib.loads(path.read_bytes())['RunAtLoad'])
        startup(self.root,False,home=home,system='Darwin')
        path.write_bytes(plistlib.dumps({'Label':'another app'}))
        before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'another installation'):
            startup(self.root,True,home=home,system='Darwin')
        self.assertEqual(path.read_bytes(),before)


class Credentials(unittest.TestCase):
    def setUp(self):
        self.config={'controllers':{},'pairing':None}

    def test_code_single_use_and_credentials_have_separate_scope(self):
        code=credentials.create_pairing(self.config)
        result=credentials.redeem(self.config,code['code'],'Home')
        self.assertNotIn(result['token'],json.dumps(self.config))
        self.assertEqual(credentials.principal(self.config,result['token']),result['controller_id'])
        self.assertIsNone(credentials.principal(self.config,result['inference_token']))
        self.assertEqual(credentials.principal(self.config,result['inference_token'],inference=True),result['controller_id'])
        with self.assertRaisesRegex(ValueError,'already used'):
            credentials.redeem(self.config,code['code'],'Again')

    def test_expiry_rotation_and_revocation(self):
        code=credentials.create_pairing(self.config)
        with patch.object(credentials.time,'time',return_value=code['expires']+1):
            with self.assertRaises(ValueError):credentials.redeem(self.config,code['code'],'Late')
        first=credentials.redeem(self.config,code['code'],'Home')
        second=credentials.rotate(self.config,first['controller_id'])
        self.assertIsNone(credentials.principal(self.config,first['token']))
        self.assertEqual(credentials.principal(self.config,second['token']),first['controller_id'])
        del self.config['controllers'][first['controller_id']]
        self.assertIsNone(credentials.principal(self.config,second['token']))
