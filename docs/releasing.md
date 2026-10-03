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

## Unified release workflow

From a reviewed, green `main` revision whose VERSION and release notes match:

```sh
gh workflow run release.yml --ref main -f version=0.3.0
```

The workflow validates source and browser journeys, builds/smoke-tests Windows x64, macOS ARM64 and Linux x64 packages, creates CycloneDX SBOM files, verifies every package version/checksum, assembles the managed/Grok bundles and attaches GitHub build attestations before uploading all assets to a draft release. It publishes the draft only after every upload succeeds, so update checks never observe a partial release. `docs/release-notes.md` is the reviewed publication text. Do not rerun with an existing release tag; failed attempts must be inspected rather than overwritten.

Verify downloaded assets with GitHub's attestation tooling, for example `gh attestation verify ARCHIVE --repo thierry-gilgen-ict/ai-constitution`. The dashboard separately validates the release checksums and file manifests. See [GitHub's official attestation guide](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

### Optional publisher identities

`package_local.py` invokes `sign_package.py` before hashing the native payload. On a controlled Windows build host, set `WINDOWS_SIGN_CERTIFICATE` to a private PFX file and `WINDOWS_SIGN_PASSWORD` in the process environment, with Windows SDK `signtool` on PATH. On macOS, install the Developer ID identity in the build keychain and set `MACOS_SIGN_IDENTITY`; configure a notarytool keychain profile and set `MACOS_NOTARY_PROFILE` to request notarization of the completed archive. Signing/notarization failures fail the build. Never commit certificates, passwords or keychain exports.

The default hosted workflow has no publisher identities provisioned and therefore emits **unsigned preview** manifests. To publish signed builds, provision these inputs on a controlled runner or a reviewed secret/keychain setup step; repository permissions alone cannot create an OS signing identity. GitHub provenance and SBOMs work independently of signing. A notarized ZIP is not a stapled macOS application bundle.
