---
name: constitution-onboarding
description: Onboard a repository to an existing AI Constitution checkout, preserving its instructions and recording project context. Use when the user asks to install or adopt the shared constitution in a project.
---

# Constitution onboarding

Locate the checkout from the user's supplied path, `AI_CONSTITUTION_HOME`, or `~/.config/ai-constitution`. If none is available, use the public repository at https://github.com/thierry-gilgen-ict/ai-constitution and a reviewed release.

Read `onboarding/project.md` in that checkout. Inspect the target project's current instructions and relevant setup documentation. Run the installer's dry run, then onboard within the user's authorization. Fill `.ai/project.md` from repository evidence, preserving existing content. Run `doctor --project <path>` and perform the fresh-session acceptance check. Distinguish files installed from instructions proven loaded. Do not publish or deploy a project as part of onboarding.

If the project already has `.ai/constitution.lock.json` but this machine has no enrollment, use `onboard --project PATH --adopt --dry-run`, then `--adopt`. This verifies allowed managed files and hashes without upgrading or changing the pin. Do not bypass a mismatch. Follow with `sync --all --dry-run` to preview eligible updates. A portable legacy lock proves consistency, not independent publisher authenticity.
