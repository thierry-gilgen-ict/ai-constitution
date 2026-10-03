# Compatibility and physical acceptance

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

## Repeatable two-machine check

Use disposable projects, a small model known to fit each machine, and private worker pairing. Record OS/runtime/driver versions locally. Never publish pairing codes, account identifiers or private logs.

1. Confirm both nodes report their version and fresh health; verify certificate pin rejection with the fixture suite.
2. Qualify a local primary and remote fallback at the same context. Run each bounded coding evaluation; record actual memory and latency.
3. Open a managed local session. Start a long response and choose Gaming. Verify the active response completes on its original node, subsequent requests use the tested fallback, and the protected GPU reports no managed residency before declaring release.
4. Pause the fallback before a new request. Verify a clear pre-dispatch error or another ready, tested route. Never replay a partially received generation.
5. Resume the worker, then put it into maintenance. Test package staging, guarded restart, version verification and rollback while all clients are idle.
6. Repeat after sleep/wake on each machine and after controller restart. Confirm Gaming remains protected, stale sessions are identified, and failed operations remain visible.

## Availability soak

Run explicitly in your own terminal:

```sh
python scripts/soak_local.py --hours 48 --interval 60 --output /private/reports/local-control-soak.json
```

The monitor reads controller and paired-worker diagnostics only. It never sends inference, changes routes, unloads models, installs drivers or restarts a service. Reports contain counts/status/version/platform, not addresses, account identifiers, prompts or token values. Sleep/wake and driver changes are performed deliberately outside this script. An availability report cannot by itself certify GPU stability or uninterrupted client work.

Acceptance requires reviewing gaps, failed operations, driver events and the explicit two-machine checks. The 48-hour run is **not yet completed for this release**.

## External usability trial

Ask three people unfamiliar with the project to: onboard a repository without losing its instructions; identify their subscription; configure a private backup and restore it; find the correct worker package; and explain what an update restart will interrupt. Record completion time, mistakes, unclear text and assistance required. Use test accounts and fixtures. Publish aggregated findings only with participant consent. This trial requires real participants and remains an external release-quality gate.
