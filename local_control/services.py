"""Bounded controller maintenance; no work starts outside the running service."""
import threading
import time
from . import synchronization, project_vault, monitoring


def synchronize(control, progress=lambda _: None):
    try: return synchronization.reconcile(control.root, control.config, progress=progress)
    except (ValueError, OSError):
        from .storage import atomic
        atomic(control.root / 'sync-error.json', {'time': time.time(), 'message': 'Synchronization needs attention. Check library validation, local edits and folder permissions; retry from Projects.'})
        raise


class Services:
    def __init__(self, control):
        self.control = control
        self.stopped = threading.Event()
        self.wake = threading.Event()
        self.last_monitor = 0
        self.thread = threading.Thread(target=self.run, name='local-control-maintenance', daemon=True)

    def tick(self):
        control = self.control
        if control.stopping: return
        with control.lock:
            active = [j for j in control.jobs.values() if j['status'] in ('queued','running')]
        if len(active) < 4 and not any(j.get('operation') in ('synchronize','reconcile') for j in active):
            if synchronization.settings(control.root)['enabled']:
                try: control.submit('Synchronize enrolled projects', synchronize, control)
                except ValueError: pass
        with control.lock:
            room = sum(j['status'] in ('queued','running') for j in control.jobs.values()) < 4
        if room and project_vault.claim_due(control.root):
            try: control.submit('Scheduled project configuration backup', project_vault.scheduled, control.root)
            except ValueError: pass  # Queue saturation is reported in Activity; retry next interval.
        if time.time() - self.last_monitor >= 300 and monitoring.load(control.root)['codex_enabled']:
            self.last_monitor = time.time()
            try: control.submit('Refresh local subscription usage', monitoring.refresh, control)
            except ValueError: pass

    def run(self):
        while not self.stopped.is_set():
            try: self.tick()
            except Exception: pass  # One unavailable integration must not stop backups/sync forever.
            self.wake.wait(60); self.wake.clear()

    def start(self): self.thread.start()

    def close(self):
        self.stopped.set(); self.wake.set(); self.thread.join(timeout=2)
