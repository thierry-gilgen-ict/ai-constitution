"""Claude support is exercised only in disposable homes and fake clients."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts import audit, constitution as kit, clients
from scripts.adoption import project_record


class ClaudeCore(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.home=self.base/'home';self.home.mkdir()
        self.project=self.base/'project';self.project.mkdir();self.state=self.base/'state'
        self.profile=self.home/'.claude';self.profile.mkdir()

    def scan(self, **extra):
        return audit.scan({'projects':[str(self.project)],'profiles':[{'id':'claude','client':'claude-code','home':str(self.profile),'client_version':'2.1.286',**extra}]})

    def test_opt_in_enrollment_ownership_and_adoption(self):
        (self.project/'CLAUDE.md').write_text('Existing owner guidance\n')
        kit.install(kit.ROOT,self.state,project=self.project)
        self.assertNotIn('@AGENTS.md',(self.project/'CLAUDE.md').read_text())
        kit.install(kit.ROOT,self.state,project=self.project,selected_clients=['claude-code'])
        lock=json.loads((self.project/'.ai/constitution.lock.json').read_text())
        self.assertEqual(lock['schema_version'],2)
        self.assertEqual(kit.state_load(self.state)['schema_version'],2)
        self.assertIn('Existing owner guidance',(self.project/'CLAUDE.md').read_text())
        record=project_record(self.project,modules=kit.MODULES,safe_path=kit.safe_path,managed_hash=kit.managed_hash,digest=kit.digest)
        self.assertIn('claude-code',record['clients'])
        (self.project/'CLAUDE.md').write_text((self.project/'CLAUDE.md').read_text().replace('@AGENTS.md','Changed owned block'))
        with self.assertRaisesRegex(ValueError,'Local edits'):kit.install(kit.ROOT,self.state,project=self.project)

    def test_custom_global_home_survives_sync_and_doctor(self):
        custom=self.base/'custom';custom.mkdir()
        kit.install(kit.ROOT,self.state,platform='claude-code',home=self.home,claude_dir=custom)
        self.assertTrue((custom/'CLAUDE.md').is_file())
        self.assertFalse(any(r['status']=='error' for r in kit.sync(kit.ROOT,self.state)))
        self.assertTrue(all(r['status']=='files-verified' for r in kit.doctor(kit.ROOT,self.state)))

    def test_imports_rules_local_and_read_only(self):
        (self.project/'AGENTS.md').write_text('Project standards\n')
        (self.project/'CLAUDE.md').write_text('@AGENTS.md\n`@missing.md`\n')
        rules=self.project/'.claude/rules';rules.mkdir(parents=True)
        (rules/'python.md').write_text('---\npaths:\n  - "**/*.py"\n---\nUse typed functions\n')
        (self.project/'CLAUDE.local.md').write_text('Personal guidance\n')
        before={str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        result=self.scan();sources={s['id']:s for s in result['sources']}
        chain=result['chains'][0]['sources']
        self.assertTrue(any(sources[c['source']]['name']=='AGENTS.md' and c['status']=='expected' for c in chain))
        self.assertTrue(any(c['status']=='conditional' for c in chain))
        self.assertFalse(any(f['code']=='missing-reference' for f in result['findings']))
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()})

    def test_external_imports_exclusions_and_version_gate(self):
        outside=self.base/'outside.md';outside.write_text('Never read outside scope')
        (self.project/'CLAUDE.md').write_text('@../outside.md\n@missing.md\n')
        report=self.scan()
        self.assertTrue(any('outside approved' in g['reason'] for g in report['coverage']['gaps']))
        self.assertNotIn(str(outside),[s['path'] for s in report['sources']])
        (self.project/'CLAUDE.md').unlink();(self.project/'AGENTS.md').write_text('Shared guidance')
        old=self.scan(client_version='2.1.100')
        self.assertTrue(any(c['status']=='version-dependent' for c in old['chains'][0]['sources']))

    def test_registry_keeps_legacy_defaults(self):
        self.assertEqual(clients.LEGACY,('codex','cursor'))
        self.assertEqual(clients.capabilities()['claude-code']['local_api'],'messages')

    def test_existing_unowned_import_is_not_duplicated_or_rewritten(self):
        path=self.project/'CLAUDE.md';path.write_text('Owner guidance\n@./AGENTS.md\n')
        before=path.read_bytes()
        kit.install(kit.ROOT,self.state,project=self.project,selected_clients=['claude-code'])
        self.assertEqual(before,path.read_bytes())
        record=project_record(self.project,modules=kit.MODULES,safe_path=kit.safe_path,managed_hash=kit.managed_hash,digest=kit.digest)
        self.assertNotIn('CLAUDE.md',record['files'])
        path.write_text('Owner removed import\n')
        with self.assertRaisesRegex(ValueError,'Unowned'):kit.install(kit.ROOT,self.state,project=self.project)

    def test_managed_policy_requires_scope_and_cannot_be_excluded(self):
        from unittest.mock import patch
        managed=self.base/'organization/ClaudeCode';managed.mkdir(parents=True)
        path=managed/'CLAUDE.md';path.write_text('Organization policy')
        (self.profile/'settings.json').write_text(json.dumps({'claudeMdExcludes':[str(path)]}))
        with patch('scripts.claude_audit.platform.system',return_value='Windows'),patch.dict('os.environ',{'ProgramFiles':str(managed.parent)}):
            first=self.scan();second=self.scan(files=[str(path)])
        self.assertTrue(any('Organization instructions' in gap['reason'] for gap in first['coverage']['gaps']))
        policy=next(s for s in second['sources'] if s['path']==str(path))
        self.assertEqual(policy['classification'],'managed-policy')
        self.assertTrue(any(c['source']==policy['id'] and c['status']=='expected' for c in second['chains'][0]['sources']))
