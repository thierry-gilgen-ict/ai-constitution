"""Optional publisher signing hooks. No identity means an explicitly unsigned build."""
import json
import os
from pathlib import Path
import platform
import subprocess


def sign(directory, executable):
    system = platform.system()
    if system == 'Windows' and os.environ.get('WINDOWS_SIGN_CERTIFICATE'):
        args = ['signtool', 'sign', '/fd', 'SHA256', '/td', 'SHA256', '/tr', 'http://timestamp.digicert.com',
                '/f', os.environ['WINDOWS_SIGN_CERTIFICATE']]
        if os.environ.get('WINDOWS_SIGN_PASSWORD'): args += ['/p', os.environ['WINDOWS_SIGN_PASSWORD']]
        subprocess.run([*args, str(executable)], check=True, capture_output=True)
        subprocess.run(['signtool','verify','/pa',str(executable)], check=True, capture_output=True)
        return 'Windows Authenticode signature verified'
    if system == 'Darwin' and os.environ.get('MACOS_SIGN_IDENTITY'):
        identity = os.environ['MACOS_SIGN_IDENTITY']
        candidates = []
        for path in Path(directory).rglob('*'):
            if not path.is_file(): continue
            kind = subprocess.run(['file','-b',str(path)],capture_output=True,text=True,check=True).stdout
            if 'Mach-O' in kind: candidates.append(path)
        for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
            subprocess.run(['codesign','--force','--options','runtime','--timestamp','--sign',identity,str(path)],check=True,capture_output=True)
        subprocess.run(['codesign','--verify','--strict','--verbose=2',str(executable)],check=True,capture_output=True)
        return 'Apple Developer ID signature verified; notarization is a separate release step'
    return 'Unsigned preview; checksums and GitHub provenance do not replace publisher signing'


def notarize(archive):
    profile = os.environ.get('MACOS_NOTARY_PROFILE')
    if platform.system() != 'Darwin' or not profile: return {'status':'not-configured'}
    result = subprocess.run(['xcrun','notarytool','submit',str(archive),'--keychain-profile',profile,
                             '--wait','--output-format','json'],check=True,capture_output=True,text=True,timeout=1800)
    status = json.loads(result.stdout)
    if status.get('status') != 'Accepted': raise ValueError('Apple notarization did not accept this archive')
    return {'status':'accepted','submission_id':status['id']}
