"""Source and packaged entry points, using argument lists instead of shell strings."""
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys


def command(*args):
    prefix = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/local_control.py')]
    return [*prefix, *map(str, args)]


def open_project(root, project, client):
    project = Path(project).resolve(strict=True)
    if not project.is_dir() or client not in ('codex', 'cursor'):
        raise ValueError('Choose an existing project directory and supported client')
    args = command('--state-dir', root, client, '--project', project)
    if client == 'cursor':
        subprocess.Popen(args, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    elif os.name == 'nt':
        terminal = shutil.which('wt.exe')
        if terminal:
            subprocess.Popen([terminal, 'new-tab', '--startingDirectory', str(project), *args])
        else:
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif platform.system() == 'Darwin':
        target = root / 'launch-local-codex.command'
        target.write_text('#!/bin/sh\nexec ' + shlex.join(args) + '\n', encoding='utf-8')
        target.chmod(0o700)
        subprocess.Popen(['open', '-a', 'Terminal', str(target)])
    else:
        terminal = shutil.which('x-terminal-emulator')
        if not terminal:
            raise ValueError('Install a terminal launcher or run the displayed Codex command in your terminal')
        subprocess.Popen([terminal, '-e', *args])
    return {'status': 'launched', 'client': client, 'note': 'Client process launched; a successful model request verifies the integration'}
