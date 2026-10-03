"""Data-only tests for release updates, encrypted backups, models and connectors."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
from scripts import architecture, catalog, constitution as kit, releases
from scripts.catalog import digest, json_bytes
from local_control import updates, encrypted_backup, monitoring, connectors, insights, model_inbox, project_vault, routing, schedules
from local_control.storage import atomic
from local_control.core import Control, ALIAS
from local_control.studio import Studio
from local_control.services import Services

ROOT = Path(__file__).resolve().parents[1]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.root = self.base / 'control'
        home = patch.object(Path, 'home', return_value=self.base / 'home')
        home.start(); self.addCleanup(home.stop)
    def control(self):
        result = Control(self.root, lambda *a, **k: {})
        self.addCleanup(result.pool.shutdown)
        return result
    def vault(self):
        folder = self.base / 'configs/demo'; folder.mkdir(parents=True); (folder / '.env').write_text('EXAMPLE=fixture')
        project_vault.configure(self.root, {'config_root': str(folder.parent), 'backup_root': str(self.base / 'backups'),
            'entry': {'id':'demo', 'folder':str(folder)}, 'schedule':{'enabled':True,'hours':24}})


class Updates(Fixture):
    def record(self):
        return {'tag_name':'v99.0.0','body':'Fixture release', 'assets':[{'name':n,'browser_download_url':updates.REPOSITORY+'/releases/download/v99.0.0/'+n}
            for n in ('ai-constitution-release.zip','ai-constitution-release.sha256')]}

    def test_check_preserves_last_success_when_network_fails(self):
        with patch.object(updates, 'fetch', return_value=json_bytes(self.record())): updates.check(self.root)
        before = updates.read(self.root)
        self.assertTrue(before['available'])
        with patch.object(updates, 'fetch', side_effect=OSError('fixture')):
            with self.assertRaises(ValueError): updates.check(self.root)
        result=updates.read(self.root)
        self.assertEqual(result['checked_at'],before['checked_at']); self.assertEqual(result['latest'],'99.0.0')
        self.assertTrue(result['error'])

    def test_redirect_never_accepts_non_github_hosts(self):
        with self.assertRaises(ValueError): updates.fetch('https://example.invalid/app.zip',1024)
        with self.assertRaises(ValueError): updates.fetch('http://github.com/app.zip',1024)

    def test_source_stage_verifies_manifest_and_detects_later_tampering(self):
        path=self.base/'bundle.zip'; info=releases.export(ROOT,path); data=path.read_bytes()
        version=(ROOT/'VERSION').read_text().strip()
        atomic(self.root/'updates.json',{'latest':version,'assets':{'ai-constitution-release.zip':'zip','ai-constitution-release.sha256':'checksum'}})
        def fetch(url,limit): return info['sha256'].encode() if url=='checksum' else data
        with patch.object(updates,'current',return_value='0.0.1'),patch.object(updates,'fetch',side_effect=fetch):
            updates.stage(self.root,version)
        record=updates.read(self.root)['staged']; updates.verify_staged(record)
        (Path(record['directory'])/'constitution.md').write_text('modified')
        with self.assertRaisesRegex(ValueError,'modified'): updates.verify_staged(record)

    def test_staging_recovers_when_rollback_capture_was_interrupted(self):
        path=self.base/'bundle.zip'; info=releases.export(ROOT,path); data=path.read_bytes()
        version=(ROOT/'VERSION').read_text().strip()
        atomic(self.root/'updates.json',{'latest':version,'assets':{'ai-constitution-release.zip':'zip','ai-constitution-release.sha256':'checksum'}})
        with patch.object(updates,'current',return_value='0.0.1'),patch.object(updates,'fetch',side_effect=lambda url,limit:info['sha256'].encode() if url=='checksum' else data):
            with patch.object(updates,'capture_current',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError): updates.stage(self.root,version)
            updates.stage(self.root,version)
        updates.verify_staged(updates.read(self.root)['staged'])

    def test_restart_preview_blocks_sessions_and_does_not_modify_live_state(self):
        control=self.control(); atomic(self.root/'updates.json',{'staged':{'version':'99.0.0','prefix':['fixture']}})
        with patch.object(control,'sessions',return_value=[{'status':'open'}]):
            preview=updates.preview(control)
            self.assertIn('Managed coding sessions',preview['blockers'])
            with self.assertRaises(ValueError): updates.apply(Mock(control=control),{'plan':preview['plan'],'acknowledge_external':True})
        self.assertFalse(control.stopping)

    def test_failed_startup_restarts_previous_only_after_child_exits(self):
        control=self.control(); ticket='a'*32
        intent={'status':'waiting','process':{'pid':999999},'target':{'version':'99.0.0','prefix':['fixture-new']},
            'previous':{'version':'0.2.0','prefix':['fixture-old']},'args':[],'url':'http://127.0.0.1:1','worker':False}
        atomic(self.root/'updates'/('restart-'+ticket+'.json'),intent)
        with patch.object(updates.processes,'matches',return_value=False),patch.object(updates.subprocess,'Popen',return_value=Mock(poll=lambda:1)) as start:
            updates.finish(self.root,ticket)
        self.assertEqual(start.call_count,2)
        self.assertEqual(start.call_args.args[0],['fixture-old'])
        self.assertEqual(updates.read(self.root)['restart_status'],'rolled-back')
        with self.assertRaises(ValueError): updates.finish(self.root,ticket)


class Backups(Fixture):
    def test_password_only_in_child_environment_and_raw_errors_not_exposed(self):
        encrypted_backup.configure(self.root,{'repository':str(self.base/'encrypted'),'password_env':'FIXTURE_RESTIC_PASSWORD'})
        observed={}
        def run(args,**kw):
            observed.update(args=args,env=kw['env']);kw['stdout'].write(b'{"status":"ok"}');return Mock(returncode=0)
        with patch.dict(os.environ,{'FIXTURE_RESTIC_PASSWORD':'fixture-password','RESTIC_PASSWORD_COMMAND':'must-not-execute'}),patch.object(encrypted_backup.shutil,'which',return_value='restic'),patch.object(encrypted_backup.subprocess,'run',side_effect=run):
            self.assertEqual(encrypted_backup.run(self.root,['check']),{'status':'ok'})
        self.assertNotIn('fixture-password',json.dumps(observed['args']))
        self.assertNotIn('RESTIC_PASSWORD_COMMAND',observed['env'])
        self.assertEqual(observed['env']['RESTIC_PASSWORD'],'fixture-password')
        self.assertNotIn('fixture-password',(self.root/'restic.json').read_text())

    def test_retention_refuses_changed_inventory_and_out_of_scope_deletions(self):
        identity='a'*64; other='b'*64
        with patch.object(encrypted_backup,'snapshots',return_value=[{'id':identity}]),patch.object(encrypted_backup,'run',return_value=[{'remove':[{'id':identity}]}]):
            plan=encrypted_backup.retention(self.root)
        with patch.object(encrypted_backup,'snapshots',return_value=[{'id':other}]),patch.object(encrypted_backup,'run',return_value=[{'remove':[{'id':identity}]}]):
            with self.assertRaises(ValueError): encrypted_backup.retention(self.root,plan['plan'])

    def test_backup_preview_binds_encryption_backend_and_destination(self):
        self.vault(); original=project_vault.plan(self.root)
        encrypted_backup.configure(self.root,{'repository':str(self.base/'encrypted'),'enabled':True})
        reviewed=project_vault.plan(self.root)
        self.assertEqual(reviewed['destination'],str(self.base/'encrypted'))
        self.assertNotEqual(reviewed['plan'],original['plan'])
        with self.assertRaises(ValueError): project_vault.backup(self.root,original['plan'])
        encrypted_backup.configure(self.root,{'repository':str(self.base/'other-encrypted')})
        with self.assertRaises(ValueError): encrypted_backup.backup(self.root,reviewed['plan'])

    def test_restore_rejects_destination_in_encrypted_repository(self):
        self.vault(); encrypted_backup.configure(self.root,{'repository':str(self.base/'encrypted')})
        with patch.object(encrypted_backup,'snapshots',return_value=[{'id':'a'*64}]):
            with self.assertRaisesRegex(ValueError,'backup storage'):
                encrypted_backup.restore_plan(self.root,{'snapshot':'a'*64,'destination':str(self.base/'encrypted/restored')})

    def test_os_schedulers_are_owned_per_user_and_use_explicit_arguments(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(args)
            if '/XML' in args and '/Create' in args:
                text=Path(args[args.index('/XML')+1]).read_text(encoding='utf-16')
                self.assertIn('InteractiveToken',text); self.assertIn('LeastPrivilege',text)
                self.assertIn('backup --due',text)
            return Mock(returncode=1 if '/Query' in args else 0,stdout='')
        with patch.object(schedules,'user_sid',return_value='S-1-5-21-1'):
            schedules.configure(self.root,True,12,system='Windows',runner=runner)
        self.assertTrue(any('/Create' in c for c in calls))
        with self.assertRaisesRegex(ValueError,'unrelated'):
            schedules.configure(self.root,False,system='Windows',runner=lambda *a,**kw:Mock(returncode=0,stdout='unrelated'))
        schedules.configure(self.root,True,12,system='Linux',home=self.base,runner=runner)
        self.assertTrue(any('enable' in c for c in calls))
        self.assertTrue(schedules.read(self.root)['enabled'])
        schedules.configure(self.root,False,system='Linux',home=self.base,runner=runner)
        self.assertFalse(list((self.base/'.config/systemd/user').glob('*.timer')))
        with patch.object(schedules.os,'getuid',return_value=123,create=True):
            schedules.configure(self.root,True,12,system='Darwin',home=self.base,runner=runner)
        self.assertTrue(any('bootstrap' in c for c in calls))

    def test_scheduled_job_rejected_retries_and_keeps_error(self):
        self.vault(); control=self.control();atomic(self.root/'updates.json',{'automatic_check':False})
        with patch.object(control,'submit',side_effect=ValueError('queue full')): Services(control).tick()
        value=project_vault.read(self.root)
        self.assertEqual(value['schedule_status'],'rejected');self.assertIsNone(value['last_attempt']);self.assertTrue(value['last_error'])

    def test_interrupted_pending_claim_is_recovered_before_daily_interval(self):
        self.vault(); self.assertTrue(project_vault.claim_due(self.root,100000))
        self.assertFalse(project_vault.claim_due(self.root,100010))
        self.assertTrue(project_vault.claim_due(self.root,100301))


class ModelsAndTemplates(Fixture):
    def test_inheritance_overrides_and_dependency_constraints_are_enforced(self):
        parent={'schema_version':1,'id':'parent','name':'Parent','version':'1.0.0','description':'Fixture',
            'components':[{'id':'library','name':'Library','role':'custom','reference':'1.2.0'}], 'files':{'demo.txt':'parent'},'constraints':{'library':'>=1.0.0,<2.0.0'}}
        child={**parent,'id':'child','extends':parent,'components':[],'files':{'demo.txt':'child'}}
        self.assertEqual(architecture.resolve(child)['components'][0]['reference'],'1.2.0')
        self.assertFalse(architecture.review(child)['errors'])
        child['components']=[{'id':'library','name':'Library','role':'custom','reference':'2.0.0'}]
        self.assertTrue(architecture.review(child)['errors'])
        with self.assertRaises(ValueError): architecture.render(child,'demo')

    def test_measured_profiles_do_not_combine_contexts(self):
        for i,ctx in enumerate((8192,8192,16384)):
            atomic(self.root/'evaluations'/f'{i}.json',{'node':'local','model':'fixture','context':ctx,'hardware':{},'fixture_version':1,
                'created':i+1,'status':'passed','level':'coding-tested','first_text_seconds':i+1,'output_tokens_per_second':10})
        rows=insights.profiles(self.root)
        self.assertEqual(len(rows),2);self.assertEqual(next(r for r in rows if r['context']==8192)['first_text_seconds'],1.5)

    def test_inbox_records_model_diffs_and_rejects_stale_application(self):
        studio=Studio(self.root);studio.dispatch('templates')
        document=kit.read_json(studio.draft/'registry/catalog.json')
        before=document['providers']; provider=next(iter(before)); model=next(iter(before[provider]['models']))
        updated=copy.deepcopy(before); updated[provider]['models'][model]['name']='Changed fixture model'
        model_inbox.check(self.root,raw=json_bytes(updated));value=model_inbox.read(self.root)
        self.assertTrue(any(v['model']==model for v in value['changes']))
        with self.assertRaises(ValueError): model_inbox.apply(self.root,'stale')
        model_inbox.apply(self.root,value['plan'])
        self.assertEqual(kit.read_json(studio.draft/'registry/catalog.json')['providers'][provider]['models'][model]['name'],'Changed fixture model')

    def test_fallback_only_before_dispatch_and_respects_maintenance_and_gaming(self):
        control=self.control()
        control.config['nodes']['remote']={'kind':'worker','url':'https://192.168.1.10:8767','name':'Fixture'}
        primary={'node':'local','model':'a','cpu':False};fallback={'node':'remote','model':'b','cpu':False,'contract':{'level':'protocol-tested'}}
        control.config.update(primary=primary,fallback=fallback)
        control.health={'local':{'status':'offline','checked_at':time.time()},'remote':{'status':'online','checked_at':time.time(),'ready_models':['b']}}
        with control.lease({'model':ALIAS}) as (node,body):
            self.assertEqual(body['model'],'b')
            control.config['maintenance'].append('remote')
            self.assertEqual(body['model'],'b')
        with self.assertRaises(ValueError): control.route()
        control.config['maintenance']=[];control.mode='gaming';control.config['nodes']['remote']['gaming_eligible']=False
        with self.assertRaises(ValueError):control.route()


class Connectors(Fixture):
    def test_costs_use_correct_units_and_last_good_report_survives(self):
        monitoring.configure(self.root,{'account':{'provider':'anthropic','login':'fixture@example.com'}})
        identity=next(iter(monitoring.load(self.root)['accounts']))
        connectors.configure(self.root,{'account':identity,'connector':'anthropic-api','key_env':'FIXTURE_ADMIN_KEY'})
        data={'data':[{'starting_at':'2026-10-01T00:00:00Z','results':[{'amount':'123.45','currency':'USD'}]}]}
        with patch.dict(os.environ,{'FIXTURE_ADMIN_KEY':'fixture'}):
            connectors.refresh(self.root,identity,fetch=lambda *a:data)
            self.assertEqual(monitoring.load(self.root)['accounts'][identity]['report']['daily'][0]['amount'],'1.2345')
            with self.assertRaises(ValueError): connectors.refresh(self.root,identity,fetch=Mock(side_effect=OSError('raw private provider error')))
        report=monitoring.load(self.root)['accounts'][identity]['report']
        self.assertEqual(report['last_successful']['status'],'available')
        self.assertNotIn('raw private provider error',json.dumps(report))

    def test_codex_failure_preserves_success_and_history(self):
        monitoring.configure(self.root,{'codex_enabled':True})
        with patch.object(monitoring,'codex_binary',return_value='fixture'),patch.object(monitoring,'codex_snapshot',return_value={'status':'available','login':'fixture@example.com','plan':'Fixture','observed_at':1,'windows':[]}):
            monitoring.collect(self.root)
        with patch.object(monitoring,'codex_binary',return_value='fixture'),patch.object(monitoring,'codex_snapshot',side_effect=ValueError('fixture')):
            monitoring.collect(self.root)
        result=monitoring.load(self.root)
        self.assertEqual(result['observations']['codex']['last_successful']['login'],'fixture@example.com')
        self.assertEqual(len(result['history']['codex']),1)


if __name__=='__main__': unittest.main()
