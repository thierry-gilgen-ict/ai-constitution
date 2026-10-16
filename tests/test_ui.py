"""Presentation changes use isolated homes and never launch a real client."""
from pathlib import Path
from unittest.mock import patch

from tests.test_workspace_workflows import Fixture
from local_control import ui, launch_advice, project_setup
from local_control.studio import Studio
from scripts.catalog import digest


class Interface(Fixture):
    def test_preparation_directory_is_reviewed_and_cannot_escape(self):
        sub=self.project/'service';sub.mkdir()
        recipe={'schema':1,'id':'fixture','name':'Fixture','steps':[{'id':'check','kind':'command','argv':['python','--version'],'cwd':'service'}]}
        value=project_setup.preview(self.root,{'project':str(self.project),'recipe':recipe})
        self.assertEqual(project_setup.working_directory(self.project,value['steps'][0]),sub)
        for path in ('../outside','/absolute','C:/absolute','service/../../outside'):
            recipe['steps'][0]['cwd']=path
            with self.assertRaises(ValueError): project_setup.preview(self.root,{'project':str(self.project),'recipe':recipe})

    def test_home_and_detail_do_not_initialize_or_scan(self):
        control = self.control()
        with patch.object(Studio, 'initialize', side_effect=AssertionError('read mutated library')):
            data = ui.home(control)
            project = data['projects'][0]
            self.assertNotIn(str(self.project), project['id'])
            self.assertEqual(ui.detail(control, project['id'])['inspection']['findings'], [])
            self.assertEqual(ui.bootstrap(control)['ui_protocol'], 1)

    def test_preferences_version_and_scope_validation(self):
        ui.save_preferences(self.root, {'favorites':['one'], 'onboarding':{'goal':'project','clients':['claude-code']}})
        self.assertEqual(ui.preferences(self.root)['favorites'], ['one'])
        for body in ({'schema':9}, {'permissions':['apply']}, {'onboarding':{'step':True}}, {'onboarding':{'worker_platform':'unknown'}}):
            with self.assertRaises(ValueError): ui.save_preferences(self.root, body)
        self.assertEqual(ui.preferences(self.root)['favorites'], ['one'])

    def test_failed_inventory_retains_previous_observations(self):
        control=self.control()
        initial=ui.home(control)
        with patch('local_control.ui.projects', side_effect=OSError('unavailable')):
            stale=ui.home(control)
        self.assertTrue(stale['projects_stale'])
        self.assertEqual(stale['projects'],initial['projects'])
        self.assertTrue(stale['issues'])
        self.assertIn('operations',stale)

    def test_remote_projects_require_inventory_scope_and_keep_owner_identity(self):
        control=self.control()
        peer={'id':'fixture','name':'Other machine','scopes':['inventory']}
        original=ui.plans.read
        def read(root,name,default,**kwargs):
            if name=='fleet.json':return {'schema':1,'peers':{'fixture':peer}}
            if name=='peer-fixture.json':return {'schema':1,'received_at':1,'snapshot':{'projects':[{'id':'checkout','name':'Remote project'}]}}
            return original(root,name,default,**kwargs)
        with patch('local_control.ui.plans.read',side_effect=read):
            rows=ui.projects(control)
            remote=next(p for p in rows if not p['local'])
            self.assertEqual(remote['machine'],'Other machine')
            self.assertEqual(remote['observed_at'],1)
            self.assertNotIn('checkout',remote['id'])
            peer['scopes']=[]
            self.assertFalse(any(not p['local'] for p in ui.projects(control)))

    def draft(self):
        studio = Studio(self.root); studio.initialize()
        before = (studio.draft/'constitution.md').read_bytes()
        body = {'path':'constitution.md','sha256':digest(before), 'content':before.decode()+'\nTest candidate preference.\n'}
        return studio, before, body

    def test_candidates_do_not_publish_and_reject_concurrent_edit(self):
        studio, before, body = self.draft()
        saved = ui.draft_save(self.root, body)
        self.assertEqual((studio.draft/'constitution.md').read_bytes(), before)
        self.assertEqual(ui.draft_view(self.root)['files']['constitution.md']['revision'], saved['revision'])
        with self.assertRaisesRegex(ValueError, 'Another editor'): ui.draft_save(self.root, body)
        ui.draft_save(self.root, {**body, 'revision':saved['revision']})
        preview = ui.draft_action(self.root, 'preview', {})
        ui.draft_action(self.root, 'publish', {'plan':preview['plan']})
        self.assertEqual((studio.draft/'constitution.md').read_text(), body['content'])
        self.assertEqual(ui.drafts(self.root)['files'], {})

    def test_changed_library_or_policy_invalidates_publication(self):
        studio, before, body = self.draft(); ui.draft_save(self.root, body)
        preview = ui.draft_action(self.root, 'preview', {})
        (studio.draft/'constitution.md').write_bytes(before+b'\nIndependent edit.\n')
        with self.assertRaisesRegex(ValueError, 'changed'): ui.draft_action(self.root, 'publish', {'plan':preview['plan']})
        self.assertIn('constitution.md', ui.drafts(self.root)['files'])

    def test_discard_requires_current_candidate_and_keeps_library(self):
        studio, before, body = self.draft(); saved=ui.draft_save(self.root, body)
        with self.assertRaises(ValueError): ui.draft_action(self.root, 'discard', {'path':body['path'],'sha256':'stale'})
        ui.draft_action(self.root, 'discard', {'path':body['path'],'sha256':saved['revision']})
        self.assertEqual((studio.draft/'constitution.md').read_bytes(), before)

    def test_shared_claude_launcher_uses_reviewed_profile(self):
        control=self.control(); preview=launch_advice.advice(control, str(self.project))
        with patch('local_control.launcher.open_claude',return_value={'status':'fixture'}) as launch:
            launch_advice.launch(control,{'project':str(self.project),'plan':preview['plan'],'client':'claude-code','mode':'hosted','profile':'fixture'})
        launch.assert_called_once_with(self.root, str(self.project), 'fixture', 'hosted')


    def test_editor_candidates_are_isolated_and_revision_checked(self):
        from local_control import toolkits
        document={'schema':1,'id':'fixture','name':'Fixture','version':'1.0.0','rules':[], 'skills':[], 'commands':[], 'mcp':[]}
        body={'kind':'toolkit','context':'library','document':document}
        saved=ui.editor_draft(self.root,body,save=True)
        self.assertEqual(toolkits.overview(self.root)['kits'],{})
        self.assertEqual(ui.editor_draft(self.root,body)['draft']['document'],document)
        with self.assertRaisesRegex(ValueError,'another editor'): ui.editor_draft(self.root,body,save=True)
        with self.assertRaisesRegex(ValueError,'another editor'): ui.editor_draft(self.root,body,discard=True)
        ui.editor_draft(self.root,{**body,'revision':saved['revision']},discard=True)
        self.assertIsNone(ui.editor_draft(self.root,body)['draft'])
        self.assertEqual(toolkits.overview(self.root)['kits'],{})
        with self.assertRaises(ValueError): ui.editor_draft(self.root,{**body,'document':{**document,'schema':9}},save=True)
        with self.assertRaises(ValueError): ui.editor_draft(self.root,{'kind':'preparation','context':str(self.base/'unregistered')})

    def test_project_inspection_is_explicit_and_retained(self):
        control=self.control(); identity=ui.projects(control)[0]['id']
        with patch('local_control.inspector.inspect',side_effect=AssertionError('Implicit scan')):
            self.assertIsNone(ui.detail(control,identity)['inspected_at'])
        inspected=ui.inspect_project(control,identity)
        self.assertEqual(inspected['inspection']['installation'][0]['status'],'files-verified')
        self.assertEqual(inspected['inspection']['evidence']['client_loading']['value'],'unverified')
        with patch('local_control.inspector.inspect',side_effect=AssertionError('Implicit scan')):
            self.assertEqual(ui.detail(control,identity),inspected)
        with self.assertRaises(ValueError): ui.inspect_project(control,'unavailable')

    def test_operation_history_keeps_unresolved_work_and_filters_target(self):
        control=self.control()
        control.jobs={str(i):{'id':str(i),'status':'failed','operation':'fixture','label':'Fixture','created_at':i+1,'target':str(self.project)} for i in range(105)}
        first=ui.operations(control)
        self.assertEqual(first['total'],105);self.assertEqual(first['next'],100)
        self.assertEqual(len(ui.operations(control,{'offset':100})['jobs']),5)
        self.assertEqual(ui.operation_detail(control,'0')['operation']['id'],'0')
        self.assertNotIn('cancel',first['jobs'][0]['actions'])
        self.assertIsNone(first['jobs'][0]['elapsed_seconds'])
        control.jobs['104']['target']='another checkout'
        self.assertEqual(ui.operations(control,{'project':str(self.project)})['total'],104)
        with self.assertRaises(ValueError): ui.operations(control,{'offset':-1})
        with self.assertRaises(ValueError): ui.operations(control,{'project':str(self.base/'unknown')})

    def test_search_does_not_initialize_editable_library(self):
        from local_control import workflows
        control=self.control()
        with patch.object(Studio,'initialize',side_effect=AssertionError('Search initialized library')):
            self.assertTrue(workflows.search(control,'constitution')['items'])
