# Compatibility and physical acceptance

## Claude Code 0.6 preview

Disposable tests cover explicit enrollment, legacy locks, custom profiles, imports, ownership, stale previews, telemetry isolation, output limits and reviewed prose. Browser journeys cover opt-in Claude controls and accessibility. See the [Claude guide](claude-code.md) and [illustrated manual](manual/claude.md).

Actual Windows terminal/IDE/desktop instruction loading, native MCP connectivity, macOS/Linux client acceptance, real Messages inference and two-PC Gaming/GPU-release acceptance remain pending. Desktop/IDE local inference is not enabled through an unverified integration. Existing Codex/Cursor evidence does not certify Claude.

Report evidence separately for source tests, packaged startup and real inference. A green fixture suite does not certify a GPU driver or promise that an arbitrary model fits.

| Surface | Automated coverage | Physical acceptance for 0.3 |
| --- | --- | --- |
| Windows, Python 3.11 / 3.13 | Core/companion fixtures, real temporary junction guard, private state creation | Multi-PC inference and driver recovery pending |
| macOS, Python 3.11 / 3.13 | Core/companion fixtures | Apple Silicon load/unload and sleep/wake pending |
| Linux, Python 3.11 / 3.13 | Core/companion fixtures | GPU/backend combinations pending |
| Windows x64 native | Frozen application smoke build | Signed distribution identity not configured |
| Apple Silicon native | Frozen application smoke build | Developer ID/notarization identity not configured |
| Linux x64 native | Frozen application smoke build | Distribution-specific desktop testing pending |
| Chromium dashboard | Synthetic onboarding, templates, backups, workers, updates, keyboard/axe checks | External usability trial pending |
| Other architectures | Source installation where Python/dependencies support the host | No native package claim |

Current CI results are linked from the README. Consult the workflow run for the exact release commit; this table describes the test matrix rather than claiming every future build passed.

Remote HTTPS workers require `cryptography>=50.0.2,<51`. Its [upstream compatibility changes](https://cryptography.io/en/latest/changelog/#v49-0-0) remove Intel macOS and 32-bit Windows support. The instruction toolkit, dashboard and local gateway use the standard library and can run without this optional dependency on hosts supporting Python 3.11+. For remote TLS, choose a supported worker host; do not restore an older vulnerable dependency to work around the platform limit. CI covers Windows x64, macOS ARM64 and Linux x64 with this dependency.

## Repeatable two-machine check

Use disposable projects, a small model known to fit each machine, and private worker pairing. Record OS/runtime/driver versions locally. Never publish pairing codes, account identifiers or private logs.

1. Confirm both nodes report their version and fresh health; verify certificate pin rejection with the fixture suite.
2. Qualify a local primary and remote fallback at the same context. Run each bounded coding evaluation; record actual memory and latency.
3. Open a managed local session. Start a long response and choose Gaming. Verify the active response completes on its original node, subsequent requests use the tested fallback, and the protected GPU reports no managed residency before declaring release.
4. Pause the fallback before a new request. Verify a clear pre-dispatch error or another ready, tested route. Never replay a partially received generation.
5. Resume the worker, then put it into maintenance. Test package staging, guarded restart, version verification and rollback while all clients are idle.
6. Repeat after sleep/wake on each machine and after controller restart. Confirm Gaming remains protected, stale sessions are identified, and failed operations remain visible.

## Workspace 0.4 acceptance

Automated fixtures cover controller TLS scope separation and certificate pinning, one-use invitations, peer conflicts, mapped recovery, native toolkit ownership/removal/rollback, quota freshness, FIFO admission and resource schedules. Browser journeys cover all workflow sections, keyboard search and accessibility. The illustrated manual uses synthetic data.

Physical acceptance remains pending: pair two independent controllers on Windows and macOS; disconnect/reconnect a peer without losing its last successful snapshot; stage competing edits and recover a renamed checkout; restore an encrypted configuration on the second machine; enable a real game-process trigger with a tested remote/CPU fallback; observe active-response completion and actual GPU release; repeat after sleep/wake. Do not run these inference/driver tests implicitly during repository checks.

## Constitution health 0.5 preview acceptance

Automated disposable fixtures cover custom profiles, Codex overrides/fallbacks/limits, conditional Cursor rules, worktree discovery, bounded file hashing, scoped references, managed ownership, stale previews, durable requests, revoked grants, reviewed prose, cached handoffs, scheduling and history-only restoration. Loopback HTTP tests exercise worker scan → preview → correction → verification → rollback. Browser journeys exercise the health controls and accessibility. Optional MCP tests exercise the official SDK and stdio transport.

These are separate from the physical gate: on each Windows computer, enroll a disposable project, approve its local worker roots, remove one owned file, scan, preview, explicitly apply, rescan and roll back. Verify later edits prevent unsafe rollback and revoked permissions prevent access. Physical main/second-PC execution and actual macOS Codex/Cursor/package acceptance are **pending**. Native-client loading and unattended semantic review are not inferred from file or SDK tests.

## Availability soak

Run explicitly in your own terminal:

```sh
python scripts/soak_local.py --hours 48 --interval 60 --output /private/reports/local-control-soak.json
```

The monitor reads controller and paired-worker diagnostics only. It never sends inference, changes routes, unloads models, installs drivers or restarts a service. Reports contain counts/status/version/platform, not addresses, account identifiers, prompts or token values. Sleep/wake and driver changes are performed deliberately outside this script. An availability report cannot by itself certify GPU stability or uninterrupted client work.

Acceptance requires reviewing gaps, failed operations, driver events and the explicit two-machine checks. The 48-hour run is **not yet completed for this release**.

## External usability trial

Ask three people unfamiliar with the project to: onboard a repository without losing its instructions; identify their subscription; configure a private backup and restore it; find the correct worker package; and explain what an update restart will interrupt. Record completion time, mistakes, unclear text and assistance required. Use test accounts and fixtures. Publish aggregated findings only with participant consent. This trial requires real participants and remains an external release-quality gate.

## Projects-first 0.7 preview acceptance

Automated coverage uses one isolated controller per browser engine. It covers Home/navigation/history, 320px layouts, authentication pause, stalled reads, hosted onboarding, draft isolation/publication, worker commands, recovery and demo connection restrictions. Python fixtures check stale candidates, reviewed publication and scoped preparation directories. Core CI retains Windows/macOS/Linux coverage.

Physical checks remain separate: production shortcut/sign-in/restart, worker setup on the second Windows computer, native loading in all selected clients, real model qualification and GPU residency. macOS/Linux native package acceptance and three unfamiliar-user trials remain pending until recorded. Time hosted onboarding with an already installed/signed-in client; target five minutes excluding downloads and authentication. Participants must identify affected targets and publication scope before approving a change. Do not call the preview production-ready until blocking findings are addressed.
