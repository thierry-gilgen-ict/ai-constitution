# Acceptance checks

## Files and recovery

- `check` succeeds and generated artifacts match their sources.
- Install in a temporary home and onboard a disposable project containing existing instructions.
- Repeat the install: no duplicate managed sections or content churn.
- Edit outside the managed section: synchronization preserves the change.
- Edit inside an owned section: synchronization reports drift before overwriting it.
- Roll back an installation: original bytes return. Later edits cause a refusal.

## Actual client loading

Use a fresh Codex session, a fresh Cursor Agent conversation, and an enrolled Grok Bot separately:

> Identify the AI Constitution version and instruction sources actually available to you. Cite one applicable working rule. Do not claim to have read a file unless you have its contents.

Then request a small, harmless task in a disposable project. Check that project-specific commands and boundaries are followed. Record the client version, installed release, result, and date locally. A successful `doctor` run alone does not pass this check.

## Catalog and local servers

- Query OpenAI, Anthropic, xAI, and Google offline.
- Refresh the same data twice; the second refresh leaves the snapshot unchanged.
- Simulate malformed data, a network error, and removed records; keep the existing snapshot.
- Use a local metadata server fixture; verify only the model-list endpoint was called.

## Public release

- Review the staged file list and diff; check the image and licenses.
- Run the built-in `scan` and a dedicated secret scanner over the repository/history.
- Include no local paths, credentials, account inventories, conversation exports, or private project facts.
- Record the exact commit and CI results. Keep any live-client limitations explicit.
