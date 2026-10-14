"""Bounded controller maintenance; no work starts outside the running service."""
import threading
import time
from . import synchronization, project_vault, monitoring, updates, resource_profiles


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
    def __init__(self, control, *, worker=False):
        self.control = control
        self.worker = worker
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
        from .claude import settings
        if time.time() - self.last_monitor >= 300 and (monitoring.load(self.control.root)['codex_enabled'] or settings(self.control.root)['monitoring']):
            if self.submit('Refresh local subscription usage', monitoring.refresh, self.control): self.last_monitor = time.time()

    def health(self):
        if time.time() - self.last_health >= 60:
            if self.submit('Refresh machine readiness', readiness, self.control): self.last_health = time.time()

    def releases(self):
        value = updates.read(self.control.root)
        if value.get('automatic_check', True) and time.time() - value.get('last_check', 0) >= 86400:
            self.submit('Check application updates', updates.check, self.control.root)

    def profiles(self):
        if resource_profiles.overview(self.control.root)['enabled']:
            self.submit('Apply automatic resource profile',resource_profiles.automatic_profile,self.control)

    def toolkits(self):
        from .toolkits import overview,synchronize_toolkits
        if synchronization.settings(self.control.root)['enabled'] and overview(self.control.root)['projects']:
            self.submit('Synchronize project toolkits',synchronize_toolkits,self.control)

    def audit(self):
        from . import auditing
        config=auditing.settings(self.control.root)
        if (config['schedule']['enabled'] or config['semantic']['enabled']) and not config['schedule']['paused']:
            from .audit_store import Store
            last=Store(self.control.root).get('schedule','last',{})
            semantic=Store(self.control.root).get('schedule','semantic',{})
            structural_due=config['schedule']['enabled'] and (config['schedule']['changes'] and time.time()-last.get('checked_at',0)>=300 or time.time()-last.get('at',0)>=config['schedule']['hours']*3600)
            review_due=config['semantic']['enabled'] and time.time()-semantic.get('at',0)>=config['semantic']['hours']*3600
            if structural_due or review_due:
                self.submit('Scheduled constitution health scan',auditing.run_scheduled,self.control)

    def tick(self):
        if self.control.stopping: return
        # The peer listener is independently optional. A stale record cannot
        # manufacture an active listener when this service was started without it.
        errors = []
        tasks=(self.audit,) if self.worker else (self.backups, self.synchronize, self.monitor, self.health, self.releases, self.profiles, self.toolkits, self.audit)
        for task in tasks:
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
