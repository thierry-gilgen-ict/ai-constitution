"""Real source-service handoff and rollback with disposable, offline state."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from local_control import updates, processes
from local_control.storage import atomic
from local_control.transport import request
from scripts import releases
from scripts.catalog import atomic_bytes

ROOT = Path(__file__).resolve().parents[1]


class Restart(unittest.TestCase):
    def test_service_handoff_rollback_and_original_entrypoint(self):
        with tempfile.TemporaryDirectory(prefix='constitution-update-') as temporary:
            base = Path(temporary).resolve(); state = base / 'control'
            candidate = base / 'candidate'
            for name, body in releases.files(ROOT).items():
                atomic_bytes(candidate / name, body)
            (candidate / 'VERSION').write_text('99.0.0\n', encoding='utf-8')
            archive = base / 'release.zip'; info = releases.export(candidate, archive)
            atomic(state / 'updates.json', {'automatic_check': False, 'latest': '99.0.0',
                'assets': {'ai-constitution-release.zip': 'zip', 'ai-constitution-release.sha256': 'sha'}})
            with patch.object(updates, 'fetch', side_effect=lambda url, limit: info['sha256'].encode() if url == 'sha' else archive.read_bytes()):
                updates.stage(state, '99.0.0')
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1', 0)); port = port_socket.getsockname()[1]
            args = [sys.executable, str(ROOT / 'scripts/local_control.py'), '--state-dir', str(state),
                    'serve', '--port', str(port), '--no-background-services']
            endpoint = {'url': f'http://127.0.0.1:{port}', 'kind': 'ollama', 'token': ''}
            child = None

            def wait_for(predicate, timeout=40):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        if predicate(): return
                    except (ValueError, OSError, KeyError): pass
                    time.sleep(.1)
                self.fail('Disposable service did not reach the expected state')

            def api(path, body=None): return request(endpoint, '/api/' + path, body, timeout=2)
            def stopped(): return not processes.matches(json.loads((state / 'runtime.json').read_text()))
            try:
                with (base / 'service.log').open('wb') as log:
                    child = subprocess.Popen(args, stdout=log, stderr=log,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                wait_for(lambda: (state / 'config.json').exists())
                endpoint['token'] = json.loads((state / 'config.json').read_text())['token']
                wait_for(lambda: api('version')['version'] == updates.current())
                plan = api('updates/preview', {})
                self.assertEqual(plan['blockers'], [])
                api('updates/apply', {'plan': plan['plan'], 'acknowledge_external': True})
                self.assertEqual(child.wait(15), 0)
                wait_for(lambda: api('version')['version'] == '99.0.0')
                wait_for(lambda: updates.read(state).get('restart_status') == 'verified')
                self.assertEqual(json.loads((state / 'config.json').read_text())['token'], endpoint['token'])
                plan = api('updates/preview', {'rollback': True})
                api('updates/apply', {'rollback': True, 'plan': plan['plan'], 'acknowledge_external': True})
                wait_for(lambda: api('version')['version'] == updates.current())
                wait_for(lambda: json.loads((state / 'active-application.json').read_text())['version'] == updates.current())
                api('stop', {'acknowledge_external': True}); wait_for(stopped)
                # Starting the original checkout follows the verified active copy.
                with (base / 'service.log').open('ab') as log:
                    child = subprocess.Popen(args, stdout=log, stderr=log,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                wait_for(lambda: api('version')['version'] == updates.current())
                api('stop', {'acknowledge_external': True})
                self.assertEqual(child.wait(15), 0)
                wait_for(stopped)
            finally:
                try:
                    api('stop', {'acknowledge_external': True})
                    wait_for(stopped, 10)
                except (ValueError, OSError): pass
                if child is not None and child.poll() is None:
                    child.terminate(); child.wait(10)


if __name__ == '__main__': unittest.main()
