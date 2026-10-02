"""Process identity checks prevent stale PIDs from authorizing termination."""
import hashlib
import os
from pathlib import Path
import platform
import subprocess


def identity(pid):
    if type(pid) is not int or pid < 1:
        return None
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
            kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                    return None
                size = wintypes.DWORD(32768)
                name = ctypes.create_unicode_buffer(size.value)
                if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
                    return None
                start = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                return {'pid': pid, 'started': str(start), 'executable': str(Path(name.value).resolve())}
            finally:
                kernel.CloseHandle(handle)
        if platform.system() == 'Linux':
            proc = Path('/proc') / str(pid)
            start = (proc / 'stat').read_text().rpartition(')')[2].split()[19]
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            return {'pid': pid, 'started': boot + ':' + start, 'executable': str((proc / 'exe').resolve(strict=True))}
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'comm='], capture_output=True, text=True, timeout=3)
        value = result.stdout.strip()
        if result.returncode or not value:
            return None
        return {'pid': pid, 'started': value[:24], 'executable': value[24:].strip()}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def matches(record):
    expected = record.get('process') if isinstance(record, dict) else None
    return bool(expected and identity(expected.get('pid')) == expected)
