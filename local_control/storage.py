"""Private, atomic state and process ownership for Windows, macOS and Linux."""
import json
import os
from pathlib import Path
import secrets


def private_root():
    return Path(os.environ.get("AI_CONSTITUTION_LOCAL_HOME", str(Path.home() / ".config/ai-constitution/local-control"))).absolute()


def atomic(path, value):
    path = Path(path)
    for parent in (path, *path.parents):
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("Private state must not traverse symbolic links or junctions")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
        path.parent.mkdir(parents=True, exist_ok=True)
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


def load(root):
    path = root / "config.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") != 1:
            raise ValueError("Unsupported Local Control state version; preserve it before upgrading")
        if "gateway_token" not in value:
            value["gateway_token"] = secrets.token_urlsafe(32)
            atomic(path, value)
        return value
    value = {"schema": 1, "token": secrets.token_urlsafe(32), "gateway_token": secrets.token_urlsafe(32), "nodes": {
        "local": {"name": "This computer", "url": "http://127.0.0.1:11434", "kind": "ollama"}},
        "primary": None, "fallback": None, "mode": "work", "managed": {}, "context": 65536}
    atomic(path, value)
    return value
