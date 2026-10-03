# Architecture

The toolkit uses Python's standard library. `scripts/constitution.py` owns rendering, managed installation, enrollment, drift checks, rollback, exports, and the command interface. `scripts/catalog.py` owns public fetches, catalog validation and diffs, and local model discovery. The PowerShell wrapper passes arguments through unchanged.

## Public source and private state

The checkout holds authored policy, curated routes, generated adapters, and the bundled community catalog snapshot. Private state defaults to `~/.config/ai-constitution/state/`, outside the checkout. Routine refreshes write immutable snapshots under `catalogs/`; private preferences live in `overrides/policy.json`; managed library upgrades use `releases/` and a journaled active-release pointer. Tests use isolated temporary roots. `.local/` is reserved and ignored for contributor scratch state.

Global installs render module copies into `~/.config/ai-constitution/libraries/<client>/`. Their installation metadata points back to the source checkout. Project copies use relative paths and a lock file with no local absolute paths.

## Managed files

`AGENTS.md` uses a marked section so surrounding instructions survive byte-for-byte. Generated bundle files are owned as whole files. A previous checksum is checked before replacement; an unowned file with different contents causes a conflict. Project context is user-owned and excluded from synchronization.

All writes are preflighted. Each transaction journals the prior bytes privately, writes each file through a temporary sibling and atomic replace, then marks itself applied. A caught write error restores completed files. This handles ordinary errors; abrupt power loss can leave a prepared journal requiring manual inspection. It is not a distributed transaction or a database.

Symlinks and junctions in installation destinations are rejected. New source releases must preserve these boundaries. The tool does not recursively delete directories.

For a relocated Cursor profile, `--cursor-dir` selects its real configuration directory explicitly. The choice is retained in private enrollment state; library and project files keep their standard locations. No path through a junction is traversed to perform writes.

## Deterministic generation

`scripts/architecture.py` validates portable component snapshots and plans project baselines using the existing installer transaction. Ownership fingerprints live in private `state/architectures.json`; project snapshots contain no controller paths. `local_control/studio.py` stages private library edits, uses trusted imported render/validation functions, and exposes preview hashes for saves, activation and application. The controller serializes studio requests; workers and inference tokens have no access to this API. Preview hashes include pre-existing target fingerprints, so stale browser plans cannot silently replace newer work.

`build` produces `routing.md` and native adapters from the authored core and small route registry. `check` recomputes those artifacts and fails on drift. Source URLs and evidence are retained. The large catalog never enters every agent prompt.

## Product boundaries

File verification is deterministic. Model compliance, client instruction discovery, model availability, and workflow improvement are separate acceptance checks. The program does not claim a universal precedence hierarchy, force model switches, or change host approval controls.

## Intentional first-release limits

- Codex and Cursor have native file installers; actual Grok Bots have an explicit cloud onboarding/export path.
- Arbitrary semantic conflicts between existing instructions require agent or human review.
- Custom `CODEX_HOME` layouts use manual adapter installation in this release.
- Core `local` discovery lists metadata. The optional Local Control companion separately performs explicitly requested model downloads, inference probes and gateway routing; see [Local Control](local-control.md).
- Route recommendations are provisional and small; the broad catalog has community provenance.
- Refreshes and installations are explicit. There is no daemon or silent self-update.
