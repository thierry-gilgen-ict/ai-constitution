#!/usr/bin/env python3
"""AI Constitution: portable instructions, model catalogs, and reversible installs."""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile
if __package__:
    from .paths import is_link
else:
    from paths import is_link

if __package__:
    from .adoption import project_record
    from . import policy, releases, source_review, architecture, catalog
    from .catalog import (atomic_bytes, catalog_diff, digest, discover_local, effective_providers, fetch_public,
                          json_bytes, refresh, utc_now, validate_providers)
else:
    from adoption import project_record
    import policy, releases, source_review, architecture, catalog
    from catalog import (atomic_bytes, catalog_diff, digest, discover_local, effective_providers, fetch_public,
                         json_bytes, refresh, utc_now, validate_providers)

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- ai-constitution:begin -->"
END = "<!-- ai-constitution:end -->"
MODULES = ("constitution.md", "engineering.md", "research.md", "maintenance.md", "routing.md", "VERSION")


@contextmanager
def state_lock(state):
    """Serialize read/modify/write operations across CLI processes; OS releases on exit."""
    no_links(state)
    lock_path = state.parent / (".constitution-" + digest(str(state.absolute()).encode())[:16] + ".lock")
    no_links(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(lock_path, "a+b")
    try:
        stream.write(b"\0")
        stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("Another installation or rollback is running; retry after it finishes") from None
        yield
    finally:
        stream.close()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def text(path):
    return Path(path).read_bytes().decode("utf-8")


def no_links(path):
    for part in (path, *path.parents):
        if is_link(part):
            raise ValueError("Refusing to write through a symbolic link or junction")


def safe_path(root, relative):
    path = root / relative
    no_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Destination escapes its selected root")
    return path


def installed_path(root, relative, cursor_dir=None):
    if cursor_dir is not None and relative.startswith(".cursor/"):
        return safe_path(Path(cursor_dir), relative[len(".cursor/"):])
    return safe_path(root, relative)


def managed(existing, content):
    block = BEGIN + "\n" + content.rstrip() + "\n" + END
    starts, ends = existing.count(BEGIN), existing.count(END)
    if starts == ends == 0:
        return existing + ("\n\n" if existing and not existing.endswith("\n\n") else "") + block + "\n"
    if starts != 1 or ends != 1 or existing.index(BEGIN) > existing.index(END):
        raise ValueError("Malformed managed markers; resolve them before installation")
    start, stop = existing.index(BEGIN), existing.index(END) + len(END)
    return existing[:start] + block + existing[stop:]


def managed_hash(body):
    value = body.decode("utf-8")
    if value.count(BEGIN) != 1 or value.count(END) != 1 or value.index(BEGIN) > value.index(END):
        return None
    start, stop = value.index(BEGIN), value.index(END) + len(END)
    return digest(value[start:stop].replace("\r\n", "\n").encode())


def state_load(state):
    path = state / "installations.json"
    result = read_json(path) if path.exists() else {"schema_version": 1, "targets": {}}
    if result.get("schema_version") != 1 or not isinstance(result.get("targets"), dict):
        raise ValueError("Unsupported installation-state schema; migrate state before continuing")
    return result


def validate(root):
    errors = []
    for path in (root / 'templates/architectures').glob('*.json'):
        architecture.validate(read_json(path))
    version = text(root / "VERSION").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("VERSION must be a three-part numeric release")
    sources = read_json(root / "registry/sources.json")["sources"]
    source_ids = {s["id"] for s in sources}
    models_doc = read_json(root / "registry/models.json")
    models = models_doc["models"]
    keys = {m["key"] for m in models}
    if len(keys) != len(models) or len(source_ids) != len(sources):
        errors.append("Duplicate model or source identifiers")
    for model in models:
        if model["source"] not in source_ids:
            errors.append("Model refers to an unknown source")
        dt.date.fromisoformat(model["verified_at"])
        if model["selection"] == "managed" and model["selector"] is not None:
            errors.append("Managed platform must not declare a selectable model")
    seen = set()
    for route in read_json(root / "registry/routes.json")["routes"]:
        identity = (route["platform"], route["task"])
        if identity in seen:
            errors.append("Duplicate route")
        seen.add(identity)
        for key in [route["preferred"], *route["fallbacks"]]:
            if key not in keys:
                errors.append("Route refers to an unknown model")
            elif next(m for m in models if m["key"] == key)["surface"] != route["platform"]:
                errors.append("Route crosses platforms without an explicit handoff")
    catalog_path = root / "registry/catalog.json"
    if catalog_path.exists():
        catalog = read_json(catalog_path)
        providers = validate_providers(catalog["providers"])
        if len(providers) != catalog["provider_count"] or sum(len(p["models"]) for p in providers.values()) != catalog["model_count"]:
            errors.append("Catalog counts disagree with its contents")
        effective_providers(root)
    else:
        errors.append("Catalog snapshot missing; run update")
    if errors:
        raise ValueError("; ".join(errors))


def render(root, preferences=None):
    version = text(root / "VERSION").strip()
    core = text(root / "constitution.md").strip()
    models = {m["key"]: m for m in read_json(root / "registry/models.json")["models"]}
    sources = {s["id"]: s for s in read_json(root / "registry/sources.json")["sources"]}
    routes = read_json(root / "registry/routes.json")["routes"]
    if preferences:
        core = preferences["instructions"]["constitution.md"].strip()
        routes = preferences["routes"]["routes"]
    lines = ["# Routing", "", f"Generated for v{version}. Edit `registry/models.json` and `registry/routes.json`, then run `build`.", "",
             "These are provisional starting points, not measured rankings. Respect an explicit model choice. Confirm account access and required tools before selecting a model. Reasoning levels and model identifiers can differ between clients.", "",
             "| Platform | Task | Preferred | Fallback |", "| --- | --- | --- | --- |"]
    for route in routes:
        lines.append(f"| {route['platform']} | {route['task']} | {models[route['preferred']]['name']} | "
                     + (", ".join(models[k]["name"] for k in route["fallbacks"]) or "Platform managed") + " |")
    lines += ["", "## Selection boundaries", "",
              "- Codex: use supported settings or the model picker. This guide never rewrites your active model settings.",
              "- Cursor: use the model picker or supported SDK. Native Auto remains managed by Cursor.",
              "- Grok Bot: there is no model picker. Routing describes task/tool selection and authorized handoffs.",
              "- Local servers: discover installed models explicitly with `local`. Tool calling, context, and reasoning support must be tested on that server; model names are insufficient.",
              "- When a candidate is unavailable, use an available listed fallback. If none fits, state the limitation.",
              "- Keep source verification dates separate from catalog download dates. Review stale recommendations before selecting them.", "", "## Evidence", ""]
    for model in models.values():
        source = sources[model["source"]]
        lines.append(f"- **{model['name']}** ({model['surface']}): {model['status']}; checked {model['verified_at']}. {model['evidence']} [Source]({source['url']}).")
    common = f"AI Constitution v{version}\n\n{core}\n\n"
    common += ("For an onboarded project, use its `.ai/shared/` bundle and `.ai/project.md`; its scoped defaults refine the global baseline. "
               "Read `.ai/architecture.md` when present for the selected project baseline. "
               "Otherwise locate the library through `AI_CONSTITUTION_HOME` or `~/.config/ai-constitution`. Read `engineering.md`, `research.md`, or `routing.md` only when relevant. "
               "If the library is inaccessible, use this embedded core and report any task-relevant missing guidance.\n")
    bot_description = (f"Use AI Constitution v{version} from BUNDLE_ROOT. Read its constitution.md when starting substantive work, and specialized modules only as needed. "
                       "Use the current project bundle when present. Keep your role and project knowledge separate. Model selection is platform managed. "
                       "Existing user authorization and platform permissions govern actions. Confirm the version from files, not memory.\n")
    bot_skill = ("---\nname: ai-constitution\ndescription: Load the shared AI Constitution for a Grok Bot's project work and verify its installed version.\n---\n\n"
                 "# Load the shared constitution\n\nLocate BUNDLE_ROOT from this Bot's description. Read VERSION and constitution.md there. "
                 "If working in an onboarded project, prefer its .ai/shared bundle and .ai/project.md for scoped defaults. "
                 "Read .ai/architecture.md when present for the selected baseline and its implementation handoff. "
                 "Read engineering.md for code work, research.md for source verification, and routing.md when selecting tools or recommending a handoff. "
                 "Report missing files precisely. Do not assume a cloud Bot can read a local Windows path. "
                 "Never claim to change the platform-managed underlying model.\n")
    return {
        "routing.md": "\n".join(lines) + "\n",
        "adapters/codex/AGENTS.md": common,
        "adapters/cursor/user-rules.md": common,
        "adapters/cursor/ai-constitution.mdc": "---\ndescription: Shared AI Constitution working defaults\nalwaysApply: true\n---\n\n" + common,
        "adapters/grok-bot/description.md": bot_description,
        "adapters/grok-bot/SKILL.md": bot_skill,
    }


def build(root, check=False):
    changed = []
    for relative, content in render(root).items():
        path = safe_path(root, relative)
        data = content.encode("utf-8")
        if not path.exists() or path.read_bytes() != data:
            changed.append(relative)
            if not check:
                atomic_bytes(path, data)
    if check and changed:
        raise ValueError("Generated files are stale: " + ", ".join(changed))
    return changed


def transaction(state, writes, *, dry_run=False):
    prepared = []
    for path, after in writes.items():
        path = path.absolute()
        no_links(path)
        before = path.read_bytes() if path.exists() else None
        if before == after:
            continue
        prepared.append({"path": str(path), "before": base64.b64encode(before).decode() if before is not None else None,
                         "after_sha256": digest(after) if after is not None else None, "data": after})
    if dry_run:
        return {"status": "preview", "files": [p["path"] for p in prepared]}
    if not prepared:
        return {"status": "unchanged", "files": []}
    snapshot = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    no_links(state)
    record = {"schema_version": 1, "id": snapshot, "state": "prepared",
              "files": [{k: v for k, v in p.items() if k != "data"} for p in prepared]}
    journal = state / "transactions" / (snapshot + ".json")
    atomic_bytes(journal, json_bytes(record))
    completed = []
    try:
        for item in prepared:
            if item['data'] is None:
                Path(item['path']).unlink(missing_ok=True)
            else:
                atomic_bytes(Path(item["path"]), item["data"])
            completed.append(item)
        record["state"] = "applied"
        atomic_bytes(journal, json_bytes(record))
    except Exception:
        for item in reversed(completed):
            path = Path(item["path"])
            if item["before"] is None:
                path.unlink()
            else:
                atomic_bytes(path, base64.b64decode(item["before"]))
        record["state"] = "reverted-on-error"
        atomic_bytes(journal, json_bytes(record))
        raise
    return {"status": "installed", "snapshot": snapshot, "files": [p["path"] for p in prepared]}


def install(root, state, **kwargs):
    if kwargs.get("dry_run"):
        return _install(root, state, **kwargs)
    with state_lock(state):
        return _install(root, state, **kwargs)


def adopt(state, project, dry_run=False):
    project = project.absolute()
    def apply():
        record = project_record(project, modules=MODULES, safe_path=safe_path,
                                managed_hash=managed_hash, digest=digest)
        override = safe_path(project, "AGENTS.override.md")
        if override.exists() and override.stat().st_size:
            raise ValueError("AGENTS.override.md shadows AGENTS.md; reconcile it first")
        db = state_load(state)
        identity = "project:" + str(project)
        if identity in db["targets"] and db["targets"][identity] != record:
            raise ValueError("Project already enrolled with different evidence; run doctor")
        db["targets"][identity] = record
        result = transaction(state, {state / "installations.json": json_bytes(db)}, dry_run=dry_run)
        return {**result, "version": record["version"], "pinned": record["pinned"],
                "evidence": "portable-lock-consistency; publisher authenticity not established",
                "next": "Use sync --all --dry-run to preview an upgrade; pinned projects stay pinned."}
    if dry_run:
        return apply()
    with state_lock(state):
        return apply()


def _install(root, state, *, platform=None, project=None, home=None, cursor_dir=None, dry_run=False, pin=None, planned=None, database=None, source_reference=None):
    validate(root)
    build(root, check=True)
    db = database if database is not None else state_load(state)
    target_root = (project or home or Path.home()).absolute()
    no_links(target_root)
    if project and not target_root.is_dir():
        raise ValueError("Project directory must already exist")
    identity = ("project:" if project else platform + ":") + str(target_root)
    previous = db["targets"].get(identity, {})
    if project and not previous and safe_path(target_root, ".ai/constitution.lock.json").exists():
        raise ValueError("Existing project lock: run onboard --adopt to verify and enroll this bundle first")
    if pin is None:
        pin = previous.get("pinned", False)
    if platform == "cursor":
        cursor_dir = cursor_dir or (Path(previous["cursor_dir"]) if previous.get("cursor_dir") else None)
        if cursor_dir is not None:
            cursor_dir = cursor_dir.absolute()
            no_links(cursor_dir)
            if not cursor_dir.is_dir():
                raise ValueError("The explicit Cursor configuration directory must already exist")
            if previous and previous.get("cursor_dir") != str(cursor_dir):
                raise ValueError("Cursor is already enrolled at another location; preserve or roll back that installation first")
    else:
        cursor_dir = None
    writes, tracked = {}, {}
    preferences = policy.resolve(root, state, project, portable=True)
    outputs = render(root, preferences)

    def module_bytes(name):
        if name in preferences["instructions"]:
            return preferences["instructions"][name].encode("utf-8")
        if name == "routing.md":
            return outputs["routing.md"].encode("utf-8")
        return (root / name).read_bytes()

    def add(relative, data, block=False, create_only=False):
        path = installed_path(target_root, relative, cursor_dir)
        existing = path.read_bytes() if path.exists() else b""
        if create_only and path.exists():
            return
        old = previous.get("files", {}).get(relative)
        if old and path.exists():
            actual = managed_hash(existing) if old["managed"] else digest(existing)
            if actual != old["sha256"]:
                raise ValueError(f"Local edits detected in {relative}; preserve or reconcile them before syncing")
        if block:
            data = managed(existing.decode("utf-8"), data.decode("utf-8")).encode("utf-8")
        elif path.exists() and not old and existing != data:
            raise ValueError(f"Unmanaged file already exists: {relative}")
        writes[path] = data
        tracked[relative] = {"sha256": managed_hash(data) if block else digest(data), "managed": block}

    version = text(root / "VERSION").strip()
    if project:
        if (target_root / "AGENTS.override.md").exists() and (target_root / "AGENTS.override.md").stat().st_size:
            raise ValueError("AGENTS.override.md shadows AGENTS.md; reconcile the override before onboarding")
        core = preferences["instructions"]["constitution.md"].strip()
        body = f"AI Constitution v{version}\n\n{core}\n\nProject context: `.ai/project.md`. If present, read `.ai/architecture.md` for the chosen project baseline and `.ai/architecture-onboarding.md` for its implementation handoff. Specialized guidance: `.ai/shared/engineering.md`, `.ai/shared/research.md`, and `.ai/shared/routing.md`, loaded when relevant.\n"
        add("AGENTS.md", body.encode(), block=True)
        for name in MODULES:
            add(".ai/shared/" + name, module_bytes(name))
        add(".ai/project.md", (root / "templates/project.md").read_bytes(), create_only=True)
        # Project context belongs to the user, not to the managed bundle.
        tracked.pop(".ai/project.md", None)
        lock = {"schema_version": 1, "version": version, "pinned": pin,
                "source": "https://github.com/thierry-gilgen-ict/ai-constitution",
                "files": {k: v for k, v in tracked.items()}}
        add(".ai/constitution.lock.json", json_bytes(lock))
    else:
        source = "adapters/codex/AGENTS.md" if platform == "codex" else "adapters/cursor/ai-constitution.mdc"
        source_reference = source_reference or root
        library = target_root / ".config/ai-constitution/libraries" / platform
        content = outputs[source] + f"\nInstalled shared library: `{library.as_posix()}`. Source checkout: `{source_reference.as_posix()}`.\n"
        for name in MODULES:
            add(f".config/ai-constitution/libraries/{platform}/{name}", module_bytes(name))
        add(f".config/ai-constitution/libraries/{platform}/installation.json", json_bytes({
            "schema_version": 1, "source_root": str(source_reference), "version": version, "platform": platform,
        }))
        if platform == "codex":
            # Respect CODEX_HOME only for the actual default home, not fixture homes.
            codex_dir = Path(os.environ.get("CODEX_HOME", str(target_root / ".codex"))) if home is None else target_root / ".codex"
            if codex_dir.absolute() != target_root / ".codex":
                raise ValueError("Custom CODEX_HOME: use --home with a standard test layout or install the exported adapter manually")
            if (codex_dir / "AGENTS.override.md").exists() and (codex_dir / "AGENTS.override.md").stat().st_size:
                raise ValueError("Global AGENTS.override.md shadows AGENTS.md; reconcile it first")
            add(".codex/AGENTS.md", content.encode(), block=True)
        else:
            add(".cursor/rules/ai-constitution.mdc", content.encode())
        for name in ("constitution-onboarding", "constitution-maintenance"):
            skill = text(root / f"skills/{name}/SKILL.md") + f"\nInstalled source checkout: `{source_reference.as_posix()}`.\n"
            add(f".{platform}/skills/{name}/SKILL.md", skill.encode())
    db["targets"][identity] = {"kind": "project" if project else platform, "root": str(target_root),
                               "version": version, "pinned": pin, "files": tracked}
    if cursor_dir is not None:
        db["targets"][identity]["cursor_dir"] = str(cursor_dir)
    writes[state / "installations.json"] = json_bytes(db)
    if planned is not None:
        planned.update(writes)
        return {"status": "planned", "target": str(target_root)}
    return transaction(state, writes, dry_run=dry_run)


def sync(root, state, include_pinned=False, dry_run=False):
    results = []
    for target in state_load(state)["targets"].values():
        if target["pinned"] and not include_pinned:
            results.append({"status": "skipped-pinned", "target": target["root"]})
            continue
        try:
            kwargs = {"project": Path(target["root"])} if target["kind"] == "project" else {"platform": target["kind"], "home": Path(target["root"])}
            results.append(install(root, state, **kwargs, pin=target["pinned"], dry_run=dry_run))
        except (OSError, ValueError) as error:
            results.append({"status": "error", "target": target["root"], "error": str(error)})
    return results


def rollback(state, snapshot):
    with state_lock(state):
        return _rollback(state, snapshot)


def _rollback(state, snapshot):
    if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", snapshot):
        raise ValueError("Invalid snapshot identifier")
    path = state / "transactions" / (snapshot + ".json")
    record = read_json(path)
    if record["state"] not in ("applied", "prepared", "rolling-back"):
        raise ValueError("Snapshot is not an applied transaction")
    for item in record["files"]:
        target = Path(item["path"])
        no_links(target)
        actual = target.read_bytes() if target.exists() else None
        before = base64.b64decode(item["before"]) if item["before"] is not None else None
        already_restored = record["state"] in ("prepared", "rolling-back") and actual == before
        if not already_restored and (digest(actual) if actual is not None else None) != item["after_sha256"]:
            raise ValueError("A target changed since this snapshot; rollback refused to preserve later edits")
    record["state"] = "rolling-back"
    atomic_bytes(path, json_bytes(record))
    for item in reversed(record["files"]):
        target = Path(item["path"])
        if item["before"] is None:
            target.unlink(missing_ok=True)
        else:
            atomic_bytes(target, base64.b64decode(item["before"]))
    record["state"] = "rolled-back"
    atomic_bytes(path, json_bytes(record))
    return {"status": "rolled-back", "snapshot": snapshot}


def doctor(root, state, project=None):
    validate(root)
    build(root, check=True)
    observations = []
    targets = list(state_load(state)["targets"].values())
    if project:
        targets = [t for t in targets if Path(t["root"]).resolve() == project.resolve()]
        if not targets:
            return [{"status": "not-enrolled", "target": str(project)}]
    for target in targets:
        problems = []
        for relative, expected in target["files"].items():
            path = installed_path(Path(target["root"]), relative, target.get("cursor_dir"))
            if not path.exists():
                problems.append(relative + ": missing")
            else:
                value = managed_hash(path.read_bytes()) if expected["managed"] else digest(path.read_bytes())
                if value != expected["sha256"]:
                    problems.append(relative + ": modified")
        override = Path(target["root"]) / (".codex/AGENTS.override.md" if target["kind"] == "codex" else "AGENTS.override.md")
        if target["kind"] != "cursor" and override.exists() and override.stat().st_size:
            problems.append("AGENTS.override.md shadows the installed entry point")
        observations.append({"target": target["root"], "kind": target["kind"], "version": target["version"],
                             "status": "drift" if problems else "files-verified", "problems": problems,
                             "activation": "Verify loading in a fresh client session; file checks do not prove model behavior."})
    return observations


def source_check(root, state):
    return source_review.check(root, state, state_lock)


def upgrade(source, state, dry_run=False, payload=None, expected_plan=None):
    """Stage an immutable library and update eligible targets in one transaction."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        candidate = Path(folder).resolve()
        payload = releases.files(source) if payload is None else payload
        for name, data in payload.items():
            if not releases.allowed(name):
                raise ValueError("Unsafe release source path")
            atomic_bytes(candidate / name, data)
        validate(candidate)
        build(candidate, check=True)
        def apply():
            identity, destination = releases.prepare(payload, state, preview=True)
            db = state_load(state)
            enrollment = digest(json_bytes(db))
            writes, targets = {}, []
            for target in list(db["targets"].values()):
                if target["pinned"]:
                    targets.append({"target": target["root"], "status": "skipped-pinned"})
                    continue
                kwargs = {"project": Path(target["root"])} if target["kind"] == "project" else {
                    "platform": target["kind"], "home": Path(target["root"]),
                    "cursor_dir": Path(target["cursor_dir"]) if target.get("cursor_dir") else None}
                targets.append(_install(candidate, state, **kwargs, source_reference=destination,
                                        pin=target["pinned"], planned=writes, database=db))
            active = state / "active-release.json"
            previous = read_json(active).get("identity") if active.exists() else None
            record = {"schema_version": 1, "identity": identity, "previous": previous}
            if previous == identity:
                record = read_json(active)
            writes[active] = json_bytes(record)
            signature = {}
            for path, after in writes.items():
                no_links(path)
                signature[str(path)] = [digest(path.read_bytes()) if path.exists() else None, digest(after)]
            plan = digest(json_bytes({'release': identity, 'enrollment': enrollment, 'writes': signature}))
            if expected_plan is not None and expected_plan != plan:
                raise ValueError('Library or installed targets changed since preview. Preview activation again.')
            if not dry_run:
                releases.prepare(payload, state)
            result = transaction(state, writes, dry_run=dry_run)
            return {**result, "plan": plan, "release": identity, "targets": targets, "source_checkout_changed": False,
                    "scope": "instruction library; invoke the installed scripts for this release's CLI features"}
        if dry_run:
            return apply()
        with state_lock(state):
            return apply()


def explain(root, state, project=None):
    selected = policy.resolve(root, state, project)
    return {"release": text(root / "VERSION").strip(),
            "catalog": str(catalog.catalog_path(root, state)),
            "effective_sha256": selected["effective_sha256"], "layers": selected["layer_hashes"],
            "route_sources": selected["provenance"], "routes": selected["routes"]["routes"],
            "installation": doctor(root, state, project),
            "portable_bundle": "Personal prose and routes stay private; project policy is rendered into project bundles.",
            "host_loading": "unverified; file ownership checks do not establish client instruction loading"}


def scan(root):
    # Scans the exact Git file set, including force-added ignored files; never prints matches.
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, capture_output=True)
    if result.returncode:
        raise ValueError("Initialize Git before scanning the publishable file set")
    names = sorted(set(result.stdout.decode().split("\0")) - {""})
    staged = set(subprocess.check_output(["git", "ls-files", "-z", "--cached"], cwd=root).decode().split("\0"))
    patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}",
                r"\b(?:sk-proj-|sk-ant-|xai-)[A-Za-z0-9_-]{24,}", r"\bAKIA[A-Z0-9]{16}\b",
                r"(?i)(?:password|passwd|api_key|client_secret)\s*[=:]\s*[\"'](?!YOUR_|EXAMPLE|PLACEHOLDER|<|\$)[A-Za-z0-9+/=_-]{16,}[\"']"]
    findings = []
    for name in names:
        parts = Path(name).parts
        if releases.private_path(name):
            findings.append({"file": name, "rule": "private-file"})
            continue
        path = root / name
        if path.is_symlink():
            findings.append({"file": name, "rule": "symlink"})
            continue
        versions = []
        if name in staged:
            versions.append(subprocess.check_output(["git", "show", ":" + name], cwd=root))
        if path.exists():
            versions.append(path.read_bytes())
        # Include both staged and working content: fixing a working file does not unstage a secret.
        data = b"\n".join(dict.fromkeys(versions))
        if path.suffix.lower() == ".png":
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                findings.append({"file": name, "rule": "invalid-image"})
            continue
        try:
            value = data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append({"file": name, "rule": "unexpected-binary"})
            continue
        for number, pattern in enumerate(patterns):
            if re.search(pattern, value):
                findings.append({"file": name, "rule": f"credential-pattern-{number + 1}"})
        if re.search(r"(?i)[A-Z]:[\\/]Users[\\/](?!<|example|YOUR_|runner)[^\s/\\]+", value):
            findings.append({"file": name, "rule": "personal-home-path"})
    return {"files_scanned": len(names), "findings": findings,
            "scope": "Git tracked and nonignored files; heuristic scan, not a guarantee. Review the staged diff too."}


def export_bundle(root, output):
    validate(root)
    build(root, check=True)
    files = list(MODULES) + ["LICENSE", "onboarding/bot.md", "onboarding/project.md", "docs/updates.md", "checks/acceptance.md", "checks/evaluation.md"]
    files += list(render(root))
    files += ["registry/models.json", "registry/routes.json", "registry/sources.json"]
    no_links(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Explicit allowlist excludes local state, full catalog, credentials, and project facts.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(set(files)):
            archive.writestr(relative, (root / relative).read_bytes())
    return {"output": str(output), "files": len(set(files)), "sha256": digest(output.read_bytes())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, help="Private state (default: ~/.config/ai-constitution/state)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check", "scan"):
        sub.add_parser(name)
    upgrading = sub.add_parser("upgrade", help="Activate a verified library without changing the source checkout")
    upgrading.add_argument("--source", type=Path, help="Reviewed local checkout")
    upgrading.add_argument("--archive", type=Path)
    upgrading.add_argument("--sha256")
    upgrading.add_argument("--dry-run", action="store_true")
    release = sub.add_parser("release", help="Export a managed-upgrade archive")
    release.add_argument("--output", type=Path, required=True)
    explaining = sub.add_parser("explain")
    explaining.add_argument("--project", type=Path)
    explaining.add_argument("--json", action="store_true", help="JSON output (also the default)")
    sources = sub.add_parser("sources", help="Inspect durable pending source changes or acknowledge an exact revision")
    sources.add_argument("--check", action="store_true")
    sources.add_argument("--review")
    sources.add_argument("--revision")
    update = sub.add_parser("update", help="Refresh every provider/model definition from models.dev")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--allow-removals", action="store_true")
    update.add_argument("--sources", action="store_true", help="Also check curated official documentation for changes")
    update.add_argument("--source-checkout", action="store_true", help="Contributor mode: refresh the tracked snapshot instead of private cache")
    setup = sub.add_parser("install", help="Install global Codex/Cursor instructions and skills")
    setup.add_argument("--platform", choices=["codex", "cursor", "all"], default="all")
    setup.add_argument("--home", type=Path)
    setup.add_argument("--cursor-dir", type=Path, help="Explicit real Cursor configuration directory for relocated profiles; retained privately for sync")
    setup.add_argument("--dry-run", action="store_true")
    onboard = sub.add_parser("onboard", help="Adopt a project without replacing its own guidance")
    onboard.add_argument("--project", type=Path, required=True)
    onboard.add_argument("--pin", action="store_true", default=None)
    onboard.add_argument("--dry-run", action="store_true")
    onboard.add_argument("--adopt", action="store_true", help="Verify an existing portable bundle and enroll it without upgrading")
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("--all", action="store_true", required=True)
    sync_parser.add_argument("--include-pinned", action="store_true")
    sync_parser.add_argument("--dry-run", action="store_true")
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--project", type=Path)
    undo = sub.add_parser("rollback")
    undo.add_argument("--snapshot", required=True)
    query = sub.add_parser("models", help="Search the bundled catalog offline")
    query.add_argument("--provider")
    query.add_argument("--search", default="")
    query.add_argument("--tools", action="store_true")
    query.add_argument("--open-weights", action="store_true")
    query.add_argument("--json", action="store_true")
    query.add_argument("--limit", type=int, default=30)
    sub.add_parser("providers", help="List every catalog provider and its model count")
    route_parser = sub.add_parser("route")
    route_parser.add_argument("--platform", choices=["codex", "cursor", "grok-bot"], required=True)
    route_parser.add_argument("--task", choices=["small", "implementation", "deep", "review", "research"], default="implementation")
    route_parser.add_argument("--available", action="append", help="Eligible registry key; repeat to supply account-verified availability")
    route_parser.add_argument("--project", type=Path)
    local = sub.add_parser("local", help="Discover models on an explicitly selected local server")
    local.add_argument("--kind", choices=["ollama", "openai-compatible"], default="ollama")
    local.add_argument("--url")
    local.add_argument("--allow-remote", action="store_true")
    local.add_argument("--api-key-env")
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    architectures = sub.add_parser('architecture', help='List, inspect or apply portable project baselines')
    architectures.add_argument('operation', choices=['list','show','plan','apply'])
    architectures.add_argument('--template', help='Bundled template ID or path to an exported JSON template')
    architectures.add_argument('--project', type=Path)
    architectures.add_argument('--name', help='Project slug used in scaffold files')
    architectures.add_argument('--plan', help='Exact preview hash required for apply')
    args = parser.parse_args(argv)
    root = args.root.absolute()
    state = (args.state_dir or Path(os.environ.get("AI_CONSTITUTION_STATE_DIR", str(Path.home() / ".config/ai-constitution/state")))).absolute()
    if args.command not in {"build", "check", "scan", "release", "upgrade", "architecture"} and not getattr(args, "source_checkout", False):
        root = releases.selected(state, root)
    if args.command not in {"build", "check", "scan", "models", "providers", "route", "export"}:
        no_links(state)
    result, exit_code = None, 0
    if args.command == "build":
        result = {"generated": build(root)}
    elif args.command == "check":
        validate(root)
        build(root, check=True)
        result = {"status": "passed", "version": text(root / "VERSION").strip()}
    elif args.command == 'architecture':
        directory = root / 'templates/architectures'
        if args.operation == 'list':
            result = [architecture.validate(read_json(p)) for p in sorted(directory.glob('*.json'))]
        else:
            if not args.template:
                raise ValueError('Choose --template ID or a JSON file')
            path = Path(args.template) if args.template.endswith('.json') else directory / (architecture.identifier(args.template) + '.json')
            value = architecture.validate(read_json(path))
            if args.operation == 'show':
                result = {'template': value, 'review': architecture.review(value)}
            else:
                if not args.project or not args.name:
                    raise ValueError('Choose --project and --name')
                kit = sys.modules[__name__]
                result = (architecture.plan(kit, root, state, args.project, value, args.name)[0] if args.operation == 'plan' else
                          architecture.apply(kit, root, state, args.project, value, args.name, args.plan))
    elif args.command == "update":
        with state_lock(state):
            result = refresh(root, state, preview=args.dry_run, allow_removals=args.allow_removals, source_checkout=args.source_checkout)
        if result["status"] == "review-required":
            exit_code = 2
        elif not args.dry_run and args.source_checkout:
            build(root)
        if args.sources:
            result["sources"] = source_check(root, state)
            if any(v["status"] == "unavailable" for v in result["sources"].values()):
                exit_code = 2
        result["report"] = str(state / "catalog-diff.json")
        result["routing_defaults_changed"] = False
        result = {k: len(v) if isinstance(v, list) else v for k, v in result.items()}
    elif args.command == "install":
        platforms = ["codex", "cursor"] if args.platform == "all" else [args.platform]
        if args.cursor_dir and args.platform == "codex":
            raise ValueError("--cursor-dir applies to Cursor installation")
        result = [install(root, state, platform=p, home=args.home, cursor_dir=args.cursor_dir, dry_run=args.dry_run) for p in platforms]
    elif args.command == "onboard":
        if args.adopt and args.pin is not None:
            raise ValueError("Adoption preserves the existing pin; omit --pin")
        result = adopt(state, args.project, args.dry_run) if args.adopt else install(root, state, project=args.project, pin=args.pin, dry_run=args.dry_run)
    elif args.command == "sync":
        result = sync(root, state, args.include_pinned, args.dry_run)
        exit_code = 2 if any(r["status"] == "error" for r in result) else 0
    elif args.command == "doctor":
        result = doctor(root, state, args.project)
        exit_code = 2 if any(r["status"] != "files-verified" for r in result) else 0
    elif args.command == "rollback":
        result = rollback(state, args.snapshot)
    elif args.command == "scan":
        result = scan(root)
        exit_code = 2 if result["findings"] else 0
    elif args.command in ("models", "providers"):
        providers = effective_providers(root, state)
        if args.command == "providers":
            result = [{"id": key, "name": p["name"], "models": len(p["models"])} for key, p in providers.items()]
        else:
            if args.provider and args.provider not in providers:
                raise ValueError("Unknown provider; run providers to list available identifiers")
            if args.limit < 1:
                raise ValueError("--limit must be positive")
            rows = []
            for provider, record in providers.items():
                if args.provider and provider != args.provider:
                    continue
                for model_id, model in record["models"].items():
                    if args.search.lower() not in (model_id + " " + model["name"]).lower():
                        continue
                    if args.tools and not model.get("tool_call"):
                        continue
                    if args.open_weights and not model.get("open_weights"):
                        continue
                    rows.append({**model, "provider": provider, "id": model_id} if args.json else
                                {"provider": provider, "id": model_id, "name": model["name"], "context": model.get("limit", {}).get("context"), "tools": model.get("tool_call")})
            result = {"matches": len(rows), "showing": min(len(rows), args.limit), "models": rows[:args.limit]}
    elif args.command == "route":
        preferences = policy.resolve(root, state, args.project)
        routes = preferences["routes"]["routes"]
        models = {m["key"]: m for m in read_json(root / "registry/models.json")["models"]}
        route = next(r for r in routes if r["platform"] == args.platform and r["task"] == args.task)
        candidates = [route["preferred"], *route["fallbacks"]]
        candidates = [c for c in candidates if args.available is None or c in args.available]
        if not candidates:
            raise ValueError("No eligible route or fallback; retain the current configuration and verify availability")
        selected = models[candidates[0]]
        age = (dt.datetime.now(dt.timezone.utc).date() - dt.date.fromisoformat(selected["verified_at"])).days
        result = {"recommendation": selected, "note": route["note"], "account_verified": args.available is not None,
                  "preference_source": preferences["provenance"][args.platform + "/" + args.task],
                  "stale": age > read_json(root / "registry/models.json")["max_age_days"], "applied": False}
    elif args.command == "local":
        url = args.url or ("http://127.0.0.1:11434" if args.kind == "ollama" else "http://127.0.0.1:1234/v1")
        inventory = discover_local(url, args.kind, allow_remote=args.allow_remote, key_env=args.api_key_env)
        filename = "local-models-" + digest(url.encode())[:12] + ".json"
        atomic_bytes(state / filename, json_bytes(inventory))
        result = {"status": "discovered", "models": len(inventory["models"]), "saved_privately": str(state / filename), "inference_requests": 0}
    elif args.command == "export":
        result = export_bundle(root, args.output)
    elif args.command == "upgrade":
        if args.source and args.archive or bool(args.archive) != bool(args.sha256):
            raise ValueError("Use --source or --archive with --sha256")
        payload = releases.unpack(args.archive.read_bytes(), args.sha256) if args.archive else None if args.source else releases.latest()
        result = upgrade(args.source or root, state, args.dry_run, payload)
    elif args.command == "release":
        validate(root)
        build(root, check=True)
        result = releases.export(root, args.output)
    elif args.command == "sources":
        if args.check and args.review or bool(args.review) != bool(args.revision):
            raise ValueError("Use --check or --review SOURCE --revision SHA256")
        result = source_check(root, state) if args.check else source_review.acknowledge(state, args.review, args.revision, state_lock) if args.review else source_review.read(state)
    elif args.command == "explain":
        result = explain(root, state, args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        # Network exceptions can embed URLs or headers; avoid serializing their full representation.
        if isinstance(error, OSError):
            print(f"Error: {type(error).__name__}. Check access, network, or server availability. Existing files are retained.", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
