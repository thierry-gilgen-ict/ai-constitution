"""llmfit estimates and Hugging Face metadata, kept outside the public registry."""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.parse
import urllib.request


def fit_executable(root):
    def version(path):
        import re
        parts = next((p for p in path.parts if re.fullmatch(r"\d+\.\d+\.\d+", p)), "0.0.0")
        return tuple(int(n) for n in parts.split("."))
    candidates = sorted((root / "tools/llmfit").glob("**/llmfit.exe" if platform.system() == "Windows" else "**/llmfit"), key=version)
    return str(candidates[-1]) if candidates else shutil.which("llmfit")


def run_fit(root, args):
    executable = fit_executable(root)
    if not executable:
        raise ValueError("Install the hardware helper: python scripts/local_control.py setup --llmfit")
    result = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", timeout=90,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ValueError("llmfit could not complete this query; check its installed version with doctor")
    return json.loads(result.stdout)


def recommendations(root, context=65536):
    hardware = run_fit(root, ["--json", "system"])
    actual = hardware.get("system", hardware)
    memory = actual.get("gpu_vram_gb", 0)
    args = ["--max-context", str(context)]
    if memory:
        args += ["--memory", f"{memory * 0.85:.1f}G"]
    args += ["recommend", "--json", "--runtime", "llamacpp", "--capability", "tool_use", "--use-case", "coding", "--min-fit", "good", "--limit", "200"]
    result = run_fit(root, args)
    models = []
    for model in result.get("models", []):
        if model.get("effective_context_length", 0) < context:
            continue
        if not (model.get("ollama_name") or model.get("gguf_sources") or "gguf" in model["name"].lower()):
            continue
        # A llama.cpp estimate is not an Ollama format/architecture certification.
        model["hugging_face_url"] = "https://huggingface.co/" + model["name"]
        model["download_verified"] = False
        models.append(model)
    from .insights import profiles
    return {"measured_profiles": profiles(root), "system": actual, "models": models[:12], "context": context, "headroom_percent": 15,
            "note": "Predictions, not benchmarks. Verify a GGUF file, license and Ollama tool support before adopting a model."}


def context_advice(system):
    """A conservative starting point, never a guarantee that a particular model fits."""
    memory = system.get('gpu_vram_gb') or system.get('total_ram_gb') or 0
    suggested = 65536 if memory >= 48 else 32768 if memory >= 16 else 16384 if memory >= 8 else 8192
    return {'suggested': suggested, 'evidence': 'hardware estimate',
            'reason': 'Starting context based on reported accelerator memory, or system RAM for CPU-only hardware. Model weights and KV cache vary; verify both routes before adopting it.'}


def refresh_models(root):
    executable = fit_executable(root)
    if not executable:
        raise ValueError("Install llmfit with setup --llmfit first")
    # v1.1.16 prints human-readable update output even with --json; use its exit contract.
    result = subprocess.run([executable, "update"], capture_output=True, text=True, encoding="utf-8", timeout=180,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ValueError("Model refresh failed; the previous llmfit cache remains available")
    return {"status": "updated", "weights_downloaded": False,
            "note": "llmfit model metadata refreshed. Use llmfit update --status to inspect its platform-specific cache."}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError("Metadata redirect refused")


def hf_get(path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open("https://huggingface.co/api/" + path, timeout=20) as response:
        body = response.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise ValueError("Hugging Face metadata exceeds size limit")
    return json.loads(body)


def hf_search(query):
    if not query or len(query) > 150:
        raise ValueError("Enter a model search of 1–150 characters")
    records = hf_get("models?" + urllib.parse.urlencode({"search": query, "filter": "gguf", "limit": 12, "sort": "downloads", "direction": -1}))
    return [{"id": r["id"], "downloads": r.get("downloads", 0), "url": "https://huggingface.co/" + r["id"]} for r in records]


def hf_files(repo):
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Expected a Hugging Face owner/repository identifier")
    metadata = hf_get("models/" + repo + "?blobs=true")
    files = [{"name": f["rfilename"], "bytes": f.get("size", f.get("lfs", {}).get("size")),
              "sha256": f.get("lfs", {}).get("sha256")} for f in metadata.get("siblings", [])
             if f["rfilename"].lower().endswith(".gguf")]
    return {"id": repo, "license": metadata.get("cardData", {}).get("license", "unknown — read the model card"),
            "url": "https://huggingface.co/" + repo, "files": files, "gated": bool(metadata.get("gated")),
            "note": "GGUF files may still require a newer Ollama architecture. File size excludes context memory."}
