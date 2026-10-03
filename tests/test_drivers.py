"""Driver discovery, scoped update handoff and recovery; never run installers."""
import copy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_control import drivers
from local_control.core import Control, ALIAS
from local_control.server import Server


def report(version='31.0.1'):
    return {'schema': 1, 'status': 'ok', 'platform': 'Windows', 'checked_at': time.time(),
            'adapters': [drivers.adapter('Radeon test GPU', version, 'AMD', device='fixture')],
            'updates': {'status': 'not-checked'}, 'actions': [{'id': 'windows-update', 'label': 'Windows Update'}]}


class InventoryTests(unittest.TestCase):
    def test_windows_normalizes_signed_and_virtual_without_device_identifiers(self):
        raw = {'reboot_pending': True, 'adapters': [dict(name='Parsec Virtual Display Adapter', vendor='Parsec',
                version='0.45.0.0', date='2024-01-25', device='PRIVATE-DEVICE-IDENTIFIER', signed=True)]}
        with patch.object(drivers.platform, 'system', return_value='Windows'), patch.object(drivers, 'powershell', return_value=raw):
            value = drivers.inspect()
        self.assertTrue(value['adapters'][0]['virtual'])
        self.assertTrue(value['reboot_pending'])
        self.assertNotIn('PRIVATE-DEVICE', json.dumps(value))
        self.assertEqual(value['updates']['status'], 'not-checked')
        self.assertIn('vendor-parsec', [a['id'] for a in value['actions']])

    def test_macos_reports_os_build_not_invented_separate_driver_version(self):
        replies = ['15.7', '24G200', json.dumps({'SPDisplaysDataType': [{'sppci_model': 'Apple M4'}]})]
        with patch.object(drivers.platform, 'system', return_value='Darwin'), patch.object(drivers, 'run', side_effect=replies):
            value = drivers.inspect()
        self.assertEqual(value['adapters'][0]['version'], '15.7 (24G200)')
        self.assertEqual(value['adapters'][0]['version_kind'], 'macOS')
        self.assertEqual(value['actions'][0]['id'], 'macos-update')

    def test_linux_nvidia_fallback_and_headless_updater(self):
        with patch.object(Path, 'glob', return_value=[]), patch.object(drivers.shutil, 'which', return_value='/usr/bin/nvidia-smi'), \
             patch.object(drivers, 'run', return_value='Example GPU, 555.20'), patch.dict(drivers.os.environ, {}, clear=True):
            value = drivers.linux_inventory()
            self.assertEqual(drivers.actions('Linux', value), [])
        self.assertEqual(value[0]['version'], '555.20')

    def test_query_failure_is_explicit_and_does_not_leak_stderr(self):
        with patch.object(drivers.platform, 'system', return_value='Windows'), patch.object(drivers, 'powershell', side_effect=ValueError('PRIVATE PATH')):
            value = drivers.inspect()
        self.assertEqual(value['status'], 'unavailable')
        self.assertNotIn('PRIVATE PATH', json.dumps(value))

    def test_no_windows_offers_does_not_mean_latest(self):
        with patch.object(drivers, 'powershell', return_value=[]) as query:
            value = drivers.check_updates(report())
        self.assertEqual(value['status'], 'none-offered')
        self.assertIn('does not mean latest', value['note'])
        self.assertEqual(query.call_args.kwargs['timeout'], 120)
        self.assertIn("DriverClass -eq 'Display'", drivers.WINDOWS_UPDATES)
        self.assertNotIn('CreateUpdateInstaller', drivers.WINDOWS_UPDATES)

    def test_scan_failure_is_not_reported_as_no_updates(self):
        with patch.object(drivers, 'powershell', side_effect=subprocess.TimeoutExpired('fixture', 120)):
            self.assertEqual(drivers.check_updates(report())['status'], 'unavailable')

    def test_fixed_native_uri_and_no_install_success_claim(self):
        with patch.object(drivers, 'inspect', return_value=report()), patch.object(drivers.os, 'startfile', create=True) as opener:
            value = drivers.open_updater('windows-update')
            opener.assert_called_once_with('ms-settings:windowsupdate-optionalupdates')
            with self.assertRaises(ValueError):
                drivers.open_updater('https://untrusted.example/driver.exe')
        self.assertEqual(value['status'], 'handoff')
        self.assertIn('No installation', value['note'])


class DriverControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.resident = []
        self.remote_report = report()
        self.remote_failure = None
        self.calls = []
        def rpc(node, path, payload=None, **kwargs):
            self.calls.append((node, path, payload))
            if path == '/drivers/check':
                if self.remote_failure:
                    raise self.remote_failure
                return copy.deepcopy(self.remote_report)
            if path == '/api/ps': return {'models': list(self.resident)}
            if path == '/api/generate':
                self.resident = [m for m in self.resident if m['name'] != payload['model']]
            if path == '/api/version': return {'version': 'fixture'}
            return {'status': 'handoff'}
        self.control = Control(self.root, rpc)
        self.control.config['nodes']['local-cpu'] = {'name': 'CPU', 'url': 'http://127.0.0.1:11435', 'kind': 'ollama'}
        self.control.config['nodes']['remote'] = {'name': 'Worker', 'url': 'https://192.0.2.10:8767', 'kind': 'worker', 'gaming_eligible': False}
        self.control.save()
        self.inventory = patch.object(drivers, 'inspect', side_effect=lambda: report())
        self.inventory.start()
        self.opener = patch.object(drivers, 'open_updater', return_value={'status': 'handoff'})
        self.open_mock = self.opener.start()

    def tearDown(self):
        self.inventory.stop()
        self.opener.stop()
        self.control.pool.shutdown()
        self.temp.cleanup()

    def test_cpu_shares_host_cache_and_changed_versions_survive_restart(self):
        self.control.driver_check('local-cpu')
        self.assertNotIn('local-cpu', self.control.drivers)
        with patch.object(drivers, 'inspect', return_value=report('32.0.2')):
            value = self.control.driver_check('local')
        self.assertEqual(value['changes'][0]['before'], '31.0.1')
        other = Control(self.root, self.control.rpc)
        try: self.assertEqual(other.status()['drivers']['local']['adapters'][0]['version'], '32.0.2')
        finally: other.pool.shutdown()

    def test_older_worker_and_offline_preserve_last_observation(self):
        self.control.driver_check('remote')
        self.remote_failure = ValueError('Selected machine returned HTTP 404')
        self.assertEqual(self.control.driver_check('remote')['status'], 'worker-upgrade')
        self.remote_failure = OSError('PRIVATE ENDPOINT')
        value = self.control.driver_check('remote')
        self.assertEqual(value['adapters'][0]['version'], '31.0.1')
        self.assertEqual(value['status'], 'unavailable')
        self.assertEqual(value['actions'], [])
        self.assertNotIn('PRIVATE ENDPOINT', json.dumps(value))

    def test_one_click_pauses_both_local_runtimes_and_restart_keeps_pause(self):
        self.control.config['primary'] = {'node': 'local-cpu', 'model': 'cpu:latest', 'cpu': True}
        self.control.driver_update('local', 'windows-update', True)
        self.open_mock.assert_called_once()
        self.assertEqual(set(self.control.config['maintenance']), {'local', 'local-cpu'})
        other = Control(self.root, self.control.rpc)
        try:
            with self.assertRaisesRegex(ValueError, 'maintenance'):
                with other.lease({'model': ALIAS}): pass
        finally: other.pool.shutdown()
        self.control.driver_resume('local-cpu')
        self.assertEqual(self.control.config['maintenance'], [])
        self.assertFalse(self.control.config['nodes']['remote']['gaming_eligible'])

    def test_open_session_without_other_computer_blocks_before_mutation(self):
        self.control.config['primary'] = {'node': 'local', 'model': 'gpu:latest'}
        self.control.config['fallback'] = {'node': 'local-cpu', 'model': 'cpu:latest', 'cpu': True}
        with patch.object(self.control, 'sessions', return_value=[{'status': 'open'}]):
            with self.assertRaisesRegex(ValueError, 'whole computer'):
                self.control.driver_update('local', 'windows-update', True)
        self.open_mock.assert_not_called()
        self.assertEqual(self.control.config['maintenance'], [])

    def test_verified_remote_replacement_and_existing_lease_drains_before_handoff(self):
        self.control.config['primary'] = {'node': 'local', 'model': 'gpu:latest'}
        self.control.config['fallback'] = {'node': 'remote', 'model': 'remote:latest'}
        self.control.config['nodes']['remote']['gaming_eligible'] = True
        errors = []
        def update():
            try: self.control.driver_update('local', 'windows-update', True)
            except Exception as error: errors.append(error)
        with patch('local_control.core.compatibility.qualify', return_value={'verified': True}):
            with self.control.lease({'model': ALIAS}):
                thread = threading.Thread(target=update)
                thread.start()
                deadline = time.monotonic() + 3
                while not self.control.config['maintenance'] and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertIn('local', self.control.config['maintenance'])
                self.open_mock.assert_not_called()
                with self.control.lease({'model': ALIAS}) as (node, _):
                    self.assertEqual(node['kind'], 'worker')
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.open_mock.assert_called_once()

    def test_unmanaged_gpu_residency_blocks_updater_without_unloading_it(self):
        self.resident = [{'name': 'external', 'size_vram': 123}]
        with self.assertRaisesRegex(ValueError, 'GPU models remain'):
            self.control.driver_update('local', 'windows-update', True)
        self.open_mock.assert_not_called()
        self.assertEqual(self.resident[0]['name'], 'external')
        self.assertIn('local', self.control.config['driver_paused'])
        with self.assertRaisesRegex(ValueError, 'maintenance'):
            self.control.lifecycle('local', 'fixture', 'load')

    def test_action_and_external_client_ack_required_before_maintenance(self):
        for action, ack in [('windows-update', False), ('run-shell', True)]:
            with self.assertRaises(ValueError): self.control.driver_update('local', action, ack)
        self.assertEqual(self.control.config['maintenance'], [])
        self.open_mock.assert_not_called()

    def test_remote_update_and_resume_use_only_scoped_worker_endpoints(self):
        self.control.driver_update('remote', 'windows-update', True)
        self.open_mock.assert_not_called()
        self.assertIn('/drivers/open', [p for _, p, _ in self.calls])
        self.control.maintenance('remote', False)
        self.assertIn('/drivers/resume', [p for _, p, _ in self.calls])
        self.assertFalse(self.control.config['nodes']['remote']['gaming_eligible'])

    def test_worker_hold_blocks_every_controller_until_explicit_resume(self):
        self.control.worker_driver_open('windows-update')
        other = Control(self.root, self.control.rpc)
        try:
            with self.assertRaisesRegex(ValueError, 'maintenance'):
                with other.lease({'model': 'fixture'}, direct=True): pass
        finally: other.pool.shutdown()
        self.control.worker_driver_resume()
        with self.control.lease({'model': 'fixture'}, direct=True): pass

    def test_worker_active_request_blocks_handoff(self):
        with self.control.lease({'model': 'fixture'}, direct=True):
            with self.assertRaisesRegex(ValueError, 'active responses'):
                self.control.worker_driver_open('windows-update')
        self.open_mock.assert_not_called()

    def test_failed_resume_save_keeps_worker_inference_blocked(self):
        self.control.worker_driver_open('windows-update')
        with patch.object(self.control, 'save', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError):
                self.control.worker_driver_resume()
        self.assertTrue(self.control.config['driver_hold'])
        with self.assertRaisesRegex(ValueError, 'maintenance'):
            with self.control.lease({'model': 'fixture'}, direct=True): pass


class DriverHTTPTests(unittest.TestCase):
    def test_inference_token_cannot_query_or_launch_update_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            control = Control(Path(directory).resolve())
            pairing = control.pairing_code()
            issued = control.redeem_pairing(pairing['code'], 'fixture')
            server = Server(('127.0.0.1', 0), control, worker=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def call(path, token, body):
                conn = http.client.HTTPConnection(*server.server_address, timeout=3)
                conn.request('POST', path, json.dumps(body), {'Authorization': 'Bearer ' + token})
                response = conn.getresponse(); status = response.status; response.read(); conn.close()
                return status
            try:
                with patch.object(drivers, 'inspect', return_value=report()), patch.object(drivers, 'open_updater') as opener:
                    for path in ('/node/drivers/check', '/node/drivers/open', '/node/drivers/resume'):
                        self.assertEqual(call(path, issued['inference_token'], {}), 401)
                    self.assertEqual(call('/node/drivers/check', issued['token'], {}), 200)
                    self.assertEqual(call('/node/drivers/open', issued['token'], {'action':'arbitrary-command'}), 400)
                    opener.assert_not_called()
                    control.config['driver_hold'] = True
                    self.assertEqual(call('/node/api/generate', issued['token'], {'model':'fixture','prompt':'hello'}), 400)
                    self.assertEqual(call('/node/api/generate', issued['token'], {'model':'fixture','keep_alive':0,'images':['fixture']}), 400)
                    self.assertEqual(call('/node/v1/responses', issued['inference_token'], {'model':'fixture'}), 400)
                    # A lifecycle request already queued before maintenance must
                    # recheck the hold after acquiring the administration lock.
                    control.config['driver_hold'] = False
                    results = []
                    entered = threading.Event()
                    class ObservedLock:
                        def __enter__(self):
                            entered.set()
                            original.acquire()
                        def __exit__(self, *_): original.release()
                    original = control.operation
                    control.operation = ObservedLock()
                    with original:
                        queued = threading.Thread(target=lambda: results.append(call('/node/api/generate', issued['token'], {'model':'fixture'})))
                        queued.start()
                        self.assertTrue(entered.wait(1))
                        control.config['driver_hold'] = True
                    queued.join(3)
                    self.assertEqual(results, [400])
            finally:
                server.shutdown(); server.server_close(); thread.join(); control.pool.shutdown()


if __name__ == '__main__':
    unittest.main()
