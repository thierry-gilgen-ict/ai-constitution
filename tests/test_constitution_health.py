"""Constitution health exercises disposable instructions and private evidence only."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import audit, constitution as kit
from local_control import auditing
from local_control.audit_store import Store
from tests.test_workspace_workflows import Fixture


class Inventory(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.project=self.base/'project';self.project.mkdir()
        self.profile=self.base/'profile';self.profile.mkdir()
    def scan(self,**kw):
        return audit.scan({'projects':[str(self.project)],'profiles':[{'id':'codex','client':'codex','home':str(self.profile)}],**kw})
    def test_read_only_chain_overrides_and_limits(self):
        (self.profile/'AGENTS.md').write_text('Global defaults\n')
        (self.project/'AGENTS.md').write_text('Root instructions\n')
        (self.project/'AGENTS.override.md').write_text('Override rules\n')
        (self.profile/'config.toml').write_text('project_doc_max_bytes=20\n')
        before={str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        result=self.scan();chain=result['chains'][0]
        self.assertTrue(any(s['status']=='shadowed' for s in chain['sources']))
        self.assertTrue(any(f['code']=='loading-limit' for f in result['findings']))
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()})
    def test_nested_fallback_and_unrelated_scope(self):
        nested=self.project/'nested';nested.mkdir();(nested/'TEAM.md').write_text('Nested fallback')
        (self.profile/'config.toml').write_text('project_doc_fallback_filenames=["TEAM.md"]')
        result=audit.scan({'projects':[str(self.project)],'profiles':[{'id':'codex','client':'codex','home':str(self.profile),'cwd':str(nested)}]})
        self.assertTrue(any(s['name']=='TEAM.md' for s in result['sources']))
        self.assertEqual(result['chains'][0]['sources'][0]['status'],'expected')
    def test_large_file_hashes_without_inlining(self):
        (self.project/'ROUTING.md').write_text('Instruction\n'*20000)
        result=self.scan();source=result['sources'][0]
        self.assertEqual(source['sha256'],audit.fingerprint(Path(source['path'])))
        self.assertTrue(source['sampled']);self.assertFalse(result['coverage']['complete'])
        self.assertNotIn('Instruction\nInstruction',json.dumps(result))
    def test_cursor_conditional_and_account_unknown(self):
        rules=self.project/'.cursor/rules';rules.mkdir(parents=True)
        (rules/'test.mdc').write_text('---\ndescription: Scoped rule\nalwaysApply: false\nglobs: "src/**"\n---\nUse tests.')
        result=audit.scan({'projects':[str(self.project)],'profiles':[{'id':'cursor','client':'cursor','home':str(self.profile)}]})
        self.assertEqual(result['chains'][0]['sources'][0]['status'],'conditional')
        self.assertFalse(result['coverage']['complete'])
    def test_invalid_and_expired_governance(self):
        folder=self.project/'.ai';folder.mkdir()
        value={'schema_version':1,'exceptions':[{'id':'one','reason':'temporary','owner_role':'owner','scope':'review','review_date':'2020-01-01'}]}
        (folder/'governance.json').write_text(json.dumps(value))
        self.assertIn('expired-exception',[f['code'] for f in self.scan()['findings']])
        value['risk']='nonsense';(folder/'governance.json').write_text(json.dumps(value))
        self.assertIn('invalid-governance',[f['code'] for f in self.scan()['findings']])

    def test_cursor_unsupported_markdown_and_nested_rules_are_not_assumed_loaded(self):
        folder=self.project/'frontend/.cursor/rules';folder.mkdir(parents=True)
        (folder/'nested.mdc').write_text('---\nalwaysApply: true\n---\nUse frontend checks.')
        (folder/'ignored.md').write_text('Plain markdown is not a native project rule.')
        (self.project/'CLAUDE.md').write_text('Another client guidance.')
        report=audit.scan({'projects':[str(self.project)],'profiles':[{'id':'cursor','client':'cursor','home':str(self.profile)}]})
        self.assertIn('unsupported-rule-format',[f['code'] for f in report['findings']])
        statuses={next(s['name'] for s in report['sources'] if s['id']==c['source']):c['status'] for c in report['chains'][0]['sources']}
        self.assertEqual(statuses['nested.mdc'],'conditional');self.assertEqual(statuses['CLAUDE.md'],'unsupported-entry')

    def test_prefixed_and_quoted_credentials_are_withheld(self):
        (self.project/'AGENTS.md').write_text('DATABASE_PASSWORD='+('s'*20)+'\n'+json.dumps({'service_token':'gh'+'p_'+('x'*36)}))
        report=self.scan();self.assertTrue(report['sources'][0]['sensitive'])
        self.assertNotIn('s'*20,json.dumps(report))
    def test_project_references_do_not_grant_access(self):
        (self.project/'AGENTS.md').write_text('Read [missing](missing.md) and [outside](../private.md).')
        (self.base/'private.md').write_text('private fixture')
        result=self.scan()
        self.assertIn('broken-reference',[f['code'] for f in result['findings']])
        self.assertNotIn('private fixture',json.dumps(result))
    def test_discovery_includes_worktree_file(self):
        (self.project/'.git').write_text('gitdir: ../metadata')
        metadata=self.base/'metadata';metadata.mkdir();(metadata/'HEAD').write_text('ref: refs/heads/example')
        result=audit.scan({'roots':[str(self.base)],'profiles':[]})
        self.assertEqual(len(result['projects']),1);self.assertTrue(result['projects'][0]['git'])
    def test_parent_traversal_cannot_pass_a_root_grant(self):
        outside=self.base/'outside';outside.mkdir()
        target={'kind':'project','root':str(self.project/'..'/'outside'),'files':{}}
        self.assertFalse(auditing.target_allowed(target,{'profiles':[],'roots':[str(self.project)]}))

    def test_monorepo_child_resolves_ancestors_only_within_selected_scope(self):
        (self.project/'.git').mkdir();(self.project/'.git/HEAD').write_text('ref: refs/heads/example')
        (self.project/'AGENTS.md').write_text('Repository-wide rules.')
        child=self.project/'packages/app';(child/'.ai').mkdir(parents=True);(child/'.ai/project.md').write_text('Application context.')
        (child/'AGENTS.md').write_text('Application rules.')
        profile={'id':'codex','client':'codex','home':str(self.profile)}
        scoped=audit.scan({'projects':[str(child)],'profiles':[profile]})
        self.assertTrue(any('Ancestor repository' in g['reason'] for g in scoped['coverage']['gaps']))
        self.assertFalse(any(s['path']==str(self.project/'AGENTS.md') for s in scoped['sources']))
        full=audit.scan({'roots':[str(self.project)],'profiles':[profile]})
        children=[p for p in full['projects'] if p['path']==str(child)];self.assertEqual(len(children),1)
        chain=next(c for c in full['chains'] if c['project']==children[0]['id'])
        names=[next(s['path'] for s in full['sources'] if s['id']==c['source']) for c in chain['sources']]
        self.assertIn(str(self.project/'AGENTS.md'),names);self.assertIn(str(child/'AGENTS.md'),names)


class Reconciliation(Fixture):
    def setUp(self):
        super().setUp()
        self.studio=__import__('local_control.studio',fromlist=['Studio']).Studio(self.root);self.studio.initialize()
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':[]}})
    def target(self):return auditing.overview(self.root)['targets'][0]['id']
    def test_file_integrity_separate_from_loading(self):
        result=auditing.scan(self.root)
        self.assertGreater(len(result['ownership']),0)
        self.assertTrue(all(v['integrity']=='current' for v in result['ownership'].values()))
        self.assertEqual(result['client_loading'],'unverified')
    def test_missing_owned_file_is_a_structural_finding(self):
        (self.project/'.ai/shared/research.md').unlink()
        result=auditing.scan(self.root)
        self.assertIn('installation-missing',[f['code'] for f in result['findings']])
    def test_restore_is_reviewed_idempotent_and_reversible(self):
        path=self.project/'.ai/shared/research.md';path.unlink()
        proposal=auditing.preview(self.root,{'target':self.target()})
        self.assertIn('restore-missing',[c['correction'] for c in proposal['changes']])
        body={'proposal':proposal['id'],'plan':proposal['plan'],'request':'a'*32}
        result=auditing.apply(self.root,body)
        self.assertTrue(path.exists());self.assertEqual(auditing.apply(self.root,body)['snapshot'],result['snapshot'])
        kit.rollback(self.state,result['snapshot']);self.assertFalse(path.exists())
    def test_stale_preview_preserves_later_edits(self):
        path=self.project/'.ai/shared/research.md';path.unlink()
        proposal=auditing.preview(self.root,{'target':self.target()})
        path.write_text('Later user edit')
        with self.assertRaisesRegex(ValueError,'changed'):auditing.apply(self.root,{'proposal':proposal['id'],'plan':proposal['plan']})
        self.assertEqual(path.read_text(),'Later user edit')
    def test_automatic_policy_needs_approved_source_and_types(self):
        path=self.project/'.ai/shared/research.md';path.unlink()
        proposal=auditing.preview(self.root,{'target':self.target()})
        with self.assertRaisesRegex(ValueError,'preauthorized'):auditing.apply(self.root,{'proposal':proposal['id'],'plan':proposal['plan']},automatic=True)
        auditing.configure(self.root,{'mode':'automatic','corrections':['restore-missing'],'approve_source':True})
        proposal=auditing.preview(self.root,{'target':self.target()})
        auditing.apply(self.root,{'proposal':proposal['id'],'plan':proposal['plan']},automatic=True)
        self.assertTrue(path.exists())
    def test_pin_and_local_modified_files_are_not_repaired(self):
        path=self.project/'.ai/shared/research.md';path.write_text('Local edit')
        with self.assertRaises(ValueError):auditing.preview(self.root,{'target':self.target()})
    def test_worker_grants_are_local_and_bound_to_roots(self):
        with self.assertRaises(ValueError):auditing.authorize(self.root,'worker','scan')
        auditing.grant(self.root,{'controller':'worker','roots':[str(self.project)],'permissions':['scan','report'],'profiles':[]},{'controllers':{'worker':{}}})
        granted=auditing.authorize(self.root,'worker','scan')
        with self.assertRaises(ValueError):auditing.authorize(self.root,'worker','apply')
        scoped=auditing.current_scope(self.root,granted)
        self.assertEqual(scoped['projects'],[str(self.project)]);self.assertEqual(scoped['profiles'],[])
    def test_repeated_scan_notifications_are_quiet(self):
        (self.project/'AGENTS.override.md').write_text('Temporary override')
        auditing.scan(self.root);before=len(Store(self.root).list('notification'))
        auditing.scan(self.root)
        self.assertEqual(len(Store(self.root).list('notification')),before)
    def test_unknown_schema_and_restore_never_restore_authority(self):
        store=Store(self.root)
        store.put('report','fixture',{'id':'fixture','findings':[]})
        store.put('request','x',{'status':'started'})
        backup=self.base/'backup';store.backup(backup)
        restored=Store(self.base/'restored');restored.restore(backup)
        self.assertIsNotNone(restored.get('report','fixture'));self.assertIsNone(restored.get('request','x'))
        with restored.connect() as db:db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):Store(self.base/'restored')
    def test_schedule_disabled_does_not_scan_or_write_projects(self):
        with patch.object(auditing,'scan') as run:
            self.assertEqual(auditing.scheduled(self.root)['status'],'disabled');run.assert_not_called()

    def test_semantic_due_is_independent_and_unchanged_snapshots_are_cached(self):
        auditing.configure(self.root,{'semantic':{'enabled':True}})
        first=auditing.scheduled(self.root);self.assertTrue(first['reviews'])
        self.assertEqual(auditing.scheduled(self.root)['status'],'not-due')
        Store(self.root).put('schedule','semantic',{'at':0})
        second=auditing.scheduled(self.root)
        self.assertEqual(first['reviews'],second['reviews'])

    def test_change_triggers_do_not_append_unchanged_reports(self):
        auditing.configure(self.root,{'schedule':{'enabled':True,'changes':True}})
        auditing.scheduled(self.root);before=len(Store(self.root).list('report',200))
        Store(self.root).put('schedule','last',{'at':time.time(),'checked_at':0})
        self.assertEqual(auditing.scheduled(self.root)['status'],'unchanged')
        self.assertEqual(len(Store(self.root).list('report',200)),before)

    def test_schedule_cannot_reconcile_an_enrolled_project_outside_selected_scope(self):
        second=self.base/'unselected';second.mkdir();kit.install(self.library,self.state,project=second)
        auditing.configure(self.root,{'mode':'propose','schedule':{'enabled':True}})
        selected=auditing.schedule_targets(self.root,auditing.scan(self.root))
        self.assertEqual(selected,{self.target()})
        with patch.object(auditing,'preview',wraps=auditing.preview) as preview:
            auditing.scheduled(self.root)
            self.assertTrue(all(call.args[1]['target'] in selected for call in preview.call_args_list))

    def test_reviewed_prose_respects_a_new_project_pause(self):
        from local_control import audit_review,synchronization
        path=self.project/'.ai/project.md';path.write_text('Facts.\n')
        report=auditing.scan(self.root);src=next(s for s in report['sources'] if s['path']==str(path))
        handoff=audit_review.prepare(self.root,{'report':report['id'],'sources':[src['id']]})
        proposal=audit_review.import_result(self.root,{'snapshot':handoff['id'],'result':{'schema':1,'snapshot':handoff['id'],'edits':[{'source':src['id'],'content':'Updated facts.\n','reason':'Clarify facts'}]}})
        from local_control.storage import atomic
        atomic(self.root/'synchronization.json',{'schema':1,'enabled':True,'paused_projects':[str(self.project)]})
        with self.assertRaisesRegex(ValueError,'pause'):audit_review.apply_reviewed(self.root,{'proposal':proposal['id'],'plan':proposal['plan'],'reviewed':True})
        self.assertEqual(path.read_text(),'Facts.\n')

    def test_loading_evidence_expires_on_configuration_change(self):
        profile=self.base/'profile';profile.mkdir();(profile/'config.toml').write_text('project_doc_max_bytes=32768')
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':[{'id':'codex','client':'codex','home':str(profile)}]}})
        report=auditing.scan(self.root);chain=report['chains'][0]
        auditing.loading(self.root,{'report':report['id'],'profile':'codex','project':chain['project'],'level':'agent-reported','client_version':'fixture'})
        self.assertEqual(auditing.scan(self.root)['chains'][0]['loading'],'agent-reported')
        (profile/'config.toml').write_text('project_doc_max_bytes=65536')
        self.assertEqual(auditing.scan(self.root)['chains'][0]['loading'],'stale')

    def test_semantic_import_never_auto_approves_and_preserves_managed_core(self):
        from local_control import audit_review
        context=self.project/'.ai/project.md';context.write_text('Existing project facts.\n')
        report=auditing.scan(self.root);src=next(s for s in report['sources'] if s['path']==str(context))
        handoff=audit_review.prepare(self.root,{'report':report['id'],'sources':[src['id']]})
        result={'schema':1,'snapshot':handoff['id'],'findings':[{'source':src['id'],'detail':'Clarify the test command.'}],
                'edits':[{'source':src['id'],'content':'Existing project facts.\nRun the documented tests.\n','reason':'Make acceptance observable.'}]}
        proposal=audit_review.import_result(self.root,{'snapshot':handoff['id'],'result':result})
        self.assertFalse(proposal['automatic_eligible']);self.assertEqual(context.read_text(),'Existing project facts.\n')
        with self.assertRaises(ValueError):audit_review.apply_reviewed(self.root,{'proposal':proposal['id'],'plan':proposal['plan']})
        audit_review.apply_reviewed(self.root,{'proposal':proposal['id'],'plan':proposal['plan'],'reviewed':True})
        self.assertIn('documented tests',context.read_text())

    def test_semantic_result_rejects_invented_sources_and_stale_snapshots(self):
        from local_control import audit_review
        report=auditing.scan(self.root);handoff=audit_review.prepare(self.root,{'report':report['id']})
        with self.assertRaises(ValueError):audit_review.import_result(self.root,{'snapshot':handoff['id'],'result':{'schema':1,'snapshot':handoff['id'],'findings':[{'source':'invented','detail':'Do something'}]}})
        self.assertIn('untrusted DATA',handoff['prompt'])

    def test_semantic_review_requires_a_profile_when_client_profiles_are_ambiguous(self):
        from local_control import audit_review
        profiles=[]
        for name in ('work','personal'):
            path=self.base/name;path.mkdir();(path/'AGENTS.md').write_text(name+' global guidance.')
            profiles.append({'id':name,'client':'codex','home':str(path)})
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':profiles}})
        report=auditing.scan(self.root)
        with self.assertRaisesRegex(ValueError,'profile'):audit_review.prepare(self.root,{'report':report['id'],'client':'codex'})
        handoff=audit_review.prepare(self.root,{'report':report['id'],'client':'codex','profile':'work'})
        self.assertEqual(handoff['profile'],'work');self.assertNotIn('personal global guidance',handoff['prompt'])

    def test_mcp_scope_is_revocable_and_has_no_apply_interface(self):
        from local_control.audit_mcp import Access
        with self.assertRaises(ValueError):Access(self.root,self.project,'codex')
        auditing.configure(self.root,{'mcp_projects':[{'project':str(self.project),'profiles':['codex']}]})
        access=Access(self.root,self.project,'codex');access.scan()
        self.assertEqual(len(access.report()['projects']),1)
        auditing.configure(self.root,{'mcp_projects':[]})
        with self.assertRaises(ValueError):access.report()

    def test_target_policy_can_only_preapprove_selected_corrections(self):
        auditing.configure(self.root,{'target':self.target(),'mode':'automatic','corrections':['restore-missing']})
        self.assertEqual(auditing.policy_for(self.root,self.target())['mode'],'automatic')
        self.assertEqual(auditing.settings(self.root)['mode'],'notify')

    def test_unknown_platform_controls_are_not_claimed_as_enforcement(self):
        from local_control.audit_governance import compare_controls
        findings=compare_controls({'status':'observed','required_reviews':None,'classic_protection':'unknown','required_checks':[],'open_candidates':3}, {'required_reviews':2,'required_checks':['tests'],'wip_limit':1})
        self.assertEqual(next(f['evidence'] for f in findings if f['code']=='review-enforcement-unknown'),'unknown')
        self.assertEqual(next(f['evidence'] for f in findings if f['code']=='check-enforcement-gap'),'unknown')
        self.assertTrue(any(f['code']=='wip-threshold' for f in findings))


class OptionalMCP(Fixture):
    def test_official_sdk_protocol_and_tool_boundary(self):
        try:from mcp.client import Client
        except ImportError:self.skipTest('Optional MCP runtime not installed')
        from local_control.audit_mcp import server
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':[]},'mcp_projects':[{'project':str(self.project),'profiles':['codex']}]})
        import asyncio
        async def exercise():
            async with Client(server(self.root,self.project,'codex')) as client:
                tools=await client.list_tools()
                self.assertEqual({t.name for t in tools.tools},{'constitution_inventory','constitution_report','constitution_scan','constitution_propose_reconciliation'})
                result=await client.call_tool('constitution_scan',{})
                self.assertFalse(result.is_error)
        asyncio.run(exercise())
    def test_stdio_transport_in_disposable_project(self):
        try:
            from mcp.client import Client
            from mcp.client.stdio import StdioServerParameters
        except ImportError:self.skipTest('Optional MCP runtime not installed')
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':[]},'mcp_projects':[{'project':str(self.project),'profiles':['codex']}]})
        import asyncio
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'scripts/constitution_mcp.py'),'--state-dir',str(self.root),'--project',str(self.project),'--profile','codex'])
            async with Client(params) as client:
                tools=await client.list_tools();self.assertEqual(len(tools.tools),4)
                response=await client.call_tool('constitution_inventory',{});self.assertFalse(response.is_error)
        asyncio.run(exercise())


if __name__=='__main__':unittest.main()
