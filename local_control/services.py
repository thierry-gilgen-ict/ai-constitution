"""Bounded controller maintenance; no work starts outside the running service."""
import threading
import time
from . import synchronization, project_vault, monitoring, updates


def errors(root):
    from scripts import constitution as kit
    path = root / 'services-error.json'
    try:
        kit.no_links(path)
        return kit.read_json(path).get('errors', [])
    except FileNotFoundError: return []
    except (ValueError, OSError): return [{'service': 'maintenance', 'message': 'Service status could not be read. Check private state permissions.'}]


def synchronize(control, progress=lambda _: None):
    try:
        result = synchronization.reconcile(control.root, control.config, progress=progress)
        if any(p.get('status') == 'conflict' for p in result.get('projects', [])):
            raise ValueError('Some projects have synchronization conflicts. Open Projects to review and resolve them.')
        return result
    except (ValueError, OSError):
        from .storage import atomic
        atomic(control.root / 'sync-error.json', {'time': time.time(), 'message': 'Synchronization needs attention. Check library validation, local edits and folder permissions; retry from Projects.'})
        raise


def readiness(control, progress=lambda _: None):
    return control.health_check(progress=progress, force=False)


class Services:
    def __init__(self, control):
        self.control = control
        self.stopped = threading.Event()
        self.wake = threading.Event()
        self.last_monitor = 0
        self.last_health = 0
        self.thread = threading.Thread(target=self.run, name='local-control-maintenance', daemon=True)

    def submit(self, label, function, *args, quiet=True):
        with self.control.lock:
            if any(j['status'] in ('queued','running') and j.get('operation') == function.__name__ for j in self.control.jobs.values()):
                return False
        self.control.submit(label, function, *args, quiet=quiet)
        return True

    def backups(self):
        with self.control.lock:
            active = [j for j in self.control.jobs.values() if j['status'] in ('queued','running')]
        if len(active) >= 4 or any(j.get('operation') == 'scheduled' for j in active): return
        if project_vault.claim_due(self.control.root):
            try: self.submit('Scheduled project configuration backup', project_vault.scheduled, self.control.root, quiet=False)
            except ValueError: project_vault.schedule_state(self.control.root, 'rejected')

    def synchronize(self):
        if synchronization.settings(self.control.root)['enabled'] and synchronization.status(self.control.root)['projects']:
            self.submit('Synchronize enrolled projects', synchronize, self.control)

    def monitor(self):
        if time.time() - self.last_monitor >= 300 and monitoring.load(self.control.root)['codex_enabled']:
            if self.submit('Refresh local subscription usage', monitoring.refresh, self.control): self.last_monitor = time.time()

    def health(self):
        if time.time() - self.last_health >= 60:
            if self.submit('Refresh machine readiness', readiness, self.control): self.last_health = time.time()

    def releases(self):
        value = updates.read(self.control.root)
        if value.get('automatic_check', True) and time.time() - value.get('last_check', 0) >= 86400:
            self.submit('Check application updates', updates.check, self.control.root)

    def tick(self):
        if self.control.stopping: return
        errors = []
        for task in (self.backups, self.synchronize, self.monitor, self.health, self.releases):
            try: task()
            except Exception as error:
                # Saturation is transient. Each independent service still gets its
                # opportunity, and malformed state never suppresses another service.
                if isinstance(error, ValueError) and ('operations are already queued' in str(error) or 'stopping' in str(error)): continue
                errors.append({'service': task.__name__, 'message': 'Maintenance could not run. Review its settings, private state and permissions.'})
        from .storage import atomic
        path = self.control.root / 'services-error.json'
        if errors: atomic(path, {'errors': errors, 'time': time.time()})
        else: path.unlink(missing_ok=True)

    def run(self):
        while not self.stopped.is_set():
            try: self.tick()
            except (OSError, ValueError): pass  # State itself may be unavailable; next tick retries.
            self.wake.wait(60); self.wake.clear()

    def start(self): self.thread.start()

    def close(self):
        self.stopped.set(); self.wake.set(); self.thread.join(timeout=2)
