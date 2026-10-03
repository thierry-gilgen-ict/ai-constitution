"""Optional thin desktop controls; the existing local dashboard remains the UI."""
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import webbrowser
from .launcher import command
from .storage import load, atomic
from .transport import request

LABEL = 'org.ai-constitution.local-control'


def startup(root, enabled, *, home=None, system=None, address=None, port=8767):
    home = Path(home or Path.home())
    system = system or platform.system()
    label = LABEL + ('-worker' if address else '')
    if address:
        import ipaddress
        ip = ipaddress.ip_address(address)
        if ip.version != 4 or not ip.is_private or ip.is_unspecified or not 1 <= port <= 65535: raise ValueError('Choose a private IPv4 address and valid port')
    args = command('--state-dir', root, 'node', '--address', address, '--port', port) if address else command('--state-dir', root, 'start')
    if system == 'Windows':
        # Per-user registration. REG_SZ is a CreateProcess argument string, not a shell script.
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            if enabled:
                winreg.SetValueEx(key, label, 0, winreg.REG_SZ, subprocess.list2cmdline(args))
            else:
                try: winreg.DeleteValue(key, label)
                except FileNotFoundError: pass
        target = 'Current-user login startup entry'
    elif system == 'Darwin':
        path = home / 'Library/LaunchAgents' / (label + '.plist')
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError('Autostart must not traverse symbolic links')
        if path.exists():
            existing = plistlib.loads(path.read_bytes())
            if existing.get('Label') != label or existing.get('ProgramArguments') != args:
                raise ValueError('An existing startup entry belongs to another installation; preserve it and disable it there first')
        path.parent.mkdir(parents=True, exist_ok=True)
        if enabled:
            path.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':args,'RunAtLoad':True}))
        else:
            path.unlink(missing_ok=True)
        target = str(path)
    else:
        raise ValueError('Desktop autostart is available on Windows and macOS; use the foreground CLI elsewhere')
    atomic(root / 'desktop.json', {'schema':1, 'autostart':enabled, 'role':'worker' if address else 'controller', 'address':address, 'port':port})
    return {'autostart':enabled,'target':target,'applies':'next login; the current service is unchanged'}


def tray(root):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        raise ValueError('Tray controls need the optional requirements-desktop.txt dependencies') from None
    config = load(root)
    runtime = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    endpoint = {'url':runtime['url'],'kind':'ollama','token':config['token']}
    image = Image.new('RGB',(64,64),'#edf0e5')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10,8,54,56),radius=11,fill='#526c45')
    draw.line((24,44,32,18,40,44),fill='#edf0e5',width=4)
    draw.line((27,35,37,35),fill='#edf0e5',width=3)
    def open_dashboard(*_):
        webbrowser.open(runtime['url'] + '/#' + config['token'])
    def mode(name):
        def run(icon, _):
            try:
                request(endpoint,'/api/action',{'action':'mode','mode':name},timeout=5)
                icon.title = 'Local Control · switching to ' + name
            except (ValueError,OSError):
                icon.title = 'Local Control · open dashboard for status'
                open_dashboard()
        return run
    icon = pystray.Icon('ai-constitution',image,'AI Constitution · Local Control',menu=pystray.Menu(
        pystray.MenuItem('Open dashboard',open_dashboard,default=True),
        pystray.MenuItem('Work mode',mode('work')),
        pystray.MenuItem('Free this GPU',mode('gaming')),
        pystray.MenuItem('Quit tray (service stays running)',lambda icon,_:icon.stop())))
    icon.run()
