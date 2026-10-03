# Security and privacy

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

`scan` checks tracked and nonignored files for private filenames, common credential patterns, personal Windows home paths, and unexpected binaries. It reports file names and rule IDs rather than secret values. Also run a dedicated secret scanner over Git history and review the staged diff.

Public source exports and native build inputs use the reviewed `checks/release-files.json` inventory. Files merely present in an allowed directory are not automatically published, even if Git ignores them. Sensitive filenames are rejected, declared inputs must exist, and links/reparse points are refused. Private Studio editing still uses its separate runtime library; it does not expand the public export inventory.

Native builds require an empty output directory and compile from an isolated inventory copy. Complete release assembly accepts only the expected native ZIP/checksum/SBOM inputs. Existing files are preserved when a stale output is rejected.

Every workflow upload is gated by `scripts/scan_publication.py`. It verifies a pinned Gitleaks download, inspects nested ZIP paths and private filenames, and scans the actual upload inputs with fully redacted output. Missing inputs, scanner failures, excessive archive nesting and unresolved findings block publication, including failure reports. A generic-key flag in a manifest is dismissed only when its exact redacted match reconstructs a declared SHA-256 and the referenced packaged file has that digest; manifests are never blanket-ignored. See the [release guide](docs/releasing.md) for local commands.

GitHub secret scanning, push protection, dependency alerts and automatic dependency security-fix pull requests are enabled. Weekly Dependabot reviews cover Python, npm and GitHub Actions. Dependency proposals still require review and passing checks; enabling security fixes does not enable automatic merging.

Publication scans use the scanner's default rule set with an explicit empty ignore file and ignore `gitleaks:allow` comments. A local scanner config or inline annotation cannot silently exempt upload inputs.

Heuristics cannot prove the absence of all secrets. The upload scanner does not OCR images or unpack PyInstaller bytecode; review screenshot pixels and use synthetic data, and build only on an isolated host/environment. Keep the public checkout separate from personal configuration and never initialize a Git repository around your entire configuration directory.

## Reporting

Use [GitHub's private vulnerability reporting](https://github.com/thierry-gilgen-ict/ai-constitution/security/advisories/new), which is enabled for this repository. Include affected versions, reproduction steps and impact using synthetic data. Do not post credentials or sensitive exploit details in a public issue. Ordinary reproducible bugs can be reported in Issues.

Application updates use only the named public GitHub repository, verified SHA-256 archives and complete file manifests. Restart requires idle tracked sessions, no active responses/jobs, and acknowledgement of other clients. The previous application is retained; an ambiguous new process is never blindly terminated. API cost connectors refuse HTTP redirects so authorization headers cannot be forwarded to another host. Passwords and API keys are referenced through private files/environment, never entered in account labels or public artifacts.
