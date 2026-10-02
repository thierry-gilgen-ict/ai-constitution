# Updates, upgrades, and recovery

There are three operations: refresh model facts, change your policy, and upgrade the toolkit. Keeping them distinct makes each one predictable.

## Refresh definitions

```sh
python scripts/constitution.py update
```

This fetches every provider and model from models.dev, validates the response, updates the bundled snapshot, and regenerates derived instructions. It needs no API key. The detailed diff is in the private state directory reported by the command.

Use `update --dry-run` to inspect changes without replacing the snapshot. Use `update --sources` to also check the curated official documentation URLs. HTML changes are only review signals; navigation or formatting can change a hash. Source failures are reported, retain the last good observation, and cause a nonzero exit status.

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

## Upgrade the toolkit

From a clean checkout:

```sh
python scripts/constitution.py upgrade
```

This fetches `origin/main` and tags, fast-forwards only, validates the new checkout, and uses the new CLI to synchronize enrolled targets. It never force-resets local changes. Review and commit your intentional source edits before upgrading; generated catalog refreshes count as source edits too. The Git remote is your chosen source of executable code, so use a repository you trust.

For a controlled release, check out a published tag such as `v0.1.0`, run `check`, then `sync --all`. Review `CHANGELOG.md` for migration notes. The current schema is version 1; future incompatible state changes must ship a migration before sync is allowed.

## Roll back an installation

The installer prints a snapshot ID. To undo that target's transaction:

```sh
python scripts/constitution.py rollback --snapshot SNAPSHOT_ID
```

Rollback restores original file bytes and removes files created by the transaction. It refuses if a file changed afterward, including subsequent installation state. Roll back in reverse order. Preserve and reconcile later edits rather than forcing a rollback.

To roll back the shared policy release instead, check out the previous Git tag and synchronize. Keep the source checkout and private state backups; snapshots can contain private preexisting instructions and must never be committed.

## Convenience without a hidden scheduler

The installed onboarding and maintenance skills work from Codex or Cursor. A manual GitHub Actions catalog-refresh workflow produces a reviewable artifact. No scheduled job or paid evaluation is enabled by installation. If you add a schedule later, notify only on actionable changes and run the same tested commands.
