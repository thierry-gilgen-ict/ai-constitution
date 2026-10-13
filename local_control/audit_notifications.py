"""Optional fixed-text OS notifications; no source excerpts or account metadata."""
import os
import platform
import shutil
import subprocess


def notify(*, system=None, runner=subprocess.run):
    system=system or platform.system()
    if system=='Windows':
        executable=shutil.which('powershell.exe')
        if not executable:return {'status':'unavailable'}
        script=("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null; "
                "$auditToastXml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
                "$auditToastXml.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>AI Constitution</text><text>New constitution findings. Open Local Control to review.</text></binding></visual></toast>'); "
                "$auditToast = [Windows.UI.Notifications.ToastNotification]::new($auditToastXml); "
                "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Windows PowerShell').Show($auditToast)")
        args=[executable,'-NoProfile','-NonInteractive','-Command',script]
    elif system=='Darwin':args=['osascript','-e','display notification "New constitution findings. Open Local Control to review." with title "AI Constitution"']
    elif system=='Linux':args=['notify-send','AI Constitution','New constitution findings. Open Local Control to review.']
    else:return {'status':'unsupported'}
    try:
        result=runner(args,capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return {'status':'sent' if result.returncode==0 else 'unavailable'}
    except (OSError,subprocess.SubprocessError):return {'status':'unavailable'}
