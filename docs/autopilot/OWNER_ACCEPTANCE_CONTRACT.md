# Owner's Autopilot directive — persistent project contract

**Status:** project-level working instructions, first recorded 2026-11-22.
**Authority:** user-supplied intent interpreted conservatively; does not override
legal restrictions, platform policies, scoped permissions, safety controls or
the owner’s later explicit decisions.

## Outcome expected

Build a **deeply engineered, verifiable Hermes Autopilot**, rather than
quickly generating a convincing prompt or falsely declaring "done."
The user wants substantial research, comparison of best primary sources,
responsible architecture selection, implementation, self-criticism, repeated
testing, and careful integration. Treat this project as **high-complexity**.
Work through as much as is feasible in the active execution opportunity
without inventing elapsed time, test outcomes or deployment status.

The user specifically wants continuous work across A0–A5 profiles and
long-running work that survives individual ChatGPT conversation loss;
agents should be replaceable from durable state without requiring the user
to redownload the local build or restate established instructions.

## Permanent delivery quality rules for agents

1. Always start by inspecting exact source revisions and the current user
   decision record. Never trust a summary without reconciling with source.
2. Prefer primary repositories, official docs, live interfaces and
   executable experiments over marketing, popularity or model confidence.
3. Look for contradictions and failure modes before making an
   architecture choice. Explicitly compare "already upstream" with
   "must build."
4. Every nontrivial change gets a reproducible acceptance test and
   critical self-review. Refuse silent weakening of a test or policy.
5. Report four levels separately:
   **designed / implemented / tested / deployed and independently observed**.
6. Before declaring a project task **done**, require exact revision
   evidence for all agreed criteria. A single unit-test pass, an AI
   summary, an open PR or a GitHub 'success' with no real checks is
   insufficient proof of end-to-end operation.
7. Never publish credentials, grant global filesystem write, delete data,
   bypass human approval or switch production runtimes for speed.
8. Route normal ambiguity to careful analysis; escalate only material,
   irreducible, owner-authority decisions. State them precisely and briefly.
9. When an interface is disconnected (e.g. local Obsidian MCP), mark
   dependent work as **not performed**, retain a safe backlog, and
   do not claim cross-system synchronization.
10. Preserve a project state snapshot containing source SHA, branch/PR,
    currently verified checks, unresolved risks, exact next task, and
    decision provenance.
11. After every failed test, triage root cause, add regression coverage,
    and rerun the relevant check. Retain unsuccessful evidence.
12. Explicit STOP from the owner pauses all project-associated work,
    recurring triggers, background children, notifications and external
    write intents. Require proof that no new side effects are started.
13. A project decision belongs to the canonical project record and
    approved Obsidian location; worker chat history alone is not durable
    authority.
14. Prioritize Windows/WSL runtime compatibility, user-local working copy,
    explicit file ownership, reproducible installation and rollback.
15. Do not assume Hermes upstream features from April 2026 are still
    missing in November 2026. Modern upstream Kanban must be considered
    before introducing duplicate infrastructure.

## Evidence report format

Every substantive owner report should show:

| Field | Required value |
|---|---|
| Scope | Exact project and goal |
| Source | Repository, base SHA and changed head |
| Implemented | Files and live actions actually completed |
| Verified | Check command, CI job ID, conclusion, scope of pass |
| Not verified | Missing tests, disconnected systems, uncertain effects |
| Risk | Highest unresolved severity and blast radius |
| Reconciliation | How to detect unknown remote side effects |
| Safety | Whether changes are draft, read-only, gated or enabled |
| Next milestone | Specific acceptance gate, not generic "continue" |

Avoid arbitrary numeric "10/10" or percent completion without a declared
rubric. Confidence must be explained by evidence.

## Explicit non-goals

- No promise of infinite work after the present interaction;
  ongoing autonomous execution needs an actually deployed runner.
- No unsupervised infinite self-prompting or unlimited token consumption.
- No creation of new agents by evading product authentication, UI limits,
  captcha or terms of service.
- No treating model self-evaluation as independent test evidence.
- No silent in-place merge from a much newer upstream into the user's
  working Windows build.
- No second canonical task scheduler alongside modern Hermes Kanban.

## Current exact checkpoint

- Owner's fork: https://github.com/Podtverzhdeno/hermes-agent
- Main baseline when work began:
  \`7e9100901819ee44c16b4ddcb79a6bcb7909f591\`.
- Draft implementation:
  https://github.com/Podtverzhdeno/hermes-agent/pull/1
- Canonical upstream comparison:
  \`docs/autopilot/UPSTREAM_PARITY_AUDIT_2026-11-22.md\`.
- Architecture and failure matrix:
  \`docs/autopilot/ARCHITECTURE.md\`.
- Actual deployment status: **not deployed / not turned on**.
- Local Obsidian synchronization status: **not performed (MCP unavailable)**.

This document is repository-based persistent project context, not a claim that
the ChatGPT account's personal Memory settings were modified.
