# Publishing a release

Publish from a clean reviewed commit on `main`. Keep the core toolkit version separate from the companion's preview status: a toolkit release does not certify physical inference hardware or make an unsigned executable generally available.

## Prepare the revision

1. Update the three-part numeric `VERSION`, move completed changes into a dated `CHANGELOG.md` entry, and update affected guides and the README. Do not rename old tags or overwrite an existing release.
2. Run `python scripts/constitution.py build` to regenerate adapters and routing. Inspect the diff for private data, accidental generated changes and stale claims.
3. Run the checks in [Contributing](https://github.com/thierry-gilgen-ict/ai-constitution/blob/main/CONTRIBUTING.md). Require green GitHub tests and history secret scanning on the revision being merged.
4. Merge the reviewed pull request, fast-forward the local `main`, and confirm it matches `origin/main`. Record its full commit ID. Check the merged revision's CI too.

## Build public assets

From the merged checkout:

```sh
python scripts/constitution.py release --output dist/ai-constitution-release.zip
python scripts/constitution.py export --output dist/grok-bot.zip
gh workflow run package-preview.yml --ref main
```

The release command returns a SHA-256. Write that digest and archive filename to `ai-constitution-release.sha256`; the managed updater requires those exact two asset names. Validate the archive manifest with `scripts.releases.unpack` before publishing, including the previous supported updater when changing the archive format or allowlist. Use a temporary home/state for an upgrade rehearsal; never exercise an installer against a maintainer's real client files.

Wait for the packaging workflow on the exact recorded commit. Download its Windows/macOS/Linux artifacts. Each artifact contains a portable `ai-constitution-worker-<os>-<architecture>.zip` and matching `.zip.sha256`; publish those inner files, not a second ZIP wrapper around the workflow artifact. Each build runs the frozen-application smoke check. Preserve license notices and dependency manifests inside the archives.

Create `SHA256SUMS.txt` covering all published payloads. Compare native package digests to their adjacent checksum files. Review any screenshots manually; use fixture accounts and paths. Do not publish private Studio drafts, local state, env files, account exports, support logs or build-environment directories.

## Publish and verify

Create a draft GitHub release with a new `vX.Y.Z` tag targeting the recorded commit. Attach all reviewed assets before making it public. Its notes should contain:

- The concrete workflows added, changes since the previous version and links to versioned documentation.
- Download guidance separating the managed instruction archive, Grok Bot bundle and unsigned native companions.
- The tested commit and links to successful checks/package builds, plus unverified physical acceptance gates.
- Upgrade steps, preserved private state, opt-in settings and material limitations.

Publish the complete draft and mark the toolkit release latest. Verify the tag commit, uploaded asset sizes and SHA-256 digests. Download the public managed archive and checksum through the normal updater and validate them without changing real installation state. Check README links and ensure the local worktree is clean.

The core updater uses the latest published non-prerelease and named archive assets. If a toolkit release is marked prerelease, it will not become the default `upgrade` target. The optional Local Control binaries can remain explicitly labelled preview within a normal toolkit release.
