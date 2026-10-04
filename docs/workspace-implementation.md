# Workspace workflow implementation

Implementation started October 4, 2026 from v0.3.1. This page tracks the accepted plan; it does not claim that an unfinished feature has shipped.

| Workstream | Implementation status | Acceptance evidence |
| --- | --- | --- |
| Shared workflow foundations | Implemented and fixture-verified | Checkpoints, deterministic previews, additive private state and journaled removals |
| Effective setup inspector | Implemented | File/loading/access evidence remains distinct |
| Workspace change previews | Implemented | Per-project transactions, canary selection, pins, pauses and stale review checks |
| Project preparation | Implemented | Reviewed argument lists, private environment references and interrupted-step review |
| Global search and command palette | Implemented and browser-verified | Keyboard metadata search; secret contents excluded |
| Agent toolkits | Implemented | Native adapters, conservative ownership, explicit interoperability losses |
| Subscription-aware launch | Implemented | Observation freshness, deduplication and local/native launch choices |
| Controller synchronization | Implemented; physical networking pending | Separate TLS scopes, cached snapshots, three-way conflicts and deliberate staging |
| New-computer recovery | Implemented | Portable mappings, template/toolkit bindings; separate encrypted config restore |
| Model comparison lab | Implemented for local fixtures | Repeated bounded evaluation, fingerprints, start budgets and zero paid calls |
| Automatic resource profiles | Implemented; physical triggers pending | Opt-in triggers, manual priority, cooldown, idle deferral and fair admission |

The implementation preserves the standard-library core, managed ownership and private transaction journals. Runtime operations require fresh reviewed plans. Remote project management has a different permission boundary from inference-worker pairing. Existing automatic synchronization remains subject to its pins, pauses and drift checks.

Each feature includes appropriate fixture tests, browser journeys, documentation and screenshot updates before publication. Physical multi-computer/GPU/sleep-wake validation, the availability soak, signing identities and external usability evidence remain governed by the [acceptance matrix](compatibility-matrix.md).
