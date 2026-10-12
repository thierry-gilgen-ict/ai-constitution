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


def next_version(root):
    major, minor, patch = map(int, (root / 'VERSION').read_text().strip().split('.'))
    return f'{major}.{minor}.{patch + 1}'


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
        upgraded_version = next_version(self.root)
        (self.root / "VERSION").write_text(upgraded_version, encoding="utf-8")
        kit.build(self.root)
        kit.adopt(state, self.project, dry_run=True)
        self.assertFalse(state.exists())
        result = kit.adopt(state, self.project)
        self.assertIn("authenticity not established", result["evidence"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(kit.sync(self.root, state)[0]["status"], "installed")
        self.assertEqual(context.read_bytes(), b"Private project facts\r\n")
        self.assertEqual((self.project / '.ai/shared/VERSION').read_text(), upgraded_version)

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
        path.write_text(path.read_text().replace('"schema_version": 2', '"schema_version": 2, "schema_version": 2'), encoding='utf-8')
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
        (self.root / 'VERSION').write_text(next_version(self.root), encoding='utf-8')
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
        (self.root / 'VERSION').write_text(next_version(self.root), encoding='utf-8')
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


class ContractRouting(unittest.TestCase):
    setUp = fixtures.Workspace.setUp

    def models(self):
        self.assertNotIn("security.md", kit.MODULES)
        self.assertIn("security-guidance.md", kit.MODULES)
        return {m["key"]: m for m in kit.read_json(self.root / "registry/models.json")["models"]}

    def put_policy(self, value, personal=False):
        path = self.state.parent / "overrides/policy.json" if personal else self.project / ".ai/policy.json"
        catalog.atomic_bytes(path, catalog.json_bytes(value))

    def test_constraints_cannot_widen_and_private_limits_are_not_published(self):
        self.put_policy({"schema_version": 2, "constraints": {"max_workers": 1}}, personal=True)
        actual = policy.resolve(self.root, self.state, self.project)
        portable = policy.resolve(self.root, self.state, self.project, portable=True)
        self.assertEqual(actual["constraints"]["max_workers"], 1)
        self.assertEqual(portable["constraints"]["max_workers"], 2)
        for bad in (True, 0, 3, "2"):
            self.put_policy({"schema_version": 2, "constraints": {"max_workers": bad}})
            with self.assertRaises(ValueError):
                policy.resolve(self.root, self.state, self.project)
        self.put_policy({"schema_version": 2, "constraints": {"max_workers": 2}})
        with self.assertRaisesRegex(ValueError, "inherited"):
            policy.resolve(self.root, self.state, self.project)

    def test_route_exception_expiry_and_cross_platform_refusal(self):
        base = {"schema_version": 2, "routes": [{"platform": "codex", "task": "small", "preferred": "codex:balanced", "exception": "x"}],
                "exceptions": [{"id": "x", "owner": "Fixture owner", "reason": "Bounded context need",
                                "expires": "2099-12-31", "evidence": "private fixture receipt"}]}
        self.put_policy(base)
        selected = policy.resolve(self.root, self.state, self.project)
        self.assertEqual(selected["provenance"]["codex/small"], "project")
        self.assertIn("metadata only", selected["exceptions"][0]["authority"])
        base["exceptions"][0]["expires"] = "2000-01-01"
        self.put_policy(base)
        with self.assertRaisesRegex(ValueError, "expired"):
            policy.select_route(self.root, policy.resolve(self.root, self.state, self.project), "codex", "small")
        base["exceptions"][0]["expires"] = "2099-12-31"
        base["routes"][0]["preferred"] = "cursor:fast"
        self.put_policy(base)
        with self.assertRaisesRegex(ValueError, "different-platform"):
            policy.resolve(self.root, self.state, self.project)

    def test_missing_capability_does_not_escalate_and_access_is_not_inferred(self):
        selected = policy.resolve(self.root, self.state)
        good = policy.select_route(self.root, selected, "codex", "operational", risk="high", available=["codex:balanced"])
        self.assertEqual(good["recommendation"]["key"], "codex:balanced")
        self.assertEqual(good["requested_effort"], "high")
        self.assertFalse(good["account_verified"])
        self.assertFalse(good["applied"])
        self.assertEqual(good["actual_model"], "unknown")
        with self.assertRaisesRegex(ValueError, "Missing capability"):
            policy.select_route(self.root, selected, "codex", "operational", risk="critical",
                                available=["codex:deep"], missing_capabilities=["deployment authorization"])
        with self.assertRaisesRegex(ValueError, "No eligible"):
            policy.select_route(self.root, selected, "codex", "deep", available=["codex:deep"])
        escalated = policy.select_route(self.root, selected, "codex", "deep", available=["codex:deep"],
                                       escalation_reason="Authorized fixture escalation; no dispatch")
        self.assertEqual(escalated["recommendation"]["key"], "codex:deep")
        unknown = policy.select_route(self.root, selected, "grok-bot", "review")
        self.assertEqual(unknown["risk"], "unknown")
        self.assertEqual(unknown["recommendation"]["selection"], "managed")

    def test_taxonomy_duplicate_fields_and_oversized_core_are_rejected(self):
        routes = kit.read_json(self.root / "registry/routes.json")
        routes["routes"][0]["task"] = "invented"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            policy.validate_routes(routes, self.models())
        self.put_policy({"schema_version": 2, "instructions": {"constitution.md": "x" * 9000}})
        with self.assertRaisesRegex(ValueError, "byte budget"):
            policy.resolve(self.root, self.state, self.project)
        path = self.project / ".ai/policy.json"
        path.write_text('{"schema_version":2,"schema_version":2}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            policy.read_layer(path)

    def test_legacy_six_module_bundle_can_be_adopted_and_upgraded(self):
        kit.install(self.root, self.state, project=self.project)
        lock_path = self.project / ".ai/constitution.lock.json"
        lock = kit.read_json(lock_path)
        lock["schema_version"], lock["version"] = 1, "0.4.0"
        lock.pop("modules")
        lock.pop("release_sha256")
        for name in ("security-guidance.md", "collaboration.md", "operational.md"):
            lock["files"].pop(".ai/shared/" + name)
            (self.project / ".ai/shared" / name).unlink()
        version_path = self.project / ".ai/shared/VERSION"
        version_path.write_bytes(b"0.4.0\n")
        lock["files"][".ai/shared/VERSION"]["sha256"] = catalog.digest(version_path.read_bytes())
        lock_path.write_bytes(catalog.json_bytes(lock))
        new_state = self.base / "legacy-adoption"
        result = kit.adopt(new_state, self.project)
        self.assertEqual(result["version"], "0.4.0")
        self.assertEqual(kit.sync(self.root, new_state)[0]["status"], "installed")
        self.assertEqual(kit.read_json(lock_path)["schema_version"], 2)
        self.assertTrue((self.project / ".ai/shared/security-guidance.md").exists())

    def test_release_identity_and_known_authority_findings_are_distinct(self):
        kit.install(self.root, self.state, project=self.project)
        doctor = kit.doctor(self.root, self.state, self.project)[0]
        self.assertEqual(doctor["status"], "files-verified")
        self.assertIn("fresh client", doctor["activation"])
        (self.root / "engineering.md").write_text("Changed instructions", encoding="utf-8")
        self.assertEqual(kit.doctor(self.root, self.state, self.project)[0]["status"], "drift")
        (self.project / "ROUTING.md").write_text("gpt-example model table", encoding="utf-8")
        (self.project / "STATE.md").write_text("x" * 65537, encoding="utf-8")
        findings = policy.authority_findings(self.project)
        self.assertEqual({f["rule"] for f in findings}, {"project-model-table", "oversized-active-authority"})



    def test_installed_guards_match_effective_policy_and_escalation_survives_override(self):
        value = {"schema_version": 2, "constraints": {"max_workers": 1, "max_attempts": 2},
                 "routes": [{"platform": "codex", "task": "implementation", "preferred": "codex:deep", "exception": "x"}],
                 "exceptions": [{"id": "x", "owner": "Fixture owner", "reason": "Bounded test",
                                 "expires": "2099-12-31", "evidence": "synthetic receipt"}]}
        self.put_policy(value)
        selected = policy.resolve(self.root, self.state, self.project)
        with self.assertRaisesRegex(ValueError, "No eligible"):
            policy.select_route(self.root, selected, "codex", "implementation")
        kit.install(self.root, self.state, project=self.project)
        guide = (self.project / ".ai/shared/routing.md").read_text()
        collaboration = (self.project / ".ai/shared/collaboration.md").read_text()
        self.assertIn("1 active workers", guide)
        self.assertIn("Escalation-only models", guide)
        self.assertIn("expires 2099-12-31 UTC", guide)
        self.assertIn("at most 1 active workers, 2 total attempts", collaboration)
        self.put_policy({"schema_version": 1, "routes": [{"platform": "codex", "task": "implementation", "fallbacks": []}]}, personal=True)
        layered = policy.resolve(self.root, self.state, self.project)
        with self.assertRaisesRegex(ValueError, "No eligible"):
            policy.select_route(self.root, layered, "codex", "implementation")
        value["routes"][0]["task"] = "small"
        self.put_policy(value)
        safe = policy.select_route(self.root, policy.resolve(self.root, self.state, self.project), "codex", "small")
        self.assertEqual(safe["recommendation"]["key"], "codex:balanced")
        value["routes"][0]["task"] = "implementation"
        self.put_policy(value)
        with mock.patch.object(policy.dt, "datetime") as clock:
            clock.now.return_value.date.return_value = policy.dt.date(2100, 1, 1)
            with self.assertRaisesRegex(ValueError, "expired"):
                policy.select_route(self.root, selected, "codex", "implementation")
        expired = copy.deepcopy(value)
        expired["exceptions"][0]["expires"] = "2000-01-01"
        self.put_policy(expired)
        selected = policy.resolve(self.root, self.state, self.project)
        self.assertEqual(policy.select_route(self.root, selected, "codex", "research")["recommendation"]["key"], "codex:balanced")

    def test_missing_global_enrollment_does_not_overwrite_edited_block(self):
        kit.install(self.root, self.state, platform="codex", home=self.home)
        path = self.home / ".codex/AGENTS.md"
        path.write_bytes(path.read_bytes().replace(b"AI Constitution", b"Edited Constitution"))
        before = path.read_bytes()
        (self.state / "installations.json").unlink()
        with self.assertRaisesRegex(ValueError, "without enrollment"):
            kit.install(self.root, self.state, platform="codex", home=self.home)
        self.assertEqual(path.read_bytes(), before)

    def test_private_state_boundary_and_preview_plan_are_enforced(self):
        for state in (self.root / "docs/private-state", self.project / "private-state"):
            with self.assertRaisesRegex(ValueError, "outside"):
                kit.install(self.root, state, project=self.project)
            self.assertFalse(state.exists())
        kit.install(self.root, self.state, project=self.project)
        preview = kit.upgrade(self.root, self.state, dry_run=True)
        p = self.root / "research.md"
        p.write_text(p.read_text() + "\nNew source fact.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Preview"):
            kit.upgrade(self.root, self.state, expected_plan=preview["plan"])
        with self.assertRaisesRegex(ValueError, "--plan"):
            kit.main(["--root", str(self.root), "--state-dir", str(self.state), "upgrade", "--source", str(self.root)])

    def test_skill_source_identity_and_malformed_collision_archives(self):
        kit.install(self.root, self.state, platform="codex", home=self.home)
        p = self.root / "skills/constitution-maintenance/SKILL.md"
        p.write_text(p.read_text() + "\nChanged skill.\n", encoding="utf-8")
        self.assertEqual(kit.doctor(self.root, self.state)[0]["status"], "drift")
        data = b"not a zip"
        with self.assertRaisesRegex(ValueError, "malformed"):
            releases.unpack(data, catalog.digest(data))
        payload = {"VERSION": b"0.5.0", "docs/A.md": b"a", "docs/a.md": b"b"}
        with self.assertRaisesRegex(ValueError, "Case-colliding"):
            releases.prepare(payload, self.state)
        for path in ("docs/CON.md", "docs/name. /file.md"):
            with self.assertRaisesRegex(ValueError, "portable"):
                releases.destination_keys([path])


class ReviewBoundaries(unittest.TestCase):
    setUp = fixtures.Workspace.setUp

    def test_export_checks_inputs_before_creating_output(self):
        output = self.base / 'out/bundle.zip'
        original = kit.no_links
        def reject(path):
            if path == self.root / 'engineering.md':
                raise ValueError('fixture input link')
            return original(path)
        with mock.patch.object(kit, 'no_links', side_effect=reject):
            with self.assertRaisesRegex(ValueError, 'input link'):
                kit.export_bundle(self.root, output)
        self.assertFalse(output.parent.exists())

    def test_extra_cached_file_prevents_activation(self):
        payload = releases.public_files(self.root)
        _, destination = releases.prepare(payload, self.state)
        catalog.atomic_bytes(destination / 'docs/extra.md', b'later evidence')
        with self.assertRaisesRegex(ValueError, 'unexpected files'):
            kit.upgrade(self.root, self.state)
        self.assertFalse((self.state / 'active-release.json').exists())
        self.assertEqual((destination / 'docs/extra.md').read_bytes(), b'later evidence')

    def test_error_recovery_preserves_concurrent_edit(self):
        first, second = self.project / 'first.txt', self.project / 'second.txt'
        first.write_bytes(b'original')
        original = kit.atomic_bytes
        def write(path, data):
            if path == second:
                first.write_bytes(b'concurrent edit')
                raise PermissionError('fixture failure')
            return original(path, data)
        with mock.patch.object(kit, 'atomic_bytes', side_effect=write):
            with self.assertRaises(PermissionError):
                kit.transaction(self.state, {first: b'managed', second: b'next'})
        self.assertEqual(first.read_bytes(), b'concurrent edit')
        journal = kit.read_json(next((self.state / 'transactions').glob('*.json')))
        self.assertEqual(journal['state'], 'prepared')
        self.assertEqual(journal['recovery_conflicts'], [str(first)])

    def test_alias_enrollment_reuses_owner_and_duplicate_legacy_state_blocks(self):
        kit.install(self.root, self.state, project=self.project)
        alias = self.project / '..' / self.project.name
        self.assertEqual(kit.adopt(self.state, alias)['status'], 'unchanged')
        db = kit.state_load(self.state)
        self.assertEqual(len(db['targets']), 1)
        target = next(iter(db['targets'].values()))
        db['targets']['legacy-alias'] = {**target, 'root': str(alias)}
        catalog.atomic_bytes(self.state / 'installations.json', catalog.json_bytes(db))
        with self.assertRaisesRegex(ValueError, 'Duplicate physical'):
            kit.state_load(self.state)

    def test_exception_identity_review_requirement_and_malformed_fields(self):
        path = self.project / '.ai/policy.json'
        value = {'schema_version': 2,
                 'routes': [{'platform': 'codex', 'task': 'small', 'preferred': 'codex:balanced', 'exception': 'x'}],
                 'exceptions': [{'id': 'x', 'owner': 'Fixture owner', 'reason': 'Test', 'expires': '2099-12-31', 'evidence': 'fixture'}]}
        catalog.atomic_bytes(path, catalog.json_bytes(value))
        first = policy.resolve(self.root, self.state, self.project)
        value['exceptions'][0]['expires'] = '2000-01-01'
        catalog.atomic_bytes(path, catalog.json_bytes(value))
        second = policy.resolve(self.root, self.state, self.project)
        self.assertNotEqual(first['effective_sha256'], second['effective_sha256'])
        route = policy.select_route(self.root, first, 'codex', 'deep', risk='medium')
        self.assertTrue(route['independent_review'])
        self.assertEqual(policy.select_route(self.root, first, 'codex', 'research')['independent_review'], 'unknown')
        for field, bad in (('fallbacks', None), ('exception', [])):
            malformed = copy.deepcopy(value)
            malformed['routes'][0][field] = bad
            catalog.atomic_bytes(path, catalog.json_bytes(malformed))
            with self.assertRaises(ValueError):
                policy.resolve(self.root, self.state, self.project)


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
