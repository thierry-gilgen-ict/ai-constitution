"""Regressions from the review; all fixtures use isolated private profiles."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts import constitution as kit
from scripts.catalog import json_bytes
from scripts.paths import is_link
from local_control import operations, project_vault, synchronization, workspace
from local_control.core import Control
from local_control.services import Services
from local_control.storage import atomic
from local_control.studio import Studio

ROOT = Path(__file__).resolve().parents[1]


class Reliability(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.root = self.base / 'control'
        self.project = self.base / 'project'; self.project.mkdir()

    def vault(self):
        config = self.base / 'config' / 'demo'; config.mkdir(parents=True)
        (config / '.env').write_text('EXAMPLE=fixture-value')
        project_vault.configure(self.root, {'config_root': str(config.parent), 'backup_root': str(self.base / 'backup'),
            'entry': {'id': 'demo', 'folder': str(config)}, 'schedule': {'enabled': True, 'hours': 24}})

    def test_unsaved_template_is_pinned_and_survives_reconciliation(self):
        studio = Studio(self.root, source=ROOT)
        value = copy.deepcopy(studio.dispatch('templates')['templates'][0]['template'])
        value['description'] = 'My unsaved baseline that must survive synchronization'
        body = {'template': value, 'project': str(self.project), 'name': 'demo'}
        preview = studio.dispatch('project-preview', body)
        self.assertEqual(preview['policy'], 'pinned')
        studio.dispatch('project-apply', dict(body, plan=preview['plan']))
        synchronization.reconcile(self.root)
        self.assertEqual(kit.read_json(self.project / '.ai/architecture.json')['description'], value['description'])
        with self.assertRaisesRegex(ValueError, 'Save this template'):
            studio.dispatch('project-preview', dict(body, policy='latest'))

    def test_tilde_roundtrip_uses_selected_home(self):
        self.vault()
        with patch.dict(os.environ, {'HOME': str(self.base), 'USERPROFILE': str(self.base)}):
            project_vault.configure(self.root, {'backup_root': '~/backups'})
            self.assertEqual(project_vault.read(self.root)['backup_root'], str(self.base / 'backups'))
            snapshot = project_vault.backup(self.root)
            self.assertTrue((self.base / 'backups' / snapshot['snapshot']).is_dir())

    def test_rejected_schedule_does_not_consume_daily_interval(self):
        self.vault()
        self.assertTrue(project_vault.claim_due(self.root, 100000))
        project_vault.schedule_state(self.root, 'rejected', 100000)
        value = project_vault.read(self.root)
        self.assertIsNone(value['last_attempt']); self.assertIsNone(value['last_success'])
        self.assertTrue(value['last_error'])
        self.assertFalse(project_vault.claim_due(self.root, 100030))
        self.assertTrue(project_vault.claim_due(self.root, 100061))

    def test_failure_survives_success_history_and_acknowledgement(self):
        jobs = {'failure': {'id': 'failure', 'status': 'failed', 'detail': 'Fixture'}}
        jobs.update({str(i): {'id': str(i), 'status': 'done'} for i in range(80)})
        operations.save(self.root, jobs, [])
        recovered, _ = operations.recover(self.root)
        self.assertIn('failure', recovered); self.assertEqual(len(recovered), 51)
        recovered['failure']['acknowledged'] = 1
        operations.save(self.root, recovered, [])
        self.assertNotIn('failure', recovered)

    def test_private_permissions_failure_prevents_credentials(self):
        with patch('local_control.storage.directory', side_effect=OSError('ACL unavailable')):
            with self.assertRaises(OSError): Control(self.root)
        self.assertFalse((self.root / 'config.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction fixture')
    def test_real_windows_junction_rejected_on_all_supported_pythons(self):
        target = self.base / 'outside'; target.mkdir()
        junction = self.base / 'junction'
        # Both paths are verified fixture children; cmd creates the junction only.
        subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(junction), str(target)], check=True, capture_output=True)
        try:
            self.assertTrue(is_link(junction))
            with self.assertRaises(ValueError): atomic(junction / 'config.json', {'fixture': True})
            with self.assertRaises(ValueError): kit.no_links(junction / 'child')
            self.assertFalse((target / 'config.json').exists())
        finally:
            junction.rmdir()

    def test_batch_onboarding_preserves_instructions_and_stale_preview(self):
        (self.project / '.git').mkdir()
        (self.project / 'AGENTS.md').write_text('Keep the existing project conventions.\n')
        found = workspace.discover(self.root, {'roots': [str(self.base)]})
        self.assertEqual(len(found['projects']), 1)
        body = {'projects': [{'project': str(self.project)}]}
        preview = workspace.onboard(self.root, body)
        (self.project / 'AGENTS.md').write_text('Changed while reviewing.\n')
        with self.assertRaises(ValueError): workspace.onboard(self.root, dict(body, plan=preview['plan']), True)
        preview = workspace.onboard(self.root, body)
        workspace.onboard(self.root, dict(body, plan=preview['plan']), True)
        self.assertIn('Changed while reviewing.', (self.project / 'AGENTS.md').read_text())


if __name__ == '__main__': unittest.main()
