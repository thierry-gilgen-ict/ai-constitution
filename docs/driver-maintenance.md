# Display drivers, across your machines

Open **Your machines** to see installed display-driver versions on the main computer and every paired worker. The first visit reads each host; **Refresh all driver versions** repeats that read. It does not load a model or install anything. The isolated CPU runtime shares its computer's graphics drivers, so its card points to the same inventory.

Each physical host shows adapters, reported versions, driver dates where available, the observation time, and the inventory source. Virtual adapters are identified separately. A changed version is shown as a before/after observation. This is evidence of a version change, not evidence that inference is stable or faster. Driver dates are metadata, not installation dates or proof that a driver is outdated.

## Check and update

1. On Windows, choose **Check Windows updates**. This explicitly queries the configured Windows Update service for applicable, visible, uninstalled **display** drivers. It may take up to two minutes. A failed or policy-blocked check is reported as unavailable. “No drivers offered” does not claim that the vendor has no newer release.
2. Choose **Update drivers** on the intended machine. Select its OS updater or official vendor support page. The dialog names the target: a worker opens its controls on the worker's desktop, not in the controller's browser. Sign in there first, locally or through your existing remote-desktop connection.
3. Confirm external model clients are idle, then choose **Prepare & open updater**. Local Control moves new requests to a qualified fallback on another computer when needed, waits for existing responses, unloads only its managed models, and checks for remaining Ollama GPU residency. Unmanaged GPU models block the handoff. Other applications and direct Ollama clients are outside its control.
4. Review and install the applicable update in the OS/vendor interface. It may request administrator approval or a reboot. Local Control opens the controls; it does not click through an installer, automatically install every offer, or restart the computer. A completed handoff is never labeled as a completed installation.
5. After any restart, start the worker/controller using the **same private state directory**. Choose **Refresh versions** to compare observations. Once ready, choose **Recheck & resume model use**. This checks inventory and runtime reachability, and removes the driver-maintenance pause. It does not certify GPU stability, change Gaming eligibility, or qualify the model again; re-test the route before relying on changed hardware/software.

Updating the main computer pauses **both** its GPU and CPU runtimes. Its CPU fallback cannot protect a task from that computer restarting. With open managed sessions or active requests, a qualified route on another computer is required. With no active/managed sessions and external clients acknowledged idle, a single-computer setup can pause its route until resumption. A full computer reboot also stops any client or gateway running on it: the app does not migrate desktop processes or promise uninterrupted tasks across a controller reboot.

<!-- screenshots:update:begin -->

**In the dashboard · Prepare driver maintenance.** Review the target computer and update method. Confirm other clients are idle before opening that machine’s native updater.

![Prepare driver maintenance — demonstration data, UI 0.3.1](assets/screenshots/driver-update.png)

[Illustrated walkthrough](manual/machines.md) · Fictional data; UI 0.3.1.

<!-- screenshots:update:end -->

## Platform coverage

| Platform | Installed information | Update controls |
| --- | --- | --- |
| Windows | Signed display-driver inventory: adapter, provider, driver-store version, driver date; common Windows Update/CBS restart indicators | Windows Optional updates plus detected AMD, NVIDIA, Intel and Parsec official support pages. Explicit Windows Update offer scan. |
| macOS | System Information adapters and macOS version/build; graphics drivers ship with the OS | System Settings → Software Update. No invented separate Apple GPU driver version or automatic OS upgrade. |
| Linux | DRM cards and bound driver module/kernel version; `nvidia-smi` fallback when DRM is absent | Available Ubuntu, GNOME or KDE desktop update application. Headless hosts use their distribution's tools. Mesa/compute package inventories and automatic privileged installation are not included. |

Windows driver-store numbers and vendor marketing package numbers can differ. Match the **exact GPU family and OS** on the official support page. Older AMD families, for example, may use a different maintained branch than current GPUs. A newer date on an unrelated package does not establish compatibility. Virtual display updates can affect remote-desktop access; review them on the machine that uses them.

Live Windows inventory was verified during development. macOS/Linux parsers and launch contracts have fixture tests; physical updater handoff, installation and post-install inference on those platforms remain acceptance work. No real driver was installed by the automated tests.

## Upgrade existing workers

The controller cannot add new capabilities to an older worker executable. Older nodes show **Worker update needed**; unreachable nodes retain their last observation with an unavailable status and timestamp. Neither is reported as current driver evidence.

Drain the worker first and wait for its active responses to finish. Stop its Local Control process, update its source checkout or replace the **complete extracted portable application directory**, then start it with the same `--state-dir`, address and port. Keep private state separate from the application directory; this preserves certificates, pairing and credentials. Updating only the main dashboard is insufficient. Refresh driver versions after both ends run the new code.

This addition uses optional configuration fields and a private `drivers.json` cache. No re-pairing or model download is needed. Do not downgrade a worker during driver maintenance: older binaries do not enforce the new worker hold. Finish/recheck/resume maintenance first, or keep the worker stopped while rolling back.

## Recovery and security

- A worker enforces driver maintenance for all its paired controllers. Inference and model-loading requests are blocked while held; metadata reads and unload requests remain available. Existing responses are never killed to open an updater.
- A failed handoff after draining leaves the computer paused. Fix the reported issue and retry, or choose **Recheck & resume model use** to cancel maintenance. Opening an updater without installing anything is safe to recover this way.
- Maintenance state survives a service or computer restart. Resumption is explicit, including when the original controller lost the handoff response.
- Driver query/update endpoints require management credentials and pinned worker TLS. Inference tokens cannot read inventory, launch update controls, or resume a paused worker.
- Update actions are fixed allowlisted commands/official URLs selected from the target host's capabilities. No client-supplied URL, executable, script or driver package is accepted. OS prompts remain under local user control.
- Inventory and observations stay in private Local Control state. Device IDs are hashed for comparison; raw IDs, credentials and host paths are excluded from driver reports. This inventory is not added to the public repository or the allowlisted support export.

## Sources

- [Microsoft: signed driver inventory fields](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/legacy/aa394354(v=vs.85))
- [Microsoft: automatic and optional driver distribution](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/understanding-windows-update-automatic-and-optional-rules-for-driver-distribution)
- [Microsoft: driver-update metadata](https://learn.microsoft.com/en-us/windows/win32/wua_sdk/iwindowsdriverupdateentry-properties)
- [Microsoft: supported Settings launch URIs](https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-settings)
- [Apple: Software Update](https://support.apple.com/108382)
- [Intel: graphics drivers are built into macOS](https://www.intel.com/content/www/us/en/support/articles/000022440/graphics.html)
- [Ubuntu: Additional Drivers](https://wiki.ubuntu.com/SoftwareAndUpdatesSettings)
