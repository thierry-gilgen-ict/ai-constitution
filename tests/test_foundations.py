"""Portable ownership, release migrations and durable provider-review evidence."""
import copy
import json
from pathlib import Path
import tempfile
import io
import zipfile
import unittest
from unittest import mock
import test_constitution as fixtures
from test_constitution import kit, catalog
import policy
import releases
import source_review


class Adoption(unittest.TestCase):
    setUp = fixtures.Workspace.setUp

    def original(self, pin=False):
        kit.install(self.root, self.state, project=self.project, pin=pin)
        return self.base / "second-computer"

    def test_adopt_old_bundle_then_upgrade_preserves_context(self):
        state = self.original()
        context = self.project / ".ai/project.md"
        context.write_bytes(b"Private project facts\r\n")
        before = {p: p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        (self.root / "VERSION").write_text("0.2.0", encoding="utf-8")
        kit.build(self.root)
        kit.adopt(state, self.project, dry_run=True)
        self.assertFalse(state.exists())
        result = kit.adopt(state, self.project)
        self.assertIn("authenticity not established", result["evidence"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(kit.sync(self.root, state)[0]["status"], "installed")
        self.assertEqual(context.read_bytes(), b"Private project facts\r\n")
        self.assertEqual((self.project / '.ai/shared/VERSION').read_text(), '0.2.0')

    def test_preserves_pin_and_rollback_only_unenrolls(self):
        state = self.original(pin=True)
        before = (self.project / "AGENTS.md").read_bytes()
        result = kit.adopt(state, self.project)
        self.assertTrue(result["pinned"])
        self.assertEqual(kit.sync(self.root, state)[0]["status"], "skipped-pinned")
        kit.rollback(state, result["snapshot"])
        self.assertFalse((state / "installations.json").exists())
        self.assertEqual(before, (self.project / "AGENTS.md").read_bytes())

    def test_modified_bundle_refused(self):
        state = self.original()
        (self.project / '.ai/shared/engineering.md').write_text('Edited', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, "local edits"):
            kit.adopt(state, self.project)
        self.assertFalse(state.exists())

    def test_lock_cannot_claim_arbitrary_file_or_nonboolean_ownership(self):
        state = self.original()
        lock_path = self.project / '.ai/constitution.lock.json'
        original = kit.read_json(lock_path)
        for name in ('../outside', '/absolute', 'C:/outside', '.ai/project.md'):
            lock = copy.deepcopy(original)
            lock['files'][name] = {'managed': False, 'sha256': 'a'*64}
            lock_path.write_bytes(catalog.json_bytes(lock))
            with self.assertRaisesRegex(ValueError, 'allowed managed files'):
                kit.adopt(state, self.project)
        lock = copy.deepcopy(original)
        lock['files']['AGENTS.md']['managed'] = 'false'
        lock_path.write_bytes(catalog.json_bytes(lock))
        with self.assertRaisesRegex(ValueError, 'managed-file evidence'):
            kit.adopt(state, self.project)
        self.assertFalse(state.exists())

    def test_duplicate_fields_and_reversed_markers_rejected(self):
        state = self.original()
        path = self.project / '.ai/constitution.lock.json'
        path.write_text(path.read_text().replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            kit.adopt(state, self.project)
        self.assertIsNone(kit.managed_hash((kit.END + kit.BEGIN).encode()))

    def test_missing_private_state_requires_explicit_adoption(self):
        state = self.original()
        with self.assertRaisesRegex(ValueError, '--adopt'):
            kit.install(self.root, state, project=self.project)


class ReleasePolicy(unittest.TestCase):
    setUp = fixtures.Workspace.setUp

    def test_upgrade_preserves_source_preferences_context_and_pins(self):
        kit.install(self.root, self.state, platform='codex', home=self.home)
        kit.install(self.root, self.state, project=self.project, pin=True)
        before = (self.project / 'AGENTS.md').read_bytes()
        prefs = self.state.parent / 'overrides/policy.json'
        catalog.atomic_bytes(prefs, catalog.json_bytes({'schema_version': 1, 'instructions': {'constitution.md': 'Private preference.'}}))
        (self.root / 'VERSION').write_text('0.2.0', encoding='utf-8')
        kit.build(self.root)
        source_files = releases.files(self.root)
        preview = kit.upgrade(self.root, self.state, dry_run=True)
        self.assertEqual(preview['status'], 'preview')
        self.assertFalse((self.state / 'active-release.json').exists())
        result = kit.upgrade(self.root, self.state)
        self.assertEqual(releases.files(self.root), source_files)
        self.assertEqual(before, (self.project / 'AGENTS.md').read_bytes())
        self.assertIn('Private preference.', (self.home / '.codex/AGENTS.md').read_text(encoding='utf-8'))
        selected = releases.selected(self.state, self.root)
        self.assertEqual(selected.name, result['release'])
        self.assertEqual(kit.sync(selected, self.state)[0]['status'], 'unchanged')
        kit.rollback(self.state, result['snapshot'])
        self.assertFalse((self.state / 'active-release.json').exists())
        self.assertEqual(prefs.read_bytes(), catalog.json_bytes({'schema_version': 1, 'instructions': {'constitution.md': 'Private preference.'}}))

    def test_portable_bundle_contains_only_project_prose_and_routes(self):
        personal = {'schema_version': 1, 'instructions': {'constitution.md': 'Private preference.'},
                    'routes': [{'platform': 'codex', 'task': 'small', 'preferred': 'codex:deep'}]}
        catalog.atomic_bytes(self.state.parent / 'overrides/policy.json', catalog.json_bytes(personal))
        project = {'schema_version': 1, 'instructions': {'engineering.md': 'Project test command.'}}
        catalog.atomic_bytes(self.project / '.ai/policy.json', catalog.json_bytes(project))
        kit.install(self.root, self.state, project=self.project)
        self.assertNotIn('Private preference.', (self.project / 'AGENTS.md').read_text(encoding='utf-8'))
        self.assertIn('Project test command.', (self.project / '.ai/shared/engineering.md').read_text(encoding='utf-8'))
        self.assertEqual(policy.resolve(self.root, self.state, self.project)['provenance']['codex/small'], 'personal')
        self.assertEqual(policy.resolve(self.root, self.state, self.project, portable=True)['provenance']['codex/small'], 'release')

    def test_drift_in_one_target_prevents_activation_and_other_target_writes(self):
        kit.install(self.root, self.state, platform='codex', home=self.home)
        kit.install(self.root, self.state, project=self.project)
        global_before = (self.home / '.codex/AGENTS.md').read_bytes()
        (self.project / '.ai/shared/research.md').write_text('User edits', encoding='utf-8')
        (self.root / 'VERSION').write_text('0.2.0', encoding='utf-8')
        kit.build(self.root)
        with self.assertRaisesRegex(ValueError, 'Local edits'):
            kit.upgrade(self.root, self.state)
        self.assertFalse((self.state / 'active-release.json').exists())
        self.assertEqual(global_before, (self.home / '.codex/AGENTS.md').read_bytes())

    def test_archive_integrity_and_path_validation(self):
        archive = self.base / 'release.zip'
        result = releases.export(self.root, archive)
        self.assertIn('VERSION', releases.unpack(archive.read_bytes(), result['sha256']))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            releases.unpack(archive.read_bytes(), '0' * 64)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('../escape', 'invalid')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            releases.unpack(stream.getvalue(), catalog.digest(stream.getvalue()))

    def test_installed_release_tampering_is_detected(self):
        kit.upgrade(self.root, self.state)
        root = releases.selected(self.state, self.root)
        (root / 'constitution.md').write_text('Changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            releases.selected(self.state, self.root)


class Metadata(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'source'
        self.state = self.root.parent / 'private/state'
        self.payload = {'test': {'name': 'Test', 'models': {'one': {'name': 'One', 'tool_call': True}}}}
        catalog.refresh(self.root, self.state, raw=catalog.json_bytes(self.payload), source_checkout=True)

    def test_private_refresh_leaves_source_and_unknown_fields_intact(self):
        before = (self.root / 'registry/catalog.json').read_bytes()
        changed = copy.deepcopy(self.payload)
        changed['new'] = {'name': 'New', 'models': {'two': {'name': 'Two', 'future_field': [1], 'tool_call': None}}}
        catalog.refresh(self.root, self.state, raw=catalog.json_bytes(changed))
        self.assertEqual((self.root / 'registry/catalog.json').read_bytes(), before)
        self.assertEqual(catalog.effective_providers(self.root, self.state), changed)

    def test_invalid_known_fields_do_not_replace_accepted_snapshot(self):
        catalog.refresh(self.root, self.state, raw=catalog.json_bytes(self.payload))
        for bad in ({'tool_call': 'false'}, {'limit': {'context': True}}, {'limit': {'output': -1}},
                    {'cost': {'input': -1}}, {'cost': {'output': float('nan')}}, {'modalities': {'input': 'text'}}):
            changed = copy.deepcopy(self.payload)
            changed['test']['models']['one'].update(bad)
            with self.assertRaises(ValueError):
                catalog.refresh(self.root, self.state, raw=catalog.json_bytes(changed))
            self.assertEqual(catalog.effective_providers(self.root, self.state), self.payload)

    def test_pending_sources_survive_repeat_checks_and_network_failure(self):
        catalog.atomic_bytes(self.root / 'registry/sources.json', catalog.json_bytes({'sources': [{'id': 'one', 'url': 'https://docs.ollama.com/api'}]}))
        with mock.patch.object(source_review, 'fetch_public', return_value=b'first'):
            first = kit.source_check(self.root, self.state)['one']
            again = kit.source_check(self.root, self.state)['one']
        self.assertTrue(first['pending'] and again['pending'])
        sha = first['observed']['sha256']
        source_review.acknowledge(self.state, 'one', sha, kit.state_lock)
        with mock.patch.object(source_review, 'fetch_public', return_value=b'second'):
            second = kit.source_check(self.root, self.state)['one']
        with self.assertRaisesRegex(ValueError, 'revision changed'):
            source_review.acknowledge(self.state, 'one', sha, kit.state_lock)
        with mock.patch.object(source_review, 'fetch_public', side_effect=OSError('offline')):
            offline = kit.source_check(self.root, self.state)['one']
        self.assertTrue(offline['pending'])
        self.assertEqual(offline['reviewed']['sha256'], sha)
        self.assertEqual(offline['observed'], second['observed'])
