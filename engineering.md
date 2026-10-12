# Engineering

Load for implementation, debugging and code review.

- Read applicable guidance, relevant code and working-tree status. Preserve domain architecture and unrelated work.
- Bind one bounded issue/owner outcome to measurable acceptance, independent risk and resource budget; use one worker on an isolated branch.
- Trace the cause, prefer established commands/libraries and make focused diffs. Avoid unrelated formatting, dependencies and redesign.
- Test behavior and negative cases that could disprove the claim: wrong environment/entity, reordered responses, absent domain fields, failed persistence, lost acknowledgments and stale publication. Do not mock away the failing boundary.
- Nontrivial changes need independent exact-revision review and relevant CI on the same candidate. High/critical risk needs stronger verification, not an expensive model for every step.
- Integrate small accepted slices; preserve human deployment authority and separate semantic/business acceptance. Load collaboration.md and operational.md when relevant.
- Use literal filesystem paths and parameterized APIs. Validate destructive targets/ownership before separately authorized actions.
- Report implementation, review, integration, deployment and acceptance separately. Green CI and an agent DONE statement cannot promote one to another.
- Low-impact mechanical/docs work may use diff inspection and deterministic checks. Stop broadening verification when relevant checks pass unless new evidence warrants it.
