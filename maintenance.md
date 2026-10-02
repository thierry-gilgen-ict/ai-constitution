# Maintenance

Keep the constitution useful, short, and evidence based.

1. Run `python scripts/constitution.py update` to collect official-source change observations. Network errors are reported separately; they never remove a working route.
2. Review the generated local report. A changed page hash is a signal to investigate, not proof of a model release. Open relevant sources and verify exact product availability.
3. Edit `registry/models.json` for verified facts and `registry/routes.json` for deliberate routing choices. Record source references, verification dates, and the basis for each choice.
4. For a new default, compare representative tasks using `checks/evaluation.md`. Initial recommendations are explicitly provisional. Do not call paid APIs without an agreed budget.
5. Review affected guidance too: a new model may make an old prompt workaround unnecessary. Change stable principles only when the evidence supports it.
6. Run `build`, `check`, the tests, and `scan`. Review the diff and bump `VERSION` for a released change. Explain the impact in `CHANGELOG.md`.
7. Run `sync --all` to update registered, unpinned local installations. Review pending cloud/Bot steps. Start fresh sessions and verify instruction loading.

Run all command names through `python scripts/constitution.py COMMAND` or the PowerShell wrapper. See [the update guide](docs/updates.md) for the full workflow.

Use `rollback --snapshot ID` to reverse a local installation transaction. The rollback checks for later edits first. Use a previous Git release and synchronize to roll back the published policy version.
