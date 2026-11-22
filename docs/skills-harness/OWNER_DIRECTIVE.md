# Owner directive: Specialized Hermes Skills and per-skill Harness

Recorded: 2026-11-22.
Project priority: **high-complexity, evidence-driven engineering**.

The owner explicitly rejects superficial prompt rewrites, premature "10/10"
claims and finishing after trivial inspection. They require deep comparison
with primary sources, actual code improvements, independently checked
tests, repeated critical re-evaluation and meticulous per-Skill design.
Apply this directive as a durable **project instruction**, not as a claim
that ChatGPT account Memory preferences were changed.

## Permanent standards for future A0–A5 work

- Every individual Skill needs its own triggers and anti-triggers, procedure,
  risk/permission boundary, output contract, evidence standard, and failure
  recovery behavior. A shared harness is infrastructure, NOT a replacement
  for specialization.
- Base architecture decisions on current upstream implementation, available
  trusted tools and observed failures. Reuse existing Hermes mechanisms,
  including Kanban, Skill Court and other audited components, before writing
  duplicate infrastructure.
- Research in depth, but grade sources by accuracy, freshness, provenance,
  replicability and direct relevance; quantity of sources alone is not proof.
- Separate facts into: **designed**, **implemented**, **offline-tested**,
  **model/e2e-tested**, **deployed**, and **independently observed**.
- Never mark an operation successful from model-produced JSON alone.
  External writes require independent read-back; exact revision,
  target and authorization must match.
- Audit permission boundaries, prompt injection, source provenance,
  supply-chain installs, secret leakage, timeout ambiguity, cancellation,
  duplication, cross-agent file conflicts and Windows compatibility.
- Run negative tests and adversarial fixtures; retain failures and amend
  regression tests rather than downgrading requirements to make them green.
- Do not silently auto-install plugins, change the running Hermes profile,
  widen local MCP scope, merge PRs or deploy production while experimenting.
- Preserve exact head SHA, PR, test run, completed steps, known failures and
  next concrete acceptance gate in the project state record.
- The owner prefers a substantial, complete pass over repeated easy
  questions. Escalate only decisions with genuinely owner-only authority.
- Continuous operation after a chat requires a deployed service. Do not
  promise indefinite background work without one.
- Update per-Skill documentation in the approved project knowledge store
  when the connector is healthy; on disconnection, record pending sync
  rather than claiming notes were written.

## Current project checkpoint

Target: Podtverzhdeno/hermes-agent, special Skills development branch
feat/specialized-skills-harness-20261122, draft PR #31.
Canonical detailed plan:
docs/skills-harness/ARCHITECTURE_AND_EVALS.md.

Gates to inspect next:
  1. Current PR head CI, including Linux/Windows contract matrix and full pytest;
  2. actual wheel/sdist installation of sibling harness.json;
  3. black-box model routing with/without each Skill;
  4. trusted broker enforcement for side effects;
  5. Windows/Obsidian/GitHub real-world integration without extra scope.
