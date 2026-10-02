"""Authenticated loopback UI, TLS worker API and transparent inference streaming."""
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
from contextlib import nullcontext
from urllib.parse import parse_qs, urlsplit

from . import hardware, credentials, diagnostics, launcher
from .core import ALIAS, model_name
from .transport import connect

WEB = Path(__file__).parent / "web"
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
NODE_GET = {"/api/version", "/api/tags", "/api/ps"}
NODE_POST = {"/api/show", "/api/create", "/api/generate", "/api/pull", "/v1/responses", "/v1/chat/completions"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, control, *, worker=False, advertised=None):
        self.control, self.worker = control, worker
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)
        host, port = self.server_address[:2]
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"{host}:{port}"}
        if advertised:
            self.hosts.add(urlsplit(advertised).netloc)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, address)

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalControl"

    def log_message(self, *_):
        pass  # URLs, headers and inference payloads are never written to logs.

    def setup(self):
        super().setup()
        self.connection.settimeout(30)
        self.started = False

    def headers_common(self, content_type):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def reply(self, value, status=200, *, cookie=False):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.headers_common("application/json")
        if cookie:
            self.send_header("Set-Cookie", "local_control=" + self.server.control.config["token"] + "; HttpOnly; SameSite=Strict; Path=/" + ("; Secure" if self.server.worker else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.started = True
        self.wfile.write(body)

    def authenticated(self, *, bearer_only=False):
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token and not bearer_only:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
                token = cookies["local_control"].value if "local_control" in cookies else ""
            except Exception:
                token = ""
        config = self.server.control.config
        self.principal = None
        if self.server.worker:
            inference = self.path.startswith('/node/v1/')
            self.principal = credentials.principal(config, token, inference=inference)
            if self.principal:
                return not self.path.startswith('/node/admin/')
            if self.path.startswith('/node/admin/'):
                return hmac.compare_digest(token, config['token'])
            return bool(config.get('legacy_worker_token') and hmac.compare_digest(token, config['token']))
        if self.path.startswith("/v1/") and hmac.compare_digest(token, config["gateway_token"]):
            return True
        return hmac.compare_digest(token, config["token"])

    def guard(self):
        if self.headers.get("Host") not in self.server.hosts:
            self.reply({"error": "Unrecognized host"}, 403)
            return False
        origin = self.headers.get("Origin")
        expected_scheme = "https" if self.server.worker else "http"
        if origin and origin != expected_scheme + "://" + self.headers.get("Host", ""):
            self.reply({"error": "Cross-origin requests are refused"}, 403)
            return False
        return True

    def read_body(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Use a JSON body with Content-Length")
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 32 * 1024 * 1024:
            raise ValueError("JSON request size must be between 1 byte and 32 MiB")
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError("Incomplete request body")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        try:
            if not self.guard():
                return
            parsed = urlsplit(self.path)
            path, query = parsed.path, parse_qs(parsed.query)
            if self.server.worker and post and path == '/node/pair':
                body = self.read_body()
                self.reply(self.server.control.redeem_pairing(body.get('code'), body.get('name')))
                return
            if not post and path in ASSETS and not self.server.worker:
                filename, mime = ASSETS[path]
                data = (WEB / filename).read_bytes()
                self.send_response(200)
                self.headers_common(mime + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.started = True
                self.wfile.write(data)
                return
            bearer = path.startswith(("/node/", "/v1/")) or path == "/api/login"
            if not self.authenticated(bearer_only=bearer):
                self.reply({"error": "Open the dashboard using the private launch link"}, 401)
                return
            body = self.read_body() if post else None
            control = self.server.control
            if self.server.worker and not path.startswith("/node/"):
                self.reply({"error": "Worker nodes expose only the paired node API"}, 404)
                return
            if path.startswith("/node/"):
                if not self.server.worker:
                    self.reply({"error": "Not a worker node"}, 404)
                    return
                target = path.removeprefix("/node")
                if target == '/admin/pairing' and post:
                    self.reply(control.pairing_code())
                elif target == '/admin/controllers' and not post:
                    self.reply({'controllers': [{'id': k, 'name': v['name'], 'created': v['created']} for k, v in control.config['controllers'].items()],
                                'legacy_enabled': control.config.get('legacy_worker_token', False)})
                elif target == '/admin/credentials' and post:
                    self.reply(control.worker_credentials(body.get('action'), body.get('id')))
                elif target == '/credentials/revoke' and post and self.principal:
                    self.reply(control.worker_credentials('revoke', self.principal))
                elif target == '/credentials/rotate' and post and self.principal:
                    self.reply(control.worker_credentials('rotate', self.principal))
                elif target == "/hardware" and not post:
                    self.reply(hardware.run_fit(control.root, ["--json", "system"]))
                elif target == "/recommendations" and not post:
                    self.reply(hardware.recommendations(control.root))
                elif target in (NODE_POST if post else NODE_GET):
                    self.proxy(target, body, direct=True)
                else:
                    self.reply({"error": "Unsupported node endpoint"}, 404)
            elif path in ("/v1/responses", "/v1/chat/completions") and post:
                self.proxy(path, body)
            elif path == "/v1/models" and not post:
                self.reply({"object": "list", "data": [{"id": ALIAS, "object": "model", "owned_by": "local-control"}]})
            elif path == "/api/login" and post:
                self.reply({"authenticated": True}, cookie=True)
            elif path == "/api/status" and not post:
                self.reply(control.status())
            elif path == '/api/setup' and not post:
                self.reply(control.setup_status())
            elif path == '/api/diagnostics' and not post:
                self.reply(diagnostics.report(control))
            elif path == '/api/evaluations' and not post:
                self.reply(control.evaluations())
            elif path == '/api/context-advice' and not post:
                value = hardware.run_fit(control.root, ['--json', 'system'])
                self.reply(hardware.context_advice(value.get('system', value)))
            elif path == '/api/session' and post:
                self.reply(control.session(body.get('action'), body))
            elif path == '/api/stop' and post:
                result = control.stop_ready(body.get('acknowledge_external') is True)
                self.reply(result)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif path == "/api/inventory" and not post:
                self.reply(control.inventory(query.get("node", ["local"])[0]))
            elif path in ("/api/hardware", "/api/recommendations") and not post:
                node_id = query.get("node", ["local"])[0]
                if node_id != "local":
                    self.reply(control.rpc(control.node(node_id), "/hardware" if path.endswith("hardware") else "/recommendations", timeout=100))
                else:
                    self.reply(hardware.run_fit(control.root, ["--json", "system"]) if path.endswith("hardware") else hardware.recommendations(control.root, control.config["context"]))
            elif path == "/api/hf/search" and not post:
                self.reply(hardware.hf_search(query.get("q", [""])[0]))
            elif path == "/api/hf/files" and not post:
                self.reply(hardware.hf_files(query.get("repo", [""])[0]))
            elif path == "/api/action" and post:
                action = body.get("action")
                node, model = body.get("node", "local"), body.get("model", "")
                if action == "mode":
                    self.reply(control.submit("Switch to " + str(body.get("mode")), control.switch, body.get("mode")))
                elif action == "configure":
                    self.reply(control.submit("Test and configure route", control.configure, node, model, body.get("role"), body.get("cpu", False)))
                elif action in ("load", "unload"):
                    self.reply(control.submit(action.title() + " model", control.lifecycle, node, model, action))
                elif action == "pull":
                    self.reply(control.submit("Download / update model", control.pull, node, model))
                elif action == "pair":
                    self.reply(control.pair(body.get("code"), body.get("name")))
                elif action == 'cancel':
                    self.reply(control.cancel(body.get('job')))
                elif action == 'cancel-request':
                    self.reply(control.cancel_request(body.get('request')))
                elif action == 'routing-policy':
                    self.reply(control.routing_policy(body.get('preference'), body.get('node'), body.get('eligible')))
                elif action == 'health':
                    self.reply(control.submit('Check machines', control.health_check))
                elif action == 'maintenance':
                    self.reply(control.submit('Change machine maintenance', control.maintenance, node, body.get('enabled')))
                elif action == 'upgrade-runtime':
                    self.reply(control.submit('Upgrade local Ollama', control.upgrade_runtime))
                elif action == 'remove-node':
                    self.reply(control.submit('Remove worker', control.remove_node, node))
                elif action == 'rotate-node':
                    self.reply(control.rotate_node(node))
                elif action == 'setup':
                    self.reply(control.submit('Set up component', control.setup_component, body.get('component')))
                elif action == 'context':
                    self.reply(control.set_context(body.get('context')))
                elif action == 'launch':
                    self.reply(launcher.open_project(control.root, body.get('project', ''), body.get('client')))
                elif action == 'benchmark':
                    self.reply(control.submit('Evaluate configured model', control.benchmark, body.get('role')))
                elif action == 'autostart':
                    from .desktop import startup
                    if type(body.get('enabled')) is not bool:
                        raise ValueError('Choose enable or disable for autostart')
                    self.reply(startup(control.root, body['enabled']))
                else:
                    raise ValueError("Unknown action")
            else:
                self.reply({"error": "Unknown endpoint"}, 404)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True
        except Exception as error:
            if not self.started:
                message = str(error) if isinstance(error, ValueError) else type(error).__name__ + ": check service availability"
                self.reply({"error": message}, 400 if isinstance(error, ValueError) else 503)
            else:
                # Once headers/tokens have been emitted, close the stream. Never silently replay.
                self.close_connection = True

    def forward(self, node, path, body, *, timeout=600):
        conn, response = connect(node, path, body, timeout=timeout)
        try:
            self.send_response(response.status)
            self.headers_common(response.getheader("Content-Type", "application/json"))
            self.send_header("Connection", "close")
            self.end_headers()
            self.started = True
            self.close_connection = True
            while True:
                block = response.read1(65536)
                if not block:
                    break
                self.wfile.write(block)
                self.wfile.flush()
        finally:
            conn.close()

    def proxy(self, path, body, direct=False):
        control = self.server.control
        if path.startswith("/v1/"):
            with control.lease(body, direct=direct) as (node, payload):
                self.forward(node, path, payload)
        elif path in NODE_GET or path == '/api/show':
            if body and 'model' in body:
                model_name(body['model'])
            # Read-only metadata must remain available during downloads and lifecycle
            # work. A stalled read must not hold the worker's administration lock.
            self.forward(control.node('local'), path, body, timeout=10)
        else:
            if body and "model" in body:
                model_name(body["model"])
            # Worker management waits behind lifecycle operations; reject unload while generating.
            with control.operation, (control.administer("local") if path in ("/api/create", "/api/generate") else nullcontext()):
                with control.lock:
                    if path in ("/api/create", "/api/generate") and sum(control.active.values()):
                        raise ValueError("Worker has active responses; retry after draining")
                self.forward(control.node("local"), path, body)
