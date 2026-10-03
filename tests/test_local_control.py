"""Isolated lifecycle, gateway, authentication and request-boundary switching tests."""
from contextlib import contextmanager
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import ssl
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_control.core import ALIAS, Control, model_name
from local_control.server import Server
from local_control.storage import ProcessLock
from local_control.transport import request, validate_url


class FakeOllama:
    def __init__(self):
        self.calls = []
        self.resident = [{"name": "gpu:latest", "size_vram": 100, 'context_length': 65536}]
        self.fail = False

    def __call__(self, node, path, payload=None, **kwargs):
        self.calls.append((path, payload))
        if self.fail:
            raise ValueError("Offline fallback")
        if path == "/api/show":
            return {"capabilities": ["tools", "completion"]}
        if path == "/v1/responses":
            if payload.get('tools') and not any(isinstance(v, dict) and v.get('type') == 'function_call_output' for v in payload.get('input', [])):
                return {'output': [{'type': 'function_call', 'name': 'constitution_probe', 'call_id': 'probe', 'arguments': '{"value":"ready"}'}]}
            return {"output": [{"type": "message", 'content': [{'type': 'output_text', 'text': 'LOCAL_TOOL_OK'}]}]}
        if path == '/api/version':
            return {'version': 'fixture'}
        if path == '/api/tags':
            return {'models': [{'name': name, 'digest': name + '-digest'} for name in ('gpu:latest', 'cpu:latest')]}
        if path == "/api/ps":
            return {"models": self.resident + [{"name": "cpu:latest", "size_vram": 0, 'context_length': 65536}]}
        if path == "/api/generate" and payload["keep_alive"] == 0:
            self.resident = [m for m in self.resident if m["name"] != payload["model"]]
        return {"status": "success"}


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.ollama = FakeOllama()
        self.control = Control(self.root, self.ollama)
        self.control.config.update(primary={"node": "local", "model": "gpu:latest", "cpu": False},
                                   fallback={"node": "local", "model": "cpu:latest", "cpu": True},
                                   managed={"local": ["gpu:latest", "cpu:latest"]})
        self.control.save()
        self.control.config['limits']['concurrent_per_node'] = 2

    def tearDown(self):
        self.control.pool.shutdown(wait=True)
        self.temp.cleanup()

    def test_switch_drains_active_response_and_routes_next_to_cpu(self):
        output = []
        with self.control.lease({"model": ALIAS, "input": "test"}) as (_, body):
            self.assertEqual(body["model"], "gpu:latest")
            thread = threading.Thread(target=lambda: output.append(self.control.switch("gaming")))
            thread.start()
            deadline = time.monotonic() + 3
            while self.control.mode != "draining" and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(self.control.mode, "draining")
            self.assertTrue(thread.is_alive())
            self.assertFalse(any(p == "/api/generate" for p, _ in self.ollama.calls))
            with self.control.lease({"model": ALIAS}) as (_, next_body):
                self.assertEqual(next_body["model"], "cpu:latest")
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(output[0]["gpu_released"])
        self.assertEqual(self.control.mode, "gaming")

    def test_unavailable_fallback_leaves_gpu_route_and_models_untouched(self):
        self.ollama.fail = True
        with self.assertRaisesRegex(ValueError, "Offline"):
            self.control.switch("gaming")
        self.assertEqual(self.control.mode, "work")
        self.assertFalse(any(p == "/api/generate" for p, _ in self.ollama.calls))

    def test_unverified_cpu_placement_refuses_switch(self):
        self.ollama.resident.append({"name": "cpu:latest", "size_vram": 500})
        with self.assertRaisesRegex(ValueError, "GPU-free"):
            self.control.switch("gaming")
        self.assertEqual(self.control.mode, "work")

    def test_other_apps_gpu_models_are_reported_not_unloaded(self):
        self.ollama.resident.append({"name": "other-app:latest", "size_vram": 50})
        result = self.control.switch("gaming")
        self.assertFalse(result["gpu_released"])
        self.assertEqual(result["remaining_models"], ["other-app:latest"])

    def test_restart_preserves_gaming_route(self):
        self.control.switch("gaming")
        second = Control(self.root, self.ollama)
        with second.lease({"model": ALIAS}) as (_, body):
            self.assertEqual(body["model"], "cpu:latest")
        second.pool.shutdown()

    def test_state_write_failure_does_not_switch(self):
        with patch.object(self.control, "save", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self.control.switch("gaming")
        self.assertEqual(self.control.mode, "work")
        self.assertEqual(self.control.config["mode"], "work")

    def test_stateful_conversation_and_wrong_alias_fail_closed(self):
        for body in ({"model": ALIAS, "previous_response_id": "resp_1"}, {"model": "another-model"},
                     {"model": ALIAS, "conversation": "conv_1"}):
            with self.assertRaises(ValueError):
                with self.control.lease(body):
                    self.fail("should not get a lease")
        self.assertEqual(sum(self.control.active.values()), 0)

    def test_cancelled_request_releases_lease(self):
        with self.assertRaises(BrokenPipeError):
            with self.control.lease({"model": ALIAS}):
                raise BrokenPipeError()
        self.assertEqual(sum(self.control.active.values()), 0)

    def test_administration_excludes_new_requests(self):
        entered = threading.Event()
        def inference():
            with self.control.lease({"model": ALIAS}):
                entered.set()
        with self.control.administer("local"):
            thread = threading.Thread(target=inference)
            thread.start()
            self.assertFalse(entered.wait(.05))
        thread.join(2)
        self.assertTrue(entered.is_set())

    def test_no_unload_during_active_request(self):
        with self.control.lease({"model": ALIAS}):
            with self.assertRaisesRegex(ValueError, "active responses"):
                self.control.lifecycle("local", "gpu:latest", "unload")

    def test_no_gpu_load_in_gaming_mode(self):
        self.control.switch("gaming")
        with self.assertRaisesRegex(ValueError, "Gaming mode"):
            self.control.lifecycle("local", "another:latest", "load")

    def test_status_omits_secrets(self):
        self.control.config["nodes"]["test"] = {"token": "PRIVATE", "fingerprint": "FINGERPRINT", "name": "Test"}
        value = json.dumps(self.control.status())
        self.assertNotIn("PRIVATE", value)
        self.assertNotIn("FINGERPRINT", value)
        self.assertNotIn(self.control.config["token"], value)

    def configuring_worker(self):
        self.control.config['nodes']['remote'] = {'url': 'https://192.168.1.10:8767', 'kind': 'worker', 'name': 'Worker'}
        tags = [{'name': 'small:latest', 'digest': 'base-digest'}]
        resident = []
        nodes = []
        def rpc(node, path, payload=None, **kwargs):
            nodes.append(node['url'])
            if path == '/api/tags':
                return {'models': tags}
            if path == '/api/create':
                tags.append({'name': payload['model'], 'digest': 'alias-digest'})
                resident.append({'name': payload['model'], 'context_length': payload['parameters']['num_ctx'],
                                 'size_vram': 0 if payload['parameters']['num_gpu'] == 0 else 100})
                return {'status': 'success'}
            if path == '/api/ps':
                return {'models': resident}
            return self.ollama(node, path, payload, **kwargs)
        self.control.rpc = rpc
        return nodes

    def test_configure_remote_in_gaming_preserves_legacy_cpu_alternative(self):
        nodes = self.configuring_worker()
        previous = copy.deepcopy(self.control.config['fallback'])
        self.control.mode = self.control.config['mode'] = 'gaming'
        result = self.control.configure('remote', 'small:latest', 'fallback')
        self.assertTrue(result['tool_execution_tested'])
        self.assertEqual(self.control.route()['node'], 'remote')
        self.assertEqual(self.control.mode, 'gaming')
        self.assertEqual(self.control.config['fallbacks'], [result['route'], previous])
        self.assertEqual(set(nodes), {'https://192.168.1.10:8767'})
        self.control.configure('remote', 'small:latest', 'fallback')
        self.assertEqual(len(self.control.config['fallbacks']), 2)

    def test_configure_in_gaming_refuses_primary_protected_gpu_and_excluded_worker(self):
        nodes = self.configuring_worker()
        self.control.mode = 'gaming'
        for identity, role in [('remote', 'primary'), ('local', 'fallback')]:
            with self.assertRaisesRegex(ValueError, 'Gaming mode'):
                self.control.configure(identity, 'small:latest', role)
        self.control.config['nodes']['remote']['gaming_eligible'] = False
        with self.assertRaisesRegex(ValueError, 'Gaming mode'):
            self.control.configure('remote', 'small:latest', 'fallback')
        self.assertEqual(nodes, [])

    def test_configure_refuses_maintenance_and_active_responses(self):
        nodes = self.configuring_worker()
        self.control.config['maintenance'] = ['remote']
        with self.assertRaisesRegex(ValueError, 'maintenance'):
            self.control.configure('remote', 'small:latest', 'fallback')
        self.control.config['maintenance'] = []
        with self.control.lease({'model': ALIAS}):
            with self.assertRaisesRegex(ValueError, 'active responses'):
                self.control.configure('remote', 'small:latest', 'fallback')
        self.assertEqual(nodes, [])

    def test_configure_failed_verification_or_save_keeps_gaming_route(self):
        self.configuring_worker()
        self.control.mode = self.control.config['mode'] = 'gaming'
        previous = copy.deepcopy(self.control.config)
        with patch('local_control.core.compatibility.qualify', side_effect=ValueError('failed probe')):
            with self.assertRaisesRegex(ValueError, 'failed probe'):
                self.control.configure('remote', 'small:latest', 'fallback')
        self.assertEqual(self.control.config, previous)
        with patch.object(self.control, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.control.configure('remote', 'small:latest', 'fallback')
        self.assertEqual(self.control.config, previous)
        self.assertEqual(self.control.mode, 'gaming')

    def test_single_process_ownership(self):
        lock = ProcessLock(self.root / "server.lock")
        try:
            with self.assertRaises(ValueError):
                ProcessLock(self.root / "server.lock")
        finally:
            lock.close()
        other = ProcessLock(self.root / "server.lock")
        other.close()


class BoundaryTests(unittest.TestCase):
    def test_refresh_accepts_llmfit_human_readable_success_output(self):
        from local_control import hardware
        from subprocess import CompletedProcess
        with patch.object(hardware, "fit_executable", return_value="llmfit"), patch.object(hardware.subprocess, "run", return_value=CompletedProcess([], 0, "Models updated", "")):
            self.assertEqual(hardware.refresh_models(Path("unused"))["status"], "updated")

    def test_remote_http_credentials_and_redirect_origins_rejected(self):
        for url in ("http://192.168.1.2:8767", "http://user:pass@127.0.0.1:11434", "http://127.0.0.1:11434/evil", "http://example.com:80", "http://0.0.0.0:11434"):
            with self.assertRaises(ValueError):
                validate_url(url, worker=True)
        validate_url("https://192.168.1.2:8767", worker=True)
        validate_url("http://127.0.0.1:11434")

    def test_invalid_and_cloud_model_tags_refused(self):
        for value in ("../private", "-flag", "x;rm", "model:cloud", "hello\nthere"):
            with self.assertRaises(ValueError):
                model_name(value)
        self.assertEqual(model_name("hf.co/owner/repository:model-Q4_K_M.gguf"), "hf.co/owner/repository:model-Q4_K_M.gguf")


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.control = Control(Path(self.temp.name).resolve(), FakeOllama())
        self.server = Server(("127.0.0.1", 0), self.control)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.control.pool.shutdown()
        self.temp.cleanup()

    def get(self, path, headers=None, method="GET", body=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def auth(self):
        return {"Authorization": "Bearer " + self.control.config["token"]}

    def test_dashboard_no_external_assets_and_private_api_requires_auth(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotRegex(body, rb'(?:src|href)=["\x27]https?://')
        self.assertEqual(self.get("/api/status")[0], 401)
        self.assertEqual(self.get("/api/status", self.auth())[0], 200)

    def test_cross_origin_and_dns_rebinding_blocked_even_with_token(self):
        self.assertEqual(self.get("/api/status", {**self.auth(), "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.get("/api/status", {**self.auth(), "Host": "evil.example"})[0], 403)

    def test_login_cookie_http_only_strict(self):
        status, headers, _ = self.get("/api/login", self.auth(), "POST", "{}")
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly; SameSite=Strict", headers["Set-Cookie"])

    def test_path_traversal_is_not_a_static_asset(self):
        self.assertEqual(self.get("/../config.json", self.auth())[0], 404)

    def test_stateful_response_fails_before_any_upstream_stream(self):
        status, _, body = self.get("/v1/responses", self.auth(), "POST", json.dumps({"model": ALIAS, "previous_response_id": "old"}))
        self.assertEqual(status, 400)
        self.assertIn(b"full conversation", body)

    def test_worker_api_disabled_on_dashboard(self):
        self.assertEqual(self.get("/node/api/tags", self.auth())[0], 404)

    def test_worker_metadata_remains_available_during_administration(self):
        self.server.worker = True
        self.control.config['legacy_worker_token'] = True
        forwarded = []
        def forward(handler, node, path, body, *, timeout=600):
            forwarded.append((path, timeout))
            handler.reply({'status': 'read-only metadata'})
        with patch('local_control.server.Handler.forward', new=forward):
            for path, method, body in [('/api/version', 'GET', None), ('/api/tags', 'GET', None),
                                       ('/api/ps', 'GET', None), ('/api/show', 'POST', '{"model":"fixture:latest"}')]:
                result, finished = [], threading.Event()
                def read():
                    result.append(self.get('/node' + path, self.auth(), method, body))
                    finished.set()
                with self.control.operation:
                    thread = threading.Thread(target=read)
                    thread.start()
                    available = finished.wait(1)
                thread.join(3)
                self.assertTrue(available, path + ' waited behind an unrelated operation')
                self.assertEqual(result[0][0], 200)
        self.assertEqual([path for path, _ in forwarded], ['/api/version', '/api/tags', '/api/ps', '/api/show'])
        self.assertTrue(all(timeout <= 10 for _, timeout in forwarded))

    def test_inference_credential_cannot_control_machines(self):
        headers = {"Authorization": "Bearer " + self.control.config["gateway_token"]}
        self.assertEqual(self.get("/v1/models", headers)[0], 200)
        self.assertEqual(self.get("/api/status", headers)[0], 401)
        self.assertEqual(self.get("/api/action", headers, "POST", '{"action":"mode","mode":"gaming"}')[0], 401)


class StreamingTests(unittest.TestCase):
    def test_stream_is_forwarded_once_and_lease_is_released(self):
        calls = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"delta":"hello"}\n\ndata: [DONE]\n\n')
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as directory:
            control = Control(Path(directory).resolve())
            control.config["nodes"]["local"]["url"] = "http://127.0.0.1:" + str(upstream.server_port)
            control.config["primary"] = {"node": "local", "model": "test:latest"}
            gateway = Server(("127.0.0.1", 0), control)
            gate_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            gate_thread.start()
            try:
                conn = http.client.HTTPConnection(*gateway.server_address, timeout=3)
                conn.request("POST", "/v1/responses", json.dumps({"model": ALIAS, "input": "test", "stream": True}),
                             {"Authorization": "Bearer " + control.config["token"]})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b'data: {"delta":"hello"}\n\ndata: [DONE]\n\n')
                conn.close()
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["model"], "test:latest")
                self.assertFalse(calls[0]["store"])
                self.assertEqual(sum(control.active.values()), 0)
            finally:
                gateway.shutdown()
                gateway.server_close()
                gate_thread.join()
                control.pool.shutdown()
        upstream.shutdown()
        upstream.server_close()
        thread.join()

    def test_paired_tls_worker_and_certificate_mismatch(self):
        try:
            from local_control.setup import certificate
            import cryptography
        except ImportError:
            self.skipTest("Optional remote TLS dependency is not installed")
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"version":"fixture"}')
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            cert, key, fingerprint = certificate(root, "127.0.0.1")
            control = Control(root)
            control.config['legacy_worker_token'] = True
            control.config["nodes"]["local"]["url"] = "http://127.0.0.1:" + str(upstream.server_port)
            worker = Server(("127.0.0.1", 0), control, worker=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            worker.socket = context.wrap_socket(worker.socket, server_side=True)
            worker_thread = threading.Thread(target=worker.serve_forever, daemon=True)
            worker_thread.start()
            node = {"kind": "worker", "url": "https://127.0.0.1:" + str(worker.server_port),
                    "token": control.config["token"], "fingerprint": fingerprint}
            try:
                self.assertEqual(request(node, "/api/version"), {"version": "fixture"})
                code = request(node, '/admin/pairing', {})
                issued = request({k:v for k,v in node.items() if k != 'token'}, '/pair', {'code':code['code'],'name':'Test controller'})
                paired = {**node, **issued}
                self.assertEqual(request(paired, '/api/version'), {'version':'fixture'})
                with self.assertRaisesRegex(ValueError,'401'):
                    request({**paired,'token':issued['inference_token']}, '/api/version')
                request(paired, '/credentials/revoke', {})
                with self.assertRaisesRegex(ValueError,'401'):
                    request(paired, '/api/version')
                with self.assertRaisesRegex(ValueError,'400'):
                    request({k:v for k,v in node.items() if k != 'token'}, '/pair', {'code':code['code'],'name':'Replay'})
                with self.assertRaisesRegex(ValueError, "certificate changed"):
                    request({**node, "fingerprint": "0" * 64}, "/api/version")
                with self.assertRaisesRegex(ValueError, "401"):
                    request({**node, "token": "invalid"}, "/api/version")
            finally:
                worker.shutdown()
                worker.server_close()
                worker_thread.join()
                control.pool.shutdown()
        upstream.shutdown()
        upstream.server_close()
        thread.join()


if __name__ == "__main__":
    unittest.main()
