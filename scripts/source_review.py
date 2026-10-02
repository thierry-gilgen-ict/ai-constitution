"""Observed source revisions stay pending until a specific revision is reviewed."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
from catalog import atomic_bytes, digest, fetch_public, json_bytes, utc_now


def read(state):
    path = state / "source-observations.json"
    return json.loads(path.read_text(encoding="utf-8")).get("sources", {}) if path.exists() else {}


def check(root, state, lock):
    sources = json.loads((root / "registry/sources.json").read_text(encoding="utf-8"))["sources"]
    def observe(source):
        try:
            return source, {"sha256": digest(fetch_public(source["url"])), "checked_at": utc_now()}
        except Exception as error:
            return source, {"error_type": type(error).__name__, "attempted_at": utc_now()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        observations = list(pool.map(observe, sources))
    with lock(state):
        results = read(state)
        for source, observed in observations:
            old = results.get(source["id"], {})
            # Legacy observations were not explicit acknowledgments.
            reviewed = old.get("reviewed") if old.get("url") == source["url"] else None
            current = old.get("observed") if old.get("url") == source["url"] else None
            if "sha256" in observed:
                current = observed
            pending = bool(current and (not reviewed or reviewed["sha256"] != current["sha256"]))
            results[source["id"]] = {"url": source["url"], "observed": current, "reviewed": reviewed,
                                     "pending": pending,
                                     "status": "unavailable" if "error_type" in observed else "pending-review" if pending else "reviewed"}
            if "error_type" in observed:
                results[source["id"]].update(observed)
        atomic_bytes(state / "source-observations.json", json_bytes({"schema_version": 2, "sources": results}))
    return results


def acknowledge(state, identity, revision, lock):
    if not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise ValueError("Review needs the exact observed SHA-256 revision")
    with lock(state):
        results = read(state)
        record = results.get(identity)
        if not record or not record.get("observed") or record["observed"]["sha256"] != revision:
            raise ValueError("Source revision changed or was never observed; inspect the current pending revision")
        record["reviewed"] = {"sha256": revision, "reviewed_at": utc_now()}
        record["pending"] = False
        record["status"] = "reviewed" if record["status"] != "unavailable" else "unavailable"
        atomic_bytes(state / "source-observations.json", json_bytes({"schema_version": 2, "sources": results}))
        return record
