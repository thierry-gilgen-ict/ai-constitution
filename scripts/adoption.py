"""Validate portable enrollment evidence without trusting it as publisher identity."""
import json
import re

SOURCE = "https://github.com/thierry-gilgen-ict/ai-constitution"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field in project lock")
        result[key] = value
    return result


def project_record(project, *, modules, safe_path, managed_hash, digest):
    lock_path = safe_path(project, ".ai/constitution.lock.json")
    if lock_path.stat().st_size > 65536:
        raise ValueError("Project lock exceeds the size limit")
    lock = json.loads(lock_path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if (not isinstance(lock, dict) or type(lock.get("schema_version")) is not int
            or lock["schema_version"] not in (1, 2) or lock.get("source") != SOURCE
            or not isinstance(lock.get("version"), str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", lock["version"])
            or type(lock.get("pinned")) is not bool):
        raise ValueError("Unsupported or invalid portable project lock")
    legacy = ("constitution.md", "engineering.md", "research.md", "maintenance.md", "routing.md", "VERSION")
    version = tuple(map(int, lock["version"].split(".")))
    expected_modules = legacy if version < (0, 5, 0) else modules
    if lock["schema_version"] == 2:
        if (lock.get("modules") != list(expected_modules)
                or not isinstance(lock.get("release_sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", lock["release_sha256"])):
            raise ValueError("Invalid module allowlist or instruction release identity")
    allowed = {"AGENTS.md", *(".ai/shared/" + name for name in expected_modules)}
    files = lock.get("files")
    if not isinstance(files, dict) or set(files) != allowed:
        raise ValueError("Project lock must contain exactly the allowed managed files")
    for name, expected in files.items():
        if (not isinstance(expected, dict) or set(expected) != {"sha256", "managed"}
                or type(expected["managed"]) is not bool or expected["managed"] != (name == "AGENTS.md")
                or not isinstance(expected["sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected["sha256"])):
            raise ValueError("Invalid managed-file evidence in project lock")
        path = safe_path(project, name)
        if not path.is_file():
            raise ValueError("Project bundle is incomplete; reconcile before adopting")
        actual = managed_hash(path.read_bytes()) if expected["managed"] else digest(path.read_bytes())
        if actual != expected["sha256"]:
            raise ValueError("Project bundle has local edits; reconcile before adopting")
    if safe_path(project, ".ai/shared/VERSION").read_text().strip() != lock["version"]:
        raise ValueError("Project lock and installed VERSION disagree")
    # Track the lock itself privately; a portable lock cannot hash itself.
    tracked = {**files, ".ai/constitution.lock.json": {"sha256": digest(lock_path.read_bytes()), "managed": False}}
    record = {"kind": "project", "root": str(project), "version": lock["version"],
              "pinned": lock["pinned"], "files": tracked}
    if lock["schema_version"] == 2:
        record["release_sha256"] = lock["release_sha256"]
    return record
