# Contributing

Contributions should reduce setup work, improve correctness, or make a real limitation clearer. Prefer a narrow fix with evidence over adding more universal instructions.

## Development

```sh
python scripts/constitution.py build
python scripts/constitution.py check
python scripts/release_inventory.py
python -m unittest discover -s tests -v
python scripts/constitution.py scan
python scripts/check_docs.py
python scripts/check_screenshots.py
```

Use Python 3.11+ and the standard library. Keep network access out of unit tests. Use temporary homes and projects for installer tests; never modify a contributor's actual client configuration in CI.

For worker TLS coverage, install `requirements-local-node.txt` in an isolated environment; CI tests Python 3.11 and 3.13 on Windows, macOS and Linux. Desktop/tray/build dependencies are optional and listed separately. The [architecture guide](docs/architecture.md) maps modules to responsibilities; [Local Control](docs/local-control.md) describes the inference and lifecycle invariants.

Use the issue forms for reproducible bugs and workflow proposals. Include the application version, OS and relevant sanitized evidence, never account exports, private configuration files or raw logs. Security reports belong in [private vulnerability reporting](https://github.com/thierry-gilgen-ict/ai-constitution/security/advisories/new).

## Model updates

Use `update` for imported metadata. Use a source-linked record in `registry/overrides.json` for a verified release missing upstream. Do not imply that catalog availability means availability inside Codex, Cursor, or Grok Bot. Include the source and verification date for curated route changes. State whether a recommendation has been evaluated.

## Instruction changes

Explain the recurring problem the instruction solves. Keep the core small and move task-specific guidance into the appropriate module. Preserve user intent, host permissions, and platform-specific loading behavior. Do not add ceremonial approval or testing requirements.

## Pull requests

Describe the problem, resulting behavior, validation, and relevant limitations. For a new adapter, include a native loading reference and a reproducible activation check. For installation changes, test preservation, drift, failure recovery, and rollback.

Never commit local state, credentials, personal paths, account exports, or private project facts. Review the staged diff and run the scanner before publishing. A clean heuristic scan does not replace that review.

After adding or removing a public source file, run `python scripts/release_inventory.py --write` and review the inventory diff. Exporting does not recursively pick up unrelated or ignored files. Native builds require a fresh empty output directory. CI scans actual upload inputs before publishing packages or reports; a failed scan blocks the upload even when the preceding test failed. Do not bypass a scanner finding by excluding an entire manifest or report.

Maintainers should follow the [release guide](docs/releasing.md) for versioned archives, package checksums, smoke checks and upgrade documentation.

For dashboard changes, run `npm ci --ignore-scripts`, `npx playwright install chromium`, and `npm run test:browser`. These tests use an isolated synthetic server on port 18766, never your real Local Control state. Keep node_modules and browser reports ignored. The optional restic, signing and physical acceptance workflows are described in the documentation; do not claim fixture success establishes physical hardware compatibility.

Refresh the illustrated manual with `npm run screenshots` after dashboard or capture-source changes. Review the images before publication. The [screenshot maintenance guide](docs/screenshot-maintenance.md) explains fixtures, captions, CI comparisons, privacy review and explicitly pending external application captures.
