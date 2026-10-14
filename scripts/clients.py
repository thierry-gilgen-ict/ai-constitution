"""Client capabilities shared by installers, scanners and companion surfaces."""
import copy
import os
from pathlib import Path
import re
import shutil
import subprocess
import platform

CLIENTS = {
    'codex': {'name': 'Codex', 'directory': '.codex', 'executable': 'codex', 'adapter': 'adapters/codex/AGENTS.md'},
    'cursor': {'name': 'Cursor', 'directory': '.cursor', 'executable': 'cursor', 'adapter': 'adapters/cursor/ai-constitution.mdc'},
    'claude-code': {'name': 'Claude Code', 'directory': '.claude', 'executable': 'claude', 'adapter': 'adapters/claude-code/CLAUDE.md'},
}
LEGACY = ('codex', 'cursor')


def claude_managed_directory():
    if platform.system()=='Windows':return Path(os.environ.get('ProgramFiles','C:/Program Files'))/'ClaudeCode'
    if platform.system()=='Darwin':return Path('/Library/Application Support/ClaudeCode')
    return Path('/etc/claude-code')


def directory(client, home=None):
    base = Path(home or Path.home())
    if client == 'claude-code' and home is None:
        return Path(os.environ.get('CLAUDE_CONFIG_DIR', str(base / '.claude'))).expanduser().absolute()
    return base / CLIENTS[client]['directory']


def capabilities():
    return {key: {**copy.deepcopy(value), 'audit': True, 'mcp': True,
                  'local_api': 'messages' if key == 'claude-code' else 'responses' if key == 'codex' else None}
            for key, value in CLIENTS.items()}


def version_tuple(value):
    match = re.search(r'\b(\d+)\.(\d+)\.(\d+)\b', value or '')
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def probe(client, runner=subprocess.run):
    executable = shutil.which(CLIENTS[client]['executable'])
    if not executable:
        return {'installed': False, 'version': None, 'status': 'not-found-on-path'}
    try:
        result = runner([executable, '--version'], capture_output=True, text=True, timeout=5)
        match = re.search(r'\b\d+\.\d+\.\d+\b', result.stdout[:4096])
        version = match.group(0) if result.returncode == 0 and match else None
        return {'installed': True, 'version': version, 'status': 'available' if version else 'unknown-version'}
    except (OSError, subprocess.TimeoutExpired):
        return {'installed': True, 'version': None, 'status': 'unavailable'}
