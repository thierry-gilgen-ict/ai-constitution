# Updates, upgrades, and recovery

There are three operations: refresh model facts, change your policy, and upgrade the toolkit. Keeping them distinct makes each one predictable.

## Refresh definitions

```sh
python scripts/constitution.py update
```

This fetches every provider and model from models.dev, validates known field types, and activates an immutable private catalog snapshot. It needs no API key and does not change the source checkout or preferred routes. Offline queries use the accepted private snapshot, falling back to the bundled snapshot before the first refresh. The detailed diff is in the private state directory. Contributors updating the public snapshot use `update --source-checkout` explicitly.

Use `update --dry-run` to inspect changes without replacing the snapshot. Use `update --sources` to also check the curated official documentation URLs. HTML changes are only review signals; navigation or formatting can change a hash. Source failures are reported, retain the last good observation, and cause a nonzero exit status.

Source observations remain pending across repeated checks until you acknowledge the exact revision after review:

```sh
python scripts/constitution.py sources
python scripts/constitution.py sources --review SOURCE_ID --revision OBSERVED_SHA256
```

Legacy observations are not treated as reviewed evidence. An unavailable page retains its last observed and reviewed revisions. Acknowledgment does not modify model facts or routes.

Removals require `--allow-removals` after review. Source failures and malformed catalogs never replace the current catalog. Repeating an unchanged refresh does not churn the public snapshot's timestamp.

## A model is announced before the catalog updates

Ask Codex or Cursor to use `constitution-maintenance`. It should verify official sources and add an explicit record to `registry/overrides.json`. Overrides are merged for queries while the imported snapshot remains intact. Every override requires a source URL and verification date. The provider's actual identifier stays unchanged. Remove the override once upstream contains equivalent, verified data.

Do not hand-edit `registry/catalog.json`: the next refresh replaces imported data. Do not paste API keys or account inventories into an override.

## Change preferred routes

1. Verify availability in the intended product and account.
2. Edit the small `registry/models.json` and `registry/routes.json` files.
3. Compare representative work using [the evaluation worksheet](../checks/evaluation.md). Until then, call the route provisional.
4. Run the commands below and inspect the diff.

```sh
python scripts/constitution.py build
python scripts/constitution.py check
python -m unittest discover -s tests -v
python scripts/constitution.py scan
python scripts/constitution.py sync --all
```

Synchronization updates only registered targets and skips pinned projects. A conflict in one target is reported while other targets can complete. It is not a transaction across all projects. Each target has its own recoverable installation transaction.

Changing the shared source does not retroactively change a running conversation. Restart or begin a fresh session and verify the loaded version. Re-export and re-enroll cloud Bots as described in [Bot onboarding](../onboarding/bot.md).

## Personal preferences and portable project policy

Keep private preferences in `~/.config/ai-constitution/overrides/policy.json`. Put portable project preferences in `.ai/policy.json`. Both use this schema:

```json
{"schema_version": 1, "instructions": {"engineering.md": "Use the existing project test command."}, "routes": [{"platform": "codex", "task": "small", "preferred": "codex:fast"}]}
```

Routes reference curated keys for the same platform. Resolution is release → personal → project. Personal prose and routes are rendered only into private global libraries; portable project bundles include project-owned additions. `route --project PATH` applies both layers privately. `explain --project PATH` shows provenance and installation evidence. These merge rules do not change host instruction precedence or the active model.

## Adopt a project on another computer

```sh
python scripts/constitution.py onboard --project /path/to/clone --adopt --dry-run
python scripts/constitution.py onboard --project /path/to/clone --adopt
python scripts/constitution.py sync --all --dry-run
```

Adoption verifies the exact managed file allowlist and hashes, then records private enrollment without changing the project, its context or its pin. Modified or malformed bundles require reconciliation. A legacy lock establishes file consistency, not independent publisher authenticity.

## Upgrade the installed library

Activate a reviewed local source checkout without changing its Git state:

```sh
python scripts/constitution.py upgrade --source /path/to/reviewed/checkout --dry-run
python scripts/constitution.py upgrade --source /path/to/reviewed/checkout
```

The command stages a content-verified immutable library under `~/.config/ai-constitution/releases/`, preflights every eligible target, then activates the release and changes those targets in one recoverable transaction. It skips pins and preserves personal policy, catalog snapshots and unrelated checkout edits. Drift in any eligible target prevents activation. Unreferenced staged releases may remain after a failed preflight; they are never silently selected.

`upgrade` without `--source` downloads the latest public release's `ai-constitution-release.zip` and matching checksum. Older releases without these assets return a clear error. An offline archive uses `upgrade --archive FILE --sha256 DIGEST`. Checksums establish integrity against the supplied manifest or HTTPS release source; they are not a code-signing claim. The updater never executes downloaded code to validate it. Invoke the installed release's scripts when using its CLI features; this library activation does not replace an already-running CLI, gateway or client session.

Maintainers create the archive with `release --output dist/ai-constitution-release.zip` after checks and the public-file scan. Publish its returned SHA-256 as `ai-constitution-release.sha256`. Read `CHANGELOG.md` before activation. Enrollment remains schema 1; source-review state migrates conservatively to schema 2.

## Roll back an installation

The installer prints a snapshot ID. To undo that target's transaction:

```sh
python scripts/constitution.py rollback --snapshot SNAPSHOT_ID
```

Rollback restores original file bytes and removes files created by the transaction. It refuses if a file changed afterward, including subsequent installation state. Roll back in reverse order. Preserve and reconcile later edits rather than forcing a rollback.

An upgrade snapshot also restores the previous active-release pointer and enrolled files. Immutable release content and downloaded metadata remain cached. Keep private state backups; snapshots can contain private preexisting instructions and must never be committed.

## Convenience without a hidden scheduler

The installed onboarding and maintenance skills work from Codex or Cursor. A manual GitHub Actions catalog-refresh workflow produces a reviewable artifact. No scheduled job or paid evaluation is enabled by installation. If you add a schedule later, notify only on actionable changes and run the same tested commands.
