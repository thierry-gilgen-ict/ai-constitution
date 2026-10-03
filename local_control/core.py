"""Model lifecycle and request-boundary switching. No prompt or response logging."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import hashlib
import json
import re
import threading
import time
import uuid
import shutil
import os

from . import hardware, operations, credentials, processes, compatibility, evaluation, drivers
from .storage import atomic, load
from .transport import connect, request, validate_url

ALIAS = "constitution-local"


def model_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,249}", value) or ".." in value:
        raise ValueError("Invalid model identifier")
    if "cloud" in value.lower().split(":")[-1]:
        raise ValueError("Cloud-backed tags are excluded from Local Control")
    return value


class Control:
    def __init__(self, root, rpc=request):
        self.root, self.rpc = root, rpc
        self.config = load(root, migrate=True)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.operation = threading.Lock()
        self.active = {}
        self.admin_nodes = set()
        self.jobs, self.events = operations.recover(root)
        self.cancelled = set()
        self.health = {}
        history = root / 'health-history.json'
        self.health_history = json.loads(history.read_text(encoding='utf-8')) if history.exists() else []
        driver_file = root / 'drivers.json'
        self.drivers = json.loads(driver_file.read_text(encoding='utf-8')) if driver_file.exists() else {}
        self.driver_lock = threading.Lock()
        self.waiting = {}
        self.cancelled_requests = set()
        self.queued = 0
        self.stopping = False
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="local-control")
        self.mode = self.config.get("mode", "work")
        # A restart in gaming mode must never silently resume use of the GPU.
        self.mode = "gaming" if self.mode in ("gaming", "draining") else "work"
        self.phase = "idle"

    def save(self):
        atomic(self.root / "config.json", self.config)

    def event(self, message):
        with self.lock:
            self.events.insert(0, {"time": time.strftime("%H:%M:%S"), "message": message})
            del self.events[80:]
            operations.save(self.root, self.jobs, self.events)

    def node(self, identity):
        with self.lock:
            if identity not in self.config["nodes"]:
                raise ValueError("Unknown machine")
            return copy.deepcopy(self.config["nodes"][identity])

    def status(self):
        with self.lock:
            nodes = {k: {a: b for a, b in n.items() if a not in ("token", "inference_token", "fingerprint")} for k, n in self.config["nodes"].items()}
            return {"nodes": nodes, "primary": self.config["primary"], "fallback": self.config["fallback"],
                    "mode": self.mode, "phase": self.phase, "active_requests": sum(self.active.values()),
                    "jobs": list(self.jobs.values())[-15:][::-1], "events": self.events[:20], "alias": ALIAS,
                    "context": self.config["context"], "managed": copy.deepcopy(self.config["managed"]),
                    "health": copy.deepcopy(self.health), "queued_requests": self.queued,
                    "health_history": self.health_history[-20:], "waiting_requests": list(self.waiting),
                    "routing_policy": self.config.get('routing_policy', 'configured'), "inference_policy": "local-only",
                    "sessions": self.sessions(), "stopping": self.stopping,
                    "maintenance": self.config.get('maintenance', []),
                    "drivers": copy.deepcopy(self.drivers), "driver_paused": self.config.get('driver_paused', []),
                    "fallbacks": self.config.get('fallbacks', []),
                    "legacy_worker_credentials": self.config.get('legacy_worker_token', False)}

    def inventory(self, identity):
        node = self.node(identity)
        version = self.rpc(node, "/api/version", timeout=5)
        tags = self.rpc(node, "/api/tags", timeout=8)
        running = self.rpc(node, "/api/ps", timeout=8)
        return {"version": version["version"], "models": tags.get("models", []), "running": running.get("models", [])}

    def driver_host(self, identity):
        return 'local' if self.node(identity)['kind'] == 'ollama' else identity

    def driver_check_all(self, progress=lambda _: None):
        with self.lock:
            hosts = list(dict.fromkeys(self.driver_host(n) for n in self.config['nodes']))
        for identity in hosts:
            progress('Reading drivers on ' + self.node(identity)['name'])
            self.driver_check(identity)
        return {'checked': len(hosts)}

    def driver_check(self, identity, updates=False, progress=lambda _: None):
        identity = self.driver_host(identity)
        if type(updates) is not bool:
            raise ValueError('Choose whether to check for updates')
        if not self.driver_lock.acquire(blocking=False):
            raise ValueError('A driver check is already running; its result will appear here')
        try:
            progress('Reading display drivers' + (' and checking applicable OS updates' if updates else ''))
            previous = self.drivers.get(identity, {})
            if identity == 'local':
                report = drivers.inspect()
                if updates:
                    report['updates'] = drivers.check_updates(report)
            else:
                try:
                    report = self.rpc(self.node(identity), '/drivers/check', {'updates': updates}, timeout=155 if updates else 40)
                    if report.get('schema') != 1 or not isinstance(report.get('adapters'), list):
                        raise ValueError('Unsupported driver response')
                except (ValueError, OSError) as error:
                    legacy = isinstance(error, ValueError) and str(error).endswith('HTTP 404')
                    report = {**previous, 'status': 'worker-upgrade' if legacy else 'unavailable', 'attempted_at': time.time(),
                              'note': 'Update this worker to enable driver checks. Keep its private state directory.' if legacy else
                                      'Machine unavailable or driver query failed. Any versions shown are the last observation; retry after reconnecting.',
                              'actions': []}
            if report.get('status') == 'ok':
                old = {a['id']: a for a in previous.get('adapters', [])}
                report['changes'] = [{'name': a['name'], 'before': old[a['id']]['version'], 'after': a['version']}
                                     for a in report['adapters'] if a['id'] in old and a['version'] != old[a['id']]['version']]
                if not updates and previous.get('updates') and not report['changes']:
                    report['updates'] = previous['updates']
                if not report['changes']:
                    report['changes'] = previous.get('changes', [])
            if previous.get('handoff'):
                report['handoff'] = previous['handoff']
            with self.lock:
                self.drivers[identity] = report
                atomic(self.root / 'drivers.json', self.drivers)
            return report
        finally:
            self.driver_lock.release()

    def driver_update(self, identity, action, acknowledge_external=False, progress=lambda _: None):
        """Drain the whole physical host, then hand installation to its OS/vendor UI."""
        identity = self.driver_host(identity)
        if acknowledge_external is not True:
            raise ValueError('Confirm that external model clients on this machine are idle before opening its updater')
        report = self.driver_check(identity)
        if action not in [a['id'] for a in report.get('actions', [])]:
            raise ValueError('Refresh driver information and choose an available update control')
        with self.operation:
            group = [n for n in self.config['nodes'] if self.driver_host(n) == identity]
            current = self.config['fallback' if self.mode in ('gaming', 'draining') else 'primary']
            replacement = None
            if current and current['node'] in group:
                progress('Checking a fallback on a different computer')
                for candidate in self.fallback_candidates():
                    if candidate['node'] in group or candidate['node'] in self.config['maintenance'] or not self.gaming_eligible(candidate):
                        continue
                    try:
                        replacement = copy.deepcopy(candidate)
                        replacement['contract'] = compatibility.qualify(self, replacement)
                        break
                    except (ValueError, OSError):
                        replacement = None
            with self.changed:
                if (current and current['node'] in group and replacement is None
                        and (sum(self.active.values()) or self.queued or any(s['status'] != 'stale' for s in self.sessions()))):
                    raise ValueError('A driver update affects this whole computer, including its CPU fallback. Configure a tested fallback on another computer, or close local coding sessions first.')
                previous = copy.deepcopy(self.config)
                self.config['maintenance'] = list(dict.fromkeys([*self.config['maintenance'], *group]))
                self.config['driver_paused'] = list(dict.fromkeys([*self.config.get('driver_paused', []), *group]))
                if replacement:
                    self.config.update(fallback=replacement, mode='gaming')
                try:
                    self.save()
                except Exception:
                    self.config = previous
                    raise
                if replacement:
                    self.mode = 'gaming'
                self.changed.notify_all()
                progress('Machine paused for driver maintenance; waiting for existing responses')
                while any(n in group and count for (n, _), count in self.active.items()):
                    self.changed.wait(timeout=1)
            for n in group:
                for model in self.config['managed'].get(n, []):
                    self.rpc(self.node(n), '/api/generate', {'model': model, 'keep_alive': 0, 'stream': False})
                if any(m.get('size_vram') != 0 for m in self.rpc(self.node(n), '/api/ps', timeout=8).get('models', [])):
                    raise ValueError('GPU models remain on this machine. Close external model clients and unload their models before retrying. Machine remains in maintenance.')
            progress('Opening update controls on the selected computer; installation needs your input there')
            result = drivers.open_updater(action) if identity == 'local' else self.rpc(self.node(identity), '/drivers/open', {'action': action}, timeout=75)
            with self.lock:
                self.drivers[identity]['handoff'] = result
                atomic(self.root / 'drivers.json', self.drivers)
            return result

    def worker_driver_open(self, action):
        # A worker may have several paired controllers. Hold direct inference at
        # the worker itself, not only at the requesting controller's gateway.
        with self.operation, self.administer('local'):
            report = drivers.inspect()
            if action not in [a['id'] for a in report['actions']]:
                raise ValueError('Unsupported driver update control')
            with self.changed:
                self.config['driver_hold'] = True
                self.save()
                self.changed.notify_all()
            if any(m.get('size_vram') != 0 for m in self.rpc(self.node('local'), '/api/ps', timeout=8).get('models', [])):
                raise ValueError('Worker GPU models remain; close other clients before retrying. Driver maintenance remains active.')
            return drivers.open_updater(action)

    def worker_driver_resume(self):
        with self.operation, self.changed:
            self.rpc(self.node('local'), '/api/version', timeout=5)
            previous = self.config.get('driver_hold', False)
            self.config['driver_hold'] = False
            try:
                self.save()
            except Exception:
                self.config['driver_hold'] = previous
                raise
            self.changed.notify_all()
        return {'status': 'available'}

    def driver_resume(self, identity, progress=lambda _: None):
        identity = self.driver_host(identity)
        with self.operation:
            progress('Rechecking versions and runtime before leaving driver maintenance')
            report = self.driver_check(identity)
            if report.get('status') not in ('ok', 'empty'):
                raise ValueError('Driver inventory is unavailable; check the machine and refresh before resuming')
            group = [n for n in self.config['nodes'] if self.driver_host(n) == identity]
            for n in group:
                self.rpc(self.node(n), '/api/version', timeout=5)
            if identity != 'local':
                self.rpc(self.node(identity), '/drivers/resume', {}, timeout=10)
            with self.changed:
                old = copy.deepcopy(self.config)
                self.config['maintenance'] = [n for n in self.config['maintenance'] if n not in group]
                self.config['driver_paused'] = [n for n in self.config.get('driver_paused', []) if n not in group]
                try:
                    self.save()
                except Exception:
                    self.config = old
                    raise
                self.changed.notify_all()
            return {'status': 'available', 'note': 'Driver versions refreshed. Route selection and Gaming eligibility are unchanged; qualify the model before using this machine again.'}

    def setup_status(self):
        try:
            inventory = self.inventory('local')
        except (ValueError, OSError):
            inventory = {'version': None, 'models': [], 'running': []}
        return {'ollama': bool(shutil.which('ollama') or inventory.get('version')), 'llmfit': bool(hardware.fit_executable(self.root)),
                'codex': bool(shutil.which('codex') or shutil.which('codex.exe')),
                'disk_free_bytes': shutil.disk_usage(self.root).free, 'inventory': inventory,
                'context': self.config['context'], 'primary_ready': bool(self.config['primary']),
                'fallback_ready': bool(self.config['fallback']),
                'steps': ['Install runtime and hardware helper', 'Choose and download a fitting model',
                          'Test primary and fallback routes', 'Open a project']}

    def setup_component(self, component, progress=lambda _: None):
        from .setup import install_fit, install_ollama
        with self.operation:
            progress('Installing the selected component; an OS installer may need your input')
            if component == 'ollama':
                return install_ollama()
            if component == 'llmfit':
                return install_fit(self.root)
            if component == 'metadata':
                return hardware.refresh_models(self.root)
            raise ValueError('Choose Ollama, llmfit or model metadata')

    def set_context(self, context):
        if type(context) is not int or context not in (4096, 8192, 16384, 32768, 65536, 131072):
            raise ValueError('Choose a supported context size')
        with self.operation, self.lock:
            if self.config['primary'] or self.config['fallback'] or sum(self.active.values()) or any(s['status'] != 'stale' for s in self.sessions()):
                raise ValueError('Context is fixed for configured sessions; use a fresh private profile for another context size')
            previous = self.config['context']
            self.config['context'] = context
            try:
                self.save()
            except Exception:
                self.config['context'] = previous
                raise
        return {'context': context}

    def rotate_node(self, identity):
        with self.operation, self.lock:
            node = self.node(identity)
            if not node.get('controller_id'):
                raise ValueError('Legacy pairing needs a fresh expiring code from the updated worker')
            result = self.rpc(node, '/credentials/rotate', {})
            self.config['nodes'][identity].update({k: result[k] for k in ('token', 'inference_token')})
            try:
                self.save()
            except Exception:
                self.config['nodes'][identity] = node
                raise ValueError('Worker rotated credentials but local save failed. Revoke this controller on the worker, then pair again.') from None
            return {'status': 'rotated', 'active_streams': 'Existing streams finish; future requests use new credentials'}

    def benchmark(self, role, progress=lambda _: None):
        if role not in ('primary', 'fallback') or not self.config.get(role):
            raise ValueError('Configure the primary or fallback before evaluating it')
        endpoint = copy.deepcopy(self.config[role])
        with self.operation, self.administer(endpoint['node']):
            if any(s['status'] != 'stale' for s in self.sessions()):
                raise ValueError('Close managed coding sessions before benchmarking')
            if self.mode in ('gaming', 'draining') and not self.gaming_eligible(endpoint):
                raise ValueError('Gaming mode protects this GPU; evaluate the fallback or return to Work mode')
            return evaluation.benchmark(self, endpoint, progress)

    def evaluations(self):
        records = []
        for path in sorted((self.root / 'evaluations').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            value = json.loads(path.read_text(encoding='utf-8'))
            endpoint = next((r for r in [self.config['primary'], self.config['fallback'], *self.config['fallbacks']]
                             if r and r['node'] == value['node'] and r['model'] == value['model']), None)
            try:
                value['stale'] = not endpoint or not compatibility.current(self, {**endpoint, 'contract': value})
            except (ValueError, OSError):
                value['stale'] = True
            records.append(value)
        return records

    def sessions(self):
        records = []
        for path in (self.root / 'sessions').glob('*.json'):
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
                alive = processes.matches(record)
                records.append({'id': path.stem, 'status': 'open' if alive else 'stale', 'client': record.get('client', 'codex')})
            except (OSError, ValueError):
                records.append({'id': path.stem, 'status': 'unknown'})
        return records

    def stop_ready(self, acknowledge_external=False):
        with self.changed:
            if sum(self.active.values()) or self.queued or any(s['status'] != 'stale' for s in self.sessions()):
                raise ValueError('Active responses or managed sessions remain; close sessions before stopping the controller')
            if any(j['status'] in ('queued', 'running') for j in self.jobs.values()):
                raise ValueError('Finish or cancel pending operations before stopping')
            if not acknowledge_external:
                raise ValueError('Stopping can disrupt unknown external clients; explicitly acknowledge this effect')
            self.stopping = True
            self.changed.notify_all()
            return {'status': 'stopping', 'cpu_runtime': 'retained; idle models expire according to Ollama keep-alive'}

    def session(self, action, record):
        identity = record.get('id', '')
        if not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('Invalid session identifier')
        with self.changed:
            if action == 'close':
                (self.root / 'sessions' / (identity + '.json')).unlink(missing_ok=True)
            elif action == 'open':
                if self.stopping or not processes.matches(record):
                    raise ValueError('Controller stopping or session process cannot be verified')
                atomic(self.root / 'sessions' / (identity + '.json'), {'process': record['process'], 'client': 'codex'})
            else:
                raise ValueError('Unknown session action')
            return {'status': action}

    def cancel(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job or job['status'] not in ('queued', 'running'):
                raise ValueError('No active operation with that ID')
            if job['status'] == 'running' and job.get('operation') != 'pull':
                raise ValueError('This operation has started; let its safe transition finish')
            self.cancelled.add(identity)
            job['detail'] = 'Cancellation requested; waiting for the next download progress event'
            operations.save(self.root, self.jobs, self.events)
            return {'status': 'cancellation-requested'}

    def route(self):
        endpoint = self.config['fallback' if self.mode in ('gaming', 'draining') else 'primary']
        if not endpoint:
            raise ValueError('Configure a working route in the dashboard first')
        if endpoint['node'] in self.config['maintenance']:
            raise ValueError('Selected machine is in maintenance; choose and test another route first')
        if self.mode in ('gaming', 'draining') and not self.gaming_eligible(endpoint):
            raise ValueError('Selected route would use the protected GPU; test another fallback')
        return copy.deepcopy(endpoint)

    def gaming_eligible(self, endpoint):
        primary = self.config.get('primary')
        if self.node(endpoint['node']).get('gaming_eligible', True) is False:
            return False
        if endpoint.get('cpu'):
            return True
        node = self.node(endpoint['node'])
        return bool(primary and endpoint['node'] != primary['node'] and node.get('kind') == 'worker'
                    and validate_url(node['url'], worker=True).hostname not in ('127.0.0.1', '::1'))

    def fallback_candidates(self):
        rows, seen = [], set()
        for candidate in [self.config['fallback'], *self.config.get('fallbacks', [])]:
            key = (candidate['node'], candidate['model']) if candidate else None
            if candidate and key not in seen:
                seen.add(key)
                rows.append(copy.deepcopy(candidate))
        if self.config.get('routing_policy') == 'remote-first':
            rows.sort(key=lambda r: self.node(r['node']).get('kind') != 'worker')
        return rows

    def routing_policy(self, preference, identity=None, eligible=None):
        if preference not in ('configured', 'remote-first'):
            raise ValueError('Choose configured order or remote first')
        with self.operation, self.lock:
            previous = copy.deepcopy(self.config)
            if identity is not None:
                self.node(identity)
                if type(eligible) is not bool:
                    raise ValueError('Choose whether this machine may serve Gaming requests')
                if self.mode != 'work' and self.config['fallback'] and self.config['fallback']['node'] == identity and not eligible:
                    raise ValueError('Choose another active fallback before excluding this machine')
                self.config['nodes'][identity]['gaming_eligible'] = eligible
            self.config['routing_policy'] = preference
            try: self.save()
            except Exception:
                self.config = previous
                raise
        return {'note': 'Saved. The next Gaming transition uses this policy; active responses keep their current machine.'}

    def cancel_request(self, identity):
        with self.changed:
            if identity not in self.waiting:
                raise ValueError('This request is no longer queued; an accepted generation cannot be cancelled here')
            self.cancelled_requests.add(identity)
            self.changed.notify_all()
        return {'note': 'Queued request cancelled before inference; the client receives an explicit error'}

    def health_check(self, progress=lambda _: None):
        result = {}
        for identity in list(self.config['nodes']):
            start = time.monotonic()
            try:
                value = self.rpc(self.node(identity), '/api/version', timeout=3)
                result[identity] = {'status': 'online', 'version': value.get('version'), 'checked_at': time.time(),
                                    'latency_ms': round(1000 * (time.monotonic() - start))}
            except Exception:
                result[identity] = {'status': 'offline', 'checked_at': time.time()}
        with self.lock:
            self.health = result
            self.health_history.extend({'node': n, **value} for n, value in result.items())
            self.health_history = self.health_history[-80:]
            atomic(self.root / 'health-history.json', self.health_history)
        return result

    def maintenance(self, identity, enabled, progress=lambda _: None):
        """Move new requests first, then drain leases; never terminate a runtime."""
        if type(enabled) is not bool:
            raise ValueError('Choose enter or leave maintenance')
        self.node(identity)
        if not enabled and identity in self.config.get('driver_paused', []):
            return self.driver_resume(identity, progress)
        with self.operation:
            if not enabled:
                self.rpc(self.node(identity), '/api/version', timeout=5)
                with self.changed:
                    previous = copy.deepcopy(self.config)
                    self.config['maintenance'] = [n for n in self.config['maintenance'] if n != identity]
                    try: self.save()
                    except Exception:
                        self.config = previous
                        raise
                    self.changed.notify_all()
                return {'status': 'available', 'note': 'Routes are rechecked when selected; model updates may invalidate earlier evidence'}
            current = self.config['fallback' if self.mode in ('gaming', 'draining') else 'primary']
            replacement = None
            if current and current['node'] == identity:
                progress('Checking another machine or CPU fallback before draining')
                for candidate in self.fallback_candidates():
                    if not candidate or candidate['node'] == identity or candidate['node'] in self.config['maintenance'] or not self.gaming_eligible(candidate):
                        continue
                    candidate = copy.deepcopy(candidate)
                    try:
                        candidate['contract'] = compatibility.qualify(self, candidate)
                        replacement = candidate
                        break
                    except (ValueError, OSError):
                        continue
                if replacement is None:
                    raise ValueError('Maintenance needs a compatible route on another available runtime; configure one first')
            with self.changed:
                previous = copy.deepcopy(self.config)
                if identity not in self.config['maintenance']:
                    self.config['maintenance'].append(identity)
                if replacement:
                    self.config.update(fallback=replacement, mode='gaming')
                try: self.save()
                except Exception:
                    self.config = previous
                    raise
                if replacement:
                    self.mode = 'gaming'
                self.changed.notify_all()
                progress('New requests routed away; waiting for existing responses')
                while any(n == identity and count for (n, _), count in self.active.items()):
                    self.changed.wait(timeout=1)
            for model in self.config['managed'].get(identity, []):
                self.rpc(self.node(identity), '/api/generate', {'model': model, 'keep_alive': 0, 'stream': False})
            resident = self.rpc(self.node(identity), '/api/ps').get('models', [])
            return {'status': 'maintenance', 'remaining_models': [m['name'] for m in resident],
                    'note': 'Runtime stays running. External clients are not controlled by this gateway.'}

    def upgrade_runtime(self, progress=lambda _: None):
        from .setup import install_ollama
        with self.operation:
            local = [n for n in ('local', 'local-cpu') if n in self.config['nodes']]
            if any(n not in self.config['maintenance'] for n in local):
                raise ValueError('Drain both local runtimes in Machines before upgrading Ollama')
            route = self.route()
            if route['node'] in local or not compatibility.current(self, route):
                raise ValueError('A compatible remote route must remain available during this runtime upgrade')
            if any(n in local and count for (n, _), count in self.active.items()):
                raise ValueError('Local responses are still draining')
            progress('Running the official package manager; leave maintenance only after restarting and checking Ollama')
            return install_ollama(upgrade=True)

    def pairing_code(self):
        with self.lock:
            old = copy.deepcopy(self.config)
            result = credentials.create_pairing(self.config)
            try:
                self.save()
            except Exception:
                self.config = old
                raise
            return result

    def redeem_pairing(self, code, name):
        with self.lock:
            old = copy.deepcopy(self.config)
            result = credentials.redeem(self.config, code, name)
            try:
                self.save()
            except Exception:
                self.config = old
                raise
            return result

    def worker_credentials(self, action, identity=None):
        with self.lock:
            old = copy.deepcopy(self.config)
            if action == 'rotate':
                result = credentials.rotate(self.config, identity)
            elif action == 'revoke':
                if identity not in self.config['controllers']:
                    raise ValueError('Unknown controller')
                del self.config['controllers'][identity]
                result = {'status': 'revoked', 'active_streams': 'Existing streams finish; new requests are denied immediately'}
            elif action == 'disable-legacy':
                self.config['legacy_worker_token'] = False
                result = {'status': 'legacy-access-disabled'}
            else:
                raise ValueError('Unknown credential operation')
            try:
                self.save()
            except Exception:
                self.config = old
                raise
            return result

    def remove_node(self, identity, progress=lambda _: None):
        if identity in ('local', 'local-cpu'):
            raise ValueError('Local runtimes cannot be removed through worker removal')
        with self.operation, self.administer(identity):
            if any(r and r['node'] == identity for r in (self.config['primary'], self.config['fallback'])):
                raise ValueError('Select another primary/fallback before removing this worker')
            node = self.node(identity)
            # Revoke on the worker before removing credentials locally. Offline workers
            # need revocation from that computer; removal cannot pretend to revoke them.
            if node.get('controller_id'):
                self.rpc(node, '/credentials/revoke', {})
            with self.lock:
                old = copy.deepcopy(self.config)
                del self.config['nodes'][identity]
                self.config['fallbacks'] = [r for r in self.config['fallbacks'] if r['node'] != identity]
                self.config['maintenance'] = [n for n in self.config['maintenance'] if n != identity]
                try:
                    self.save()
                except Exception:
                    self.config = old
                    raise
            return {'status': 'removed'}

    def submit(self, label, function, *args):
        with self.lock:
            if sum(j["status"] in ("queued", "running") for j in self.jobs.values()) >= 4:
                raise ValueError("Four operations are already queued; wait for one to finish")
            identity = uuid.uuid4().hex[:12]
            job = {"id": identity, "label": label, "status": "queued", "detail": "Waiting"}
            self.jobs[identity] = job
            if len(self.jobs) > 50:
                for old in list(self.jobs):
                    if self.jobs[old]["status"] not in ("queued", "running"):
                        del self.jobs[old]
                        break
            job['operation'] = function.__name__
            operations.save(self.root, self.jobs, self.events)
        def progress(detail):
            with self.lock:
                if identity in self.cancelled and function.__name__ == 'pull':
                    raise operations.Cancelled('Download cancelled; retry explicitly to let Ollama resume available chunks')
                job["detail"] = str(detail)[:200]
                operations.save(self.root, self.jobs, self.events)
        def run():
            try:
                with self.lock:
                    if identity in self.cancelled:
                        raise operations.Cancelled('Cancelled before starting')
                    job["status"] = "running"
                    operations.save(self.root, self.jobs, self.events)
                result = function(*args, progress=progress)
                with self.lock:
                    job.update(status="done", detail="Complete", result=result)
                self.event(label + " completed")
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else type(error).__name__ + ": check machine availability"
                with self.lock:
                    job.update(status="cancelled" if isinstance(error, operations.Cancelled) else "failed", detail=message)
                self.event(label + " failed: " + message)
            finally:
                with self.lock:
                    self.phase = "idle"
                    self.cancelled.discard(identity)
        self.pool.submit(run)
        return {"job": identity}

    @contextmanager
    def administer(self, identity):
        """Reserve a node atomically against new inference leases while changing its models."""
        with self.changed:
            if any(n == identity and count for (n, _), count in self.active.items()):
                raise ValueError("This machine has active responses; wait or use Gaming mode to drain them")
            self.admin_nodes.add(identity)
        try:
            yield
        finally:
            with self.changed:
                self.admin_nodes.discard(identity)
                self.changed.notify_all()

    @contextmanager
    def lease(self, payload, *, direct=False):
        if payload.get("previous_response_id") or payload.get("conversation"):
            raise ValueError("Send full conversation history; server-side response IDs cannot move between machines")
        if not direct and payload.get('model') != ALIAS:
            raise ValueError('Use model constitution-local on this gateway')
        with self.changed:
            if self.stopping:
                raise ValueError('Controller is stopping; new requests are not accepted')
            limits = self.config['limits']
            if self.queued >= limits['queue']:
                raise ValueError('Request queue is full; wait for current work to finish')
            self.queued += 1
            request_id = uuid.uuid4().hex[:12]
            self.waiting[request_id] = time.time()
            deadline = time.monotonic() + limits['wait_seconds']
            try:
                while True:
                    if request_id in self.cancelled_requests:
                        raise ValueError('Queued request cancelled before inference; no generation was sent')
                    endpoint = {'node': 'local', 'model': model_name(payload.get('model'))} if direct else self.route()
                    node_id = endpoint['node']
                    if self.config.get('driver_hold') or node_id in self.config['maintenance']:
                        raise ValueError('Machine is paused for maintenance; resume it before sending model requests')
                    health = self.health.get(node_id, {})
                    if health.get('status') == 'offline' and 0 <= time.time() - health.get('checked_at', 0) < 15:
                        raise ValueError('Selected machine is offline; check machine health or select another route after its cooldown')
                    count = sum(n for (machine, _), n in self.active.items() if machine == node_id)
                    if self.stopping:
                        raise ValueError('Controller is stopping')
                    if node_id not in self.admin_nodes and count < limits['concurrent_per_node']:
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError('Request queue timed out before inference; no generation was sent')
                    self.changed.wait(timeout=min(1, remaining))
                key = (node_id, endpoint['model'])
                self.active[key] = self.active.get(key, 0) + 1
            finally:
                self.queued -= 1
                self.waiting.pop(request_id, None)
                self.cancelled_requests.discard(request_id)
        try:
            body = {**payload, "model": endpoint["model"], "store": False, "truncation": "disabled"}
            yield self.node(endpoint["node"]), body
        finally:
            with self.changed:
                self.active[key] -= 1
                self.changed.notify_all()

    def probe(self, endpoint):
        node = self.node(endpoint["node"])
        info = self.rpc(node, "/api/show", {"model": endpoint["model"]})
        if info.get("remote_host") or info.get("remote_model"):
            raise ValueError("Cloud-backed models are outside this local-only route")
        if "tools" not in info.get("capabilities", []):
            raise ValueError("Model does not advertise tool support; keep it outside the coding route")
        response = self.rpc(node, "/v1/responses", {"model": endpoint["model"], "input": "Reply with OK.",
                            "max_output_tokens": 64, "stream": False, "store": False}, timeout=240)
        if response.get("error") or not response.get("output"):
            raise ValueError("The Responses API probe did not return output")
        if endpoint.get("cpu"):
            running = self.rpc(node, "/api/ps").get("models", [])
            resident = next((m for m in running if m["name"] == endpoint["model"]), None)
            if resident is None or resident.get("size_vram") != 0:
                raise ValueError("CPU fallback could not be verified as GPU-free on this Ollama version")
        return info

    def configure(self, identity, model, role, cpu=False, progress=lambda _: None):
        if role not in ("primary", "fallback"):
            raise ValueError("Choose primary or fallback")
        model = model_name(model)
        if cpu and identity == "local":
            from .setup import cpu_runtime
            progress("Starting an isolated CPU Ollama runtime")
            cpu_node = cpu_runtime(self.root, model)
            with self.lock:
                self.config["nodes"]["local-cpu"] = cpu_node
                self.save()
            identity = "local-cpu"
        with self.operation, self.administer(identity):
            with self.lock:
                if sum(self.active.values()):
                    raise ValueError("Wait for active responses before changing model definitions")
                if identity in self.config['maintenance']:
                    raise ValueError("Leave maintenance before configuring this machine")
                if self.mode != "work" and not (self.mode == 'gaming' and role == 'fallback'
                        and self.gaming_eligible({'node': identity, 'cpu': bool(cpu)})):
                    raise ValueError("Gaming mode allows only CPU or eligible remote fallback configuration; return to Work for primary routes")
            node = self.node(identity)
            installed = self.rpc(node, "/api/tags").get("models", [])
            if not any(m["name"] in (model, model + ":latest") for m in installed):
                raise ValueError("Download the model explicitly before configuring a coding route")
            installed_model = next(m for m in installed if m['name'] in (model, model + ':latest'))
            suffix = hashlib.sha256((model + installed_model.get('digest', '') + str(cpu) + str(self.config["context"])).encode()).hexdigest()[:10]
            alias = "constitution-" + ("cpu-" if cpu else "gpu-") + suffix + ":latest"
            parameters = {"num_ctx": self.config["context"], "num_gpu": -1}
            if cpu:
                parameters["num_gpu"] = 0
            progress("Creating an alias that reuses installed weights")
            self.rpc(node, "/api/create", {"model": alias, "from": model, "parameters": parameters, "stream": False})
            endpoint = {"node": identity, "model": alias, "source_model": model, "cpu": bool(cpu)}
            progress("Testing tool metadata, Responses API and memory placement")
            endpoint['contract'] = compatibility.qualify(self, endpoint)
            with self.lock:
                previous = copy.deepcopy(self.config)
                alternatives = self.fallback_candidates() if role == 'fallback' else []
                self.config[role] = endpoint
                if role == 'fallback':
                    self.config['fallbacks'] = [endpoint, *[r for r in alternatives if (r['node'], r['model']) != (identity, alias)]]
                owned = self.config["managed"].setdefault(identity, [])
                if alias not in owned:
                    owned.append(alias)
                try:
                    self.save()
                except Exception:
                    self.config = previous
                    raise
            return {"route": endpoint, "responses_tested": True, "tool_execution_tested": True, 'coding_quality_tested': False}

    def switch(self, mode, progress=lambda _: None):
        if mode not in ("work", "gaming"):
            raise ValueError("Unknown mode")
        with self.operation:
            with self.lock:
                if mode == self.mode == 'work':
                    return {"mode": self.mode}
                primary, fallback = copy.deepcopy(self.config["primary"]), copy.deepcopy(self.config["fallback"])
            if not primary:
                raise ValueError("Set up the primary route first")
            endpoint = fallback if mode == "gaming" else primary
            if not endpoint:
                raise ValueError("Gaming mode needs a tested CPU fallback or a second computer")
            self.phase = "checking fallback" if mode == "gaming" else "warming GPU"
            progress(self.phase)
            if mode == 'gaming':
                candidates = self.fallback_candidates()
                failures, seen, endpoint = [], set(), None
                for candidate in candidates:
                    key = (candidate['node'], candidate['model']) if candidate else None
                    if not candidate or key in seen:
                        continue
                    seen.add(key)
                    if not self.gaming_eligible(candidate) or candidate['node'] in self.config['maintenance']:
                        continue
                    candidate = copy.deepcopy(candidate)
                    try:
                        if not compatibility.current(self, candidate):
                            candidate['contract'] = compatibility.qualify(self, candidate)
                        else:
                            self.probe(candidate)
                        endpoint = candidate
                        break
                    except (ValueError, OSError) as error:
                        failures.append(str(error) if isinstance(error, ValueError) else 'Machine unavailable')
                if endpoint is None:
                    raise ValueError('No compatible fallback is ready: ' + ('; '.join(failures) or 'choose CPU or another computer'))
            else:
                if endpoint['node'] in self.config['maintenance']:
                    raise ValueError('Leave maintenance on the primary machine before returning to Work mode')
                if not compatibility.current(self, endpoint):
                    endpoint['contract'] = compatibility.qualify(self, endpoint)
                else:
                    self.probe(endpoint)
            with self.changed:
                previous = copy.deepcopy(self.config)
                self.config["mode"] = mode
                self.config['fallback' if mode == 'gaming' else 'primary'] = endpoint
                try:
                    self.save()  # Persist before routing changes; a failed write leaves the route unchanged.
                except Exception:
                    self.config = previous
                    raise
                self.mode = "draining" if mode == "gaming" else "work"
                self.phase = "draining responses" if mode == "gaming" else "idle"
            if mode == "work":
                return {"mode": "work"}
            progress("New requests use fallback; waiting for active GPU responses")
            with self.changed:
                # Wait on actual request leases; never interrupt a generation or replay emitted tokens.
                while any(n == primary["node"] and m != endpoint["model"] and count
                          for (n, m), count in self.active.items()):
                    self.changed.wait(timeout=1)
            node = self.node(primary["node"])
            for model in self.config["managed"].get(primary["node"], []):
                if primary["node"] == endpoint["node"] and model == endpoint["model"]:
                    continue
                self.rpc(node, "/api/generate", {"model": model, "keep_alive": 0, "stream": False})
            resident = self.rpc(node, "/api/ps").get("models", [])
            with self.lock:
                self.mode = "gaming"
            remaining = [m["name"] for m in resident if m.get("size_vram", 0) > 0]
            if remaining:
                return {"mode": "gaming", "gpu_released": False, "remaining_models": remaining,
                        "note": "Other Ollama models still use GPU memory. External clients are outside this gateway's control."}
            return {"mode": "gaming", "gpu_released": True}

    def lifecycle(self, identity, model, action, progress=lambda _: None):
        model = model_name(model)
        if action not in ("load", "unload"):
            raise ValueError("Unknown model action")
        with self.operation, self.administer(identity):
            with self.lock:
                if action == 'load' and (identity in self.config['maintenance'] or self.config.get('driver_hold')):
                    raise ValueError('Machine is paused for maintenance; resume it before loading models')
                if any(n == identity and count for (n, _), count in self.active.items()):
                    raise ValueError("This machine has active responses; use Gaming mode to drain them first")
                active_role = "fallback" if self.mode in ("gaming", "draining") else "primary"
                if action == "unload" and self.config[active_role] and self.config[active_role]["node"] == identity and self.config[active_role]["model"] == model:
                    raise ValueError("This is the active route; switch modes before unloading it")
                if action == "load" and self.mode != "work" and self.config["primary"] and identity == self.config["primary"]["node"]:
                    raise ValueError("Gaming mode protects this GPU; return to Work mode to load models")
            result = self.rpc(self.node(identity), "/api/generate", {"model": model, "keep_alive": "30m" if action == "load" else 0, "stream": False})
            if action == "load":
                with self.lock:
                    owned = self.config["managed"].setdefault(identity, [])
                    if model not in owned:
                        owned.append(model)
                    self.save()
            return result

    def pull(self, identity, model, progress=lambda _: None):
        model = model_name(model)
        conn, response = connect(self.node(identity), "/api/pull", {"model": model, "stream": True}, timeout=600)
        try:
            success = False
            while True:
                line = response.readline(1024 * 1024)
                if not line:
                    break
                item = json.loads(line)
                if item.get("error"):
                    raise ValueError("Ollama could not download this model; verify its tag, license access and runtime compatibility")
                detail = item.get("status", "Downloading")
                if item.get("total"):
                    detail += f" · {100 * item.get('completed', 0) / item['total']:.0f}%"
                progress(detail)
                success = item.get("status") == "success"
            if not success:
                raise ValueError("Download ended before Ollama confirmed success; retry to resume")
            return {"model": model, "downloaded": True}
        finally:
            conn.close()

    def pair(self, code, name):
        if not isinstance(name, str) or not 1 <= len(name) <= 60:
            raise ValueError("Give the machine a short name")
        try:
            pairing = json.loads(code)
            node = {"name": name, "url": pairing["url"], "fingerprint": pairing["fingerprint"], "kind": "worker"}
        except (ValueError, KeyError, TypeError):
            raise ValueError("Paste the private pairing JSON created on the other machine") from None
        parsed = validate_url(node["url"], worker=True)
        if parsed.scheme != "https" or not re.fullmatch(r"[0-9a-f]{64}", node["fingerprint"]):
            raise ValueError("Invalid HTTPS pairing record")
        identity = hashlib.sha256(node["url"].encode()).hexdigest()[:12]
        with self.lock:
            if identity in self.config['nodes']:
                raise ValueError('Machine already paired; remove or rotate it explicitly')
            if not pairing.get('code'):
                raise ValueError('Create a fresh expiring pairing code on the updated worker')
            issued = self.rpc(node, '/pair', {'code': pairing['code'], 'name': 'Local Control'}, timeout=8)
            if not all(isinstance(issued.get(k), str) and re.fullmatch(r'[A-Za-z0-9_-]{40,100}', issued[k]) for k in ('token', 'inference_token')):
                raise ValueError('Worker returned invalid credentials')
            node.update({k: issued[k] for k in ('token', 'inference_token', 'controller_id')})
            self.config["nodes"][identity] = node
            try:
                self.save()
            except Exception:
                del self.config['nodes'][identity]
                # The worker retains a visible controller entry for explicit revocation
                # if the reply/storage was lost; never silently replay pairing.
                raise
        self.event("Paired machine: " + name)
        return {"node": identity}
