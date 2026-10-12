"""Typed preference layers; prose still requires semantic review."""
import copy
import datetime as dt
import json
from pathlib import Path
if __package__:
    from .catalog import digest, json_bytes
else:
    from catalog import digest, json_bytes

MODULES = {"constitution.md", "engineering.md", "research.md", "maintenance.md",
           "security-guidance.md", "collaboration.md", "operational.md"}
TASKS = ("small", "implementation", "deep", "review", "research", "operational")
RISKS = ("low", "medium", "high", "critical")
EFFORTS = ("low", "medium", "high")
CONSTRAINTS = {"max_workers": 2, "max_attempts": 3, "max_wip": 2}
LEGACY_MODULES = ("constitution.md", "engineering.md", "research.md", "maintenance.md", "routing.md", "VERSION")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate policy field")
        result[key] = value
    return result


def read_layer(path):
    if not path.exists():
        return {"schema_version": 1, "instructions": {}, "routes": []}
    if path.stat().st_size > 262144:
        raise ValueError("Policy exceeds the size limit")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] not in (1, 2)):
        raise ValueError("Unsupported policy schema")
    allowed = {"schema_version", "instructions", "routes"}
    if value["schema_version"] == 2:
        allowed |= {"constraints", "exceptions"}
    instructions, routes = value.get("instructions", {}), value.get("routes", [])
    if (set(value) - allowed or not isinstance(instructions, dict) or set(instructions) - MODULES
            or not all(isinstance(v, str) and len(v.encode()) <= 32000 for v in instructions.values())
            or not isinstance(routes, list)):
        raise ValueError("Unsupported policy settings or module text")
    limits = value.get("constraints", {})
    if not isinstance(limits, dict) or set(limits) - set(CONSTRAINTS):
        raise ValueError("Unknown policy constraint")
    for key, limit in limits.items():
        if type(limit) is not int or not 1 <= limit <= CONSTRAINTS[key]:
            raise ValueError("Policy constraint cannot widen the shared boundary")
    exceptions, ids = value.get("exceptions", []), set()
    if not isinstance(exceptions, list):
        raise ValueError("Exceptions must be a list")
    for item in exceptions:
        fields = {"id", "owner", "reason", "expires", "evidence"}
        if (not isinstance(item, dict) or set(item) != fields
                or not all(isinstance(item[k], str) and 0 < len(item[k]) <= 2048 for k in fields)
                or item["id"] in ids):
            raise ValueError("Exception needs unique ID, owner, reason, expiry and evidence")
        dt.date.fromisoformat(item["expires"])
        ids.add(item["id"])
    return value


def validate_routes(document, models):
    if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
            or document["schema_version"] not in (1, 2) or not isinstance(document.get("routes"), list)):
        raise ValueError("Unsupported routing schema")
    seen = set()
    for route in document["routes"]:
        if not isinstance(route, dict):
            raise ValueError("Invalid route")
        if not isinstance(route.get("platform"), str) or not isinstance(route.get("task"), str):
            raise ValueError("Invalid route identity")
        identity = (route.get("platform"), route.get("task"))
        if identity[0] not in ("codex", "cursor", "grok-bot") or identity[1] not in TASKS or identity in seen:
            raise ValueError("Unknown or duplicate route")
        seen.add(identity)
        allowed = {"platform", "task", "description", "preferred", "fallbacks", "note"}
        if document["schema_version"] == 2:
            allowed |= {"effort", "risk_efforts", "escalation_only"}
        if set(route) - allowed or not isinstance(route.get("preferred"), str) or not isinstance(route.get("fallbacks"), list):
            raise ValueError("Invalid route fields")
        candidates = [route["preferred"], *route["fallbacks"]]
        if not all(isinstance(k, str) for k in candidates) or len(candidates) != len(set(candidates)):
            raise ValueError("Invalid or duplicate model candidate")
        for key in candidates:
            if key not in models:
                raise ValueError("Route refers to an unknown model")
            if models[key]["surface"] != identity[0]:
                raise ValueError("Policy route references a different-platform model")
        if route.get("effort") is not None and route["effort"] not in EFFORTS:
            raise ValueError("Unknown route effort")
        risks = route.get("risk_efforts", {})
        if not isinstance(risks, dict) or set(risks) - set(RISKS) or any(v not in EFFORTS for v in risks.values()):
            raise ValueError("Invalid risk effort")
        escalation = route.get("escalation_only", [])
        if (not isinstance(escalation, list) or not all(isinstance(k, str) for k in escalation)
                or len(escalation) != len(set(escalation))
                or any(k not in candidates for k in escalation)):
            raise ValueError("Invalid escalation-only candidates")


def release_identity(root):
    # Bind instruction sources/renderers, not publisher authenticity.
    names = sorted(MODULES | {"VERSION", "registry/models.json", "registry/routes.json", "registry/sources.json"})
    names += ["scripts/constitution.py", "scripts/policy.py", "scripts/adoption.py", "scripts/releases.py"]
    names += ["templates/project.md", "skills/constitution-onboarding/SKILL.md", "skills/constitution-maintenance/SKILL.md"]
    return digest(json_bytes({name: digest((root / name).read_bytes()) if (root / name).is_file() else "missing" for name in names}))


def resolve(root, state, project=None, *, portable=False):
    models = {m["key"]: m for m in json.loads((root / "registry/models.json").read_text(encoding="utf-8"))["models"]}
    routes = copy.deepcopy(json.loads((root / "registry/routes.json").read_text(encoding="utf-8")))
    validate_routes(routes, models)
    by_key = {(r["platform"], r["task"]): r for r in routes["routes"]}
    provenance = {f"{p}/{t}": "release" for p, t in by_key}
    instructions = {name: (root / name).read_text(encoding="utf-8") for name in MODULES}
    layers = [("personal", state.parent / "overrides/policy.json")]
    if project:
        layers.append(("project", project / ".ai/policy.json"))
    hashes, constraints, exceptions, legacy = {}, dict(CONSTRAINTS), [], []
    for label, path in layers:
        layer = read_layer(path)
        hashes[label] = digest(json_bytes(layer))
        private = bool(portable and project and label == "personal")
        for name, content in layer.get("instructions", {}).items():
            if content and (not project or label == "project"):
                instructions[name] += f"\n\n## {label.title()} preferences\n\n{content.rstrip()}\n"
        if not private:
            for key, limit in layer.get("constraints", {}).items():
                if limit > constraints[key]:
                    raise ValueError("Policy constraint cannot widen an inherited boundary")
                constraints[key] = limit
        records = {e["id"]: e for e in layer.get("exceptions", [])}
        seen = set()
        for override in layer.get("routes", []):
            allowed = {"platform", "task", "preferred", "fallbacks"}
            if layer["schema_version"] == 2:
                allowed |= {"effort", "exception"}
            if not isinstance(override, dict) or set(override) - allowed:
                raise ValueError("Invalid policy route fields")
            if not isinstance(override.get("platform"), str) or not isinstance(override.get("task"), str):
                raise ValueError("Invalid policy route identity")
            identity = (override.get("platform"), override.get("task"))
            if identity not in by_key or identity in seen:
                raise ValueError("Unknown or duplicate policy route")
            seen.add(identity)
            chosen = {k: override[k] for k in ("preferred", "fallbacks", "effort") if k in override}
            candidate = {**by_key[identity], **chosen}
            if "preferred" in chosen and "fallbacks" not in chosen:
                candidate["fallbacks"] = [k for k in candidate["fallbacks"] if k != candidate["preferred"]]
            candidate["escalation_only"] = [k for k in candidate.get("escalation_only", []) if k in [candidate["preferred"], *candidate["fallbacks"]]]
            validate_routes({"schema_version": 2, "routes": [candidate]}, models)
            if layer["schema_version"] == 2 and chosen:
                item = records.get(override.get("exception"))
                if item is None:
                    raise ValueError("Route exception needs owner, reason, expiry and evidence")
                if not private:
                    exceptions.append({"layer": label, "route": "/".join(identity), **item,
                                       "authority": "metadata only; verify human authorization separately"})
            elif chosen and not private:
                legacy.append({"layer": label, "route": "/".join(identity), "status": "legacy metadata not verified"})
            if not private:
                by_key[identity].update(candidate)
                provenance["/".join(identity)] = label
    instructions["collaboration.md"] += ("\n## Effective scope limits\n\n"
        f"Use at most {constraints['max_workers']} active workers, {constraints['max_attempts']} total attempts and {constraints['max_wip']} unfinished candidates. Existing stricter or consumed allowances remain binding.\n")
    for name, body in instructions.items():
        if len(body.encode("utf-8")) > (8192 if name == "constitution.md" else 6144):
            raise ValueError("Active policy exceeds byte budget: " + name)
    effective = {"routes": routes, "instructions": instructions, "constraints": constraints}
    return {**effective, "provenance": provenance, "layer_hashes": hashes, "exceptions": exceptions,
            "legacy_exceptions": legacy, "release_sha256": release_identity(root),
            "effective_sha256": digest(json_bytes(effective))}


def select_route(root, selected, platform, task, *, risk=None, available=None, missing_capabilities=(), escalation_reason=None):
    for item in selected.get("exceptions", []):
        if item["route"] == platform + "/" + task and dt.date.fromisoformat(item["expires"]) < dt.datetime.now(dt.timezone.utc).date():
            raise ValueError("Route exception expired; affected new work is blocked")
    if risk is not None and risk not in RISKS:
        raise ValueError("Unknown risk")
    if missing_capabilities:
        raise ValueError("Missing capability or authority blocks dispatch; escalation cannot repair it")
    if escalation_reason is not None and not escalation_reason.strip():
        raise ValueError("Escalation needs a recorded reason and separate authorization")
    models = {m["key"]: m for m in json.loads((root / "registry/models.json").read_text(encoding="utf-8"))["models"]}
    route = next(r for r in selected["routes"]["routes"] if r["platform"] == platform and r["task"] == task)
    candidates = [route["preferred"], *route["fallbacks"]]
    candidates = [k for k in candidates if available is None or k in available]
    escalation = route.get("escalation_only", [])
    if not escalation_reason:
        candidates = [k for k in candidates if k not in escalation]
    elif any(k in escalation for k in candidates):
        candidates = [k for k in candidates if k in escalation]
    if not candidates:
        raise ValueError("No eligible route or fallback; retain configuration and verify availability")
    model = models[candidates[0]]
    age = (dt.datetime.now(dt.timezone.utc).date() - dt.date.fromisoformat(model["verified_at"])).days
    return {"recommendation": model, "requested_effort": route.get("risk_efforts", {}).get(risk, route.get("effort")),
            "risk": risk or "unknown", "actual_model": "unknown", "actual_effort": "unknown", "applied": False,
            "note": route["note"], "account_verified": False,
            "availability_evidence": "caller-reported eligible keys" if available is not None else "unverified",
            "preference_source": selected["provenance"][platform + "/" + task],
            "release_sha256": selected["release_sha256"], "effective_sha256": selected["effective_sha256"],
            "constraints": selected["constraints"], "escalation_reason": escalation_reason,
            "independent_review": risk in ("high", "critical") or task == "review",
            "stale": age > json.loads((root / "registry/models.json").read_text(encoding="utf-8"))["max_age_days"]}


def authority_findings(project):
    findings = []
    for name in ("AGENTS.md", "ROUTING.md", "STATE.md", "docs/agent-workflow/ROUTING.md", "docs/agent-workflow/STATE.md"):
        path = project / name
        if not path.is_file():
            continue
        if path.stat().st_size > 65536:
            findings.append({"file": name, "rule": "oversized-active-authority", "semantic_review": "required"})
            continue
        text = path.read_text(encoding="utf-8")
        if "CHECKLIST.md" in text and ("only authoritative" in text or "sole task-status authority" in text) and "supersedes" in text:
            findings.append({"file": name, "rule": "conflicting-checklist-authority", "semantic_review": "required"})
        if name.endswith("ROUTING.md") and "gpt-" in text and ".ai/shared/routing.md" not in text:
            findings.append({"file": name, "rule": "project-model-table", "semantic_review": "required"})
    return findings
