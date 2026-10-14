# Security and privacy

Claude support is opt-in. Account collection does not scrape authentication stores. Telemetry has a separate ingestion-only credential and stores aggregate counters without prompts or raw event bodies. Public exports reject `.claude.json` and `CLAUDE.local.md`. Isolated reviews disable tools, MCP and hooks, use temporary directories and produce candidates requiring diff approval; subscription login is not reused for unattended execution. See [Claude compatibility](docs/claude-code.md) for rollout controls and acceptance limitations.

The project distributes instructions and model metadata. It does not enforce a security boundary around an agent, replace host approval controls, or guarantee model compliance.

## Data boundaries

- The public repository contains authored policy, public model metadata, code, tests, and documentation.
- Private state lives under `~/.config/ai-constitution/state/` by default. Installation snapshots can contain preexisting private instructions. Keep this directory private.
- Public refreshes use an allowlisted HTTPS source and no credentials. Redirect targets are checked.
- Local model discovery is explicit, performs metadata GETs, refuses redirects, and does not use proxy routing. Remote discovery requires an explicit option and HTTPS.
- An optional API credential is read only from a named environment variable and is not written to state or logs.
- Source data is not executed. No model inference, package installation, or background schedule is triggered by a catalog refresh.

## Local Control

The optional controller is a real local service. Keep its private state outside repositories and expose remote workers only on a trusted network using the documented TLS pairing. Worker certificates are pinned; inference and administration use separate credentials. Inference access does not grant Studio, account-monitoring, package-management or configuration-backup access. Browser administration requires the authenticated local launch flow.

Account collection is opt-in and uses allowlisted read-only Codex CLI account methods. Each worker must separately opt in to sharing. Login identifiers and usage observations are private metadata; they are not credentials. Integration logs and support reports exclude raw prompts, responses and credential files. The collector does not read browser cookies or sign in on a user's behalf.

Configuration snapshots can contain live secrets. The local-copy backend receives private filesystem permissions but **does not encrypt content**. The optional restic backend encrypts snapshots using a separately managed password. Review restore/retention previews before applying them. Controller schedules require the controller to run; explicitly installed per-user OS schedules can run while it is closed. Architecture capture reads variable names and discards values; inspect a template before sharing it.

Portable companions are unsigned previews. Verify the release revision and checksums; a SHA-256 match establishes integrity, not an OS-trusted publisher signature. Keep existing worker state when upgrading so pairing and maintenance settings survive. Driver installation and reboot remain native OS-confirmed actions.

## Publishing checks

Constitution health uses a read-only scanner and a private SQLite evidence store. Reports, excerpts, diffs, machine paths and operator receipts must stay outside public repositories. The scanner reads bounded instruction text and metadata; it executes no repository commands or inference. Heuristic credential detection omits suspicious review excerpts but does not guarantee that prose contains no sensitive information.

Worker audit access requires a separate local grant bound to the paired controller, selected roots, profiles and operations. Pairing, legacy administration and inference credentials do not imply instruction access. Fixed audit operations provide no general remote file or shell API. Grants are rechecked before queued reads and writes; TLS pins and revocation still apply. After an uncertain remote correction, inspect its durable request instead of replaying it.

AI review uses a bounded interactive handoff with validated source IDs and fingerprints. Candidate prose remains private until explicit diff review; host client permissions still apply to the user's native review session. Optional MCP tools recheck their project/profile grant on every call and expose no apply or permission-management operations. Evidence restoration does not restore authority, schedules or interrupted corrections. SQLite backups are protected private copies; use encrypted backup storage where needed.

`scan` checks tracked and nonignored files for private filenames, common credential patterns, personal Windows home paths, and unexpected binaries. It reports file names and rule IDs rather than secret values. Also run a dedicated secret scanner over Git history and review the staged diff.

Public source exports and native build inputs use the reviewed `checks/release-files.json` inventory. Files merely present in an allowed directory are not automatically published, even if Git ignores them. Sensitive filenames are rejected, declared inputs must exist, and links/reparse points are refused. Private Studio editing still uses its separate runtime library; it does not expand the public export inventory.

Native builds require an empty output directory and compile from an isolated inventory copy. Complete release assembly accepts only the expected native ZIP/checksum/SBOM inputs. Existing files are preserved when a stale output is rejected.

Only the native build's `public/` directory is uploaded. Internal compiler aliases must resolve within the application tree; escaping or cyclic links are rejected. ZIP members are ordinary files, including internal alias-directory contents, and the extracted ZIP receives its own smoke test. Intermediate build trees never bypass the upload scanner's link rejection.

Every workflow upload is gated by `scripts/scan_publication.py`. It verifies a pinned Gitleaks download, inspects nested ZIP paths and private filenames, and scans the actual upload inputs with fully redacted output. Missing inputs, scanner failures, excessive archive nesting and unresolved findings block publication, including failure reports. A generic-key flag in a manifest is dismissed only when its exact redacted match reconstructs a declared SHA-256 and the referenced packaged file has that digest; manifests are never blanket-ignored. See the [release guide](docs/releasing.md) for local commands.

GitHub secret scanning, push protection, dependency alerts and automatic dependency security-fix pull requests are enabled. Weekly Dependabot reviews cover Python, npm and GitHub Actions. Dependency proposals still require review and passing checks; enabling security fixes does not enable automatic merging.

Version 0.3.1 requires `cryptography>=50.0.2,<51` for remote worker TLS, clearing GHSA-m2h6-j472-rp4c, GHSA-jwv3-5hgf-82ww, GHSA-g6cj-pr64-35w5 and GHSA-537c-gmf6-5ccf. Upgrade source workers' isolated environments with `python -m pip install --upgrade -r requirements-local-node.txt`, or install the current portable companion. Retain private worker state and certificates. Existing installations do not receive dependency patches merely because this repository changed. Consult the [compatibility matrix](docs/compatibility-matrix.md) before upgrading an unsupported host.

Publication scans use the scanner's default rule set with an explicit empty ignore file and ignore `gitleaks:allow` comments. A local scanner config or inline annotation cannot silently exempt upload inputs.

Heuristics cannot prove the absence of all secrets. The upload scanner does not OCR images or unpack PyInstaller bytecode; review screenshot pixels and use synthetic data, and build only on an isolated host/environment. Keep the public checkout separate from personal configuration and never initialize a Git repository around your entire configuration directory.

## Reporting

Use [GitHub's private vulnerability reporting](https://github.com/thierry-gilgen-ict/ai-constitution/security/advisories/new), which is enabled for this repository. Include affected versions, reproduction steps and impact using synthetic data. Do not post credentials or sensitive exploit details in a public issue. Ordinary reproducible bugs can be reported in Issues.

Application updates use only the named public GitHub repository, verified SHA-256 archives and complete file manifests. Restart requires idle tracked sessions, no active responses/jobs, and acknowledgement of other clients. The previous application is retained; an ambiguous new process is never blindly terminated. API cost connectors refuse HTTP redirects so authorization headers cannot be forwarded to another host. Passwords and API keys are referenced through private files/environment, never entered in account labels or public artifacts.
