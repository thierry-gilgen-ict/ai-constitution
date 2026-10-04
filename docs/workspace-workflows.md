# Workspace workflows

Local Control’s **Workspace workflows** page brings project setup and repeatable operations together. Use **Search · Ctrl K** (Cmd K on macOS) to find pages, enrolled projects, toolkit titles and library filenames. Search excludes private configuration contents, raw logs, credentials and conversations.

## Inspect, prepare and launch

Choose **Inspect setup** beside an enrolled repository. The inspector shows effective policy layers, route provenance, architecture, account mappings and an instruction-size estimate. It separates managed-file verification, client loading, observed model readiness and evaluated performance. A healthy machine without a ready alias is not evidence of model access.

**Prepare** detects a conservative recipe from requirements.txt, package-lock.json and Compose files. Review and edit its JSON before execution. Supported steps create a copied Python virtual environment, install locked dependencies, run reviewed runtime argument lists, start Compose, and check loopback HTTP health. Missing runtimes are prerequisites, not an excuse to download arbitrary installers. npm installation disables package lifecycle scripts by default; add only deliberately reviewed commands when necessary.

Select environment names in the recipe. Values come from the controller process or the project’s mapped private .env folder, remain outside previews, and are hashed to invalidate stale approval. This is a literal dotenv subset; no shell expansion occurs. Child output is withheld because project scripts can print secrets. These commands run under your OS account and are **not an operating-system sandbox**.

Keep the displayed operation ID to resume. Completed steps retain exit evidence, completed health checks are rechecked, and interrupted steps require inspection plus explicit retry. A new operation never adopts an existing virtual environment silently. Existing environments can be used by removing the creation step. Timeout does not prove every child process or container stopped; inspect native runtime state before retrying.

**Launch…** presents assigned subscriptions with observation freshness and deduplicates the same account-wide quota. Expired, stale or missing windows are unknown. Choose a managed local session or open the native client with its existing login and model settings. Account selection is metadata: it cannot authenticate another account, move an existing conversation or switch native Cursor Agent automatically. CLI identity does not prove desktop identity.

## Preview changes and use a canary

**Preview all project changes** shows actual per-project diffs, pins, pauses and conflicts. Start with **Apply one canary first** when several repositories are ready. After its operation completes, inspect the result and preview the remaining projects again. Each project has a recoverable transaction and is rechecked immediately before writing. A stale preview, local managed edit or unavailable repository stops that target rather than overwriting it. Other ready projects can still complete.

Client loading requires its own verification after updating files. Automatic synchronization respects the same project pins and pauses. Installed toolkit assets follow saved toolkit definitions when automatic project synchronization is enabled; locally edited assets produce conflicts.

## Agent toolkits

Create a versioned manifest containing rules, skills, prompt commands and MCP servers. Start with **Create toolkit**, review its starter and add only useful assets. Definitions use schema 1 and portable lowercase IDs. Credentials are environment names, never literal values. HTTP MCP endpoints require HTTPS or loopback HTTP; stdio definitions use executable names and argument lists.

| Asset | Codex | Cursor |
| --- | --- | --- |
| Rules | Separate owned block in AGENTS.md | Owned .cursor/rules/*.mdc files |
| Skills | .agents/skills/*/SKILL.md | Same shared skill directory |
| Prompt commands | Invocable skill workflow | .cursor/commands/*.md |
| MCP | Owned .codex/config.toml block | Individually owned entries in .cursor/mcp.json |

Other TOML settings and JSON server entries are preserved. Previews expose file hashes rather than existing MCP contents, which may contain credentials. Local edits block replacement or deletion. Removed unchanged assets are journaled and can be rolled back with the constitution CLI using the snapshot’s private transaction directory. Installing a toolkit starts no MCP server; enable it only in a trusted client after reviewing its commands. Local Codex launcher feature flags may restrict plugin/tool availability; verify actual loading in that session.

Native export retains the whole manifest. Rulesync export downloads a ZIP containing canonical Markdown assets and mcp.jsonc. Extract it into the reviewed target before using Rulesync. Rulesync import accepts the MCP JSON object. Continue export emits its JSON/YAML-compatible configuration subset; general YAML must first be converted to JSON. Import refuses literal credentials and reports unsupported metadata instead of pretending to preserve it. Separate skills, prompt files and model definitions require manual review. These adapters do not install Rulesync or Continue.

The verified format references are [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Cursor MCP](https://prod.cursor.com/docs/mcp), [Cursor skills](https://prod.cursor.com/docs/skills), [Rulesync file formats](https://rulesync.dyoshikawa.com/reference/file-formats.html), and [Continue configuration](https://docs.continue.dev/reference). Cloud Grok Bots use the existing [manual bundle workflow](../onboarding/bot.md); local paths and MCP installations do not grant a cloud bot access.

## Pair controllers separately from workers

Enable **Controllers → Enable controller TLS listener** with this machine’s private IPv4 address and a port (default 8768). Source users need requirements-local-node.txt. The listener is disabled by default and has its own certificate, namespace and credentials. It exposes scoped read snapshots, not the dashboard, inference, shell commands or remote filesystem operations.

To enable it on startup from source:

```console
python scripts/local_control.py serve --fleet-address <private-ipv4> --fleet-port 8768
```

For a portable package, use its executable with the same serve arguments. Allow the chosen port on the private network. Never restart a controller with active sessions to enable this feature; the dashboard can start the optional listener in the current process.

Create a five-minute, one-use private invitation. Choose library, inventory and/or accounts independently. Account scope shares login labels and usage intentionally; passwords and authentication files stay private. A library may contain private custom instructions: review it before granting access. Paste the invitation into the other controller. Certificate pinning authenticates subsequent requests. Worker pairing codes and inference tokens cannot authorize this listener.

Fetch metadata, then review the library. Initial differences are conflicts. Choose remote content only for deliberately reviewed conflicts, preview again, then stage. Later pulls use three-way fingerprints. Staging validates a disposable complete library before changing the draft. It does not activate projects or push edits back; use the rollout preview afterward. Executable code, release inventories and project-specific repository guidance are outside the shared subset. Revoke an incoming grant on its source controller to deny future reads immediately. Offline fetches retain the last successful private snapshot.

## Recover another computer

Export a recovery recipe, install the current companion on the new machine, clone repositories with your own authenticated Git tools, then import the recipe and map each ID to its actual checkout. Blank mappings are skipped. Review all library replacements. Fresh repositories are enrolled with their pin, architecture baseline and toolkit choices; an existing portable bundle requires verified adoption. Already enrolled projects are preserved.

The recipe excludes machine path mappings, account identities, pairing credentials, model weights and secret configuration contents. Custom instruction/template text can contain private information; review it before sharing. Desired model/context metadata is advisory: hardware fit and protocol evidence must be established again. Restore configuration from [encrypted backups](encrypted-backups.md) into a new private directory, register its mappings, re-pair workers and verify client loading and a real request separately. Recovery does not install drivers, execute Git URLs or silently copy authentication.

## Model comparison lab

Select configured primary/fallback routes and 1–5 repetitions. Review the experiment’s context, fixture version, maximum trials, token limit and start budget. The lab repeats protocol/function-call/full-history checks and the eight-case clamp correctness fixture. Generated Python is interpreted through the existing restricted AST checker, never executed. Managed sessions must be closed before benchmarking; Gaming protects its GPU. Only local or paired inference is permitted, so paid budget is zero.

Results show pass counts, median duration, spread and hardware/model/context fingerprints. Regression comparisons require a matching fingerprint; unrelated hardware or context is an unmatched baseline. The time budget stops **new trials**; an already-started bounded trial finishes. Cancellation also occurs between checks, not by interrupting an active model response. This is fixture evidence, not a general coding leaderboard or an arbitrary-project code sandbox. Hosted benchmarks and arbitrary project execution remain outside this implementation.

## Automatic resource profiles

Automation starts disabled. Add local-time schedules or executable-basename triggers, enable it, and choose a 60–3600 second cooldown. The first matching rule wins; overnight schedules are supported. Application triggers inspect process names only. Unavailable process detection never matches a trigger. No matching rule retains the current profile.

Manual Work/Gaming/Fast/Deep selection holds automation for 24 hours; **Resume automation now** releases the hold. Automatic transitions defer while requests are active or queued. Existing leases retain their route, Gaming checks its tested fallback and verifies GPU release, and external models can still hold VRAM. Fair gateway admission preserves arrival order per selected node; a blocked node does not reserve unrelated node capacity. The controller must be running for these rules to execute.

## Upgrade and validation boundaries

Version 0.4 uses additive schema-1 private workflow files under the controller’s workspace directory. Existing 0.3 state, pins, paths and tokens are preserved. Unknown schemas are refused without rewriting their files. Save private state and encrypted backup credentials before upgrading; use the existing reviewed idle-service update/rollback flow. Workflow state is not a public source export.

Fixture tests and synthetic browser/screenshots cover these workflows. Physical multi-controller networking, real GPU application triggers, Windows/macOS sleep/wake, publisher signing, the availability soak and external usability remain separate [acceptance gates](compatibility-matrix.md). No fixture result substitutes for those tests.
