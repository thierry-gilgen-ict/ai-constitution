"""Control-center invariants use temporary profiles; no real account or model calls."""
import copy
import json
from pathlib import Path
import tempfile
import sys
import http.client
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import constitution as kit, architecture, releases
from scripts.catalog import json_bytes
from local_control import locations, distribution, project_vault, monitoring, synchronization, project_capture
from local_control.studio import Studio
from local_control.core import Control
from local_control.server import Server


class PrivateFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'control'; self.root.mkdir()
    def tearDown(self): self.temp.cleanup()


class Locations(PrivateFixture):
    def paths(self):
        return {'models': str(self.base / 'models'), 'studio': str(self.root / 'studio'), 'downloads': str(self.root / 'downloads')}

    def test_preferences_are_separate_from_os_environment(self):
        values = self.paths(); preview = locations.settings_plan(self.root, values)
        with patch('local_control.locations.apply_models') as apply:
            locations.save_settings(self.root, values, preview['plan'])
        apply.assert_not_called()
        self.assertEqual(locations.preferences(self.root)['models'], values['models'])
        with self.assertRaises(ValueError): locations.save_settings(self.root, values, 'stale')

    def test_verified_copy_preserves_original_and_refuses_merge_or_overlap(self):
        source = self.base / 'source'; source.mkdir(); (source / '.env').write_text('DUMMY=private-fixture')
        target = self.base / 'copy'; p = locations.copy_plan(source, target)
        locations.copy_verified(source, target, p['fingerprint'])
        self.assertEqual((source / '.env').read_bytes(), (target / '.env').read_bytes())
        with self.assertRaises(ValueError): locations.copy_plan(source, target)
        with self.assertRaises(ValueError): locations.copy_plan(source, source / 'child')

    def test_folder_choice_rejects_git_and_overlap(self):
        repo=self.base/'repo';repo.mkdir();(repo/'.git').mkdir()
        with self.assertRaises(ValueError): locations.destination(str(repo/'private'))
        with self.assertRaises(ValueError): locations.settings_plan(self.root,{**self.paths(),'models':str(self.root)})
        with self.assertRaises(ValueError): locations.settings_plan(self.root,{**self.paths(),'studio':str(self.base/'models/library')})

    def test_source_changed_since_preview(self):
        source=self.base/'source';source.mkdir();(source/'config').write_text('before')
        p=locations.copy_plan(source,self.base/'target');(source/'config').write_text('after: changed length')
        with self.assertRaises(ValueError): locations.copy_verified(source,self.base/'target',p['fingerprint'])
        self.assertFalse((self.base/'target').exists())

    def test_private_profile_relocation_preserves_launches_and_enrollment(self):
        (self.root/'config.json').write_text('{"schema":1}')
        target=self.base/'moved';p,_=locations.relocation_plan(self.root,target)
        with patch.object(project_vault,'protect'):
            locations.relocate(self.root,target,p['fingerprint'])
        self.assertEqual(locations.resolve_root(self.root),target)
        self.assertTrue((self.root/'config.json').exists())
        self.assertEqual(locations.folder(target,'constitution_state'),self.base/'state')


class Vault(PrivateFixture):
    def configure(self):
        source=self.base/'configs'/'example';source.mkdir(parents=True)
        (source/'production.env').write_text('EXAMPLE_SECRET=fixture-private-value\n')
        self.source=source
        project_vault.configure(self.root,{'config_root':str(source.parent),'backup_root':str(self.base/'backups'),
            'entry':{'id':'example','name':'Example','folder':str(source)}})

    def test_backup_restore_verification_and_no_secret_preview(self):
        self.configure();p=project_vault.plan(self.root)
        self.assertNotIn('fixture-private-value',json.dumps(p))
        with patch.object(project_vault,'protect'):
            result=project_vault.backup(self.root,p['plan'])
            destination=self.base/'restored'
            restore=project_vault.restore_plan(self.root,result['snapshot'],'example',str(destination))
            project_vault.restore(self.root,result['snapshot'],'example',str(destination),restore['plan'])
        self.assertEqual((destination/'production.env').read_bytes(),(self.source/'production.env').read_bytes())
        with self.assertRaises(ValueError): project_vault.restore_plan(self.root,result['snapshot'],'example',str(self.source))
        self.assertEqual(len(project_vault.overview(self.root)['snapshots']),1)

    def test_corrupt_snapshot_and_stale_backup_blocked(self):
        self.configure();p=project_vault.plan(self.root)
        (self.source/'new.env').write_text('KEY=fixture')
        with self.assertRaises(ValueError): project_vault.backup(self.root,p['plan'])
        with patch.object(project_vault,'protect'): result=project_vault.backup(self.root)
        (self.base/'backups'/result['snapshot']/'projects/example/production.env').write_text('tampered')
        with self.assertRaises(ValueError): project_vault.restore_plan(self.root,result['snapshot'],'example',str(self.base/'restore'))

    def test_scheduler_is_opt_in_due_once_and_catches_up(self):
        self.configure();self.assertFalse(project_vault.claim_due(self.root,10000))
        project_vault.configure(self.root,{'schedule':{'enabled':True,'hours':1}})
        self.assertTrue(project_vault.claim_due(self.root,10000))
        self.assertFalse(project_vault.claim_due(self.root,10001))
        self.assertTrue(project_vault.claim_due(self.root,20000))

    def test_backup_recursion_state_and_project_overlap_refused(self):
        self.configure()
        with self.assertRaises(ValueError): project_vault.configure(self.root,{'backup_root':str(self.source/'backups')})
        with self.assertRaises(ValueError): project_vault.configure(self.root,{'entry':{'id':'duplicate','name':'Duplicate','folder':str(self.source)}})


class Monitoring(PrivateFixture):
    def test_account_and_usage_allowlist_no_credentials_or_nan(self):
        monitoring.configure(self.root,{'account':{'provider':'openai','login':'sample@example.com','label':'Sample', 'password':'ignored-secret','projects':['demo']}})
        value=monitoring.load(self.root);identity=next(iter(value['accounts']))
        self.assertNotIn('ignored-secret',json.dumps(value))
        monitoring.record_usage(self.root,identity,{'used':10,'unit':'tokens','token':'discard-me','period':'Fixture'})
        self.assertNotIn('discard-me',json.dumps(monitoring.load(self.root)))
        with self.assertRaises(ValueError): monitoring.record_usage(self.root,identity,{'used':float('nan'),'unit':'tokens'})
        with self.assertRaises(ValueError): monitoring.configure(self.root,{'account':{'provider':'openai','login':'Bearer ' + 'x'*40}})

    def test_codex_read_methods_only_and_output_minimization(self):
        calls=[]
        class Reader:
            def __init__(self,exe): pass
            def send(self,msg): calls.append(msg['method'])
            def close(self): calls.append('close')
            def call(self,method,params=None):
                calls.append(method)
                return {'initialize':{},'account/read':{'account':{'type':'chatgpt','email':'sample@example.com','planType':'pro','access_token':'NEVER-RETURN'}},
                    'account/rateLimits/read':{'rateLimitsByLimitId':{'codex':{'primary':{'usedPercent':0,'windowDurationMins':300,'resetsAt':123456}}}},
                    'account/usage/read':{'summary':{'lifetimeTokens':None},'dailyUsageBuckets':[{'startDate':'2026-01-01','tokens':20,'prompt':'NEVER-RETURN'}]}}[method]
        result=monitoring.codex_snapshot('fixture',reader=Reader)
        self.assertEqual(result['windows'][0]['used_percent'],0)
        self.assertIsNone(result['summary']['lifetimeTokens'])
        self.assertNotIn('NEVER-RETURN',json.dumps(result))
        self.assertEqual(calls,['initialize','initialized','account/read','account/rateLimits/read','account/usage/read','close'])

    def test_unsupported_usage_does_not_discard_account_or_limits(self):
        class Reader:
            def __init__(self,exe): pass
            def send(self,msg): pass
            def close(self): pass
            def call(self,method,params=None):
                if method.endswith('usage/read'): raise monitoring.ProbeError('unsupported_method')
                return {'account':{'type':'chatgpt','email':'sample@example.com'}} if method=='account/read' else {}
        result=monitoring.codex_snapshot('fixture',reader=Reader)
        self.assertEqual(result['login'],'sample@example.com')
        self.assertEqual(result['issues'][0]['code'],'unsupported_method')


class ProjectFollowing(PrivateFixture):
    def test_corresponding_templates_sync_with_pins_and_conflicts_preserved(self):
        studio=Studio(self.root);studio.initialize()
        value=kit.read_json(studio.draft/'templates/architectures/python-api.json')
        projects=[]
        for name in ('follows','edited','pinned'):
            project=self.base/name;project.mkdir();projects.append(project)
            p,_=architecture.plan(kit,studio.draft,studio.state,project,value,name)
            architecture.apply(kit,studio.draft,studio.state,project,value,name,p['plan'])
        kit.install(studio.draft,studio.state,project=projects[2],pin=True)
        (projects[1]/'.ai/architecture.md').write_text('Keep this local change')
        value['description']='A changed reusable baseline'
        (studio.draft/'templates/architectures/python-api.json').write_bytes(json_bytes(value))
        result=synchronization.reconcile(self.root,{'context':8192})
        statuses={Path(v['project']).name:v['status'] for v in result['projects']}
        self.assertEqual(statuses,{'follows':'current','edited':'conflict','pinned':'pinned'})
        self.assertIn('A changed reusable baseline',(projects[0]/'.ai/architecture.md').read_text())
        self.assertEqual((projects[1]/'.ai/architecture.md').read_text(),'Keep this local change')
        self.assertNotIn('A changed reusable baseline',(projects[2]/'.ai/architecture.md').read_text())
        again=synchronization.reconcile(self.root,{'context':16384})
        self.assertNotEqual(result['runtime_revision'],again['runtime_revision'])
        self.assertIsNone(next(p for p in again['projects'] if Path(p['project']).name == 'follows')['snapshot'])

    def test_capture_discards_values_urls_scripts_and_project_identity(self):
        studio=Studio(self.root);studio.initialize()
        project=self.base/'project';project.mkdir()
        (project/'package.json').write_text(json.dumps({'name':'PRIVATE-NAME','scripts':{'build':'echo PRIVATE-COMMAND'},'dependencies':{'next':'^15.0.0','private-package':'https://user:SECRET@example.com'}}))
        (project/'.env.example').write_text('RESEND_API_KEY=SECRET-VALUE\nCUSTOM_KEY=OTHER-SECRET\n')
        (project/'compose.yaml').write_text('password: DO-NOT-COPY')
        result=project_capture.capture(studio,self.root,{'project':str(project),'id':'captured','name':'Reusable'})
        rendered=json.dumps(result)
        for private in ('PRIVATE-NAME','PRIVATE-COMMAND','SECRET-VALUE','OTHER-SECRET','DO-NOT-COPY','user:SECRET'):
            self.assertNotIn(private,rendered)
        self.assertIn('CUSTOM_KEY',rendered)
        self.assertEqual(result['environment_keys'],2)
        self.assertEqual({v['id'] for v in result['template']['components']},{'nextjs','docker','project-config'})


class Packages(PrivateFixture):
    def test_source_bundle_excludes_private_draft_and_download_requires_digest(self):
        studio=Studio(self.root);studio.initialize()
        (studio.draft/'engineering.md').write_text('PRIVATE-DRAFT-CONTENT')
        record=distribution.source_bundle(self.root)
        path,_=distribution.download(self.root,record['id'])
        payload=releases.unpack(path.read_bytes(),record['sha256'])
        self.assertNotIn(b'PRIVATE-DRAFT-CONTENT',payload['engineering.md'])
        path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError): distribution.download(self.root,record['id'])
        with self.assertRaises(ValueError): distribution.download(self.root,'../config.json')


class Access(PrivateFixture):
    def test_private_pages_require_admin_and_worker_account_sharing_is_local_opt_in(self):
        control = Control(self.root, lambda *a,**k: {'models':[]})
        # Keep every inventory read within the disposable profile.
        project_vault.configure(self.root, {'config_root':str(self.base/'configs'),'backup_root':str(self.base/'backups')})
        server=Server(('127.0.0.1',0),control)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,token):
            connection=http.client.HTTPConnection(*server.server_address,timeout=5)
            connection.request('GET',path,headers={'Authorization':'Bearer '+token})
            response=connection.getresponse();result=(response.status,response.read());connection.close();return result
        try:
            for path in ('/api/monitoring','/api/vault','/api/workers','/api/projects/sync','/api/worker-package?id=bad'):
                self.assertEqual(request(path,control.config['gateway_token'])[0],401)
                self.assertEqual(request(path,'')[0],401)
            for path in ('/api/monitoring','/api/vault','/api/workers','/api/projects/sync'):
                self.assertEqual(request(path,control.config['token'])[0],200)
            server.worker=True;control.config['legacy_worker_token']=True
            self.assertEqual(request('/api/vault',control.config['token'])[0],404)
            self.assertEqual(request('/node/monitoring',control.config['token'])[0],400)
            self.assertEqual(request('/node/diagnostics',control.config['token'])[0],200)
            monitoring.configure(self.root,{'share_with_controllers':True})
            self.assertEqual(request('/node/monitoring',control.config['token'])[0],200)
            self.assertEqual(request('/node/monitoring',control.config['gateway_token'])[0],401)
        finally:
            server.shutdown();server.server_close();thread.join();control.pool.shutdown()

    def test_stop_prevents_new_background_work(self):
        control=Control(self.root, lambda *a,**k:{})
        try:
            control.stop_ready(True)
            with self.assertRaises(ValueError):control.submit('Should not run',lambda progress: None)
        finally:control.pool.shutdown()

    def test_background_job_does_not_reset_model_switch_phase(self):
        control=Control(self.root, lambda *a,**k:{})
        control.phase='draining responses'
        control.submit('Unrelated metadata',lambda progress: {'status':'done'})
        control.pool.shutdown(wait=True)
        self.assertEqual(control.phase,'draining responses')


if __name__=='__main__':unittest.main()
