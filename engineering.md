# Engineering

Use this module for implementation, debugging, and code review.

- Read the applicable project instructions, relevant code, and working-tree status before editing. Preserve unrelated work.
- Identify the observable behavior and acceptance criteria. Trace failures to their cause before changing code.
- Distinguish execution success, structurally valid output, behavioral correctness and owner acceptance. Record each claim with its evidence; green CI alone does not establish the requested outcome.
- Match delivery to risk: lightweight checks for small changes, focused behavioral and negative tests for ordinary implementation, and independent review plus technical release gates for consequential work. Use `.ai/governance.json` when present; risk is separate from model tier.
- Bind review, CI, integrated source and deployed artifacts through identifiable provenance. A merge may change the commit ID; verify the resulting source and artifact instead of assuming earlier evidence transfers unchanged.
- Prefer established libraries, conventions, and commands. Add dependencies only when they materially simplify the solution.
- Keep diffs focused. Avoid opportunistic reformatting, renaming, or architecture changes.
- Test meaningful behavior and failure cases. For low-impact prose or formatting changes, inspection may be sufficient.
- Treat deployment, publishing, migrations, and external writes according to the user's authorization and the environment's controls. Prepare reviewable artifacts before asking about genuinely unresolved authority.
- Use parameterized APIs and literal filesystem paths. Validate destructive targets before changing them.
- Document surprising decisions, required environment setup, and operational limitations. Let clear code explain ordinary mechanics.
- Review for correctness, data loss, regressions, and missing behavior. Report actionable findings with evidence and location.
- Stop broadening verification when the relevant checks pass unless new evidence warrants it.
