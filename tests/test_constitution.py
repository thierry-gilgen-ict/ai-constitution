"""Behavioral tests use isolated temporary homes, projects, and model servers."""

import contextlib
import copy
import http.server
import importlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import catalog
import constitution as kit


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS exposes its default temporary directory through /var -> /private/var.
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "kit"
        self.root.mkdir()
        for name in ["VERSION", "constitution.md", "engineering.md", "research.md", "maintenance.md"]:
            shutil.copy2(ROOT / name, self.root / name)
        for name in ["registry", "templates", "skills"]:
            shutil.copytree(ROOT / name, self.root / name)
        kit.build(self.root)
        # Isolated release fixtures explicitly declare their own public input set.
        import releases
        (self.root / 'checks').mkdir()
        names = sorted(set(releases.files(self.root)) | {releases.INVENTORY})
        (self.root / releases.INVENTORY).write_text(json.dumps({'schema_version': 1, 'files': names}), encoding='utf-8')
        self.state = self.base / "private"
        self.project = self.base / "a project with spaces"
        self.project.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()

    def onboard(self, **kwargs):
        return kit.install(self.root, self.state, project=self.project, **kwargs)

    def test_dry_run_has_no_writes_or_state(self):
        self.onboard(dry_run=True)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertFalse(self.state.exists())

    def test_preserves_existing_guidance_and_is_idempotent(self):
        path = self.project / "AGENTS.md"
        original = "# Team guidance\r\nUse the existing test command.\r\n"
        path.write_bytes(original.encode())
        self.onboard()
        self.assertTrue(path.read_bytes().startswith(original.encode()))
        first = path.read_bytes()
        result = self.onboard()
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(first, path.read_bytes())
        self.assertEqual(path.read_text().count(kit.BEGIN), 1)

    def test_project_context_is_never_overwritten(self):
        self.onboard()
        path = self.project / ".ai/project.md"
        path.write_text("# Real project\nUse make check.\n")
        self.onboard()
        self.assertIn("make check", path.read_text())

    def test_explicit_cursor_directory_survives_sync_and_rollback(self):
        relocated = self.base / "relocated cursor"
        relocated.mkdir()
        result = kit.install(self.root, self.state, platform="cursor", home=self.home, cursor_dir=relocated)
        self.assertTrue((relocated / "rules/ai-constitution.mdc").exists())
        self.assertTrue((relocated / "skills/constitution-maintenance/SKILL.md").exists())
        self.assertFalse((self.home / ".cursor").exists())
        self.assertEqual(kit.doctor(self.root, self.state)[0]["status"], "files-verified")
        self.assertEqual(kit.sync(self.root, self.state)[0]["status"], "unchanged")
        kit.rollback(self.state, result["snapshot"])
        self.assertFalse((relocated / "rules/ai-constitution.mdc").exists())

    def test_explicit_cursor_directory_does_not_overwrite_existing_rule(self):
        relocated = self.base / "relocated cursor"
        (relocated / "rules").mkdir(parents=True)
        path = relocated / "rules/ai-constitution.mdc"
        path.write_text("Existing user rule", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unmanaged file"):
            kit.install(self.root, self.state, platform="cursor", home=self.home, cursor_dir=relocated)
        self.assertEqual(path.read_text(), "Existing user rule")
        self.assertFalse(self.state.exists())

    def test_edit_outside_managed_block_survives_sync(self):
        self.onboard()
        path = self.project / "AGENTS.md"
        path.write_text(path.read_text() + "\n# Local context\nKeep this.\n")
        (self.root / "constitution.md").write_text("# New core\nBe concise.\n")
        kit.build(self.root)
        self.onboard()
        self.assertIn("Keep this.", path.read_text())
        self.assertIn("Be concise.", path.read_text())

    def test_managed_edit_refuses_entire_transaction(self):
        self.onboard()
        path = self.project / "AGENTS.md"
        path.write_text(path.read_text().replace("Shared constitution", "Local changed core"))
        before = (self.project / ".ai/shared/constitution.md").read_bytes()
        with self.assertRaisesRegex(ValueError, "Local edits"):
            self.onboard()
        self.assertEqual(before, (self.project / ".ai/shared/constitution.md").read_bytes())

    def test_shadowing_override_is_reported_before_writing(self):
        (self.project / "AGENTS.override.md").write_text("Existing override")
        with self.assertRaisesRegex(ValueError, "shadows"):
            self.onboard()
        self.assertFalse((self.project / ".ai").exists())

    def test_malformed_markers_fail_without_writes(self):
        (self.project / "AGENTS.md").write_text(kit.BEGIN)
        with self.assertRaisesRegex(ValueError, "markers"):
            self.onboard()
        self.assertFalse(self.state.exists())

    def test_unknown_owned_filename_is_not_clobbered(self):
        (self.project / ".ai/shared").mkdir(parents=True)
        (self.project / ".ai/shared/constitution.md").write_text("Existing policy")
        with self.assertRaisesRegex(ValueError, "Unmanaged"):
            self.onboard()
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_rollback_restores_original_bytes_and_removes_new_files(self):
        path = self.project / "AGENTS.md"
        original = b"# Existing\r\nKeep this.\r\n"
        path.write_bytes(original)
        result = self.onboard()
        kit.rollback(self.state, result["snapshot"])
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.project / ".ai/shared/constitution.md").exists())

    def test_rollback_preserves_later_edits(self):
        result = self.onboard()
        path = self.project / "AGENTS.md"
        path.write_text(path.read_text() + "Later edit")
        with self.assertRaisesRegex(ValueError, "changed since"):
            kit.rollback(self.state, result["snapshot"])
        self.assertIn("Later edit", path.read_text())

    def test_failed_transaction_reverts_completed_files(self):
        first, second = self.base / "first", self.base / "second"
        first.write_bytes(b"before")
        real = kit.atomic_bytes
        def fail(path, data):
            if path == second:
                raise OSError("disk error")
            real(path, data)
        with mock.patch.object(kit, "atomic_bytes", side_effect=fail):
            with self.assertRaises(OSError):
                kit.transaction(self.state, {first: b"after", second: b"new"})
        self.assertEqual(first.read_bytes(), b"before")

    def test_final_journal_failure_reverts_installed_bytes(self):
        target = self.base / "target"
        target.write_bytes(b"before")
        real = kit.atomic_bytes
        def fail(path, data):
            if path.parent.name == "transactions" and json.loads(data).get("state") == "applied":
                raise OSError("final journal failure")
            real(path, data)
        with mock.patch.object(kit, "atomic_bytes", side_effect=fail):
            with self.assertRaises(OSError):
                kit.transaction(self.state, {target: b"after"})
        self.assertEqual(target.read_bytes(), b"before")

    def test_interrupted_rollback_can_resume_without_overwriting_new_edits(self):
        first, second = self.base / "first", self.base / "second"
        first.write_bytes(b"old-first")
        second.write_bytes(b"old-second")
        result = kit.transaction(self.state, {first: b"new-first", second: b"new-second"})
        real = kit.atomic_bytes
        def fail(path, data):
            if path == first:
                raise OSError("restore failure")
            real(path, data)
        with mock.patch.object(kit, "atomic_bytes", side_effect=fail):
            with self.assertRaises(OSError):
                kit.rollback(self.state, result["snapshot"])
        self.assertEqual(second.read_bytes(), b"old-second")
        kit.rollback(self.state, result["snapshot"])
        self.assertEqual(first.read_bytes(), b"old-first")

    def test_other_process_lock_prevents_lost_enrollment(self):
        # A competing operation fails before reading stale enrollment state.
        with kit.state_lock(self.state):
            with self.assertRaisesRegex(ValueError, "Another installation"):
                self.onboard()
        self.onboard()
        self.assertEqual(len(kit.state_load(self.state)["targets"]), 1)

    def test_onboarding_again_preserves_pin(self):
        self.onboard(pin=True)
        self.onboard()
        self.assertTrue(kit.read_json(self.project / ".ai/constitution.lock.json")["pinned"])

    def test_pinned_projects_are_skipped(self):
        self.onboard(pin=True)
        result = kit.sync(self.root, self.state)
        self.assertEqual(result[0]["status"], "skipped-pinned")

    def test_doctor_detects_missing_file(self):
        self.onboard()
        (self.project / ".ai/shared/research.md").unlink()
        result = kit.doctor(self.root, self.state)
        self.assertEqual(result[0]["status"], "drift")

    def test_global_adapters_and_private_libraries(self):
        for platform in ("codex", "cursor"):
            kit.install(self.root, self.state, platform=platform, home=self.home)
        self.assertIn(kit.BEGIN, (self.home / ".codex/AGENTS.md").read_text())
        self.assertTrue((self.home / ".cursor/rules/ai-constitution.mdc").read_text().startswith("---\n"))
        self.assertTrue((self.home / ".config/ai-constitution/libraries/codex/routing.md").exists())
        self.assertFalse((self.home / ".codex/config.toml").exists())
        self.assertTrue(all(r["status"] == "files-verified" for r in kit.doctor(self.root, self.state)))

    def test_generated_drift_fails_check(self):
        (self.root / "routing.md").write_text("stale")
        with self.assertRaisesRegex(ValueError, "stale"):
            kit.build(self.root, check=True)

    def test_symlink_destination_is_rejected(self):
        other = self.base / "outside"
        other.mkdir()
        try:
            (self.project / ".ai").symlink_to(other, target_is_directory=True)
        except OSError:
            self.skipTest("OS does not grant symlink creation")
        with self.assertRaisesRegex(ValueError, "symbolic"):
            self.onboard()

    def test_bad_route_reference_fails_validation(self):
        path = self.root / "registry/routes.json"
        data = kit.read_json(path)
        data["routes"][0]["preferred"] = "unknown:model"
        path.write_bytes(catalog.json_bytes(data))
        with self.assertRaisesRegex(ValueError, "unknown model"):
            kit.validate(self.root)


class Catalog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / ".local"
        self.payload = {"example": {"name": "Example provider", "models": {"model-one": {
            "name": "Model One", "tool_call": True, "limit": {"context": 4096}, "new_upstream_field": [1, 2]}}}}

    def refresh(self, payload=None, **kwargs):
        return catalog.refresh(self.root, self.state, raw=catalog.json_bytes(payload if payload is not None else self.payload), source_checkout=True, **kwargs)

    def test_preserves_provider_scoped_ids_and_unknown_fields(self):
        self.refresh()
        data = kit.read_json(self.root / "registry/catalog.json")
        self.assertEqual(data["providers"], self.payload)

    def test_refresh_is_idempotent(self):
        self.refresh()
        before = (self.root / "registry/catalog.json").read_bytes()
        result = self.refresh()
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(before, (self.root / "registry/catalog.json").read_bytes())

    def test_new_provider_and_new_model_are_discovered_without_code_changes(self):
        self.refresh()
        new = copy.deepcopy(self.payload)
        new["new-provider"] = {"name": "New", "models": {"new-model": {"name": "New Model"}}}
        result = self.refresh(new)
        self.assertEqual(result["providers_added"], ["new-provider"])
        self.assertEqual(result["models_added"], ["new-provider/new-model"])

    def test_removals_require_explicit_option_and_retain_working_catalog(self):
        self.refresh()
        before = (self.root / "registry/catalog.json").read_bytes()
        new = copy.deepcopy(self.payload)
        new["example"]["models"] = {}
        result = self.refresh(new)
        self.assertEqual(result["status"], "review-required")
        self.assertEqual(before, (self.root / "registry/catalog.json").read_bytes())
        self.assertEqual(self.refresh(new, allow_removals=True)["status"], "updated")

    def test_malformed_response_does_not_replace_catalog(self):
        self.refresh()
        before = (self.root / "registry/catalog.json").read_bytes()
        with self.assertRaises(ValueError):
            self.refresh({"invalid": {"name": "Invalid", "models": []}})
        self.assertEqual(before, (self.root / "registry/catalog.json").read_bytes())

    def test_preview_never_changes_catalog(self):
        self.refresh(preview=True)
        self.assertFalse((self.root / "registry/catalog.json").exists())

    def test_override_survives_refresh_and_keeps_evidence(self):
        self.refresh()
        override = {"schema_version": 1, "models": [{"provider": "example", "id": "just-announced",
                    "source": "https://example.com/models", "verified_at": "2026-10-02",
                    "definition": {"name": "Just Announced", "tool_call": True}}]}
        (self.root / "registry/overrides.json").write_bytes(catalog.json_bytes(override))
        self.refresh()
        model = catalog.effective_providers(self.root)["example"]["models"]["just-announced"]
        self.assertEqual(model["constitution_provenance"]["source"], "https://example.com/models")
        self.assertNotIn("just-announced", kit.read_json(self.root / "registry/catalog.json")["providers"]["example"]["models"])

    def test_arbitrary_public_sources_rejected(self):
        for url in ["http://models.dev/api.json", "https://example.com", "https://user:pass@models.dev/api.json", "https://models.dev.evil.test/"]:
            with self.assertRaises(ValueError):
                catalog.public_url(url)

    def test_remote_discovery_is_explicit_and_uses_https(self):
        with self.assertRaises(ValueError):
            catalog.local_url("http://192.0.2.10:11434")
        with self.assertRaises(ValueError):
            catalog.local_url("http://192.0.2.10:11434", allow_remote=True)
        self.assertEqual(catalog.local_url("https://example.com/v1", allow_remote=True), "https://example.com/v1")

    def test_local_discovery_makes_only_a_metadata_get(self):
        calls = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(("GET", self.path))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                data = {"models": [{"name": "local-model:latest", "details": {"quantization_level": "Q4"}}]} if self.path == "/api/tags" else {"data": [{"id": "another-local-model"}]}
                self.wfile.write(json.dumps(data).encode())
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            ollama = catalog.discover_local(base, "ollama")
            compatible = catalog.discover_local(base + "/v1", "openai-compatible")
            self.assertEqual(ollama["models"][0]["id"], "local-model:latest")
            self.assertEqual(compatible["models"][0]["id"], "another-local-model")
            self.assertEqual(calls, [("GET", "/api/tags"), ("GET", "/v1/models")])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class PublicFiles(unittest.TestCase):
    def test_exports_exclude_private_state_and_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "bundle.zip"
            kit.export_bundle(ROOT, path)
            with zipfile.ZipFile(path) as archive:
                self.assertIn("constitution.md", archive.namelist())
                self.assertNotIn("registry/catalog.json", archive.namelist())
                self.assertFalse(any(".local" in name for name in archive.namelist()))

    def test_scan_finds_force_added_private_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text(".local/\n")
            (root / ".local").mkdir()
            (root / ".local/state.json").write_text("{}")
            subprocess.run(["git", "add", "-f", ".local/state.json"], cwd=root, check=True)
            findings = kit.scan(root)["findings"]
            self.assertTrue(any(f["rule"] == "private-file" for f in findings))

    def test_scan_does_not_echo_credential_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            synthetic = "gh" + "p_" + "a" * 36
            (root / "example.txt").write_text(synthetic)
            result = kit.scan(root)
            self.assertTrue(result["findings"])
            self.assertNotIn(synthetic, json.dumps(result))

    def test_scan_also_reads_staged_bytes_after_working_file_is_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "example.txt").write_text("gh" + "p_" + "b" * 36)
            subprocess.run(["git", "add", "example.txt"], cwd=root, check=True)
            (root / "example.txt").write_text("Clean working copy")
            self.assertTrue(kit.scan(root)["findings"])


if __name__ == "__main__":
    unittest.main()
