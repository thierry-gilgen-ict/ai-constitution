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

from . import hardware
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
        self.config = load(root)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.operation = threading.Lock()
        self.active = {}
        self.admin_nodes = set()
        self.jobs = {}
        self.events = []
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

    def node(self, identity):
        with self.lock:
            if identity not in self.config["nodes"]:
                raise ValueError("Unknown machine")
            return copy.deepcopy(self.config["nodes"][identity])

    def status(self):
        with self.lock:
            nodes = {k: {a: b for a, b in n.items() if a not in ("token", "fingerprint")} for k, n in self.config["nodes"].items()}
            return {"nodes": nodes, "primary": self.config["primary"], "fallback": self.config["fallback"],
                    "mode": self.mode, "phase": self.phase, "active_requests": sum(self.active.values()),
                    "jobs": list(self.jobs.values())[-15:][::-1], "events": self.events[:20], "alias": ALIAS,
                    "context": self.config["context"], "managed": copy.deepcopy(self.config["managed"])}

    def inventory(self, identity):
        node = self.node(identity)
        version = self.rpc(node, "/api/version", timeout=5)
        tags = self.rpc(node, "/api/tags", timeout=8)
        running = self.rpc(node, "/api/ps", timeout=8)
        return {"version": version["version"], "models": tags.get("models", []), "running": running.get("models", [])}

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
        def progress(detail):
            with self.lock:
                job["detail"] = str(detail)[:200]
        def run():
            job["status"] = "running"
            try:
                result = function(*args, progress=progress)
                with self.lock:
                    job.update(status="done", detail="Complete", result=result)
                self.event(label + " completed")
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else type(error).__name__ + ": check machine availability"
                with self.lock:
                    job.update(status="failed", detail=message)
                self.event(label + " failed: " + message)
            finally:
                with self.lock:
                    self.phase = "idle"
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
        with self.changed:
            if direct:
                endpoint = {"node": "local", "model": model_name(payload.get("model"))}
            else:
                if payload.get("model") != ALIAS:
                    raise ValueError("Use model constitution-local on this gateway")
                endpoint = self.config["fallback" if self.mode in ("gaming", "draining") else "primary"]
                if not endpoint:
                    raise ValueError("Configure a working route in the dashboard first")
                endpoint = copy.deepcopy(endpoint)
            while endpoint["node"] in self.admin_nodes:
                self.changed.wait(timeout=1)
            key = (endpoint["node"], endpoint["model"])
            self.active[key] = self.active.get(key, 0) + 1
        try:
            body = {**payload, "model": endpoint["model"], "store": False}
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
                if self.mode != "work":
                    raise ValueError("Return to work mode before configuring routes")
            node = self.node(identity)
            installed = self.rpc(node, "/api/tags").get("models", [])
            if not any(m["name"] in (model, model + ":latest") for m in installed):
                raise ValueError("Download the model explicitly before configuring a coding route")
            suffix = hashlib.sha256((model + str(cpu) + str(self.config["context"])).encode()).hexdigest()[:10]
            alias = "constitution-" + ("cpu-" if cpu else "gpu-") + suffix + ":latest"
            parameters = {"num_ctx": self.config["context"], "num_gpu": -1}
            if cpu:
                parameters["num_gpu"] = 0
            progress("Creating an alias that reuses installed weights")
            self.rpc(node, "/api/create", {"model": alias, "from": model, "parameters": parameters, "stream": False})
            endpoint = {"node": identity, "model": alias, "source_model": model, "cpu": bool(cpu)}
            progress("Testing tool metadata, Responses API and memory placement")
            self.probe(endpoint)
            with self.lock:
                previous = copy.deepcopy(self.config)
                self.config[role] = endpoint
                owned = self.config["managed"].setdefault(identity, [])
                if alias not in owned:
                    owned.append(alias)
                try:
                    self.save()
                except Exception:
                    self.config = previous
                    raise
            return {"route": endpoint, "responses_tested": True, "tool_execution_tested": False}

    def switch(self, mode, progress=lambda _: None):
        if mode not in ("work", "gaming"):
            raise ValueError("Unknown mode")
        with self.operation:
            with self.lock:
                if mode == self.mode and self.mode != "draining":
                    return {"mode": self.mode}
                primary, fallback = copy.deepcopy(self.config["primary"]), copy.deepcopy(self.config["fallback"])
            if not primary:
                raise ValueError("Set up the primary route first")
            endpoint = fallback if mode == "gaming" else primary
            if not endpoint:
                raise ValueError("Gaming mode needs a tested CPU fallback or a second computer")
            if mode == "gaming" and endpoint["node"] == primary["node"] and not endpoint.get("cpu"):
                raise ValueError("Fallback must use CPU or another computer to release this GPU")
            self.phase = "checking fallback" if mode == "gaming" else "warming GPU"
            progress(self.phase)
            self.probe(endpoint)
            with self.changed:
                old_mode = self.config["mode"]
                self.config["mode"] = mode
                try:
                    self.save()  # Persist before routing changes; a failed write leaves the route unchanged.
                except Exception:
                    self.config["mode"] = old_mode
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
            node = {"name": name, "url": pairing["url"], "token": pairing["token"], "fingerprint": pairing["fingerprint"], "kind": "worker"}
        except (ValueError, KeyError, TypeError):
            raise ValueError("Paste the private pairing JSON created on the other machine") from None
        parsed = validate_url(node["url"], worker=True)
        if parsed.scheme != "https" or not re.fullmatch(r"[0-9a-f]{64}", node["fingerprint"]) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", node["token"]):
            raise ValueError("Invalid HTTPS pairing record")
        self.rpc(node, "/api/version", timeout=8)
        identity = hashlib.sha256(node["url"].encode()).hexdigest()[:12]
        with self.lock:
            self.config["nodes"][identity] = node
            self.save()
        self.event("Paired machine: " + name)
        return {"node": identity}
