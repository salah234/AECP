
---
description: Debug and fix project components, ensuring alignment with CLAUDE.md and README.md
argument-hint: [component-or-issue-description]
allowed-tools: Task
---

Dispatch a subagent to debug and fix the target described below, while strictly conforming to this project's documented architecture and conventions.

Target: $ARGUMENTS

Use the Task tool to launch a subagent with `subagent_type: general-purpose` and the following brief:

1. **Read blueprints first.** Before touching any code, read `CLAUDE.md` and `README.md` at the project root in full. Extract the architecture, conventions, naming rules, module boundaries, and any explicit "must/must not" instructions they contain. Treat these as binding constraints for the rest of the task.

2. **Reproduce and localize the issue.** For the target ($ARGUMENTS), locate the relevant component(s), reproduce the failure or bug (run tests, execute the code path, or trace logic as applicable), and identify the root cause — not just the symptom.

3. **Fix within blueprint constraints.** Implement the fix so it:
   - Follows the architecture and patterns defined in CLAUDE.md (e.g. coordinator/agent boundaries, language choices, module responsibilities).
   - Matches conventions and setup described in README.md (e.g. tooling, folder structure, expected commands).
   - Does not introduce components, dependencies, or patterns that contradict either file.
   - If a fix requires deviating from CLAUDE.md or README.md, stop and flag the conflict instead of silently deviating.

4. **Verify.** Run any available tests, linters, or build steps relevant to the changed component(s) to confirm the fix works and nothing else broke.

5. **Report back** with:
   - Root cause summary
   - Files changed and why
   - Confirmation of CLAUDE.md/README.md compliance
   - Any flagged conflicts or follow-up items

If $ARGUMENTS is empty, ask the user which component or issue to target before proceeding — do not guess.