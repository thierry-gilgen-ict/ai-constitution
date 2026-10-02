# Security and privacy

The project distributes instructions and model metadata. It does not enforce a security boundary around an agent, replace host approval controls, or guarantee model compliance.

## Data boundaries

- The public repository contains authored policy, public model metadata, code, tests, and documentation.
- Private state lives under `~/.config/ai-constitution/state/` by default. Installation snapshots can contain preexisting private instructions. Keep this directory private.
- Public refreshes use an allowlisted HTTPS source and no credentials. Redirect targets are checked.
- Local model discovery is explicit, performs metadata GETs, refuses redirects, and does not use proxy routing. Remote discovery requires an explicit option and HTTPS.
- An optional API credential is read only from a named environment variable and is not written to state or logs.
- Source data is not executed. No model inference, package installation, or background schedule is triggered by a catalog refresh.

## Publishing checks

`scan` checks tracked and nonignored files for private filenames, common credential patterns, personal Windows home paths, and unexpected binaries. It reports file names and rule IDs rather than secret values. Also run a dedicated secret scanner over Git history and review the staged diff.

Heuristics cannot prove the absence of all secrets. Keep the public checkout separate from personal configuration and never initialize a Git repository around your entire configuration directory.

## Reporting

For a vulnerability, use GitHub's private vulnerability reporting when enabled. Otherwise contact the maintainer through the organization's published contact channel without including credentials or sensitive exploit details in a public issue. Ordinary reproducible bugs can be reported in Issues.
