"""Display-driver inventory and explicit handoff to trusted OS update controls.

No driver binaries, arbitrary commands, URLs from clients, or automatic reboots.
Versions are OS observations, never inferred from a driver date or model catalog.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

VENDORS = {
    'amd': ('AMD driver support', 'https://www.amd.com/en/support/download/drivers.html'),
    'nvidia': ('NVIDIA driver support', 'https://www.nvidia.com/en-us/drivers/'),
    'intel': ('Intel driver support', 'https://www.intel.com/content/www/us/en/download-center/home.html'),
    'parsec': ('Parsec display-driver help', 'https://support.parsec.app/hc/en-us/articles/32361388811284-VDD-Troubleshooting'),
}
WINDOWS_INVENTORY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$items = @(Get-CimInstance Win32_PnPSignedDriver -Filter "DeviceClass='DISPLAY'" | ForEach-Object {
    [pscustomobject]@{ name=$_.DeviceName; vendor=$_.DriverProviderName; version=$_.DriverVersion;
        date=$(if ($_.DriverDate) {$_.DriverDate.ToString('yyyy-MM-dd')}); device=$_.DeviceID;
        signed=$_.IsSigned }
})
[pscustomobject]@{adapters=$items; reboot_pending=((Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'))} | ConvertTo-Json -Depth 4 -Compress
"""
WINDOWS_UPDATES = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$session = New-Object -ComObject Microsoft.Update.Session
$session.ClientApplicationID = 'AI Constitution Local Control'
$result = $session.CreateUpdateSearcher().Search("IsInstalled=0 and IsHidden=0 and Type='Driver'")
if ($result.ResultCode -ne 2) { throw 'Windows Update scan did not complete successfully' }
$items = @($result.Updates | Where-Object {$_.DriverClass -eq 'Display'} | ForEach-Object {
    [pscustomobject]@{title=$_.Title; vendor=$_.DriverProvider; date=$_.DriverVerDate.ToString('yyyy-MM-dd')}
})
ConvertTo-Json -InputObject $items -Depth 3 -Compress
"""


def run(args, timeout=25):
    """Bounded, read-only inventory commands; never return raw stderr or host paths."""
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError('Driver query failed; check OS tools and permissions on this machine')
    return result.stdout.strip()


def powershell(script, timeout=25):
    executable = shutil.which('powershell.exe')
    if not executable:
        raise ValueError('Windows PowerShell is unavailable on this machine')
    return json.loads(run([executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script], timeout))


def adapter(name, version=None, vendor='', date=None, device='', **extra):
    name, vendor = str(name or 'Display adapter')[:200], str(vendor or '')[:120]
    text = (name + ' ' + vendor).lower()
    key = next((v for v, pattern in [('parsec', 'parsec'), ('nvidia', 'nvidia'), ('amd', 'amd'),
                                   ('amd', 'radeon'), ('intel', 'intel'), ('apple', 'apple')] if pattern in text), 'unknown')
    virtual = any(v in text for v in ('parsec', 'virtual', 'indirect', 'remote display'))
    return {'id': hashlib.sha256((device or name).encode()).hexdigest()[:16], 'name': name, 'vendor': vendor,
            'vendor_id': key, 'version': str(version)[:100] if version else None, 'date': date,
            'virtual': virtual, **extra}


def linux_inventory():
    adapters = []
    # DRM sysfs identifies the driver actually bound to each card; no sudo needed.
    for card in sorted(Path('/sys/class/drm').glob('card[0-9]*')):
        if not re.fullmatch(r'card\d+', card.name) or not (card / 'device').exists():
            continue
        device = card / 'device'
        try:
            vendor = {'0x1002': 'AMD', '0x10de': 'NVIDIA', '0x8086': 'Intel'}.get((device / 'vendor').read_text().strip(), 'Unknown')
            module = (device / 'driver').resolve().name if (device / 'driver').exists() else 'unbound'
            version_file = device / 'driver/module/version'
            version = version_file.read_text().strip() if version_file.exists() else platform.release()
            if module == 'unbound':
                version = None
            name = vendor + ' ' + card.name
            if shutil.which('lspci'):
                description = run(['lspci', '-s', device.resolve().name], timeout=5)
                name = description.split(': ', 1)[-1] or name
            adapters.append(adapter(name, version, vendor, device=card.name, component=module,
                                    version_kind='module' if version_file.exists() else 'kernel'))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    # Some containers expose NVIDIA management but not DRM sysfs.
    if not adapters and shutil.which('nvidia-smi'):
        for row in csv.reader(io.StringIO(run(['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader']))):
            if len(row) == 2:
                adapters.append(adapter(row[0].strip(), row[1].strip(), 'NVIDIA'))
    return adapters


def actions(system, adapters):
    result = []
    if system == 'Windows':
        result.append({'id': 'windows-update', 'label': 'Windows driver updates',
                       'detail': 'Opens Optional updates on this computer. Select the applicable drivers and confirm installation in Windows.'})
        for vendor in dict.fromkeys(a['vendor_id'] for a in adapters):
            if vendor in VENDORS:
                label, _ = VENDORS[vendor]
                result.append({'id': 'vendor-' + vendor, 'label': label,
                               'detail': 'Opens the official vendor website on this computer. Select this GPU and OS; confirm installation locally.'})
    elif system == 'Darwin':
        result.append({'id': 'macos-update', 'label': 'macOS Software Update',
                       'detail': 'Graphics drivers ship with macOS. Opens System Settings; review the compatible OS update and any restart there.'})
    elif system == 'Linux' and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        for executable, label in [('software-properties-gtk', 'Additional Drivers'), ('update-manager', 'Software Updater'),
                                  ('gnome-software', 'Software updates'), ('plasma-discover', 'Discover updates')]:
            if shutil.which(executable):
                result.append({'id': executable, 'label': label, 'detail': 'Opens the distribution’s update application. Review driver, kernel and Mesa updates there.'})
                break
    return result


def inspect():
    system = platform.system()
    report = {'schema': 1, 'platform': system, 'os_version': platform.release(), 'checked_at': time.time(),
              'adapters': [], 'status': 'ok', 'reboot_pending': None, 'updates': {'status': 'not-checked'},
              'note': 'Installed versions only. Driver dates do not establish whether an update is needed.'}
    try:
        if system == 'Windows':
            data = powershell(WINDOWS_INVENTORY)
            report['adapters'] = [adapter(**a) for a in data['adapters']]
            report['reboot_pending'] = data.get('reboot_pending')
            report['source'] = 'Windows signed display-driver inventory'
        elif system == 'Darwin':
            version = run(['/usr/bin/sw_vers', '-productVersion'])
            build = run(['/usr/bin/sw_vers', '-buildVersion'])
            data = json.loads(run(['/usr/sbin/system_profiler', 'SPDisplaysDataType', '-json']))
            report['os_version'] = version + ' (' + build + ')'
            report['adapters'] = [adapter(a.get('sppci_model') or a.get('_name'), report['os_version'], a.get('spdisplays_vendor', 'Apple'),
                                          version_kind='macOS') for a in data.get('SPDisplaysDataType', [])]
            report['source'] = 'macOS System Information'
            report['note'] = 'Graphics drivers are part of macOS; the OS version and build identify the installed graphics stack.'
        elif system == 'Linux':
            report['adapters'] = linux_inventory()
            report['source'] = 'Linux DRM / NVIDIA driver inventory'
            report['note'] = 'Kernel/module versions are shown. Mesa and compute-runtime packages are separate; use your distribution’s updater.'
        else:
            report['status'] = 'unsupported'
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        report.update(status='unavailable', note='Could not read display drivers. Check OS inventory tools and permissions, then retry.')
    report['actions'] = actions(system, report['adapters'])
    if not report['adapters'] and report['status'] == 'ok':
        report.update(status='empty', note='No display adapters were reported. This may be a headless host or a restricted environment.')
    return report


def check_updates(report):
    """Ask Windows Update for applicable display drivers, never install them."""
    result = {'checked_at': time.time(), 'status': 'manual', 'offers': [],
              'note': 'Use the OS/vendor updater to check compatible releases.'}
    if report['platform'] == 'Windows':
        try:
            offers = powershell(WINDOWS_UPDATES, timeout=120)
            if not isinstance(offers, list):
                raise ValueError('Unexpected update response')
            result.update(status='available' if offers else 'none-offered', offers=offers[:50],
                          note='Applicable display drivers offered by the configured Windows Update service. Vendor releases can differ; no offer does not mean latest.')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            result.update(status='unavailable', note='Windows Update could not complete its check. Retry or use the native update controls; managed policies may restrict access.')
    return result


def open_updater(action):
    """Only fixed native commands/official URLs selected from this host's capabilities."""
    report = inspect()
    if action not in [a['id'] for a in report['actions']]:
        raise ValueError('This update action is not available on the selected machine')
    try:
        if action == 'windows-update':
            os.startfile('ms-settings:windowsupdate-optionalupdates')
        elif action.startswith('vendor-'):
            os.startfile(VENDORS[action.removeprefix('vendor-')][1])
        elif action == 'macos-update':
            run(['/usr/bin/open', 'x-apple.systempreferences:com.apple.Software-Update-Settings.extension'], timeout=10)
        else:
            arguments = {'software-properties-gtk': ['--open-tab=4'], 'update-manager': [],
                         'gnome-software': ['--mode=updates'], 'plasma-discover': ['--mode', 'Update']}
            process = subprocess.Popen([shutil.which(action), *arguments[action]], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            # Reap the GUI child when it eventually closes.
            import threading
            threading.Thread(target=process.wait, daemon=True).start()
    except OSError:
        raise ValueError('Could not open update controls. Sign in to the selected machine’s desktop and retry.') from None
    return {'status': 'handoff', 'action': action, 'opened_at': time.time(),
            'note': 'Update controls requested on the selected machine. Confirm installation there, then refresh versions here. No installation or restart has been verified.'}
