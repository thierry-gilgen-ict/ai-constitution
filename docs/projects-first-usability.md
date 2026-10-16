# Projects-first workspace preview

Choose a project, choose a coding application, review readiness, and open a new session. Hosted Codex, Cursor and Claude Code workflows do not require Ollama or a local model. Existing native sign-ins stay on their owning computer.

## Find your work

| Destination | What belongs here |
| --- | --- |
| Home | Recent and favorite projects, setup, attention items |
| Projects | Checkouts, project detail, architecture templates, toolkits and preparation |
| Instructions | Published library, isolated drafts, health and history |
| Models & machines | Models, worker setup, package maintenance, GPU controls and measurements |
| Activity | Retained operations, recovery and project synchronization |
| Settings | Accounts, storage, backups, updates, startup and schedule links |

Views use browser history and shareable local URLs. Project addresses contain opaque checkout identifiers rather than filesystem paths. Authentication fragments are consumed separately and removed before navigation. On a narrow panel use **Menu**; Escape closes it. **Ctrl/Cmd K** searches metadata, instruction filenames and retained operation labels, never conversations, secret values or raw logs.

## Connect a project

1. Choose **Home → Add a project**. Enter an existing folder, or explicitly choose a discovery root. Discovery is bounded to four levels and 5,000 directories.
2. Select the coding applications. PATH detection is advisory, not proof of sign-in or instruction loading. Existing portable bundles need explicit adoption.
3. Review the target and file differences, then enroll. A conflict preserves existing instructions and explains the next action.
4. Open project detail. Review installation, loading evidence, model access and configuration separately. **Open project** chooses the application, execution mode, Claude profile when applicable, and an optional account mapping.
5. Save incomplete onboarding to resume later. Architecture templates, local inference, collection and schedules are optional follow-up choices.

The native Codex launch uses its CLI terminal; Cursor hosted launch opens its application. Cursor local integration remains a terminal workflow. Claude uses its selected, enrolled profile. No launch migrates an existing conversation or switches native account credentials. Remote controller inventories are cached observations: open the checkout on its owning computer. Sharing metadata never authorizes arbitrary remote commands.

## Save a draft, then publish

New UI instruction and template drafts live in private `workspace/ui-drafts.json`, outside the published Studio library. **Save draft** validates a candidate without synchronizing it. **Instructions → Saved drafts → Review publication** shows the diff and affected enrollment policies. Publishing rechecks source and candidate fingerprints under the existing synchronization locks and records a recoverable transaction.

Following projects receive published changes according to existing policies. Pins, pauses and local modifications stay authoritative. Global activation remains a separate reviewed action. New captured templates must be saved and published before project application. Changing a candidate in another tab invalidates an older save. Discard requires the current candidate revision.

Existing Studio contents retain their previous meaning and synchronization behavior; upgrading does not retroactively approve or unpublish them. Legacy CLI/Studio APIs retain their existing reviewed-write contracts. Only the new candidate endpoints have isolated-draft semantics.

The visual toolkit, preparation and routing editors preserve fields they do not display. Advanced JSON remains available. Preparation command steps may use a relative working directory inside the enrolled checkout; other step types run at its root. Escapes and filesystem links are refused. Environment controls accept names, not secret values. Editing or capturing a template never executes project code.

## Add a worker or a model

The worker guide saves progress through platform, package, start, pairing, access and verification. Package metadata shows checksum and signing evidence; an unknown older package version stays unknown. Complete commands run from a fresh terminal in the extracted package folder. Check model connectivity, protocol capability and audit access separately. Inference pairing grants no instruction-file access; the worker owner approves that locally.

Model suggestions show up to three relative memory choices. Fast, Balanced and Larger tasks are estimated candidates, not coding-performance rankings. Inspect the exact download, license and client qualification before adoption. New installations start with an 8K context; existing choices remain unchanged. Use **Suggest a starting context** for hardware-specific advice, then save explicitly.

Gaming mode reports fallback checks, response draining, unloading and residency verification. It does not move conversations or replay generation requests. Ollama residency evidence is not total GPU-use evidence for other applications.

## Failures and recovery

Read requests and authentication bootstrap time out after eight seconds. Failed polling backs off; sign-in failures pause authentication reads until the user retries through the launcher. Old values remain labelled stale. A browser cannot restart a stopped controller: use the installed shortcut or the source installation's `open` command.

Activity reuses durable operation IDs. Cancel appears only for supported operations; interrupted or uncertain actions require inspection before a new attempt. Recent completed history is bounded to 50 entries alongside unresolved/active work. Acknowledgement is not resolution. Version changes offer a reload after saving instruction drafts.

The separate **demonstration** page uses fictional data and in-memory simulations. Its content-security policy denies network connections. Reset discards simulated changes; exit returns to the real dashboard. It cannot install software, launch a client or access a worker.

## Upgrade and acceptance

Test a candidate package with disposable state in a separate directory. Back up private controller and enrollment state, retain the previous executable and startup preferences, then use the guarded restart only after checking active sessions and operations. Never point development and production controllers at the same private state. Restore through reviewed recovery; do not silently reactivate schedules or permissions.

Automated browser fixtures exercise the interface and permission boundaries. They do not prove native client loading, real inference, GPU release, second-computer installation or macOS/Linux native behavior. Three unfamiliar-user trials and the physical acceptance checklist remain release gates before a production-ready claim. See the [compatibility matrix](compatibility-matrix.md) and [illustrated workspace walkthrough](manual/usability.md).
