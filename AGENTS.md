# Working on AI Constitution

This repository is public. Keep private state, host paths, credentials, and project inventories out of tracked files.

- Runtime source: `scripts/constitution.py` and `scripts/catalog.py`; Python 3.11+, standard library only.
- Model data: refresh the imported snapshot with `update`. Use source-linked `registry/overrides.json` entries for verified additions missing upstream.
- Generated files: run `python scripts/constitution.py build`; do not hand-edit `routing.md` or generated adapters.
- Verification: `python scripts/constitution.py check`, `python -m unittest discover -s tests -v`, and `python scripts/constitution.py scan`.
- Test installers only in temporary homes and projects. No paid inference or live client writes in tests.
- Preserve managed-block ownership, private transaction journals, symlink protections, and non-destructive rollback.
- Keep platform capabilities honest: files installed, instructions loaded, model access, and evaluated performance are distinct claims.
- Document behavior changes and upgrade implications. Add focused tests for installation or catalog invariants.
