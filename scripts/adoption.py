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
    allowed = {"AGENTS.md", *(".ai/shared/" + name for name in modules)}
    selected = lock.get("clients", ["codex", "cursor"])
    if lock["schema_version"] == 2:
        if not isinstance(selected, list) or not selected or len(selected) != len(set(selected)) or any(c not in ("codex", "cursor", "claude-code") for c in selected):
            raise ValueError("Invalid project clients")
        bridge=lock.get('claude_bridge','managed')
        if bridge not in ('managed','existing-import'):raise ValueError('Invalid Claude bridge type')
        if "claude-code" in selected and bridge=='managed': allowed.add("CLAUDE.md")
        if bridge=='existing-import':
            if __package__:
                from .claude_audit import imports
            else:
                from claude_audit import imports
            from pathlib import Path
            if 'claude-code' not in selected or not any(Path(p)==Path('AGENTS.md') for p in imports(safe_path(project,'CLAUDE.md').read_text(encoding='utf-8'))):raise ValueError('Unowned Claude bridge import is missing')
    files = lock.get("files")
    if not isinstance(files, dict) or set(files) != allowed:
        raise ValueError("Project lock must contain exactly the allowed managed files")
    for name, expected in files.items():
        if (not isinstance(expected, dict) or set(expected) != {"sha256", "managed"}
                or type(expected["managed"]) is not bool or expected["managed"] != (name in ("AGENTS.md", "CLAUDE.md"))
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
    return {"kind": "project", "root": str(project), "version": lock["version"],
            "pinned": lock["pinned"], "files": tracked, **({"clients": selected,'claude_bridge':lock.get('claude_bridge','managed')} if lock["schema_version"] == 2 else {})}
