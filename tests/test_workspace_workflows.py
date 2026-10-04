"""Workspace workflows use disposable homes/projects; no paid or live client actions."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import constitution as kit, releases
from local_control import plans, inspector, rollouts, project_setup, project_vault, toolkits, fleet, recovery, launch_advice, model_lab, resource_profiles, workflows
from local_control.core import Control
from local_control.studio import Studio

ROOT=Path(__file__).resolve().parents[1]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.root=self.base/'control';self.library=self.base/'library'
        self.library.mkdir();self.project=self.base/'project';self.project.mkdir()
        for name in ('VERSION','constitution.md','engineering.md','research.md','maintenance.md'):
            shutil.copy2(ROOT/name,self.library/name)
        for name in ('registry','templates'):shutil.copytree(ROOT/name,self.library/name)
        kit.build(self.library)
        (self.library/'checks').mkdir()
        names=sorted(set(releases.files(self.library))|{releases.INVENTORY})
        (self.library/releases.INVENTORY).write_text(json.dumps({'schema_version':1,'files':names}))
        for p in (patch('local_control.studio.bundled_source',return_value=self.library),
                  patch.object(Path,'home',return_value=self.base/'home')):
            p.start();self.addCleanup(p.stop)
        self.state=Studio(self.root).state
        kit.install(self.library,self.state,project=self.project)

    def control(self):
        value=Control(self.root,lambda *a,**k:{});self.addCleanup(value.pool.shutdown)
        return value


class Foundations(Fixture):
    def test_checkpoint_refuses_uncertain_replay_and_changed_evidence(self):
        journal=plans.Checkpoints(self.root,'a'*12,'fixture')
        with self.assertRaises(RuntimeError):journal.step('download',lambda:(_ for _ in ()).throw(RuntimeError()))
        recovered=plans.Checkpoints(self.root,'a'*12,'fixture')
        with self.assertRaisesRegex(ValueError,'may have completed'):recovered.step('download',lambda:{'digest':'fixture'})
        recovered.step('download',lambda:{'digest':'fixture'},retry_uncertain=True)
        with self.assertRaisesRegex(ValueError,'changed'):recovered.step('download',lambda:None,lambda _:False)

    def test_inspection_distinguishes_files_from_loading_and_access(self):
        value=inspector.inspect(self.control(),str(self.project))
        self.assertEqual(value['installation'][0]['status'],'files-verified')
        self.assertEqual(value['evidence']['client_loading']['value'],'unverified')
        self.assertEqual(value['evidence']['model_access']['value'],'unverified')
        self.assertTrue(any(f['code']=='account-unassigned' for f in value['findings']))

    def test_rollout_detects_stale_preview_and_keeps_local_edits(self):
        studio=Studio(self.root);studio.initialize()
        (studio.draft/'constitution.md').write_text((studio.draft/'constitution.md').read_text()+'\nNew shared preference.\n')
        kit.build(studio.draft)
        value=rollouts.preview(self.root)
        self.assertEqual(value['projects'][0]['status'],'ready')
        path=self.project/'AGENTS.md';before=path.read_bytes();path.write_bytes(before+b'\nLocal note.\n')
        with self.assertRaisesRegex(ValueError,'changed'):rollouts.apply(self.root,{'plan':value['plan']})
        self.assertTrue(path.read_bytes().endswith(b'Local note.\n'))
        fresh=rollouts.preview(self.root);result=rollouts.apply(self.root,{'plan':fresh['plan']})
        self.assertEqual(result['projects'][0]['status'],'applied')
        self.assertTrue(path.read_bytes().endswith(b'Local note.\n'))

    def test_rollout_pin_and_unenrolled_target_are_not_overridden(self):
        kit.install(self.library,self.state,project=self.project,pin=True)
        self.assertEqual(rollouts.preview(self.root)['projects'][0]['status'],'pinned')
        with self.assertRaises(ValueError):rollouts.preview(self.root,[str(self.base/'unknown')])


class Preparation(Fixture):
    def recipe(self):return {'schema':1,'id':'verify','name':'Verify runtime','environment':[],
                             'steps':[{'id':'python','kind':'command','argv':['python','--version']}]}

    def test_credential_references_are_bound_without_values_in_preview(self):
        recipe=self.recipe();recipe['environment']=['FIXTURE_PASSWORD']
        with patch.dict(os.environ,{'FIXTURE_PASSWORD':'private-fixture-value'}):
            value=project_setup.preview(self.root,{'project':str(self.project),'recipe':recipe})
        self.assertNotIn('private-fixture-value',json.dumps(value))
        with patch.dict(os.environ,{'FIXTURE_PASSWORD':'changed-fixture'}):
            with self.assertRaisesRegex(ValueError,'changed'):
                project_setup.apply(self.control(),{'project':str(self.project),'recipe':recipe,'plan':value['plan']})

    def test_manifest_edits_invalidate_preparation(self):
        (self.project/'package.json').write_text('{}')
        value=project_setup.preview(self.root,{'project':str(self.project),'recipe':self.recipe()})
        (self.project/'package.json').write_text('{"scripts":{"test":"changed"}}')
        with self.assertRaisesRegex(ValueError,'changed'):
            project_setup.apply(self.control(),{'project':str(self.project),'recipe':self.recipe(),'plan':value['plan']})

    def test_completed_step_is_not_executed_again_on_resume(self):
        body={'project':str(self.project),'recipe':self.recipe(),'run':'b'*12}
        value=project_setup.preview(self.root,body);body['plan']=value['plan']
        with patch.object(project_setup,'run_command',return_value={'exit_code':0}) as run:
            project_setup.apply(self.control(),body);project_setup.apply(self.control(),body)
        self.assertEqual(run.call_count,1)

    def test_existing_environment_is_preserved(self):
        recipe=self.recipe();recipe['steps']=[{'id':'environment','kind':'venv'}]
        (self.project/'.venv').mkdir();(self.project/'.venv/keep.txt').write_text('keep')
        body={'project':str(self.project),'recipe':recipe};body['plan']=project_setup.preview(self.root,body)['plan']
        with self.assertRaisesRegex(ValueError,'already exists'):project_setup.apply(self.control(),body)
        self.assertEqual((self.project/'.venv/keep.txt').read_text(),'keep')

    def test_health_and_process_controls_cannot_escape_review(self):
        recipe=self.recipe();recipe['steps']=[{'id':'health','kind':'http','url':'https://example.invalid'}]
        with self.assertRaises(ValueError):project_setup.validate(recipe)
        recipe=self.recipe();recipe['environment']=['PYTHONPATH']
        with self.assertRaises(ValueError):project_setup.validate(recipe)
        recipe=self.recipe();recipe['steps'][0]['argv']=['powershell','-Command','Get-Process']
        with self.assertRaises(ValueError):project_setup.validate(recipe)


class Toolkits(Fixture):
    def value(self):return {'schema':1,'id':'quality','name':'Quality','version':'1.0.0',
        'rules':[{'id':'verify','description':'Verify changes','content':'Run documented checks.'}],
        'skills':[{'id':'review','description':'Review changes','content':'Inspect the diff.'}],
        'mcp':[{'id':'docs','url':'https://developers.openai.com/mcp','bearer_env':'DOCS_TOKEN'}]}

    def apply(self,kits=['quality']):
        body={'project':str(self.project),'kits':kits};body['plan']=toolkits.preview(self.root,body)['plan'];return toolkits.apply(self.root,body)

    def test_native_adapters_preserve_unowned_settings_and_detect_drift(self):
        (self.project/'.cursor').mkdir(exist_ok=True);path=self.project/'.cursor/mcp.json';path.write_text(json.dumps({'mcpServers':{'existing':{'command':'python','env':{'PRIVATE':'keep-private-fixture'}}}}))
        (self.project/'.codex').mkdir();(self.project/'.codex/config.toml').write_text('model = "existing-model"\n')
        toolkits.save(self.root,self.value());previewed=toolkits.preview(self.root,{'project':str(self.project),'kits':['quality']})
        self.assertNotIn('keep-private-fixture',json.dumps(previewed));self.apply()
        self.assertEqual(json.loads(path.read_text())['mcpServers']['existing']['env']['PRIVATE'],'keep-private-fixture')
        self.assertIn('model = "existing-model"',(self.project/'.codex/config.toml').read_text())
        p=self.project/'.cursor/rules/constitution-quality-verify.mdc';p.write_text(p.read_text()+'local change')
        with self.assertRaisesRegex(ValueError,'local edits'):self.apply()

    def test_removal_is_owned_recoverable_and_respects_later_edits(self):
        toolkits.save(self.root,self.value());self.apply();path=self.project/'.agents/skills/constitution-quality-review/SKILL.md';before=path.read_bytes()
        result=self.apply([]);self.assertFalse(path.exists())
        kit.rollback(self.root/'workspace/transactions',result['snapshot']);self.assertEqual(path.read_bytes(),before)
        result=self.apply([]);path.parent.mkdir(exist_ok=True);path.write_text('new local note')
        with self.assertRaisesRegex(ValueError,'target changed'):kit.rollback(self.root/'workspace/transactions',result['snapshot'])

    def test_interop_environment_references_roundtrip_literals_refused(self):
        value=self.value();value['mcp'].append({'id':'local','command':'python','args':['server.py'],'environment':['SERVICE_TOKEN']})
        for fmt in ('native','continue'):
            exported=toolkits.export(value,fmt);imported=toolkits.import_document({'format':fmt,'document':exported['document'],'id':'quality'})['toolkit']
            self.assertEqual(imported['mcp'],toolkits.validate(value)['mcp'])
        rules=toolkits.export(value,'rulesync');doc=json.loads(rules['files']['.rulesync/mcp.jsonc'])
        self.assertEqual(toolkits.import_document({'format':'rulesync','document':doc})['toolkit']['mcp'],toolkits.validate(value)['mcp'])
        doc['mcpServers']['local']['env']['SERVICE_TOKEN']='literal-fixture'
        with self.assertRaisesRegex(ValueError,'Literal'):toolkits.import_document({'format':'rulesync','document':doc})


class FleetRecovery(Fixture):
    def test_controller_tls_surface_refuses_worker_tokens_and_other_namespaces(self):
        try:import cryptography
        except ImportError:self.skipTest('Optional TLS dependency unavailable')
        from local_control.fleet_server import start
        from local_control.transport import request
        control=self.control();listener=start(control,'127.0.0.1',0)
        self.addCleanup(listener.server_close);self.addCleanup(listener.shutdown)
        private=plans.read(self.root,'fleet-listener.json',{'schema':1});endpoint={'kind':'worker','url':private['url'],'fingerprint':private['fingerprint'],'token':control.config['gateway_token']}
        with self.assertRaisesRegex(ValueError,'HTTP 401'):request(endpoint,'/fleet/snapshot',timeout=5)
        import base64
        invite=json.loads(base64.urlsafe_b64decode(fleet.pairing(self.root,{'scopes':['inventory']})['code']))
        granted=request({**endpoint,'token':''},'/fleet/pair',{'nonce':invite['nonce']},timeout=5)
        endpoint['token']=granted['token'];value=request(endpoint,'/fleet/snapshot',timeout=5)
        self.assertIn('projects',value);self.assertNotIn('library',value);self.assertNotIn('accounts',value)
        with self.assertRaisesRegex(ValueError,'HTTP 404'):request(endpoint,'/v1/responses',{'model':'fixture'},timeout=5)

    def test_pairing_is_single_use_scoped_and_separate_from_worker_credentials(self):
        plans.write(self.root,'fleet-listener.json',{'schema':1,'url':'https://127.0.0.1:8768','fingerprint':'a'*64,'heartbeat':time.time()})
        record=fleet.pairing(self.root,{'scopes':['library']});import base64
        invitation=json.loads(base64.urlsafe_b64decode(record['code']));grant=fleet.redeem(self.root,{'nonce':invitation['nonce']})
        self.assertEqual(fleet.principal(self.root,grant['token'])['scopes'],['library'])
        self.assertIsNone(fleet.principal(self.root,self.control().config['gateway_token']))
        with self.assertRaises(ValueError):fleet.redeem(self.root,{'nonce':invitation['nonce']})
        fleet.revoke(self.root,{'id':grant['id']});self.assertIsNone(fleet.principal(self.root,grant['token']))

    def test_peer_conflicts_need_explicit_review_and_stale_resolution_refused(self):
        studio=Studio(self.root);studio.initialize();bundle=fleet.portable(self.root);bundle['files']['constitution.md']+='\nRemote fixture note.\n'
        plans.write(self.root,'fleet.json',{'schema':1,'peers':{'a'*12:{'id':'a'*12,'base':{}}},'grants':{},'pairings':{}})
        plans.write(self.root,'peer-'+('a'*12)+'.json',{'schema':1,'snapshot':{'library':bundle},'received_at':1})
        body={'id':'a'*12};value=fleet.stage_preview(self.root,body);self.assertTrue(any(r['status']=='conflict' for r in value['changes']))
        with self.assertRaisesRegex(ValueError,'conflicts'):fleet.stage_apply(self.root,{**body,'plan':value['plan']})
        fleet.resolve(self.root,{**body,'plan':value['plan'],'paths':['constitution.md']});fresh=fleet.stage_preview(self.root,body)
        with self.assertRaisesRegex(ValueError,'changed'):fleet.stage_apply(self.root,{**body,'plan':value['plan']})
        fleet.stage_apply(self.root,{**body,'plan':fresh['plan']});self.assertIn('Remote fixture note.',(studio.draft/'constitution.md').read_text())

    def test_recovery_excludes_paths_credentials_and_never_overwrites_existing_bundle(self):
        control=self.control();manifest=recovery.export(control);text=json.dumps(manifest)
        self.assertNotIn(str(self.project),text);self.assertNotIn(control.config['token'],text);self.assertNotIn('password_file',text)
        new=self.base/'second-project';new.mkdir();identity=manifest['projects'][0]['id'];body={'manifest':manifest,'mapping':{identity:str(new)}}
        value=recovery.preview(self.root,body);self.assertEqual(value['projects'][0]['status'],'ready')
        recovery.recover_workspace(control,{**body,'plan':value['plan']});self.assertTrue((new/'.ai/constitution.lock.json').is_file())
        self.assertEqual(recovery.preview(self.root,body)['projects'][0]['status'],'already-enrolled')

    def test_peer_cannot_stage_executable_or_release_inventory(self):
        studio=Studio(self.root);studio.initialize();bundle=fleet.portable(self.root)
        for name in ('scripts/constitution.py','checks/release-files.json','../outside.md'):
            with self.assertRaises(ValueError):fleet.validate_bundle({**bundle,'files':{name:'malicious fixture'}},studio)


class AdviceLabProfiles(Fixture):
    def test_gateway_admission_is_fifo_for_a_selected_node(self):
        import threading
        control=self.control();control.config['primary']={'node':'local','model':'fixture'};control.config['limits']['concurrent_per_node']=1
        entered=threading.Event();release=threading.Event();order=[];errors=[]
        def first():
            try:
                with control.lease({'model':'constitution-local'}):entered.set();release.wait(10)
            except Exception as ex:errors.append(ex)
        def queued(number):
            try:
                with control.lease({'model':'constitution-local'}):order.append(number);time.sleep(.01)
            except Exception as ex:errors.append(ex)
        active=threading.Thread(target=first);active.start();self.assertTrue(entered.wait(5))
        threads=[]
        for i in range(3):
            thread=threading.Thread(target=queued,args=(i,));thread.start();threads.append(thread)
            deadline=time.monotonic()+5
            while control.queued<i+1 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(control.queued,i+1)
        release.set();active.join(5)
        for thread in threads:thread.join(5)
        self.assertEqual(errors,[]);self.assertEqual(order,[0,1,2]);self.assertFalse(control.waiting_nodes)

    def test_quota_is_deduplicated_and_stale_or_reset_is_unknown(self):
        from local_control import monitoring
        control=self.control()
        for identity in ('a'*12,'b'*12):monitoring.configure(self.root,{'account':{'id':identity,'provider':'openai','application':'codex','login':'fixture@example.invalid','plan':'test','projects':[str(self.project)]}})
        monitoring.record_usage(self.root,'a'*12,{'used':100,'limit':100,'unit':'requests','observed_at':time.time()-600})
        value=launch_advice.advice(control,str(self.project));self.assertEqual(len(value['accounts']),1);self.assertEqual(value['accounts'][0]['quota'],'unknown')
        monitoring.record_usage(self.root,'a'*12,{'used':100,'limit':100,'unit':'requests'})
        value=launch_advice.advice(control,str(self.project));self.assertEqual(value['accounts'][0]['quota'],'exhausted')
        with self.assertRaisesRegex(ValueError,'exhausted'):launch_advice.launch(control,{'project':str(self.project),'plan':value['plan'],'mode':'hosted','client':'codex','account':'a'*12})

    def test_lab_repeats_bounded_fixtures_and_reports_only_matching_baselines(self):
        control=self.control();control.config['primary']={'node':'local','model':'fixture:latest'}
        body={'roles':['primary'],'repeats':2,'minutes':1};body['plan']=model_lab.preview(control,body)['plan']
        with patch.object(control,'benchmark',return_value={'status':'passed','elapsed_seconds':1,'hardware':{'gpu_name':'fixture'}}) as benchmark:
            first=model_lab.run_lab(control,body);second=model_lab.run_lab(control,body)
        self.assertEqual(benchmark.call_count,4);self.assertEqual(first['summary'][0]['trials'],2);self.assertEqual(second['summary'][0]['regression'],'no correctness decrease observed')
        control.config['context']*=2
        with self.assertRaisesRegex(ValueError,'changed'):model_lab.run_lab(control,body)

    def test_manual_priority_idle_defer_and_overnight_schedule(self):
        control=self.control();resource_profiles.configure(self.root,{'enabled':True,'rules':[{'profile':'gaming','days':[0,1,2,3,4,5,6],'start':'22:00','end':'06:00'}]})
        value=resource_profiles.overview(self.root);clock=time.strptime('2026-10-04 23:00','%Y-%m-%d %H:%M');self.assertEqual(resource_profiles.desired(value,clock,set()),'gaming')
        resource_profiles.manual(self.root)
        self.assertEqual(resource_profiles.automatic_profile(control)['status'],'held')
        resource_profiles.configure(self.root,{'resume':True});control.active[('local','fixture')]=1
        with patch.object(resource_profiles.time,'localtime',return_value=clock):self.assertEqual(resource_profiles.automatic_profile(control)['status'],'deferred')
        with self.assertRaises(ValueError):resource_profiles.configure(self.root,{'rules':[{'profile':'gaming','applications':['../game.exe']}]})

    def test_search_never_indexes_private_configuration_contents(self):
        control=self.control();secret=self.base/'private/.env';secret.parent.mkdir();secret.write_text('FIXTURE_TOKEN=not-indexed-fixture')
        self.assertEqual(workflows.search(control,'not-indexed-fixture')['items'],[])
        self.assertTrue(any(i['kind']=='project' for i in workflows.search(control,'project')['items']))
        self.assertTrue(any(i['kind']=='model definition' and i['page']=='constitution' for i in workflows.search(control,'gpt')['items']))


if __name__=='__main__':unittest.main()
