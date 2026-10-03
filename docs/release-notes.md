AI Constitution 0.3.1 hardens public packaging and adds the complete illustrated manual.

- Public exports and native build inputs include only the reviewed release inventory. Sensitive filenames are rejected; unlisted and ignored local files cannot silently enter a release.
- Native builds compile from an isolated public source copy and require an empty output directory. Rejected stale output is preserved.
- Every package/report upload runs a checksum-verified Gitleaks scan first. Unsafe/nested private archive entries, unresolved findings, missing inputs and scanner failures block upload. Manifest checksum exceptions require verification against the actual packaged file.
- Dependency security-fix pull requests are enabled, with weekly Python/npm/GitHub Actions update reviews.
- The README and manual now cover all 14 dashboard pages with 80 images, real isolated CLI transcripts, synthetic data, and checked screenshot provenance/freshness.

Read the versioned [release guide](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.1/docs/releasing.md), [security policy](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.1/SECURITY.md) and [illustrated manual](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.1/docs/manual/README.md).

Download the managed instruction archive for the toolkit, the Grok Bot bundle for cloud setup, or the Windows x64/macOS ARM64/Linux x64 portable companion. Preserve your existing private state and pairing when upgrading. Existing 0.3.0 controllers can use the normal dashboard update flow while clients are idle; source users can pull the reviewed revision. Older public source archives remain readable; custom libraries exported with the new tooling need their own reviewed file inventory.

The instruction toolkit remains standard-library-only. Native companions remain unsigned **preview** builds. Secret scanners do not guarantee detection of arbitrary secrets, image pixels or compressed executable bytecode. Physical GPU qualification, a 48-hour soak, external usability and native application screenshots remain explicitly pending; see the [acceptance matrix](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.1/docs/compatibility-matrix.md).
