AI Constitution 0.3 makes ongoing workspace maintenance easier to review and recover.

- An **Update available** notification, GitHub release notes, verified application staging, idle-session restart checks and retained rollback copies. Compatible paired workers expose the same controls.
- A project discovery wizard with conflict/adoption previews, configuration associations and richer project cards.
- Pinned template revisions, saved revision history, immutable inheritance, dependency constraints and monorepo manifest capture. Unsaved templates no longer revert during synchronization.
- Optional encrypted restic backups, reviewed retention, verified restoration and explicit OS backup schedules. Rejected backup jobs retry without consuming the daily interval.
- Durable actionable failures, inline job progress, private Windows ACLs and Python 3.11-compatible junction protection.
- Last-successful subscription reports, bounded history and alerts, read-only OpenAI/Anthropic API cost connectors, model-definition review inbox, measured performance profiles and pre-dispatch fallback selection.
- Real browser journeys and accessibility checks, native package SBOMs, release build attestations and optional signing/notarization hooks.

The instruction toolkit remains standard-library-only. Local Control native packages remain **preview** and are unsigned unless their manifest explicitly reports a configured publisher signature. Physical two-machine GPU qualification, a 48-hour soak and external usability trials remain documented acceptance gates. No native Cursor Agent switching, in-progress generation migration or distributed VRAM pooling is claimed.

Read the versioned [workspace guide](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.0/docs/workspace-upgrades.md), [backup guide](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.0/docs/encrypted-backups.md) and [compatibility matrix](https://github.com/thierry-gilgen-ict/ai-constitution/blob/v0.3.0/docs/compatibility-matrix.md). Keep your existing private state; use the manual upgrade once from packages predating the dashboard updater.
