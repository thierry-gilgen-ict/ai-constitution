"""Private baselines, editor transactions and activation; no real client writes."""
import copy
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import constitution as kit, architecture, releases
from scripts.catalog import json_bytes, digest
from local_control.studio import Studio
from local_control.core import Control
from local_control.server import Server


class Templates(unittest.TestCase):
    def setUp(self):
        self.template = kit.read_json(ROOT / 'templates/architectures/web-product.json')

    def test_bundled_components_and_baselines_are_consistent(self):
        for path in (ROOT / 'templates/architectures').glob('*.json'):
            value = architecture.validate(kit.read_json(path))
            self.assertFalse(architecture.review(value)['errors'])
            files, _ = architecture.render(value, 'test-project')
            self.assertIn(b'test-project', files['compose.yaml'])
            self.assertIn(b'PostgreSQL 17', files['compose.yaml'])
            self.assertNotIn(b'{{project_name}}', files['compose.yaml'])
        catalog = kit.read_json(ROOT / 'templates/architecture-components.json')
        architecture.validate({**self.template, 'components': catalog['components']})

    def test_missing_capability_and_conflicts_stop_apply(self):
        self.template['components'] = [v for v in self.template['components'] if v['id'] != 'postgres']
        self.assertTrue(any('sql' in v for v in architecture.review(self.template)['errors']))
        with self.assertRaises(ValueError): architecture.render(self.template, 'demo')
        self.template['components'][0]['conflicts'] = ['typescript']
        self.assertTrue(any('conflicts' in v for v in architecture.review(self.template)['errors']))

    def test_cross_platform_paths_and_collisions_are_rejected(self):
        bad = ['../x', '/tmp/x', 'C:/x', 'a\\b', 'a//b', '.git/config', '.ai/project.md',
               'AGENTS.md', '.env', 'test/.ENV.prod', 'NUL.txt', 'COM1', 'a./x', 'a /x',
               'a:b', 'a?b', 'a\x00b', 'credentials.json', 'keys.pem', 'script.exe']
        for name in bad:
            with self.subTest(name=name), self.assertRaises(ValueError):
                architecture.validate({**self.template, 'files': {name: 'text'}})
        for paths in ({'a':'', 'a/b':''}, {'README.md':'', 'readme.md':''}):
            with self.assertRaises(ValueError): architecture.validate({**self.template,'files':paths})

    def test_credentials_values_untrusted_urls_and_unknown_fields(self):
        for field in ('password', 'api_key', 'client_secret'):
            with self.assertRaises(ValueError):
                architecture.validate({**self.template, 'decisions':[field + '="' + 'a' * 30 + '"']})
        component = self.template['components'][0]
        for url in ('http://example.org/repo','https://user:pass@example.org/repo','https://example.org/?token=x'):
            component['repository'] = url
            with self.assertRaises(ValueError): architecture.validate(self.template)
        component['repository'] = ''
        component['env'] = [{'name':'API_KEY','purpose':'API','secret':True,'value':'not-supported'}]
        with self.assertRaises(ValueError): architecture.validate(self.template)
        with self.assertRaises(ValueError): architecture.validate({**self.template, 'run':'shell'})


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.state = self.base / 'state'
        self.studio = Studio(self.base / 'control', source=ROOT, state=self.state)
        self.templates = self.studio.dispatch('templates')['templates']
        self.value = copy.deepcopy(self.templates[0]['template'])
        self.project = self.base / 'project'; self.project.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def file_body(self, name='constitution.md'):
        value = self.studio.dispatch('file', query={'path':[name]})
        return {'path':name,'sha256':value['sha256'],'content':value['content'] + '\nPrefer clear acceptance checks.\n'}

    def save(self, body):
        plan = self.studio.dispatch('file-preview', body)
        return self.studio.dispatch('file-save', {**body,'plan':plan['plan']})

    def project_body(self):
        return {'project':str(self.project),'name':'demo-project','template':self.value}

    def apply_project(self, body=None):
        body = body or self.project_body()
        plan = self.studio.dispatch('project-preview', body)
        return self.studio.dispatch('project-apply', {**body, 'plan':plan['plan']})

    def test_draft_edit_rebuilds_generators_without_activation_or_source_writes(self):
        original = (ROOT / 'constitution.md').read_bytes()
        body = self.file_body()
        with patch('subprocess.run', side_effect=AssertionError('No draft execution')):
            plan = self.studio.dispatch('file-preview', body)
            paths = [v['path'] for v in plan['changes']]
            self.assertIn('adapters/codex/AGENTS.md', paths)
            self.save(body)
        self.assertEqual((ROOT / 'constitution.md').read_bytes(), original)
        self.assertFalse((self.state / 'active-release.json').exists())
        kit.build(self.studio.draft, check=True)

    def test_stale_editor_and_stale_whole_library_plan_are_rejected(self):
        first = self.file_body()
        plan = self.studio.dispatch('file-preview', first)
        self.save(self.file_body('engineering.md'))
        with self.assertRaisesRegex(ValueError, 'Library changed'):
            self.studio.dispatch('file-save', {**first, 'plan':plan['plan']})
        self.save(first)
        with self.assertRaisesRegex(ValueError, 'changed since opening'):
            self.studio.dispatch('file-preview', first)

    def test_invalid_registry_never_changes_draft(self):
        body = self.file_body('registry/routes.json')
        before = (self.studio.draft / body['path']).read_bytes()
        body['content'] = '{"routes":[{"platform":"codex"}]}'
        with self.assertRaises(ValueError): self.studio.dispatch('file-preview', body)
        self.assertEqual((self.studio.draft / body['path']).read_bytes(), before)
        body['content'] = 'not JSON'
        with self.assertRaisesRegex(ValueError, 'Invalid JSON'): self.studio.dispatch('file-preview', body)

    def test_read_only_files_paths_and_large_catalog_paging(self):
        for name in ['../config.json','scripts/../constitution.md','local_control/../../x', 'auth.json', '.git/config']:
            with self.assertRaises(ValueError): self.studio.dispatch('file', query={'path':[name]})
        for name in ['routing.md','adapters/codex/AGENTS.md','scripts/constitution.py','registry/catalog.json']:
            value = self.studio.dispatch('file',query={'path':[name]})
            self.assertFalse(value['editable'])
            with self.assertRaises(ValueError): self.studio.dispatch('file-preview',{'path':name,'content':'x','sha256':value['sha256']})
        value = self.studio.dispatch('file',query={'path':['registry/catalog.json']})
        self.assertIsNotNone(value['next'])
        next_page = self.studio.dispatch('file',query={'path':['registry/catalog.json'],'offset':[str(value['next'])]})
        self.assertEqual(value['sha256'], next_page['sha256'])
        self.assertEqual(next_page['offset'], 64000)

    def test_editor_link_escape_is_refused(self):
        path = self.studio.draft / 'docs/linked.md'
        try: path.symlink_to(ROOT / 'README.md')
        except (OSError, NotImplementedError): self.skipTest('Symlink creation unavailable')
        with self.assertRaises(ValueError): self.studio.dispatch('file', query={'path':['docs/linked.md']})
        with self.assertRaises(ValueError): self.studio.dispatch('files')

    def test_personal_template_save_import_and_collision(self):
        self.value['id'] = 'my-template'
        body = {'template':self.value,'sha256':None}
        plan = self.studio.dispatch('template-preview',body)
        self.studio.dispatch('template-save',{**body,'plan':plan['plan']})
        self.assertTrue(any(v['template']['id'] == 'my-template' for v in self.studio.dispatch('templates')['templates']))
        with self.assertRaisesRegex(ValueError,'changed since opening'): self.studio.dispatch('template-preview',body)

    def test_apply_preserves_context_onboards_and_rolls_back(self):
        (self.project / 'AGENTS.md').write_text('Keep my project instructions.\n',encoding='utf-8')
        result = self.apply_project()
        self.assertIn('Keep my project instructions.', (self.project / 'AGENTS.md').read_text())
        self.assertIn('.ai/architecture.md', (self.project / 'AGENTS.md').read_text())
        self.assertTrue((self.project / '.ai/constitution.lock.json').exists())
        self.assertTrue((self.project / 'compose.yaml').exists())
        self.assertEqual(self.apply_project()['status'], 'unchanged')
        kit.rollback(self.state,result['snapshot'])
        self.assertEqual((self.project / 'AGENTS.md').read_text(), 'Keep my project instructions.\n')
        self.assertFalse((self.project / 'compose.yaml').exists())

    def test_project_preview_rejects_existing_file_and_later_edits(self):
        (self.project / 'compose.yaml').write_text('user data',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'would be overwritten'): self.apply_project()
        (self.project / 'compose.yaml').unlink()
        body = self.project_body(); plan = self.studio.dispatch('project-preview',body)
        (self.project / 'AGENTS.md').write_text('Added later.',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed since preview'):
            self.studio.dispatch('project-apply',{**body,'plan':plan['plan']})
        self.assertFalse((self.project / 'compose.yaml').exists())

    def test_template_updates_keep_omitted_files_and_refuse_modified_outputs(self):
        self.apply_project()
        self.value['files'] = {}
        result = self.apply_project()
        self.assertEqual(result['retained_files'], ['compose.yaml'])
        self.assertTrue((self.project / 'compose.yaml').exists())
        (self.project / '.ai/architecture.md').write_text('My changes',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'would be overwritten'): self.apply_project()

    def test_pinned_project_keeps_its_instruction_bundle(self):
        kit.install(ROOT,self.state,project=self.project,pin=True)
        original = (self.project / '.ai/shared/constitution.md').read_bytes()
        self.save(self.file_body())
        self.apply_project()
        self.assertEqual((self.project / '.ai/shared/constitution.md').read_bytes(), original)

    def test_activation_exact_preview_with_global_and_pinned_targets(self):
        home = self.base / 'home'; home.mkdir()
        kit.install(ROOT,self.state,platform='codex',home=home)
        kit.install(ROOT,self.state,project=self.project,pin=True)
        pinned = (self.project / '.ai/shared/constitution.md').read_bytes()
        self.save(self.file_body())
        plan = self.studio.dispatch('activation-preview',{})
        again = self.studio.dispatch('activation-preview',{})
        self.assertEqual(plan['plan'], again['plan'])
        result = self.studio.dispatch('activate',{'plan':plan['plan']})
        self.assertEqual(result['plan'], plan['plan'])
        self.assertEqual(pinned, (self.project / '.ai/shared/constitution.md').read_bytes())
        self.assertIn('Prefer clear acceptance checks.',(home / '.codex/AGENTS.md').read_text())
        installed_source = Path(json.loads((home / '.config/ai-constitution/libraries/codex/installation.json').read_text())['source_root'])
        self.assertEqual(installed_source, releases.selected(self.state, ROOT))
        kit.rollback(self.state,result['snapshot'])
        self.assertNotIn('Prefer clear acceptance checks.',(home / '.codex/AGENTS.md').read_text())

    def test_activation_preview_invalidated_by_changed_enrollment(self):
        plan = self.studio.dispatch('activation-preview',{})
        kit.install(ROOT,self.state,project=self.project,pin=True)
        with self.assertRaisesRegex(ValueError,'changed since preview'):
            self.studio.dispatch('activate',{'plan':plan['plan']})
        self.assertFalse((self.state / 'active-release.json').exists())

    def test_draft_rollback_preserves_later_edits(self):
        first = self.save(self.file_body())
        second = self.save(self.file_body())
        with self.assertRaisesRegex(ValueError,'changed since'):
            self.studio.dispatch('rollback',{'snapshot':first['snapshot']})
        self.studio.dispatch('rollback',{'snapshot':second['snapshot']})
        self.studio.dispatch('rollback',{'snapshot':first['snapshot']})
        self.assertEqual((self.studio.draft/'constitution.md').read_bytes(), (ROOT/'constitution.md').read_bytes())

    def test_bundle_refresh_merges_untouched_files_but_protects_conflicts(self):
        source = self.base / 'source'
        for name,data in releases.files(ROOT).items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.studio.source = source
        self.save(self.file_body())
        (source/'engineering.md').write_text('Updated engineering guidance.\n',encoding='utf-8')
        plan = self.studio.dispatch('refresh-preview',{})
        self.assertFalse(plan['conflicts'])
        self.studio.dispatch('refresh-apply',{'plan':plan['plan']})
        self.assertIn('Prefer clear', (self.studio.draft/'constitution.md').read_text())
        self.assertEqual((self.studio.draft/'engineering.md').read_text(),'Updated engineering guidance.\n')
        (source/'constitution.md').write_text('New upstream constitution.\n',encoding='utf-8')
        plan = self.studio.dispatch('refresh-preview',{})
        self.assertIn('constitution.md',plan['conflicts'])
        with self.assertRaisesRegex(ValueError,'Customized files'):
            self.studio.dispatch('refresh-apply',{'plan':plan['plan']})


class StudioHTTP(unittest.TestCase):
    def test_admin_only_and_worker_denial(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();control=Control(root/'control', lambda *a,**k:{})
            for worker in (False, True):
                control.config['legacy_worker_token'] = True
                server=Server(('127.0.0.1',0),control,worker=worker)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    for token in ('',control.config['gateway_token'],control.config['token']):
                        connection=http.client.HTTPConnection(*server.server_address,timeout=20)
                        connection.request('GET','/api/studio/templates',headers={'Authorization':'Bearer '+token})
                        response=connection.getresponse();response.read();connection.close()
                        self.assertEqual(response.status, (404 if worker else 200) if token == control.config['token'] else 401)
                finally:
                    server.shutdown();server.server_close();thread.join()
            control.pool.shutdown(wait=True)


if __name__ == '__main__': unittest.main()
