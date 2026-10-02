"""Bounded JSON requests and streaming connections; no proxies or redirects."""
import hashlib
import http.client
import ipaddress
import json
import ssl
from urllib.parse import urlsplit

MAX_JSON = 16 * 1024 * 1024


def validate_url(url, *, worker=False):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Use an endpoint origin without credentials, path, query or fragment")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        raise ValueError("Use an explicit IP address (127.0.0.1 for this computer)") from None
    if address.is_unspecified or address.is_multicast:
        raise ValueError("Use the machine's reachable IP address")
    if parsed.scheme not in ("http", "https") or (not address.is_loopback and (not worker or parsed.scheme != "https")):
        raise ValueError("Remote machines require a paired HTTPS Local Control node")
    if not parsed.port or not 1 <= parsed.port <= 65535:
        raise ValueError("An explicit valid port is required")
    return parsed


def connect(node, path, payload=None, *, timeout=180, method=None):
    parsed = validate_url(node["url"], worker=node.get("kind") == "worker")
    pin = node.get("fingerprint")
    if parsed.scheme == "https":
        context = ssl._create_unverified_context() if pin else ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=timeout, context=context)
    else:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    try:
        conn.connect()
        if pin:
            actual = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
            if actual != pin:
                raise ValueError("Machine certificate changed; pairing must be reviewed")
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json", "Connection": "close"}
        token = node.get("inference_token", node.get("token")) if path.startswith('/v1/') else node.get('token')
        if token:
            headers["Authorization"] = "Bearer " + token
        prefix = "/node" if node.get("kind") == "worker" else ""
        conn.request(method or ("POST" if body is not None else "GET"), prefix + path, body, headers)
        response = conn.getresponse()
        if response.status >= 300:
            # Do not surface server bodies: they can echo prompts, tokens or private paths.
            raise ValueError(f"Selected machine returned HTTP {response.status}")
        return conn, response
    except Exception:
        conn.close()
        raise


def request(node, path, payload=None, *, timeout=180, method=None):
    conn, response = connect(node, path, payload, timeout=timeout, method=method)
    try:
        data = response.read(MAX_JSON + 1)
        if len(data) > MAX_JSON:
            raise ValueError("Response exceeds metadata size limit")
        value = json.loads(data)
        if isinstance(value, dict) and value.get("error"):
            raise ValueError("Ollama rejected the operation; check model and runtime compatibility")
        return value
    finally:
        conn.close()
