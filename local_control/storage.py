"""Private, atomic state and process ownership for Windows, macOS and Linux."""
import json
import os
from pathlib import Path
import secrets
import time
from contextlib import contextmanager
from scripts.paths import no_links
from .permissions import directory, protect


def private_root():
    return Path(os.environ.get("AI_CONSTITUTION_LOCAL_HOME", str(Path.home() / ".config/ai-constitution/local-control"))).absolute()


@contextmanager
def wait_lock(path, timeout=10):
    """Queue brief dashboard edits behind initialization without retrying mutations."""
    from scripts import constitution as kit
    deadline = time.monotonic() + timeout
    while True:
        lock = kit.state_lock(path)
        try:
            lock.__enter__()
            break
        except ValueError as error:
            if not str(error).startswith('Another installation or rollback') or time.monotonic() >= deadline: raise
            time.sleep(.05)
    try: yield
    finally: lock.__exit__(None, None, None)


def atomic(path, value):
    path = Path(path)
    no_links(path)
    directory(path.parent)
    temp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with open(temp, "x", encoding="utf-8") as stream:
            if os.name != "nt":
                os.chmod(temp, 0o600)
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class ProcessLock:
    """OS releases ownership after a crash; no stale PID deletion is needed."""
    def __init__(self, path):
        no_links(path)
        directory(path.parent)
        if path.exists(): protect(path)
        self.file = open(path, "a+b")
        self.file.write(b"\0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError("Another Local Control process owns this state directory") from None

    def close(self):
        self.file.close()


def load(root, *, migrate=False):
    lock = ProcessLock(root / 'config.lock')
    try:
        return _load(root, migrate=migrate)
    finally:
        lock.close()


def _load(root, *, migrate=False):
    path = root / "config.json"
    if path.exists():
        no_links(path); protect(path)
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") not in (1, 2):
            raise ValueError("Unsupported Local Control state version; preserve it before upgrading")
        original = json.loads(json.dumps(value))
        if "gateway_token" not in value:
            value["gateway_token"] = secrets.token_urlsafe(32)
        if value['schema'] == 1:
            value.update(schema=2, controllers={}, pairing=None, legacy_worker_token=True,
                         fallbacks=[], maintenance=[], limits={'concurrent_per_node': 1, 'queue': 16, 'wait_seconds': 60})
        if migrate and value != original:
            backup = root / 'migrations/config-v1.json'
            if not backup.exists():
                atomic(backup, original)
            atomic(path, value)
        return value
    value = {"schema": 2, "token": secrets.token_urlsafe(32), "gateway_token": secrets.token_urlsafe(32), "nodes": {
        "local": {"name": "This computer", "url": "http://127.0.0.1:11434", "kind": "ollama"}},
        "primary": None, "fallback": None, "mode": "work", "managed": {}, "context": 65536,
        "controllers": {}, "pairing": None, "legacy_worker_token": False, "fallbacks": [], "maintenance": [],
        "limits": {"concurrent_per_node": 1, "queue": 16, "wait_seconds": 60}}
    atomic(path, value)
    return value
