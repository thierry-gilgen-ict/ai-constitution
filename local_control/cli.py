#!/usr/bin/env python3
"""Local Control: a private dashboard and stable Ollama gateway for coding sessions."""
import argparse
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import webbrowser
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_control import VERSION, hardware
from local_control.core import Control, ALIAS
from local_control.server import Server
from local_control.setup import certificate, install_fit, install_ollama, cpu_runtime
from local_control.storage import ProcessLock, atomic, load, private_root
from local_control.transport import request
from local_control import processes, locations, distribution, monitoring, project_vault
from local_control.launcher import command


def codex_args(url, catalog, context=65536):
    return ["-c", 'model_provider="constitution-local"', "-c", 'model="' + ALIAS + '"',
            "-c", 'model_providers.constitution-local.name="Local Control"',
            "-c", 'model_providers.constitution-local.base_url=' + json.dumps(url + "/v1"),
            "-c", 'model_providers.constitution-local.wire_api="responses"',
            "-c", 'model_providers.constitution-local.env_key="AI_CONSTITUTION_GATEWAY_TOKEN"',
            "-c", 'model_providers.constitution-local.supports_websockets=false',
            "-c", 'model_context_window=' + str(context), "-c", 'model_auto_compact_token_limit=' + str(context * 3 // 4),
            "-c", 'web_search="disabled"', "-c", 'model_reasoning_effort="low"',
            "-c", 'features.plugins=false', "-c", 'features.apps=false', "-c", 'features.multi_agent=false',
            "-c", 'features.remote_plugin=false',
            "-c", 'model_catalog_json=' + json.dumps(str(catalog))]


def launch_codex(root, url, project, extra):
    config = load(root)
    endpoint = {"url": url, "token": config["token"], "kind": "ollama"}
    status = request(endpoint, "/api/status", timeout=5)
    if not status.get("primary"):
        raise ValueError("Configure a primary model in Local Control first")
    context = status['context']
    # Resolve npm's native binary on Windows, avoiding shell interpretation of paths/prompts.
    executable = shutil.which("codex.exe") or shutil.which("codex")
    if os.name == "nt" and (not executable or Path(executable).suffix.lower() in (".cmd", ".ps1", ".bat")):
        npm_root = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@openai"
        binaries = list(npm_root.glob("**/codex.exe"))
        executable = str(binaries[0]) if binaries else None
    if not executable:
        raise ValueError("Install Codex CLI first: https://learn.chatgpt.com/docs/developer-commands")
    client_home = root / "clients/codex"
    client_home.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, AI_CONSTITUTION_GATEWAY_TOKEN=config["gateway_token"])
    result = subprocess.run([executable, "debug", "models", "--bundled"], env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise ValueError("This launcher needs Codex CLI with debug models --bundled; update Codex first")
    bundled = json.loads(result.stdout)["models"]
    template = next((m for m in bundled if m["slug"] == "gpt-5.2"), bundled[-1]).copy()
    template.update(slug=ALIAS, display_name="Local Control", description="Private Ollama coding route", upgrade=None,
                    base_instructions="You are a local coding assistant. Follow AGENTS.md and the user's request. Inspect relevant files, make focused changes, use tools when needed, and verify your work. State uncertainty honestly. Keep communication concise.",
                    model_messages=None, context_window=context, max_context_window=context, default_reasoning_level="low",
                    supported_reasoning_levels=[{"effort": "low", "description": "Local coding"}],
                    input_modalities=["text"], support_verbosity=False, default_reasoning_summary="none",
                    apply_patch_tool_type=None, supports_search_tool=False, supports_experimental_context=False,
                    use_responses_lite=False, node_repl_disabled=True, experimental_supported_tools=[],
                    additional_speed_tiers=[], service_tiers=[])
    template.pop("tool_mode", None)
    template.pop("multi_agent_version", None)
    catalog_path = client_home / "local-models.json"
    atomic(catalog_path, {"models": [template, *[{**m, "visibility": "hide"} for m in bundled]]})
    args = extra[1:] if extra[:1] == ["--"] else extra
    session_id = uuid.uuid4().hex
    process = processes.identity(os.getpid())
    if not process:
        raise ValueError('Cannot establish launcher identity for safe service maintenance')
    request(endpoint, '/api/session', {'action': 'open', 'id': session_id, 'process': process})
    child = None
    try:
        child = subprocess.Popen([executable, *codex_args(url, catalog_path, context), *args], cwd=project, env=environment)
        child_identity = processes.identity(child.pid)
        if child_identity:
            request(endpoint, '/api/session', {'action': 'open', 'id': session_id, 'process': child_identity})
        return child.wait()
    finally:
        if child is None or child.poll() is not None:
            try:
                request(endpoint, '/api/session', {'action': 'close', 'id': session_id}, timeout=3)
            except (OSError, ValueError):
                pass  # A stopped process is classified stale after service recovery.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=private_root())
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="Install explicitly selected components")
    setup.add_argument("--llmfit", action="store_true")
    setup.add_argument("--ollama", action="store_true")
    setup.add_argument("--upgrade-ollama", action="store_true")
    sub.add_parser("doctor")
    sub.add_parser("refresh", help="Refresh llmfit's model definitions from Hugging Face without downloading weights")
    serve = sub.add_parser("serve", help="Run the loopback dashboard and inference gateway")
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--open", action="store_true")
    sub.add_parser("open", help="Open the existing dashboard using a private login link")
    sub.add_parser('status', help='Show route, sessions and durable operation status')
    packages = sub.add_parser('packages', help='Register reviewed worker packages for dashboard downloads')
    packages.add_argument('action', choices=['add','list','source'])
    packages.add_argument('--file', type=Path)
    monitor = sub.add_parser('monitor', help='Control this OS user’s read-only account collector and worker sharing')
    monitor.add_argument('action', choices=['enable','disable','refresh'])
    monitor.add_argument('--share', action='store_true', help='Share account identifiers and usage with paired controllers')
    relocate = sub.add_parser('relocate', help='Copy private controller state after stopping it, preserving old launch commands')
    relocate.add_argument('--destination', type=Path, required=True)
    relocate.add_argument('--plan', help='Apply the fingerprint returned by a fresh stopped-service preview')
    backup = sub.add_parser('backup', help='Back up explicitly registered project configuration folders')
    backup.add_argument('--plan', help='Apply the fingerprint returned by the backup preview')
    start = sub.add_parser('start', help='Start a hidden, per-user controller if none owns its state')
    start.add_argument('--port', type=int, default=8766)
    start.add_argument('--open', action='store_true')
    stop = sub.add_parser('stop', help='Stop only after tracked sessions and responses have finished')
    stop.add_argument('--acknowledge-external-clients', action='store_true')
    sub.add_parser('tray', help='Show optional Windows tray/macOS menu-bar controls for the running service')
    startup = sub.add_parser('autostart', help='Opt in or out of per-user login startup')
    startup.add_argument('action', choices=['enable','disable'])
    node = sub.add_parser("node", help="Run a paired HTTPS worker on an explicit private-network address")
    node.add_argument("--address", required=True)
    node.add_argument("--port", type=int, default=8767)
    pair = sub.add_parser("pairing", help="Print this worker's private pairing record; never commit it")
    pair.add_argument("--address", required=True)
    pair.add_argument("--port", type=int, default=8767)
    controllers = sub.add_parser('controllers', help='List or revoke a worker controller from this machine')
    controllers.add_argument('--address', required=True)
    controllers.add_argument('--port', type=int, default=8767)
    controllers.add_argument('--revoke')
    controllers.add_argument('--disable-legacy', action='store_true')
    codex = sub.add_parser("codex", help="Start a Codex local session, also usable in Cursor's terminal")
    codex.add_argument("--project", type=Path, default=Path.cwd())
    codex.add_argument("args", nargs=argparse.REMAINDER)
    cursor = sub.add_parser("cursor", help="Open a project workspace with a Local Codex terminal task")
    cursor.add_argument("--project", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] or ['start', '--open'])
    root = locations.resolve_root(args.state_dir)
    if args.command == 'relocate':
        result = locations.relocate(root, args.destination, args.plan) if args.plan else locations.relocation_plan(root, args.destination)[0]
        print(json.dumps(result, indent=2)); return 0
    if args.command == 'packages':
        if args.action == 'add' and args.file is None: raise ValueError('Use --file with a reviewed portable ZIP')
        result = distribution.register(root, args.file) if args.action == 'add' else distribution.source_bundle(root) if args.action == 'source' else distribution.catalog(root)
        print(json.dumps(result, indent=2)); return 0
    if args.command == 'monitor':
        result = monitoring.collect(root) if args.action == 'refresh' else monitoring.configure(root, {
            'codex_enabled': args.action == 'enable', 'share_with_controllers': args.action == 'enable' and args.share})
        print(json.dumps({'status':'refreshed'} if args.action == 'refresh' else result)); return 0
    if args.command == 'backup':
        print(json.dumps(project_vault.backup(root, args.plan) if args.plan else project_vault.plan(root), indent=2)); return 0
    if args.command == "setup":
        results = {}
        if args.upgrade_ollama and (root / 'runtime.json').exists():
            running = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
            state = load(root)
            target = {'url': running['url'], 'kind': 'ollama', 'token': state['token']}
            try:
                request(target, '/api/status', timeout=3)
            except OSError:
                raise ValueError('Verify and stop existing local sessions before upgrading; start Local Control to use its maintenance workflow') from None
            print(json.dumps(request(target, '/api/action', {'action': 'upgrade-runtime'}), indent=2))
            return 0
        if args.ollama or args.upgrade_ollama:
            results.update(install_ollama(args.upgrade_ollama))
        if args.llmfit:
            results.update(install_fit(root))
        print(json.dumps(results or {"next": "Select --ollama and/or --llmfit"}, indent=2))
        return 0
    config = load(root)
    if args.command == "refresh":
        print(json.dumps(hardware.refresh_models(root), indent=2))
        return 0
    runtime_path = root / "runtime.json"
    runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {"url": "http://127.0.0.1:8766"}
    endpoint = {'url': runtime['url'], 'kind': 'ollama', 'token': config['token']}
    if args.command == 'tray':
        from local_control.desktop import tray
        tray(root)
        return 0
    if args.command == 'autostart':
        from local_control.desktop import startup
        print(json.dumps(startup(root, args.action == 'enable'), indent=2))
        return 0
    if args.command == 'status':
        print(json.dumps(request(endpoint, '/api/status', timeout=5), indent=2))
        return 0
    if args.command == 'stop':
        print(json.dumps(request(endpoint, '/api/stop', {'acknowledge_external': args.acknowledge_external_clients}), indent=2))
        return 0
    if args.command == 'start':
        import time
        try:
            request(endpoint, '/api/status', timeout=2)
        except (OSError, ValueError):
            with open(root / 'server.log', 'ab') as log:
                child = subprocess.Popen(command('--state-dir', root, 'serve', '--port', args.port),
                                         stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                         start_new_session=os.name != 'nt')
            endpoint['url'] = f'http://127.0.0.1:{args.port}'
            for _ in range(40):
                if child.poll() is not None:
                    raise ValueError('Controller could not start; check its private log')
                try:
                    request(endpoint, '/api/status', timeout=1)
                    break
                except (OSError, ValueError):
                    time.sleep(.25)
            else:
                raise ValueError('Controller startup not confirmed; inspect status before retrying')
        if args.open:
            webbrowser.open(endpoint['url'] + '/#' + config['token'])
        print('Local Control is running at ' + endpoint['url'])
        return 0
    if args.command == "doctor":
        result = {"version": VERSION, "python": sys.version.split()[0], "llmfit": bool(hardware.fit_executable(root)),
                  "codex": bool(shutil.which("codex")), "cursor": bool(shutil.which("cursor"))}
        try:
            result["ollama"] = request(config["nodes"]["local"], "/api/version", timeout=5)["version"]
            result["models"] = [m["name"] for m in request(config["nodes"]["local"], "/api/tags")["models"]]
        except Exception:
            result["ollama"] = "offline — start the Ollama app or run ollama serve"
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "open":
        webbrowser.open(runtime["url"] + "/#" + config["token"])
        return 0
    if args.command == "codex":
        if os.name == 'nt' and getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 5)
        return launch_codex(root, runtime["url"], args.project.resolve(strict=True), args.args)
    if args.command == "cursor":
        project = args.project.resolve(strict=True)
        import hashlib
        output = root / "workspaces" / (hashlib.sha256(str(project).encode()).hexdigest()[:12] + ".code-workspace")
        atomic(output, {"folders": [{"path": str(project)}], "tasks": {"version": "2.0.0", "tasks": [{
            "label": "AI Constitution: Local Codex", "type": "process", "command": command()[0],
            "args": command('--state-dir', root, 'codex', '--project', project)[1:],
            "problemMatcher": [], "presentation": {"reveal": "always", "focus": True, "panel": "dedicated"}}]}})
        if os.name == "nt":
            binary = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/cursor/Cursor.exe"
            if not binary.exists():
                raise ValueError("Open the generated .code-workspace file in Cursor; executable was not found")
            subprocess.Popen([str(binary), "--new-window", str(output)])
        elif shutil.which("cursor"):
            subprocess.Popen([shutil.which("cursor"), "--new-window", str(output)])
        else:
            raise ValueError("Enable Cursor's command-line launcher, then rerun this command")
        print("Opened Cursor workspace. Run task: AI Constitution: Local Codex. Native Cursor Agent is unchanged.")
        return 0
    if args.command in ("node", "pairing", 'controllers'):
        import ipaddress
        address = ipaddress.ip_address(args.address)
        if not address.is_private or address.is_unspecified or address.version != 4:
            raise ValueError("Choose an explicit private IPv4 address on this computer")
        cert, key, fingerprint = certificate(root, args.address)
        url = f"https://{args.address}:{args.port}"
        if args.command == "pairing":
            endpoint = {'url': url, 'kind': 'worker', 'token': config['token'], 'fingerprint': fingerprint}
            code = request(endpoint, '/admin/pairing', {}, timeout=5)
            print(json.dumps({'url': url, 'fingerprint': fingerprint, **code}))
            return 0
        if args.command == 'controllers':
            endpoint = {'url': url, 'kind': 'worker', 'token': config['token'], 'fingerprint': fingerprint}
            if args.revoke or args.disable_legacy:
                result = request(endpoint, '/admin/credentials', {'action': 'revoke' if args.revoke else 'disable-legacy', 'id': args.revoke})
            else:
                result = request(endpoint, '/admin/controllers')
            print(json.dumps(result, indent=2))
            return 0
        address = (args.address, args.port)
    else:
        address, url = ("127.0.0.1", args.port), f"http://127.0.0.1:{args.port}"
    ownership = ProcessLock(root / "server.lock")
    control = Control(root)
    if "local-cpu" in control.config["nodes"]:
        cpu_runtime(root)
    server = Server(address, control, worker=args.command == "node", advertised=url)
    if args.command == "node":
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    else:
        atomic(runtime_path, {"url": url, "pid": os.getpid(), 'process': processes.identity(os.getpid())})
        from .services import Services
        server.services = Services(control)
        server.services.start()
        if args.open:
            webbrowser.open(url + "/#" + config["token"])
    print("Local Control listening at " + url + ". Use the open command for authenticated dashboard access.", flush=True)
    try:
        while True:
            try:
                server.serve_forever()
                break
            except KeyboardInterrupt:
                try:
                    control.stop_ready(True)
                    break
                except ValueError as error:
                    print(str(error) + '. Service continues; use Gaming mode to free the GPU.', flush=True)
    finally:
        if getattr(server, 'services', None): server.services.close()
        server.server_close()
        control.pool.shutdown(wait=False, cancel_futures=True)
        ownership.close()
    return 0


def entry():
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print("Error: " + (str(error) if isinstance(error, ValueError) else type(error).__name__ + "; check setup and service availability"), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    entry()
