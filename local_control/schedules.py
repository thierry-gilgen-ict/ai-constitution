"""Explicit per-user backup scheduling; controller uptime is not required."""
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import tempfile
from xml.sax.saxutils import escape
from scripts.catalog import digest
from scripts.paths import no_links
from .launcher import command
from .storage import atomic
from .permissions import user_sid


def read(root):
    from scripts import constitution as kit
    path = Path(root) / 'backup-schedule.json'; no_links(path)
    return kit.read_json(path) if path.exists() else {'enabled': False, 'hours': 24, 'scope': 'No OS task configured'}


def configure(root, enabled, hours=24, *, system=None, home=None, runner=subprocess.run):
    if type(enabled) is not bool or type(hours) is not int or not 1 <= hours <= 720:
        raise ValueError('Choose an enabled state and interval from 1 to 720 hours')
    system = system or platform.system(); home = Path(home or Path.home())
    identity = 'ai-constitution-backup-' + digest(str(Path(root).absolute()).encode())[:12]
    args = command('--state-dir', root, 'backup', '--due')
    marker = 'AI Constitution managed backup ' + identity
    if system == 'Windows':
        name = '\\' + identity
        existing = runner(['schtasks', '/Query', '/TN', name, '/XML'], capture_output=True, text=True)
        if existing.returncode == 0 and marker not in existing.stdout:
            raise ValueError('An unrelated scheduled task uses this name; preserve it before continuing')
        if enabled:
            xml = ('<?xml version="1.0" encoding="UTF-16"?><Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
                '<RegistrationInfo><Description>' + marker + '</Description></RegistrationInfo>'
                '<Triggers><TimeTrigger><Repetition><Interval>PT' + str(hours) + 'H</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>'
                '<StartBoundary>2020-01-01T00:00:00</StartBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>'
                '<Principals><Principal id="Author"><UserId>' + user_sid() + '</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>'
                '<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>'
                '<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT2H</ExecutionTimeLimit></Settings>'
                '<Actions Context="Author"><Exec><Command>' + escape(args[0]) + '</Command><Arguments>' + escape(subprocess.list2cmdline(args[1:])) + '</Arguments></Exec></Actions></Task>')
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'task.xml'; path.write_text(xml, encoding='utf-16')
                runner(['schtasks', '/Create', '/TN', name, '/XML', str(path), '/F'], check=True, capture_output=True)
        elif existing.returncode == 0:
            runner(['schtasks', '/Delete', '/TN', name, '/F'], check=True, capture_output=True)
        scope = 'Windows Task Scheduler, current user while logged in; catches up after sleep'
    elif system == 'Darwin':
        path = home / 'Library/LaunchAgents' / (identity + '.plist'); no_links(path)
        if path.exists() and plistlib.loads(path.read_bytes()).get('Comment') != marker:
            raise ValueError('An unrelated launch agent uses this name')
        domain = 'gui/' + str(os.getuid())
        runner(['launchctl', 'bootout', domain, str(path)], capture_output=True)
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(plistlib.dumps({'Label': identity, 'Comment': marker, 'ProgramArguments': args,
                'StartInterval': hours * 3600, 'RunAtLoad': True}))
            runner(['launchctl', 'bootstrap', domain, str(path)], check=True, capture_output=True)
        else: path.unlink(missing_ok=True)
        scope = 'macOS user launch agent; available while logged in'
    elif system == 'Linux':
        base = home / '.config/systemd/user'; no_links(base)
        service, timer = base / (identity + '.service'), base / (identity + '.timer')
        for path in (service, timer):
            no_links(path)
            if path.exists() and marker not in path.read_text(): raise ValueError('An unrelated systemd unit uses this name')
        if enabled:
            base.mkdir(parents=True, exist_ok=True)
            quoted = ' '.join('"' + v.replace('\\','\\\\').replace('"','\\"').replace('%','%%').replace('$','$$') + '"' for v in args)
            service.write_text('[Unit]\nDescription=' + marker + '\n[Service]\nType=oneshot\nExecStart=' + quoted + '\n')
            timer.write_text('[Unit]\nDescription=' + marker + '\n[Timer]\nOnStartupSec=1min\nOnUnitActiveSec=' + str(hours) + 'h\n[Install]\nWantedBy=timers.target\n')
            runner(['systemctl', '--user', 'daemon-reload'], check=True, capture_output=True)
            runner(['systemctl', '--user', 'enable', '--now', identity + '.timer'], check=True, capture_output=True)
        else:
            runner(['systemctl', '--user', 'disable', '--now', identity + '.timer'], capture_output=True)
            service.unlink(missing_ok=True); timer.unlink(missing_ok=True)
            runner(['systemctl', '--user', 'daemon-reload'], check=True, capture_output=True)
        scope = 'Linux systemd user timer; user manager must be running'
    else: raise ValueError('OS backup schedules support Windows, macOS and systemd Linux')
    value = {'enabled': enabled, 'hours': hours, 'identity': identity, 'scope': scope}
    atomic(Path(root) / 'backup-schedule.json', value)
    return value
