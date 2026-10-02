"""Explicit runtime installation and pinned hardware-helper downloads."""
import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

FIT_VERSION = "1.1.16"
FIT_ASSETS = {
    ("Windows", "x86_64"): ("x86_64-pc-windows-msvc.zip", "bd95bc78e65a15f4d7b62431c082e0d55c9505739f63f6fdf6f9d69605c270ba"),
    ("Windows", "arm64"): ("aarch64-pc-windows-msvc.zip", "eea24b1c7ae94add6b63f31c5e3ae1d9ee76a869e735d3c7ad6b15c615b13973"),
    ("Darwin", "arm64"): ("aarch64-apple-darwin.tar.gz", "e5a558de2af332aa2a75547086c8983fc2f43c7c9a966fcc20d9ce4108ec6886"),
    ("Darwin", "x86_64"): ("x86_64-apple-darwin.tar.gz", "1face5fa683c84b65ecde3c9ba7cb8eb895ec31f0819a3d29861e33312467627"),
    ("Linux", "x86_64"): ("x86_64-unknown-linux-gnu.tar.gz", "27fad93d5e579156e4d87609e1bdef51675342cef3da111ef0f58e1ec10be7f1"),
    ("Linux", "arm64"): ("aarch64-unknown-linux-gnu.tar.gz", "87d1fd489cd90d4e28e4421bd9a9411d89d4f1ee2526216db0207df4ba7152ff"),
}


def install_fit(root):
    architecture = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    key = (platform.system(), architecture)
    if key not in FIT_ASSETS:
        raise ValueError("No verified llmfit binary for this platform; install it from the official project")
    asset, expected = FIT_ASSETS[key]
    executable = "llmfit.exe" if platform.system() == "Windows" else "llmfit"
    destination = root / "tools/llmfit" / FIT_VERSION / executable
    # Re-extract from a freshly verified release rather than trusting a replaced executable.
    url = f"https://github.com/AlexsJones/llmfit/releases/download/v{FIT_VERSION}/llmfit-v{FIT_VERSION}-{asset}"
    with urllib.request.urlopen(url, timeout=60) as response:
        if not response.url.startswith("https://"):
            raise ValueError("Refused an insecure download redirect")
        data = response.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("llmfit archive checksum did not match the reviewed release")
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = next(n for n in archive.namelist() if Path(n).name == executable)
            binary = archive.read(member)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = next(m for m in archive.getmembers() if Path(m.name).name == executable and m.isfile())
            binary = archive.extractfile(member).read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(binary)
    if os.name != "nt":
        temporary.chmod(0o755)
    os.replace(temporary, destination)
    return {"llmfit": FIT_VERSION, "sha256": expected}


def ollama_command(upgrade=False):
    if platform.system() == "Windows" and shutil.which("winget"):
        return ["winget", "upgrade" if upgrade else "install", "--id", "Ollama.Ollama", "--exact", "--source", "winget"]
    if platform.system() == "Darwin" and shutil.which("brew"):
        if upgrade and subprocess.run(["brew", "list", "--formula", "ollama"], capture_output=True).returncode == 0:
            return ["brew", "upgrade", "ollama"]
        return ["brew", "upgrade" if upgrade else "install", "--cask", "ollama-app"]
    raise ValueError("Install Ollama from https://ollama.com/download, then rerun doctor. macOS package automation requires Homebrew.")


def install_ollama(upgrade=False):
    if shutil.which("ollama") and not upgrade:
        return {"ollama": "already installed"}
    subprocess.run(ollama_command(upgrade), check=True)
    return {"ollama": "updated" if upgrade else "installed", "next": "Start the Ollama application, then run doctor"}


def cpu_runtime(root, source_model=None):
    """Separate processes prevent Ollama sharing CPU/GPU runners for identical weights."""
    import time
    import json
    import re
    from .storage import atomic
    from .processes import identity, matches
    from .transport import request
    endpoint = {"kind": "ollama", "url": "http://127.0.0.1:11435", "name": "This computer · CPU fallback"}
    marker = root / "cpu-runtime.json"
    try:
        request(endpoint, "/api/version", timeout=2)
        if not marker.exists():
            raise ValueError("Port 11435 is already occupied by an unmanaged service")
        existing = json.loads(marker.read_text(encoding='utf-8'))
        if 'process' not in existing:
            return {**endpoint, 'ownership': 'legacy-unverified; reuse only, never terminate by PID'}
        if not matches(existing):
            raise ValueError('CPU process identity changed; inspect the existing service before adopting it')
        return endpoint
    except OSError:
        pass
    binary = shutil.which("ollama")
    if not binary:
        raise ValueError("Install Ollama and reopen your terminal first")
    model_store = None
    if source_model:
        info = request({"url": "http://127.0.0.1:11434", "kind": "ollama"}, "/api/show", {"model": source_model})
        for line in info.get("modelfile", "").splitlines():
            if line.startswith("FROM "):
                blob = Path(line[5:].strip().strip('"'))
                if blob.is_absolute() and re.fullmatch(r"sha256-[a-f0-9]{64}", blob.name) and blob.parent.name == "blobs" and blob.is_file():
                    model_store = str(blob.parent.parent)
    elif marker.exists():
        model_store = json.loads(marker.read_text()).get("model_store")
    if not model_store:
        raise ValueError("Could not locate the installed model's Ollama store; select an installed local model first")
    environment = dict(os.environ, OLLAMA_HOST="127.0.0.1:11435", OLLAMA_NUM_PARALLEL="1", OLLAMA_MODELS=model_store,
                       OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_CONTEXT_LENGTH="65536", OLLAMA_NO_CLOUD="1",
                       CUDA_VISIBLE_DEVICES="-1", ROCR_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1")
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "cpu-runtime.log", "ab") as log:
        child = subprocess.Popen([binary, "serve"], env=environment, stdout=log, stderr=log,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(40):
        if child.poll() is not None:
            raise ValueError("CPU Ollama process exited; inspect its private runtime log")
        try:
            request(endpoint, "/api/version", timeout=1)
            process = identity(child.pid)
            if not process:
                child.terminate()
                raise ValueError('CPU process identity could not be verified')
            atomic(marker, {"pid": child.pid, 'process': process, "url": endpoint["url"], "model_store": model_store})
            return endpoint
        except OSError:
            time.sleep(.25)
    child.terminate()
    raise ValueError("CPU runtime did not start within 10 seconds")


def certificate(root, address):
    """Self-signed node certificate, authenticated by out-of-band SHA-256 pinning."""
    import datetime
    import ipaddress
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        raise ValueError("Remote worker TLS needs the optional dependency: python -m pip install -r requirements-local-node.txt") from None
    ipaddress.ip_address(address)
    cert_path, key_path = root / "node-cert.pem", root / "node-key.pem"
    root.mkdir(parents=True, exist_ok=True)
    if not cert_path.exists() and not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AI Constitution private node")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
                .not_valid_after(now + datetime.timedelta(days=365))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]), critical=False)
                .sign(key, hashes.SHA256()))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        if os.name != "nt":
            key_path.chmod(0o600)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex()
