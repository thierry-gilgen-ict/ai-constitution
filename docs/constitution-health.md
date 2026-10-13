# Constitution health

Constitution health inventories instruction sources, explains expected discovery, and prepares recoverable corrections. Open **Constitution health** in Local Control. Structural scanning uses the standard library, reads selected instruction files, and performs no inference or project command execution.

## Start with a bounded scope

Choose **Configure**, select client profiles and project/search directories, and save. Explicit projects can be non-Git folders. Search roots discover repositories and worktrees to depth four; source, directory and project limits produce visible coverage gaps. Linked directories are excluded. Files above 64 MiB are excluded; smaller large files are hashed in chunks and excerpts are bounded.

Use **Scan now**, then **Explain instructions**. Codex discovery accounts for overrides, fallback names, the working directory and byte limits. Cursor always/conditional rules and account-rule exports have different evidence. A referenced module is not automatically loaded. Missing account-managed settings remain unknown. [Cursor’s rule documentation](https://cursor.com/docs/rules) defines native formats and attachment behavior: plain `.md` files in `.cursor/rules` are ignored; nested rules and file-pattern rules depend on scope/context. `CLAUDE.md` is inventoried without assuming Cursor loads it. Rule files found in a profile directory do not prove global applicability.

Core CLI, without creating private evidence or installing anything:

```sh
python scripts/constitution.py audit --project /path/to/project --client codex
python scripts/constitution.py audit --search-root /path/to/projects --format json
```

The existing `scan` command remains the public-file secret scan. Audit reports can contain private paths and project facts; keep JSON output private.

## Findings and session evidence

The page separates installation integrity, installed release, canonical release and client loading. Older releases may be deliberate pins. Record a fresh session's client version and classify evidence as agent-reported or operator-observed. A changed source/configuration fingerprint or aged observation makes evidence stale. Record client upgrades in the profile’s installed-version field; client version collection is explicit rather than inferred from account databases. File checks do not establish instruction compliance.

Structural findings include missing/modified managed files, broken references, invalid rules, byte-limit overflow, invalid routes and expired governance exceptions. Exact repetition and possible prose contradictions are review items. Deliberate replicas and project refinements are not automatically errors. Suspected credential material is withheld from review excerpts; detection is heuristic, not a guarantee.

Findings have stable IDs and evidence fingerprints. Acknowledge, defer, accept an exception or reopen, with a reason and optional review date. Changed evidence reopens old decisions. Coverage is always for the selected scope, not every directory or account on a computer.

## Review corrections

Select **Corrections**, choose an enrolled target and preview its diff. Managed corrections restore missing owned files or update unchanged owned artifacts from a validated library. Modified/unowned files, pins, pauses and stale plans require review. Global installations remain separate targets.

Three policies are available: notify only, prepare fixes, and automatic permitted managed updates. Automatic operation requires approval of the exact current library fingerprint and selected correction types. Updating that library invalidates its previous automatic authorization. Target-specific policy overrides are available through **Correction policy** on each target and the private settings API/CLI. Reference migrations must be supplied by the normal approved release renderer; the scanner invents no path rewrites.

Every application rechecks target/source fingerprints and records a private installation snapshot. Each target has its own transaction; there is no atomic fleet-wide promise. Roll back only while later edits can be preserved. Reload affected client instructions after changing files.

## Schedules and notifications

Structural schedules start disabled. When enabled, the default interval is 24 hours; review-handoff schedules default to 168 hours. Change checks inspect fingerprints at most once every five minutes while the controller or worker runs; unchanged checks do not append duplicate reports. Maintenance windows use the owning machine’s local hour, including overnight windows. The **per-user OS job** wakes hourly and executes only due work, including after the dashboard closes. Windows runs while logged in, macOS uses a user launch agent, and Linux uses a systemd user timer. Sleeping/offline machines catch up once rather than replaying every missed run.

Controller and OS jobs share a lease and private due records. New findings notify; unchanged findings stay quiet. Native desktop notifications are optional and contain fixed text rather than paths or excerpts. Pausing a schedule does not change existing project synchronization settings.

```sh
python scripts/local_control.py audit overview
python scripts/local_control.py audit scan --project /path/to/project
python scripts/local_control.py audit settings --input /private/audit-settings.json
python scripts/local_control.py audit due
```

Private settings example:

```json
{"mode":"automatic","corrections":["restore-missing","managed-update","generated-refresh"],"approve_source":true,"schedule":{"enabled":true,"hours":24,"changes":false,"paused":false}}
```

To set one target's policy, use `{"target":"ID_FROM_OVERVIEW","mode":"propose","corrections":[]}`. The target ID is scoped to that machine's enrollment. Do not put this private inventory in a repository.

## Workers and remote corrections

Update the worker from a verified package. Version metadata advertises `constitution-audit-v1`; older workers remain usable for inference and show an audit upgrade requirement. Choose the worker in the health page and request its report or scan. Offline reports retain their timestamp and unavailable status.

Pairing grants no instruction access. Grant operations locally to the intended paired controller. The following PowerShell command prompts for every value inline, so it works in a fresh terminal without preexisting variables:

```powershell
& (Read-Host 'Installed worker executable') --state-dir (Read-Host 'Private worker state directory') audit grant --controller (Read-Host 'Paired controller ID') --root (Read-Host 'Approved project root') --permission scan --permission report --permission preview --permission apply --permission excerpts
```

The source equivalent on Windows/macOS/Linux is:

```sh
python scripts/local_control.py --state-dir /private/worker-state audit grant --controller CONTROLLER_ID --root /path/to/project --permission scan --permission report --permission preview --permission apply --permission excerpts
python scripts/local_control.py --state-dir /private/worker-state audit revoke --controller CONTROLLER_ID
```

Inspect paired IDs using the worker's existing **controllers** command. Profiles require `--profile codex` or `--profile cursor` plus roots covering both the entry point and its owned library files. Repeated `--root` arguments grant separate directories; the service checks every owned file. Grant `review` only when excerpts should be used in a client handoff. Configuration/schedule policies are owned locally on the worker; the central dashboard cannot expand its own grant.

Remote previews and writes execute on the owning computer. Grants are checked again before application. Requests have durable IDs; after a timeout, inspect request/job status instead of creating a fresh apply request. TLS pins, separate management credentials and revocation remain effective. Inference and legacy credentials cannot use audit operations.

## Semantic review

Choose **AI review** and Codex or Cursor. The controller prepares a bounded snapshot, labels instructions as untrusted data, omits detected sensitive excerpts, and returns a prompt. Use a fresh native client session with its existing login; paste the structured JSON result back for validation.

The shipped adapter uses the interactive handoff. Unattended native execution is not claimed: client permission profiles and OS confinement must be separately verified before enabling such an adapter. Scheduled reviews prepare handoffs and perform no paid model calls. Open saved handoffs from **History**; unchanged bounded snapshots reuse cached review IDs. Manual client work uses the client's own limits; ten-minute/three-project settings do not constitute an enforced monetary limit or a timeout on a user's manual conversation.

Result validation rejects unknown source IDs, stale fingerprints, oversized edits and detected sensitive content. AI prose is never automatically promoted. Explicitly reviewed project-context/unmanaged prose can be applied through a transaction. Changes to the managed core or shared source must use **Constitution files** and its reviewed build/rollout; generated routing stays generated.

## Governance and economics

Use the optional [governance template](../templates/governance.json) as `.ai/governance.json`. It records delivery profile, risk, acceptance criteria, owner roles, WIP limit and reviewable exceptions independently of the existing policy schema. Keep actual identities and organizational restrictions private.

The `receipt` CLI/API records operator-provided task/revision/artifact evidence and separate implementation, review, integration, deployment and acceptance states. Actual charges require billing evidence; unknown values remain unknown. `github` performs explicit read-only checks through an existing GitHub CLI login. It reports accessible rules/checks and open candidates, and leaves unavailable classic protection unknown. It never changes protections, merges, deploys or deletes branches/worktrees.

## Evidence recovery and MCP

Evidence is stored privately in SQLite under the controller's state directory. **History** provides consistent backup and historical restore to private directories. Backups may contain private diffs and excerpts; use protected storage and the existing encrypted-backup workflow. Register a consistent exported backup directory for encrypted project-config backups; active SQLite files are not implicitly included. Restore imports history only: grants, schedules, proposals and interrupted requests remain inactive. Retention defaults to 90 days; unresolved proposal references and rollback evidence are preserved.

Optional stdio MCP:

```sh
python -m pip install -r requirements-mcp.txt
python scripts/local_control.py audit settings --input /private/mcp-grants.json
python scripts/constitution_mcp.py --state-dir /private/control-state --project /path/to/project --profile codex
```

The grant file contains `{"mcp_projects":[{"project":"/path/to/project","profiles":["codex"]}]}`. Use the runtime where the pinned SDK is installed; MCP import is optional for the core scanner. Configure the same command/arguments in Codex or Cursor's native MCP settings and test in a fresh session. The `mcp-recipe` dashboard API generates these arguments for an existing grant. Native packages expose the equivalent `audit-mcp` subcommand.

Tools expose scoped inventory, reports, structural scanning and proposed reconciliation. Every call rechecks its project/profile grant. No apply, arbitrary shell or permission-management tools exist. SDK interoperability is distinct from actual client loading.

## Acceptance status

Automated coverage uses disposable projects, private state and fake clients. Physical main/worker scan → preview → correction → verification → rollback is a separate release gate. macOS/Linux CI and package checks are not proof of a physical client session. See [compatibility](compatibility-matrix.md), [the illustrated health manual](manual/audit.md) and [migration guidance](constitution-migration.md).
