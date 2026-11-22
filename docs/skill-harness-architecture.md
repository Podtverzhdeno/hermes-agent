# Hermes skill harness v1 — contracts, threat model and rollout

Status: **experimental pilot, not a runtime sandbox**. Branch-scoped design.
Repository baseline reviewed: fork HEAD 7e9100901819ee44c16b4ddcb79a6bcb7909f591
(2026-04-01); upstream had moved significantly by 2026-11-22. Rebase and
conflict assessment are mandatory before proposing an upstream merge.

## Scope and principle

A **skill** is domain knowledge and a procedural playbook in SKILL.md.
A **harness** is the execution framework around selection, preflight,
capabilities, evidence, verification, recovery and reporting. Do not conflate
them. A Markdown promise never substitutes for a host-side permission check.

This pilot provides:

1. An optional, **individual** harness.yaml next to SKILL.md;
2. Strict parse/type/shape checks in agent/skill_harness.py;
3. Surfacing the validated manifest in skill_view() responses;
4. A lookup-name/path guard and safer symlink boundaries for the skill reader
   and skill manager;
5. Specialized manifests for an initial risk-weighted set of skills;
6. A repository-wide inventory auditor and targeted tests.

All older skills remain loadable without a manifest. Their response reports
harness_status=legacy and harness=null. Invalid existing manifests fail closed
at skill_view(). Neither status changes the core tool authorization model.

## Deliberate limitation: no enforcement yet

`capabilities.tools`, `side_effects`, approval conditions, execution budgets and
lifecycle stages are **advisory metadata**. They are returned to the model,
but the tool dispatcher does NOT currently enforce them. Do not market this
as sandboxing, guaranteed approvals, timeout isolation or automatic rollback.
Existing Hermes host-level permissions still determine what is permitted.

Do not inject manifests into the system prompt on every tool call. Hermes
relies on stable prompts and caching; full manifests are loaded only when
the model requests an actual skill.

## Manifest format (version 1)

```yaml
schema_version: 1
skill: example
activation:
  when: ["Actual task needing this procedure"]
  not_when: ["Adjacent task better served elsewhere"]
capabilities:
  tools: ["read_file", "terminal"]
  side_effects: none  # none | local_write | external_write
  approval_required: []
lifecycle:
  preflight: ["Confirm repository and revision"]
  execute: ["Inspect the relevant changed code"]
  verify: ["Check each finding against a concrete scenario"]
  recover: ["Report blockers without inventing results"]
budget:
  max_tool_calls: 20
  max_reference_bytes: 32768
evidence:
  required: ["Revision and file:line evidence"]
output:
  format: "Verified review findings"
  acceptance: ["No unsupported blocker assertions"]
```

The validator rejects unknown keys, malformed structures, missing lifecycle
steps, oversized manifests (>32 KiB), false-positive bool-as-int budgets,
contradictory activation conditions, and external writes with no declared
approval conditions. A manifest must match the SKILL.md name. A symlinked
harness.yaml is rejected.

**This YAML is an extension to the project, not a claim that Agent Skills
requires harness.yaml.** The existing SKILL.md format remains portable.

## Risk-weighted pilot contracts

| Skill | Core risk | Specialized preflight | Proof of completion |
|---|---|---|---|
| code-review | Unsupported findings | revision, context, invariants | line-anchored evidence |
| systematic-debugging | Trial-and-error patches | reproducer and baseline | targeted regression |
| test-driven-development | Unverified change | test seam and isolation | red/green traces |
| subagent-driven-development | Conflicting writes | immutable task ownership | independent review/integration |
| github-pr-workflow | Unauthorized merge/secret exposure | account, branch, base, SHA | verified PR + CI conclusion |
| github-code-review | Stale/false PR comments | PR head and diff | confirmed anchors |
| arxiv | Citation hallucination | identifiers and search scope | versioned source/limitations |
| obsidian | Destructive edits/concurrency | canonical vault + writable subtree | readback and hashes |
| google-workspace | Unrequested external messages | scope/account/resource ID | operation receipt |
| native-mcp | Tool poisoning/overprivilege | server trust and schemas | read-only probe + inventory |

These are initial **hypotheses**, not proven quality gains. Compare against
the baseline before expanding. Avoid mass-copying an identical manifest to
all 100+ skills; each needs its own intent, risk profile and acceptance tests.

## Workflow for a hardened v2

1. **Index.** Load only names/descriptions and stable path; record source
   identity, version and content digest. Avoid recursive rescans on each turn.
2. **Route.** Evaluate positive and *negative* triggers; log false activations
   and missed triggers, not merely top-1 ranking.
3. **Admit.** Host computes effective capabilities = intersection of user
   grant, provider scope, platform policy, tool availability and declared
   skill requirements. Skill text is *never* a source of elevated authority.
4. **Prepare.** Pin dependencies; check OS, resource limits, credentials,
   environment, network egress and sandbox availability. Keep secret values
   out of skill content and model-visible traces.
5. **Execute.** Route every tool call through an independent policy decision
   point. Bind approvals to user, skill version, tool name, operation, target,
   scope and expiry; deny cross-skill permission inheritance.
6. **Observe.** Attach operation IDs, sanitized logs, input/output hashes,
   external artifact receipts, latency, tool costs and redacted traces.
7. **Verify.** Compare the result to the skill-specific acceptance contract
   using deterministic checks first and a reviewer only when needed.
8. **Recover.** Reconcile uncertain external writes before retrying. Prefer
   idempotency keys, bounded retries, checkpointed state and reversible
   local work; do not promise rollback of a sent email.
9. **Exit.** Record what is verified, what is assumed, and side effects.
   Revoke ephemeral credentials/leases and release sandbox resources.

Implement this only after baseline evals and dispatcher integration tests.
Host capabilities should not change mid-conversation if that would invalidate
Hermes prompt/tool caching; when necessary, use dedicated child contexts with
fixed tool subsets, checked by the host rather than by model instructions.

## Threat model

Assets: API tokens, user files, email/calendar content, repository branches,
review authority, project memory and execution environments.

Trust boundaries:
- Untrusted SKILL.md from hub or external_dirs vs validated local policy;
- Skill instructions vs tool registry;
- MCP server descriptions and tool results vs user/host instructions;
- Agent read permissions vs write permissions;
- One agent's workspace vs another agent's concurrent edits.

Relevant attacks: instruction injection, malicious dependency install,
credential exfiltration, traversal and symlink escape, arbitrary workspace
mutation, stale-sha writes, duplicate external effects, resource exhaustion,
unsafe implicit account selection and unverifiable completion claims.

### Residual risks in this pilot

- The guard scanner is regex-based; it is not a complete supply-chain
  assessment. Review known false positives and install-confirmation flows.
- An agent-created skill may still be accepted on scanner "ask" results
  without a synchronous approval gate. Address this separately before
  treating self-written skills as trusted.
- Local filesystem containment checks can still have TOCTOU races; full
  mitigation needs descriptor-based filesystem operations, not just resolve().
- External skill roots are currently considered trusted by configuration;
  source provenance and actual execution constraints are distinct.
- Script dependencies and external APIs can evolve beyond SKILL.md examples;
  pin and test in a controlled environment.
- Most legacy skills have no individual harness; no claim of full coverage.

## Evaluation design and release gates

Use paired baseline/candidate runs on identical tasks and fixed inputs.
Each domain suite must have positive triggers, tempting negative triggers,
normal cases, ambiguous cases, error paths, and an adversarial tool-output
case. Include multiple OS/provider surfaces where relevant. Collect actual
traces and output artifacts, not self-assessed scores.

Primary metrics:
- Activation precision/recall, false-positive skill invocation;
- Task success and severity-weighted correctness;
- Evidence fidelity (does a cited file/line/paper actually support a claim?);
- Unauthorized side effects and credential leakage (**zero tolerance**);
- Recovery behavior on timeouts, conflicts and duplicated operations;
- Tool calls, tokens, wall time, external cost and failure rate;
- Regression rate on legacy skills and baseline workloads.

Suggested graduation gate (proposal, not yet measured):
- 0 unauthorized side effects and 0 confirmed secret disclosures on suite;
- 100% of schema/path/approval negative tests passing;
- No statistically meaningful regression on task success vs baseline;
- No deterioration of activation precision on adjacent-skill negatives;
- Exact results disclosed per platform and provider, with a holdout set.

A hard fail in authorization or data isolation blocks release regardless
of any weighted quality score. Do not report "10/10" based only on tests of
parser schemas; domain accuracy requires running the tasks.

## Commands

```bash
python -m scripts.audit_skill_harness --strict
python -m scripts.audit_skill_harness --json
python -m pytest tests/agent/test_skill_harness.py \
  tests/tools/test_skill_harness_integration.py \
  tests/tools/test_skill_manager_path_boundaries.py -q
# Before merge:
python -m pytest tests/ -q
```

## Research references

- Agent Skills specification: https://agentskills.io/specification
- Client implementation / progressive disclosure:
  https://agentskills.io/client-implementation/adding-skills-support
- OpenAI, "Testing Agent Skills Systematically with Evals":
  https://developers.openai.com/blog/eval-skills
- OpenAI, "Shell + Skills + Compaction":
  https://developers.openai.com/blog/skills-shell-tips
- OWASP AI Agent Security Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
- OWASP Agentic Skills Top 10:
  https://owasp.github.io/www-project-agentic-skills-top-10/
