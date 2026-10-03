# Command reference

Run from the source checkout. Prefix every command below with `python scripts/constitution.py` or, in PowerShell, `./scripts/constitution.ps1`. Use `<command> --help` for its options.

| Command | What it does |
| --- | --- |
| `install --dry-run` | Preview global Codex/Cursor files without writing them |
| `install` | Install both clients, instruction libraries, and skills |
| `install --platform codex` | Install only one client (`cursor` is also supported) |
| `install --platform cursor --cursor-dir /real/cursor/configuration` | Use an explicitly verified, relocated Cursor profile |
| `onboard --project /path/to/project` | Preserve existing instructions and add portable project guidance |
| `onboard --project /path/to/project --pin` | Enroll a project while excluding it from ordinary synchronization |
| `onboard --project /path/to/clone --adopt` | Verify an existing portable lock and enroll without changing project files |
| `architecture list` | List portable project baselines from the selected checkout |
| `architecture show --template web-product` | Inspect a baseline and its declared compatibility |
| `architecture plan --template web-product --project /path/to/project --name my-project` | Preview onboarding, architecture and scaffold diffs |
| `architecture apply --template web-product --project /path/to/project --name my-project --plan HASH` | Apply exactly the reviewed plan with rollback |
| `explain --project /path/to/project --json` | Explain preference layers, routes, installed files and unverified host loading |
| `doctor` | Check enrolled files for drift and instruction shadowing |
| `sync --all --dry-run` | Preview updates to enrolled, unpinned targets |
| `sync --all` | Apply shared changes to enrolled, unpinned targets |
| `providers` | List every bundled provider and its definition count |
| `models --provider anthropic --json` | Read complete definitions offline; default limit is 30 |
| `models --search llama --open-weights` | Find open-weight entries by model name or ID |
| `route --platform codex --task deep` | Get a provisional recommendation without changing client settings |
| `update --dry-run` | Fetch definitions and save a private change report without replacing the snapshot |
| `update --sources` | Refresh definitions and check official source pages for changes |
| `update --source-checkout` | Contributor mode: update the tracked public snapshot |
| `sources` | List pending and reviewed source revisions |
| `sources --review ID --revision SHA256` | Acknowledge the exact source revision after reviewing it |
| `build` | Regenerate routing and adapters after editing shared source files |
| `check` | Validate registries and ensure generated files match their sources |
| `local --kind ollama` | Discover installed models at the default Ollama loopback endpoint |
| `local --kind openai-compatible` | Discover models at the default LM Studio loopback endpoint |
| `export --output dist/grok-bot.zip` | Produce an allowlisted, portable instruction bundle |
| `rollback --snapshot ID` | Restore the original bytes from an installation transaction |
| `upgrade` | Download and activate the latest managed library release; requires release archive assets |
| `upgrade --source /reviewed/checkout` | Activate a frozen library and sync eligible targets without touching Git state |
| `release --output dist/ai-constitution-release.zip` | Export a content-manifest archive for managed upgrades |
| `scan` | Inspect staged and working publishable files for common secret patterns |

For a disposable trial, use a temporary home and a separate state directory:

```sh
python scripts/constitution.py --state-dir .local/trial-state install --home .local/trial-home
python scripts/constitution.py --state-dir .local/trial-state doctor
```

`--state-dir` is a global option and must come before the command. `--home` affects installation destinations only. Actual client sessions still use their own configured home.

Commands return JSON. Exit code `0` means the command completed, `1` means an error, and `2` means an actionable review result such as drift, blocked removals, a scan finding, or an unavailable source. A successful file check does not certify that an agent loaded its instructions.

For routine maintenance, ask Codex or Cursor:

> Use constitution-maintenance to refresh all provider definitions, review new releases against official sources, and update routing where the evidence supports it. Preserve my current model settings, show the meaningful diff, run the checks, and synchronize enrolled projects.

For a new project:

> Use constitution-onboarding for this project. Inspect its existing instructions and commands, preserve them, install the shared baseline, and fill the project context with verified facts.

See [updates and rollback](updates.md), [project onboarding](../onboarding/project.md), and [Grok Bot onboarding](../onboarding/bot.md) for the full workflows.
