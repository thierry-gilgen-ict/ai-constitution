# Onboard a project

Copy the following prompt into Codex or Cursor in the target project. The same process can be performed by a Grok Bot with access to that project.

> Onboard this project using AI Constitution from https://github.com/thierry-gilgen-ict/ai-constitution. Use the local checkout if available; otherwise obtain the reviewed release. Inspect existing instructions and relevant repository documentation. Establish the project's purpose, architecture, verified development and test commands, constraints, and definition of done from evidence. Preserve existing instructions and identify conflicts. Preview `python scripts/constitution.py onboard --project <project-root> --dry-run` from the constitution checkout, then apply the onboarding within this request's scope. Fill the generated `.ai/project.md` with supported facts. Keep shared policy and project knowledge separate. Verify the installed bundle and report its version, active instruction sources, any shadowing overrides, routing limitations, and unresolved facts. Ask only for consequential information that cannot reasonably be inferred. Do not deploy, publish, or contact others as a side effect of onboarding.

The installer creates a portable bundle and a lock file. It does not infer the project facts for you. Review `.ai/project.md` before considering onboarding complete.
