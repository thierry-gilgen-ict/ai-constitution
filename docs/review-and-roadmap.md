# Review and roadmap

Reviewed October 2, 2026. The baseline was v0.1.0, commit `96c2b277a3ed86c6119b3f4481342838434e4b54`. This document separates reproduced findings, fixes in this change, and proposed work. It is not an independent certification or a claim to be the best product in the category.

## Assessment

The strongest idea is the combination of a compact shared constitution, a refreshable model catalog, and low-friction project adoption. The source/runtime split, private machine state, managed-block preservation, cross-platform tests and honest platform distinctions are worth keeping.

The original release was a useful foundation, but its local-model feature only discovered metadata. The Local Control preview makes the workflow materially more useful: hardware-aware selection, explicit downloads, real project sessions and verified GPU release. Reliability and convenient recovery matter more than adding dozens of instruction adapters.

## Reproduced issues addressed in this change

| Finding | Impact | Change |
| --- | --- | --- |
| Concurrent installs read the same enrollment database, then one overwrites the other's registration | A project can have installed files but disappear from future sync | OS-backed state lock; competing installation/rollback stops before reading stale state and can be retried |
| Final journal write fails after files are replaced | Caller sees failure while changed files remain and the journal is still prepared | Final journal write is inside the transaction's recovery boundary |
| Rollback fails after restoring only some files | Retrying rejects files already restored by the first attempt | Persist a rolling-back state; accept only the exact before/after bytes while resuming |
| Re-onboarding a pinned project clears its pin | A previously frozen project becomes eligible for sync | An omitted pin option preserves the existing pin |

Regression tests exercise these failure cases in temporary workspaces. The Local Control service independently serializes lifecycle operations and uses request leases before unloading models.

## Implementation update

The follow-up implements portable adoption; immutable library activation and private policy/catalog state; durable source review; known-field validation; effective-policy explanations; guided setup; recoverable jobs and session-aware shutdown; expiring, revocable pairing; bounded queues; machine draining; small measured coding fixtures; and unsigned portable build automation. See [Local Control](local-control.md) and [Desktop preview](desktop-preview.md) for exact behavior and limitations.

Automated verification now includes 97 tests on the reference Windows environment (96 passed, one symlink privilege skip). The updated Windows controller preserved Gaming mode on restart, its CPU route passed function-call/full-history checks and all eight bounded coding cases, and measured GPU allocation remained zero. Cross-platform CI and physical-device evidence must be reported separately.

The original priorities below are retained for context. Their implementations do not satisfy every release gate: signed/notarized distribution, physical Mac and second-computer tests, a 48-hour mixed-fleet soak, repeated sleep/wake tests, external first-run usability trials, broad coding evaluations, interoperability adapters and unattended fleet rollout remain open. Automated tests cannot substitute for missing hardware or test participants.

## Original review priorities

| Priority | Addition or enhancement | Why it matters | Acceptance evidence |
| --- | --- | --- | --- |
| P1 | Adopt an existing project lock on a new computer | With an empty private enrollment database and a newer library, onboarding can reject the old managed bundle as unmanaged | Clone an enrolled project on another machine, verify its recorded hashes, adopt without overwriting local context, then upgrade |
| P1 | Separate upstream releases, personal policy and model snapshots | A catalog refresh dirties the checkout; committing personal changes can make `upgrade` unable to fast-forward | Upgrade a customized installation and refreshed catalog without manual Git conflict work or lost preferences |
| P2 | Keep source changes pending until explicitly reviewed | A changed documentation hash is currently recorded as the next baseline, so a second check can look unchanged without human review | Repeated checks retain pending changes; an explicit acknowledgment records reviewed evidence |
| P2 | Validate known capability, cost and context field types | The catalog currently checks object structure but can accept misleading strings or negative values in known fields | Invalid known fields fail safely while unknown upstream fields remain preserved |
| P2 | Guided first-run setup and packaged launchers | Requiring Python, Git, CLI setup and a terminal is friction for new users | A new Windows or Mac user reaches a verified coding request in under ten minutes without editing config files |
| P2 | Measured model profiles | Metadata fit and advertised tool use are not coding-quality evidence | Publish reproducible tool-call, patch, test and latency checks across representative hardware and quantizations |
| P2 | Reliable service and fleet lifecycle | The preview has foreground service startup and manual token rotation | Tray/menu-bar controls, graceful stop, autostart opt-in, token revocation, node removal, update rollback and health history |
| P2 | Physical Mac and mixed-machine validation | Shared code and CI cannot establish Metal behavior, LAN stability or CPU fallback performance | Test Apple Silicon, Windows NVIDIA and a mixed cluster through sleep/wake, network loss and model updates |
| P3 | Explain effective instructions and routes | Users need to know which file or preference produced a recommendation | Show provenance, scope, overrides, confidence and the exact route that was selected |
| P3 | Interoperate with established rules tools | Maintaining every adapter duplicates mature projects' work | Import/export compatible instruction bundles with round-trip tests |

## Comparison with adjacent projects

| Project | Established strength | What AI Constitution should contribute |
| --- | --- | --- |
| [Rulesync](https://github.com/dyoshikawa/rulesync) | Broad agent integration, rule conversion and packaging | A compact opinionated baseline, source-linked model decisions and a local workflow that is verified end to end |
| [Ruler](https://github.com/intellectronica/ruler) | Centralized multi-agent instructions and distribution | Reversible adoption, visible ownership and convenient runtime management |
| [models.dev](https://github.com/anomalyco/models.dev) | Broad community provider/model metadata | Product-specific availability distinctions, private preferences and evaluated recommendations |
| [llmfit](https://github.com/AlexsJones/llmfit) | Hardware detection and model-fit estimates | Turn estimates into selected GGUF downloads, a tested project route and one-click GPU release |
| [LiteLLM](https://github.com/BerriAI/litellm) | Broad gateway provider support and routing features | A small local Ollama workflow; consider integration before attempting enterprise gateway breadth |

These projects were compared from their public source repositories and documentation, not a controlled usability benchmark. “More useful” should be demonstrated by a narrower, completed workflow and published results rather than claimed through feature counts.

## Release criteria

Before calling Local Control generally available: validate real Macs and a two-machine cluster; test a coding task through repeated mode switches; finish token revocation and graceful service controls; document recovery from interrupted downloads, controller restarts and Ollama upgrades; and run a small external usability trial. Keep the preview label until those checks have evidence.

The useful promise is specific: **less setup, clearer model choices, fewer repeated instructions, and predictable control over local resources.**
