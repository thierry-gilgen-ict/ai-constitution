# Workspace control center

Local Control groups private operational information with the shared instruction library. Open the authenticated dashboard and use the pages below. Its state stays outside the public repository; worker download archives contain application files, not your state.

## Projects that follow shared changes

**Project sync** automatically reconciles projects enrolled in this computer's constitution state. It runs once a minute while the controller is running, after Studio changes, and catches up on restart. An explicit **Synchronize now** button is also available.

Shared instructions and generated routing update unpinned projects. A saved architecture template updates projects registered with that template ID. A new reviewed application/library version is merged into untouched Studio files before synchronization. Customized sources that also changed upstream need reconciliation in **Constitution files**. Local target edits block only the affected project; its files remain intact and the UI reports the conflict. Pins and per-project pauses prevent automatic writes. Each successful change uses private transaction history and an immutable library reference.

Global client installations still use **Preview activation**. A project on another computer belongs to that computer's enrollment state: run a controller there or synchronize it through the CLI with a reviewed shared library. Pairing an inference worker does not give the main controller arbitrary access to that worker's project files. Workers do not automatically receive private Studio templates from another controller.

Configured local sessions already use the stable `constitution-local` gateway alias. Worker/model/route changes affect subsequent requests according to the gateway's tested routing policy; synchronization records a private runtime revision without writing credentials or machine inventories into project files. It does not migrate direct-provider sessions, select models inside Cursor Agent or reload instructions in an already running assistant. Verify instruction loading in a fresh client session.

## Applications, subscriptions and logins

**Apps & subscriptions** holds multiple subscription records, each with a provider, login identifier, plan, application, machine and project assignments. These are private labels, not credentials. Edit them when an account or machine changes.

Enable the **local Codex CLI account** collector to read its existing sign-in through a short-lived `codex app-server` stdio process. The collector uses only initialization and the documented `account/read`, `account/rateLimits/read`, and `account/usage/read` methods. It never starts a thread or turn, changes sign-in, consumes reset credits or sends account emails. It returns an allowlist of identity, plan, usage windows and token activity; stderr and raw account payloads are not stored. Refresh runs every five minutes while enabled, or through the button. Unsupported endpoints appear as unavailable. The CLI login may differ from the desktop app login; label a separate subscription record where needed. See the [official account protocol](https://learn.chatgpt.com/docs/app-server).

Workers must explicitly opt in on their own computer and OS user:

```sh
python scripts/local_control.py --state-dir /absolute/private/worker-state monitor enable --share
```

Then choose **Refresh usage** for that machine. The report travels through the existing pinned TLS connection using a management credential. Inference credentials cannot read it. Disable with `monitor disable`. Disabling stops collection/sharing; previously cached observations remain marked with their observation time. This version refreshes remote reports on demand.

Cursor and other subscriptions support manual observations and a small portable JSON import. Cursor's official APIs have account/role and enterprise availability constraints; this release does not scrape browser cookies, private session endpoints or application credential files. Use the provider dashboard for authoritative billing. OpenAI and Anthropic API organization cost connectors are also available with explicit admin-key environment references; API billing remains separate from subscription allowances. Last successful reports and observation history survive refresh failures. See [Cursor's API documentation](https://cursor.com/docs/account/teams/admin-api) and [analytics availability](https://cursor.com/docs/account/teams/analytics).

```json
{"used": 12000, "limit": null, "unit": "tokens", "period": "Reviewed reporting period", "model": "example-model"}
```

Supported units are tokens, requests, USD, EUR, CHF and percent. Optional `observed_at` is Unix seconds. Imported observations never masquerade as live provider readings. The UI does not sum account-wide quota windows across machines, currencies or unrelated billing periods. Missing values remain unknown.

**Diagnostics & operation log** shows each machine's version, runtime state, active/session counts and bounded operation status. The collector log adds timestamps and fixed error categories. Subscription records have their own integration events. These are Local Control integration logs, not the clients' full internal logs. Support reports deliberately exclude prompt/response contents, credentials, raw provider errors, paths and account identifiers. No API serves arbitrary log files.

## Storage and worker installation

**Storage & locations** shows observed model storage, desired defaults and destination free space. Save a new library or managed-download location to copy and verify the existing data; originals remain. Move one of those folders at a time. Model storage is separate: save a desired folder, optionally **Copy existing model weights**, then **Apply Ollama location**. Copies require a new destination; there is no destructive merge.

The environment change applies to future Ollama processes. On Windows it updates the current user's `OLLAMA_MODELS`; quit and restart Ollama when clients are idle. On macOS it uses `launchctl setenv`, which must be applied again after login. On Linux configure the Ollama service environment and ensure its service user has access. A running CPU fallback keeps its old store until restarted. The UI distinguishes an observed model store from an unverified default. Browser download preferences are controlled by the browser. See [Ollama storage documentation](https://docs.ollama.com/faq) and [Windows configuration](https://docs.ollama.com/windows).

New installations choose controller configuration with `--state-dir` or `AI_CONSTITUTION_LOCAL_HOME`. To move an existing controller, stop it once managed sessions and other clients are idle, then run:

```sh
python scripts/local_control.py --state-dir /old/private/control relocate --destination /new/private/control
python scripts/local_control.py --state-dir /old/private/control relocate --destination /new/private/control --plan FINGERPRINT_FROM_PREVIEW
python scripts/local_control.py --state-dir /old/private/control start
```

The OS ownership lock prevents relocation of a running controller. A verified copy preserves the original. The old location receives a private pointer followed by future CLI launches; enrollment state stays at its original path. The destination must be outside repositories and must not already exist. On a failed final handoff, inspect the retained copy before choosing another destination; never delete the original to force recovery.

**Set up a worker** displays cached native packages, checksums, source-package downloads, OS-specific startup/pairing commands and upgrade instructions. Prepare a source package for Python 3.11+ on Windows/macOS/Linux, or register a reviewed native ZIP with:

```sh
python scripts/local_control.py packages add --file /path/to/worker.zip
```

Native builds now produce this ZIP automatically. Preview artifacts are unsigned: checksums verify integrity, not publisher identity. Source packages come from the public application bundle, never the private Studio draft. Transfer the whole ZIP to the worker, extract into a new application folder and retain its original state directory when upgrading. Account diagnostics require this newer worker version; older workers remain usable for their existing inference capabilities.

## Central private configuration and backups

**Configs & backups** defaults the configuration root to `AI_CONSTITUTION_CONFIG_HOME` or `~/.config`. Existing project folders can contain environment files, deployment records and keys. Register each project explicitly, optionally linking its checkout. This adopts the mapping without moving existing files. Application settings alongside those projects are excluded unless separately selected. No configuration file values are served to the browser.

Choose a backup destination outside the configuration root and project repositories. The local-copy backend contains secrets and **does not encrypt them**; use an encrypted volume or select the new [restic backend](encrypted-backups.md). Snapshot staging receives current-user Windows ACLs or POSIX 0700 permissions. Files are copied and verified with SHA-256; source changes during copying prevent publishing the snapshot. Limits are 1 GiB per configuration file and 5 GiB per snapshot, intended for configuration rather than models or build outputs.

**Back up now** previews selected projects, file count, size and destination. **Scheduled backups** is off initially. Choose an interval of 1–720 hours. The running controller checks due work each minute, records attempts durably, and catches up after restart. A sleeping/offline computer cannot back up; enable the existing per-user Local Control startup if desired. Failures appear in Activity and on the backup page. No autonomous snapshot deletion is enabled; manage retention deliberately. The optional [restic backend and per-user OS scheduler](encrypted-backups.md) support encrypted remote repositories and backups while Local Control is stopped. Queue rejection now records a retry without consuming the daily interval.

Restore selects a snapshot and project, verifies its inventory and hashes, previews the copy, and writes only to a **new directory**. Existing environment files are never overwritten. Review the restored configuration, then change the private project mapping explicitly. This staged restore prevents an old production credential from silently replacing a newer one.

## Capture a reusable architecture

In **Project templates**, select **From existing project**. The capture reads supported root and immediate monorepo workspace manifests (`package.json`, `pyproject.toml`, `requirements.txt`), recognizes supported components and detects Compose presence. It reads variable names from `.env.example`; optionally choose the project's registered private configuration mapping to extract names from its top-level environment files. All right-hand-side values are discarded.

Capture never copies dependency URLs, package scripts, project identity, Docker content, deployment files or application source, and never runs commands. The result is a proposal opened in the existing editor. Review component compatibility, version pins, configuration purposes and missing custom architecture before saving. Immediate apps, packages and services workspaces are inspected too; deeper or unsupported frameworks need manual additions. Saving a captured baseline then follows the same synchronization and ownership rules as any other template.

## Workspace maintenance in 0.3

See the [workspace upgrade guide](workspace-upgrades.md) for the project wizard, template revision policies, application update notification, verified controller/worker upgrades, measured profiles and pre-dispatch fallback behavior. Failed operations remain actionable until acknowledged, and background no-change checks no longer fill Activity.
