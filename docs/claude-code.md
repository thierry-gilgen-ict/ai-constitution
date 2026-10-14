# Claude Code compatibility preview

Claude Code is an explicit client alongside Codex and Cursor. Use **Constitution health → Claude Code** to preview project enrollment, choose private collection, copy a fresh-session command and qualify local model routes. The [illustrated manual](manual/claude.md) uses synthetic data. Actual client loading and physical multi-machine inference are separate acceptance gates.

## Enable instructions

Install Claude Code using [Anthropic's platform instructions](https://code.claude.com/docs/en/setup), then sign in through the native client. AI Constitution does not copy credentials or alter organization permissions.

```sh
python scripts/constitution.py install --platform claude-code --home /path/to/user-home
python scripts/constitution.py onboard --project /path/to/project --client claude-code --dry-run
python scripts/constitution.py onboard --project /path/to/project --client claude-code
python scripts/constitution.py audit --project /path/to/project --client claude-code --format json
```

For a custom profile, pass `--claude-dir /path/to/profile` to global installation. Otherwise the actual default home respects `CLAUDE_CONFIG_DIR`. Fixture homes always use their explicit directory. Separate profiles receive independent shared-library directories and installation records.

Project enrollment adds a managed `CLAUDE.md` import of `AGENTS.md`, preserves owner text and records schema 2 with explicit client selections. Existing schema-1 projects remain readable. Synchronization preserves client selections; the legacy `install --platform all` still installs Codex and Cursor only. Existing project locks must be adopted before enrollment.

The health scanner explains Claude imports, rules, exclusions, local files and version-dependent `AGENTS.md` selection. External imports can require native approval. Rules with `paths` are conditional. Ancestors outside approved roots are coverage gaps, not automatically read. Scanning executes neither repository commands nor inference. Confirm actual loading in a fresh native session using `/context`; record the evidence in Constitution health. [Instruction behavior](https://code.claude.com/docs/en/memory).

## MCP and portable assets

Grant the project/profile under Constitution health → MCP access, then use its Claude configuration recipe in `.mcp.json`. Keep the generated machine-specific command private. Review and approve it in the native client; invoke an inventory tool in a fresh session. No apply or permission-administration tools are exposed. [MCP scopes](https://code.claude.com/docs/en/mcp).

Toolkit application adds Claude skills and MCP entries only to Claude-enabled projects. It preserves unrelated entries and checks ownership before replacement. Portable Claude exports contain rules, skills and MCP configuration; review collision/loss information before installing them. Rules already supplied by the project's shared `AGENTS.md` block are not installed again as unconditional Claude rules.

## Subscription and isolated reviews

The normal semantic handoff uses your existing native login. Copy the bounded snapshot into a fresh session and import its JSON result for validated diff review.

Isolated reviews are separately enabled in the Claude controls. They require Claude Code 2.1.286 or later, an explicitly named API-key environment variable or a qualified local route. They run in a temporary directory using bare mode, no native tools, no MCP and disabled hooks. Snapshot contents cannot grant write permission; all edits remain candidates until reviewed.

Bare mode does not use subscription login. No API execution is enabled merely by signing into Claude. Unknown usage stays unknown; client estimates are not billing guarantees. [Programmatic execution](https://code.claude.com/docs/en/headless).

## Local models and clusters

First configure primary/fallback models using existing Local Control controls. In the Claude panel, explicitly test each Messages route. The tool round trip and streaming test use local inference. Protocol evidence is independent of coding evaluations and Responses API qualification.

Copy the local launch command from the panel, or run:

```sh
python scripts/local_control.py --state-dir /private/controller-state claude --project /path/to/project --profile claude-code --mode local
```

Use `--mode hosted` for your ordinary login/backend. Local launches set credentials and aliases only in the child environment, register managed sessions and use the stable gateway. Configure the selected profile in Constitution health first.

The Messages gateway uses the qualified local Ollama subset and paired HTTPS workers. Tool history and streaming are forwarded; management credentials remain separate. Unsupported semantic fields are rejected. Token counting is unavailable rather than fabricated. Model/runtime changes invalidate refreshed qualification evidence. [Ollama compatibility](https://docs.ollama.com/api/anthropic-compatibility).

Gaming drains active responses and selects a qualified remote/CPU fallback for later requests. Without a tested fallback, the request fails before dispatch. Partial generations are never replayed. Only managed gateway sessions participate in these guarantees. Hosted/local changes start a fresh session; conversations are not transferred automatically. Desktop/IDE local inference remains unqualified until tested with those clients.

## Private monitoring

Native sign-in collection, telemetry, sharing and isolated reviews default to disabled. The collector uses bounded `claude auth status`; authentication files and transcript databases are not scraped. Subscription allowances are manual/imported or unknown; Anthropic API organization costs remain separate.

Aggregate OTLP/HTTP JSON metrics can be enabled for managed launches. The receiver uses a separate telemetry credential, deduplicates exports and stores allowlisted counters only. Prompt, tool-content and trace logging are disabled in the launch environment. Collector coverage excludes independently started clients unless configured separately. [Telemetry](https://code.claude.com/docs/en/monitoring-usage).

Workers require their normal local audit grants and approved profile/library roots. Use Worker setup's complete command, add the Claude profile ID and its locally chosen directories, and update older workers before auditing Claude. Central pairing does not authorize file access or account collection.

The lightweight worker includes owner-local controls. In a fresh terminal, substitute your installed executable and private state path in these complete commands:

```powershell
& 'C:\path\to\ai-constitution-local.exe' --state-dir 'C:\private\worker-state' claude-config show
& 'C:\path\to\ai-constitution-local.exe' --state-dir 'C:\private\worker-state' claude-config enroll --project 'C:\projects\disposable-pilot'
```

Review the returned plan, then repeat the enrollment command with `--plan` and its exact fingerprint. Configure the worker's audit profile and grants locally using **Worker setup**. Optional collector/review preferences use `claude-config settings --input` with a private JSON file containing boolean switches and an API-key environment-variable name, never its value. Worker account sharing also requires the existing `monitor enable --share` opt-in.

## Acceptance and upgrades

Automated fixtures use disposable homes, fake clients and fake runtimes. They cannot prove native loading, successful subscription authentication, GPU fit or sandbox isolation. Windows terminal, IDE, desktop local Code, macOS and second-PC physical acceptance remain pending until performed and recorded. No stable release certification follows from adding adapter files.

Review enrollment diffs and canary one disposable project before broader adoption. Existing pins, pauses, local grants and transaction rollback remain authoritative. Keep `CLAUDE.local.md`, `.claude.json`, credentials and private client state out of public exports. On restored machines, reapprove collectors, telemetry and automation locally.
