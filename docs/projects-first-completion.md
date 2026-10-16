# Projects-first delivery map

The 0.7.1 preview completes the repository implementation of the projects-first usability upgrade. The table maps each recommendation to its actual workflow. Implementation and automated checks are separate from hands-on acceptance; this document does not certify native client behavior or hardware compatibility.

| Recommendation | Implemented entry point and behavior |
| --- | --- |
| 1. Reliable launch | Launcher reconnect/start, bounded bootstrap, sign-in pause, stale observations, incompatible-version guidance, component errors and queued navigation during startup |
| 2. Navigation | Six destinations, contextual pages, opaque project URLs, Back/Forward and a narrow-screen menu |
| 3. Onboarding | Project, local-model or worker paths; bounded discovery; application choices; optional configuration mapping and architecture follow-up; private saved progress |
| 4. Project home | Overview, Instructions, Architecture, Apps & models, Configuration & backups and Activity; explicit retained inspection, preparation, toolkit installation, synchronization and common client launcher |
| 5. Useful Home | Recent/favorite projects, resumable or dismissible setup, attention items, active operations and environment/version identity |
| 6. Worker setup | Platform/package selection, integrity/signing status, complete start/pair commands, owner-local access commands and separate readiness links |
| 7. Structured editors | Toolkit, ordered preparation, routing and resource-rule forms with advanced JSON; valid unexposed fields round-trip |
| 8. Model guidance | Up to three estimated memory-fit candidates, context advice, explicit download/testing/route steps; unavailable evidence remains unknown |
| 9. Change review | Scope/effect/verification/recovery presentation; isolated instruction, template, toolkit and recipe candidates; fingerprint checks before publication or application |
| 10. Health | Needs attention, review items, exceptions and not-checked coverage; structural and semantic evidence remain distinct |
| 11. Recovery | Durable operation references and owning-workflow recovery; supported cancellation only; no automatic uncertain replay |
| 12. Notifications | Retained actionable failures, acknowledgement distinct from resolution, grouped repeats and bounded history; paginated Activity includes older unresolved work |
| 13. GPU release | Fallback checks, response draining, unloading and residency evidence; active requests and protected GPUs retain existing safeguards |
| 14. Accounts | Account/application/machine mappings, observed identity/source/time, unknown usage and shared-subscription deduplication; launch never changes native login |
| 15. Architecture templates | Component roles, requirements/conflicts, references, variable names, acceptance checks, capture review and isolated candidate publication |
| 16. Visual/accessibility foundation | Calm green/serif appearance, 16px text, responsive components, visible focus, reduced motion and status announcements |
| 17. Search | Keyboard palette, recent destinations, project/account/model/template/machine/settings/operation metadata and library filenames; no conversation or secret-value search |
| 18. Help/demo | Per-page illustrated help, synthetic screenshots and a separately labelled in-memory demo with network connections denied |

## Private state and compatibility

The update adds private presentation records under the controller's `workspace` directory:

- `ui.json`: favorites, recents and incomplete onboarding. It grants no operational permission.
- `ui-drafts.json`: instruction/template candidates outside the active library.
- `editor-drafts.json`: validated toolkit/preparation candidates. Saving does not install assets, run commands or change the saved active recipe.
- `project-inspections.json`: up to 100 retained explicit inspections. Reading a project page never starts a fresh inspection; the displayed collection time remains visible.

These files stay outside the public checkout and are included when backing up the full private controller directory. Existing operation journals hold targets and stage timestamps for new operations. Old records without these fields remain readable and explicitly unknown. Unresolved work is not hidden behind the completed-history limit.

Existing Studio material, project enrollment, follow/pause policies, pins, audit grants and schedules are preserved. Architecture selection during onboarding opens a separate review after enrollment; it cannot implicitly apply a template. Remote project metadata remains owner-local: the UI cannot turn inventory sharing into remote command execution.

## Next acceptance session

Repository verification uses disposable homes, synthetic UI fixtures and fake client/runtime responses. Review CI and package results for the exact merge before choosing a candidate deployment.

1. Install the candidate separately from development and preserve the current executable, private-state backup and startup preferences.
2. On the main Windows machine, test launch/sign-in, onboarding and application selection, edit protection, draft publication and recovery.
3. On the second Windows machine, test package setup, owner-local grants and disposable project scan → preview → correction → verification → rollback.
4. Deliberately test real model qualification, response draining and GPU release. Browser fixtures cannot establish those outcomes.
5. Record macOS/Linux native acceptance and three unfamiliar-user trials separately. Measure hosted onboarding and whether users understand the scope before approving a change.

The local production application is not switched by committing this implementation. Use the existing guarded update workflow after checking active work. Do not describe the preview as production-ready until blocking acceptance findings are addressed.
