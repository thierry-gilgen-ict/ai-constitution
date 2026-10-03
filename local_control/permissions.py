"""Create private state before writing credentials; fail closed on ACL errors."""
import functools
import os
from pathlib import Path
from scripts.paths import no_links


@functools.lru_cache(maxsize=1)
def user_sid():
    import csv
    import re
    import subprocess
    result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True,
        text=True, check=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    sid = next(csv.reader(result.stdout.splitlines()))[1]
    if not re.fullmatch(r'S-1-[0-9-]+', sid):
        raise ValueError('Cannot identify the private state owner')
    return sid


def protect(path):
    path = Path(path); no_links(path)
    if os.name != 'nt':
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    import ctypes
    from ctypes import wintypes
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    apply = advapi.SetFileSecurityW
    apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    apply.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor = ctypes.c_void_p()
    flags = 'OICI' if path.is_dir() else ''
    sddl = 'D:P(A;' + flags + ';FA;;;' + user_sid() + ')(A;' + flags + ';FA;;;SY)'
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        raise OSError(ctypes.get_last_error(), 'Cannot create private state permissions')
    try:
        if not apply(str(path), 0x80000004, descriptor):
            raise OSError(ctypes.get_last_error(), 'Cannot protect private state permissions')
    finally:
        kernel.LocalFree(descriptor)


def directory(path):
    path = Path(path); no_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(path)
    return path
