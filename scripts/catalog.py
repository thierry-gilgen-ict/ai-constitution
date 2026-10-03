"""Public catalog refresh and explicitly requested local model discovery.

No inference requests, credentials files, downloads of weights, or SDK dependencies.
"""

from __future__ import annotations

import datetime as dt
import copy
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import tempfile
import urllib.parse
import urllib.request

CATALOG_URL = "https://models.dev/api.json?type=all"
MAX_BYTES = 32 * 1024 * 1024
OFFICIAL_HOSTS = frozenset({
    "models.dev", "developers.openai.com", "platform.openai.com", "learn.chatgpt.com",
    "cursor.com", "prod.cursor.com", "docs.cursor.com", "docs.x.ai", "x.ai",
    "platform.claude.com", "docs.anthropic.com", "ai.google.dev", "docs.ollama.com",
    "lmstudio.ai",
})


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_bytes(path: Path, data: bytes):
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Refusing to write through a symbolic link or junction")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symbolic link")
    fd, temp = tempfile.mkstemp(prefix=".constitution-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def catalog_bytes(document) -> bytes:
    """Keep each model on one line so catalog refresh diffs are practical to review."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
    metadata = {k: v for k, v in document.items() if k != "providers"}
    lines = ["{"]
    for key in sorted(metadata):
        lines.append(f"  {compact(key)}: {compact(metadata[key])},")
    lines.append('  "providers": {')
    providers = sorted(document["providers"].items())
    for index, (key, provider) in enumerate(providers):
        lines.append(f"    {compact(key)}: {{")
        for field in sorted(k for k in provider if k != "models"):
            lines.append(f"      {compact(field)}: {compact(provider[field])},")
        lines.append('      "models": {')
        models = sorted(provider["models"].items())
        for offset, (model_id, model) in enumerate(models):
            comma = "," if offset + 1 < len(models) else ""
            lines.append(f"        {compact(model_id)}: {compact(model)}{comma}")
        lines.append("      }")
        lines.append("    }" + ("," if index + 1 < len(providers) else ""))
    lines.extend(["  }", "}", ""])
    return "\n".join(lines).encode("utf-8")


def public_url(url: str):
    value = urllib.parse.urlsplit(url)
    if (value.scheme != "https" or value.hostname not in OFFICIAL_HOSTS
            or value.username or value.password or value.port not in (None, 443)):
        raise ValueError("Source URL is not an allowed public HTTPS documentation host")


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Local discovery does not follow redirects")


def fetch_public(url: str) -> bytes:
    public_url(url)
    opener = urllib.request.build_opener(CheckedRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Constitution/0.1", "Accept": "application/json,text/html,text/plain"})
    with opener.open(request, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Source exceeds the download size limit")
    return data


def validate_providers(providers):
    if not isinstance(providers, dict) or not providers:
        raise ValueError("Catalog must contain a nonempty provider object")
    for key, provider in providers.items():
        if not isinstance(key, str) or not isinstance(provider, dict):
            raise ValueError("Invalid provider record")
        if not isinstance(provider.get("models"), dict):
            raise ValueError("Provider models must be an object")
        if not isinstance(provider.get("name"), str):
            raise ValueError("Provider name is missing")
        for model_id, model in provider["models"].items():
            if not isinstance(model_id, str) or not isinstance(model, dict):
                raise ValueError("Invalid model record")
            if not isinstance(model.get("name"), str):
                raise ValueError("Model name is missing")
            # Preserve unknown upstream fields without interpreting them as instructions.
            for field in ("cost", "limit", "modalities"):
                if field in model and not isinstance(model[field], dict):
                    raise ValueError(f"Invalid model {field} object")
            for field in ("attachment", "open_weights", "reasoning", "structured_output", "temperature", "tool_call"):
                if model.get(field) is not None and type(model[field]) is not bool:
                    raise ValueError(f"Model {field} must be boolean or null (unknown)")
            for field in ("context", "input", "output"):
                value = model.get("limit", {}).get(field)
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError(f"Model limit.{field} must be a nonnegative integer or null")
            def prices(record):
                for field in ("input", "output", "cache_read", "cache_write", "input_audio", "output_audio", "reasoning"):
                    value = record.get(field)
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                        raise ValueError(f"Model cost.{field} must be finite and nonnegative or null")
                if "context_over_200k" in record:
                    if not isinstance(record["context_over_200k"], dict):
                        raise ValueError("Invalid context price object")
                    prices(record["context_over_200k"])
            prices(model.get("cost", {}))
            for field in ("input", "output"):
                value = model.get("modalities", {}).get(field)
                if value is not None and (not isinstance(value, list) or not all(isinstance(v, str) and v for v in value)):
                    raise ValueError(f"Model modalities.{field} must be a string list or null")
    return providers


def flattened(providers):
    return {f"{provider}/{model_id}": model for provider, record in providers.items()
            for model_id, model in record["models"].items()}


def catalog_diff(old, new):
    before, after = flattened(old), flattened(new)
    return {
        "providers_added": sorted(set(new) - set(old)),
        "providers_removed": sorted(set(old) - set(new)),
        "models_added": sorted(set(after) - set(before)),
        "models_removed": sorted(set(before) - set(after)),
        "models_changed": sorted(key for key in set(before) & set(after) if before[key] != after[key]),
        "providers_changed": sorted(key for key in set(old) & set(new)
                                    if {k: v for k, v in old[key].items() if k != "models"}
                                    != {k: v for k, v in new[key].items() if k != "models"}),
    }


def catalog_path(root, state=None):
    pointer = state / "catalog-active.json" if state else None
    if pointer and pointer.exists():
        identity = json.loads(pointer.read_text(encoding="utf-8"))["sha256"]
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid catalog snapshot identity")
        path = state.parent / "catalogs" / (identity + ".json")
        if digest(path.read_bytes()) != identity:
            raise ValueError("Catalog snapshot checksum mismatch")
        return path
    return root / "registry/catalog.json"


def effective_providers(root: Path, state=None):
    """Merge reviewed, source-linked overrides without editing the imported snapshot."""
    document = json.loads(catalog_path(root, state).read_text(encoding="utf-8"))
    providers = copy.deepcopy(validate_providers(document["providers"]))
    path = root / "registry/overrides.json"
    overrides = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "models": []}
    if overrides.get("schema_version") != 1 or not isinstance(overrides.get("models"), list):
        raise ValueError("Invalid override schema")
    seen = set()
    for item in overrides["models"]:
        identity = (item["provider"], item["id"])
        if identity in seen or not all(isinstance(v, str) and v for v in identity):
            raise ValueError("Duplicate or invalid override identifier")
        seen.add(identity)
        source = urllib.parse.urlsplit(item["source"])
        if source.scheme != "https" or not source.hostname or source.username or source.password:
            raise ValueError("Overrides need a public HTTPS evidence URL without credentials")
        dt.date.fromisoformat(item["verified_at"])
        definition = item["definition"]
        if not isinstance(definition, dict) or not isinstance(definition.get("name"), str):
            raise ValueError("Override needs a model definition with a name")
        if "id" in definition and definition["id"] != item["id"]:
            raise ValueError("Override model identifier does not match its definition")
        provider = providers.setdefault(item["provider"], {"id": item["provider"], "name": item.get("provider_name", item["provider"]), "models": {}})
        provider["models"][item["id"]] = {**definition, "id": item["id"],
            "constitution_provenance": {"source": item["source"], "verified_at": item["verified_at"], "kind": "reviewed-override"}}
    return validate_providers(providers)


def refresh(root: Path, state: Path, *, preview=False, allow_removals=False, raw=None, source_checkout=False):
    body = fetch_public(CATALOG_URL) if raw is None else raw
    providers = validate_providers(json.loads(body))
    path = root / "registry/catalog.json" if source_checkout else catalog_path(root, state)
    old_document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old = old_document.get("providers", {})
    changes = catalog_diff(old, providers)
    report = {"checked_at": utc_now(), "source": CATALOG_URL, "sha256": digest(body), **changes}
    atomic_bytes(state / "catalog-diff.json", json_bytes(report))
    removed = changes["models_removed"] or changes["providers_removed"]
    if removed and not allow_removals:
        report["status"] = "review-required"
        return report
    count = sum(len(p["models"]) for p in providers.values())
    report.update(provider_count=len(providers), model_count=count)
    if preview:
        report["status"] = "preview"
        return report
    if old == providers:
        report["status"] = "unchanged"
        return report
    document = {
        "schema_version": 1, "source": CATALOG_URL,
        "source_license": "MIT; see docs/licenses/models-dev.txt",
        "retrieved_at": report["checked_at"], "source_sha256": report["sha256"],
        "provenance": "Community catalog snapshot, not independent verification or account availability.",
        "provider_count": len(providers), "model_count": count, "providers": providers,
    }
    data = catalog_bytes(document)
    if source_checkout:
        atomic_bytes(path, data)
    else:
        identity = digest(data)
        atomic_bytes(state.parent / "catalogs" / (identity + ".json"), data)
        atomic_bytes(state / "catalog-active.json", json_bytes({"schema_version": 1, "sha256": identity}))
    report["status"] = "updated"
    return report


def local_url(base: str, allow_remote=False):
    value = urllib.parse.urlsplit(base)
    if value.scheme not in ("http", "https") or not value.hostname or value.username or value.password or value.query or value.fragment:
        raise ValueError("Use an HTTP(S) base URL without credentials, query, or fragment")
    hostname = value.hostname
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if not loopback and not allow_remote:
        raise ValueError("Non-loopback endpoint requires --allow-remote")
    if not loopback and value.scheme != "https":
        raise ValueError("Remote model discovery requires HTTPS")
    return base.rstrip("/")


def discover_local(base: str, kind: str, *, allow_remote=False, key_env=None):
    base = local_url(base, allow_remote)
    suffix = "/api/tags" if kind == "ollama" else "/models"
    headers = {"Accept": "application/json"}
    if key_env:
        key = os.environ.get(key_env)
        if not key:
            raise ValueError("The named API-key environment variable is not set")
        headers["Authorization"] = "Bearer " + key
    # No proxies: keep localhost metadata requests on the explicitly selected server.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(base + suffix, headers=headers)
    with opener.open(request, timeout=10) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("Local catalog exceeds size limit")
    payload = json.loads(body)
    records = payload.get("models" if kind == "ollama" else "data")
    if not isinstance(records, list):
        raise ValueError("Local server did not return the expected model list")
    models = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Invalid local model record")
        model_id = item.get("name") if kind == "ollama" else item.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("Local model identifier missing")
        models.append({"id": model_id, "source": kind,
                       "capabilities": "unknown; list endpoints do not prove tool or reasoning support",
                       "details": item.get("details", {}) if kind == "ollama" else {},
                       "digest": item.get("digest") if kind == "ollama" else None})
    return {"schema_version": 1, "discovered_at": utc_now(), "endpoint": base,
            "kind": kind, "models": models, "scope": "local-only; never commit this inventory"}
