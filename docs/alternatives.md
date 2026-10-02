# Alternatives and scope

Reviewed October 2, 2026 against the projects' own documentation. These tools solve valuable problems. Use the one that fits your workflow; no unmeasured claim of universal superiority is intended.

| Project | Documented focus | When it is a strong fit |
| --- | --- | --- |
| [rulesync](https://github.com/dyoshikawa/rulesync) | Generate and import configuration for many coding tools from a unified source | You need broad adapter coverage and established import/generation workflows |
| [Ruler](https://github.com/intellectronica/ruler) | Distribute shared instructions, skills, and MCP configuration to coding agents | Your main problem is keeping many agents' configuration aligned |
| [models.dev](https://github.com/anomalyco/models.dev) | Community provider/model specifications, pricing, and capabilities | You need a comprehensive reusable model dataset; this project builds on it |
| **AI Constitution** | Shared working defaults, project onboarding, broad catalog refresh, local discovery, curated routing, and reversible local installs | You want these connected tasks in one small, inspectable workflow for Codex, Cursor, and actual Grok Bots |

The contribution here is the connection between **instructions → onboarding → model knowledge → maintenance → recovery**. It is not a claim to have more adapters than mature rule-sync tools or a more authoritative dataset than the providers.

## A concrete convenience test

Try this in a disposable project:

1. Install a shared baseline and onboard the project.
2. Keep an existing paragraph in `AGENTS.md` and edit `.ai/project.md`.
3. Update shared guidance, synchronize, and confirm both project edits survive.
4. Refresh the model catalog and inspect the additions without changing the selected model.
5. Discover a local server's models without running inference.
6. Undo an installation with its snapshot ID.

Those operations are covered by the automated tests. Fresh-session client loading and usefulness on your workload need separate evaluation. Use [acceptance checks](../checks/acceptance.md) and [the evaluation worksheet](../checks/evaluation.md), then report reproducible improvements or gaps.

## Coexistence

If rulesync or Ruler already owns an instruction file, avoid two generators owning the same section. Keep this constitution as an input module to your existing generator, or use the portable Markdown and catalog tools without the native installer. Existing tool configuration should be reviewed, not overwritten to make adoption appear successful.
