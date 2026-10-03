# Changelog

## Unreleased

## 0.3.1 — 2026-10-03

- Restricted public exports and native build inputs to a reviewed file inventory. Reject sensitive filenames and preserve existing output by requiring fresh build directories; compile the native companion from the isolated public input tree.
- Separate public native assets from compiler intermediates, reject escaping/cyclic native aliases, include internal alias contents and smoke-test an extracted copy of the distributed ZIP.
- Added checksum-verified Gitleaks publication gates for native packages, complete release assets, browser reports, screenshot comparisons and catalog patches. Reject unsafe archives and block uploads on unresolved findings or scanner failures; dismiss only cryptographically verified manifest checksums.
- Enabled dependency security-fix pull requests and added weekly dependency reviews for Python, npm and GitHub Actions. Isolated remaining test home defaults from real private configuration.
- Added an illustrated manual with 80 images across all 14 dashboard pages, detailed workflows, recovery states and responsive layouts. Updated the README and guides with screenshots beside their instructions.
- Added one-command fixture captures, real isolated CLI transcripts, screenshot provenance and integrity/freshness/coverage checks. CI produces visual comparisons and enforces image and release-size budgets. External native application captures remain explicitly pending.

## 0.3.0 — 2026-10-03

- Added GitHub update notifications, verified controller/worker staging, guarded restart and retained application rollback copies.
- Added project discovery and batch enrollment with adoption/conflict previews, configuration associations and richer project cards.
- Fixed unsaved architecture revisions reverting during synchronization; added follow/pin policy, revision history, immutable inheritance, numeric dependency constraints and monorepo capture.
- Fixed rejected scheduled backups consuming their full interval and tilde paths resolving differently at execution. Added durable reservations, bounded retry, optional encrypted restic repositories, retention previews, verified restoration and per-user OS schedules.
- Kept unacknowledged failures visible, coalesced recurring errors and removed idle synchronization from Activity. Added inline progress and recovery actions.
- Enforced Windows private-state ACLs and rejected reparse points on Python 3.11 as well as newer versions.
- Added last-successful account reports, observation history, usage alerts, API organization cost connectors, a reviewed model-definition inbox, measured hardware profiles and pre-dispatch fallback selection.
- Added worker release-package downloads and optional Windows/macOS worker autostart.
- Added synthetic Playwright journeys and accessibility checks, release assembly/attestations/SBOMs, optional signing hooks and explicit physical acceptance procedures.

Private state remains outside the checkout. New backup/collector/autostart actions are opt-in. Application release checks are on by default while the controller runs and can be disabled. Native packages remain preview; physical multi-machine/soak/usability acceptance and publisher signing identities remain external gates.

## 0.2.0 — 2026-10-03

Shared toolkit release with an optional **Local Control preview**. Native companion packages remain unsigned; physical fleet validation is still in progress. See [upgrade instructions](docs/updates.md) and [preview boundaries](docs/desktop-preview.md).

- Publish managed-upgrade archives, portable worker packages and checksums with the release. Add a documentation index, contribution issue forms, current validation evidence and a maintainer release guide.

- Add the private workspace control center: per-project automatic instruction/template synchronization with pin and drift protection; subscription login mappings; an opt-in, read-only Codex account/usage collector; worker diagnostics and bounded integration logs; manual/imported provider observations with explicit freshness and scope.
- Add configurable library, package and Ollama storage, verified model copies and stopped-service profile relocation; dashboard worker downloads and complete cross-platform setup/upgrade commands. Native builds produce a registerable portable ZIP.
- Add central private project configuration mappings, verified backups, opt-in schedules and restore into a new directory. Backups contain secrets and require private storage; they are not encrypted by the application. Capture architecture proposals from supported existing-project manifests and environment-variable names, discarding values and executable setup content.

- Add portable architecture baselines with component repositories, declared compatibility, setup guidance, environment-variable names, bounded scaffold files and agent handoffs. Dashboard and CLI previews protect existing files and apply onboarding with reversible transactions.
- Add a private constitution-library editor with search, generated-source previews, stale-edit checks, draft history, reviewed activation and conservative merging from newer controller bundles. Include the library in portable packages; existing workers need no upgrade for these controller features.

- Add per-machine display-driver inventory, Windows Update display-driver checks, version-change observations, and native OS/vendor update controls. Pause the whole physical host before update handoff, retain worker maintenance across restarts, and require an explicit recheck/resume. Existing workers need the updated package; installation and reboot remain OS-confirmed actions.

- Add conservative hardware-based context advice, sampled model-residency peaks, explicit remote-first/Gaming eligibility policy, durable health history and cancellation before queued inference is sent.

- Add guided local setup, durable jobs with interrupted-work recovery, bounded inference queues, process-identity/session tracking and graceful controller stop.
- Verify function calls, full-history replay, context and CPU placement before route switching; retain ordered fallbacks and drain machines for maintenance.
- Add expiring one-use pairing, distinct revocable credentials, worker removal/rotation, health checks and an allowlisted support report.
- Add explicit bounded coding evaluations, dashboard project launch, optional tray/login startup and portable unsigned Windows/macOS/Linux build jobs.
- Keep physical hardware, signed distribution, mixed-fleet soak and external usability validation as documented preview release gates.

- Add explicit portable-lock adoption, private policy overlays, immutable instruction-library upgrades with transactional activation, and effective-policy explanations.
- Make routine model refreshes private; contributors use `--source-checkout`. Validate known capability, context, modality and cost types while preserving unknown upstream fields.
- Retain pending source changes until an exact observed revision is explicitly reviewed; migrate legacy observations without treating them as acknowledgments.

- Add the optional Local Control preview: private dashboard, Ollama lifecycle controls, llmfit hardware suggestions, Hugging Face GGUF browsing, explicit model downloads, paired HTTPS workers, project launchers and request-boundary Gaming mode.
- Give local coding sessions a dedicated gateway alias and session-specific metadata while retaining existing client approvals and project instructions. Cursor support runs the local Codex agent inside its terminal.
- Serialize core enrollment changes across processes, recover from a final journal write failure, allow interrupted rollback to resume, and preserve project pins when onboarding again.
- Document current validation, preview limits and the prioritized project review.

## 0.1.0 — 2026-10-02

- Shared core, engineering and research modules, and generated client routing.
- Native Codex and Cursor file adapters with project onboarding skills.
- Explicit xAI Grok Bot description, skill, cloud onboarding, and portable export.
- Full models.dev snapshot: 225 providers and 8,371 provider-scoped definitions at initial retrieval.
- One-command catalog refresh, semantic diffs, provenance, reviewed overrides, and offline queries.
- Ollama and OpenAI-compatible local model discovery without inference.
- Additive installation, versioned project bundles, drift checks, private snapshots, pinning, synchronization, and rollback.
- Source-first upgrades, cross-platform tests, public-file scanning, and an Engawa-inspired README with original artwork.

Initial route recommendations are provisional. Live client activation is a separate acceptance step. See [architecture](docs/architecture.md) for first-release boundaries.
