"""Typed preference layers; prose is appended explicitly, never semantically merged."""
import copy
import json
from pathlib import Path
from catalog import digest, json_bytes

MODULES = {"constitution.md", "engineering.md", "research.md", "maintenance.md"}


def read_layer(path):
    if not path.exists():
        return {"schema_version": 1, "instructions": {}, "routes": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or set(value) - {"schema_version", "instructions", "routes"}:
        raise ValueError("Unsupported policy schema or unknown setting")
    instructions, routes = value.get("instructions", {}), value.get("routes", [])
    if (not isinstance(instructions, dict) or set(instructions) - MODULES
            or not all(isinstance(v, str) and len(v) <= 32000 for v in instructions.values()) or not isinstance(routes, list)):
        raise ValueError("Policy instructions must name a supported module and contain bounded text")
    return value


def resolve(root, state, project=None, *, portable=False):
    models = {m["key"]: m for m in json.loads((root / "registry/models.json").read_text(encoding="utf-8"))["models"]}
    routes = copy.deepcopy(json.loads((root / "registry/routes.json").read_text(encoding="utf-8")))
    by_key = {(r["platform"], r["task"]): r for r in routes["routes"]}
    provenance = {f"{p}/{t}": "release" for p, t in by_key}
    instructions = {name: (root / name).read_text(encoding="utf-8") for name in MODULES}
    layers = [("personal", state.parent / "overrides/policy.json")]
    if project:
        layers.append(("project", project / ".ai/policy.json"))
    hashes = {}
    for label, path in layers:
        layer = read_layer(path)
        hashes[label] = digest(json_bytes(layer))
        for name, content in layer.get("instructions", {}).items():
            # Personal prose remains in the private global library. Portable project
            # files include only project-owned additions, avoiding private-text publication.
            if content and (not project or label == "project"):
                instructions[name] += f"\n\n## {label.title()} preferences\n\n{content.rstrip()}\n"
        seen = set()
        for override in layer.get("routes", []):
            if not isinstance(override, dict) or set(override) - {"platform", "task", "preferred", "fallbacks"}:
                raise ValueError("Invalid policy route fields")
            identity = (override.get("platform"), override.get("task"))
            if identity not in by_key or identity in seen:
                raise ValueError("Unknown or duplicate policy route")
            seen.add(identity)
            selected = {k: override[k] for k in ("preferred", "fallbacks") if k in override}
            candidate = {**by_key[identity], **selected}
            if not isinstance(candidate["fallbacks"], list) or not isinstance(candidate["preferred"], str):
                raise ValueError("Invalid route preference types")
            for key in [candidate["preferred"], *candidate["fallbacks"]]:
                if not isinstance(key, str) or key not in models or models[key]["surface"] != identity[0]:
                    raise ValueError("Policy route references an unknown or different-platform model")
            # Private route choices are used in private resolution, not copied into a
            # project's published bundle. Project overrides are safe to render there.
            if not (portable and project and label == "personal"):
                by_key[identity].update(selected)
                provenance['/'.join(identity)] = label
    return {"routes": routes, "instructions": instructions, "provenance": provenance,
            "layer_hashes": hashes, "effective_sha256": digest(json_bytes({"routes": routes, "instructions": instructions}))}
