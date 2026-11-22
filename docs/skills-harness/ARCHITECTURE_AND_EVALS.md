# Specialized Hermes Skills — architecture and adversarial acceptance plan

State: **draft, staged, not deployed**. Date: 2026-11-22.
Base fork: Podtverzhdeno/hermes-agent at main SHA
7e9100901819ee44c16b4ddcb79a6bcb7909f591 (2026-04-01).
Separate from Autopilot PR #1; this feature is reviewed in PR #31.

## Problem statement

A SKILL.md is a knowledge package and procedural prompt, not a
transactional executor. A generic "use the best skill" instruction cannot
verify that a skill triggered correctly, respected tool boundaries, ran
its intended procedure, handled unknown network outcomes, or produced a
real artifact. Each skill has a different failure surface and evidence
shape. A reliable harness must respect that difference.

A single universal rubric would mark a GitHub PR as complete when its text
looks plausible, an Obsidian edit as complete without any disk readback,
or a model benchmark as complete with metrics from an incomparable dataset.

## Source and standards audit

1. Agent Skills open specification: https://agentskills.io/specification
   and implementation: https://agentskills.io/client-implementation/adding-skills-support
   — name, description, progressive disclosure, portable skill directory.
2. OpenAI, skill evaluations:
   https://developers.openai.com/blog/eval-skills
   — activation accuracy, real end-to-end tasks, reproducible fixtures.
3. OpenAI, shell/skills/compaction:
   https://developers.openai.com/blog/skills-shell-tips
   — negative examples and reducing false activation matter.
4. Anthropic, Agent Skills authoring and evaluation:
   https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
   — test representative positive and negative workflows before broad rollout.
5. OWASP agent security:
   https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
   — prompt-injection, least privilege, tool misuse, supply-chain threats.
6. Hermes current upstream (Nov 2026):
   https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
   — modern skill lifecycle, plugin hooks and much more than the April fork.
7. Upstream plugin catalog (reviewed, not installed):
   - skill-court: live with/without skill replays, opt-in paid trial:
     https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/skill-court.yaml
   - skill-workshop: authoring, protection and trial workflows:
     https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/skill-workshop.yaml
   - skill-governance: provenance and change acknowledgements:
     https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/skill-governance.yaml
   - hermes-skill-router: alternative index/reranking mechanism:
     https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/hermes-skill-router.yaml

These upstream plugins are optional third-party software with their own
privileges and known limitations. Do not install them automatically or
claim their execution has been validated on the owner's Windows host.

## The per-skill contract: a sibling harness.json

Each priority SKILL.md gets a **separate** sibling harness.json that must
travel with the skill on installation (MANIFEST.in currently grafts both
skills/ and optional-skills/ in source builds). It includes:

- schema_version and exact skill identity matching frontmatter name;
- short purpose and worst-case risk tier;
- positive and negative activation fixtures (not yet empirical routing);
- preflight and ordered workflow steps;
- individually named actions, each with risk, approval class and its own
  required evidence IDs;
- independently inspectable evidence source and verification method;
- task-specific failure, retry and safe-stop rules.

The schema is strictly validated. Invalid explicit profiles stop the
skill_view load before any setup/secret capture. Unprofiled legacy Skills
still load for backwards compatibility but are marked UNKNOWN by inventory;
they are never automatically assessed as safe.

Risk classification is **advisory** metadata:
- read_only: no mutation intended;
- local_write: reversible changes only within an authorized sandbox/path;
- external_write: exact owner approval for remote changes or messages;
- critical: separate second confirmation for merge or unsafe MCP launch.

The skill cannot choose its own real OS capabilities. The Python validator
checks *internal consistency*, not whether the prose secretly performs a
more dangerous operation. Tool authorization, network fencing, credential
scope, path/canonicalization and approvals belong to a **trusted broker**.

## Execution lifecycle and ownership

~~~text
Original task and exact revision
   |
   v
L0: existing Hermes skill metadata index
   |  (no harness loaded yet; token-efficient)
   v
Skill selection (model) ----- routing positive/negative evals
   |
   v
L1: skill_view, SKILL.md and sibling harness.json
   |  malformed harness => blocked before secret setup
   v
Per-operation preflight, risk, budget and permissions
   |  trusted tool adapter checks real authority
   v
Bounded execution / side effects
   |  unknown external outcome => reconcile, not blind retry
   v
Candidate output and evidence pointers
   |
   v
Structural evidence precheck
   |  NEVER marks task_complete / authenticated
   v
Independent trusted source/read-back and verifier
   |
   v
Task completion or actionable blocker in canonical Kanban
~~~

The currently implemented code provides L1, a pure structural precheck
and the per-skill profiles. It **does not** implement a trusted runtime
broker, live agent evaluation or Kanban completion integration. Do not
invoke the structural precheck as if it were an authentication service.

## Current specialization matrix

| Skill | Operations with distinct evidence | Highest risk | Main failure guarded |
|---|---|---|---|
| github-pr-workflow | inspect / publish / merge | critical | stale CI, unauthorized merge, duplicate PR |
| github-code-review | local review / publish | external_write | stale diff, duplicate review, self-approval |
| github-issues | inspect / create / modify | external_write | duplicate issue, wrong target, ambiguous write |
| codebase-inspection | scan | read_only | automatic system pip install, false metrics |
| test-driven-development | implement | local_write | claiming RED that was never observed |
| systematic-debugging | diagnose / fix | local_write | patching symptoms, no reproducer |
| subagent-driven-development | plan / execute | local_write | unbounded delegation, fabricated child completion |
| obsidian | read / edit | local_write | write outside scope, concurrent edits, MCP outage |
| google-workspace | read / write | external_write | unauthorized sharing/send, OAuth leak, duplicate write |
| evaluating-llms-harness | plan / run | local_write | metric mismatch, missing dataset/model versions |
| arxiv | search / review | read_only | unverified metadata, preprint misclassification |
| native-mcp | inspect / configure / launch | critical | untrusted code launch, overbroad tool authority |

The matrix is a **declared test plan**, not a statement that these real
workflows have all passed. For each skill, at least two positive and two
negative routing examples are machine-linted. Their current counts are
structural fixtures, **not measured model precision or recall**.

## Two independent evaluation planes

### A. Deterministic, offline tests (implemented)

- Parser/identity/version, symlink and size limits, duplicate JSON keys.
- Cross-skill exact positive/negative fixture overlap.
- Highest-risk monotonicity and approval consistency.
- Action-specific evidence; missing/stale/conflicting/wrong-source cases.
- Structural evidence cannot authenticate itself or complete the task.
- Actual skill_view and slash invocation integration; invalid harness blocks.
- No secrets/network/model calls in the isolated CI contract workflow.
- Inventory of ALL bundled/optional source skills with UNKNOWN status for
  unprofiled skills, without pretending a regex hint is a security verdict.

Commands from repository root:

~~~text
python -m unittest discover -s tests/skill_harness -p test_*.py -v
python -m scripts.audit_skill_harnesses --format markdown
python -m pytest tests/agent/test_skill_harness_integration.py -q -o addopts=
~~~

The CI contract matrix targets Linux Python 3.11/3.12/3.13 and Windows 3.12.
Always verify the exact current PR head SHA and job conclusions before
claiming checks passed.

### B. Behavioral tests (NOT YET executed)

For each skill and model/provider combination, run paired **with/without
the skill** trials using the exact same prompts, input state, tool set,
permissions, seed where supported, time budget and sandbox. Sample:
- Positive activation cases: does the model load and use this skill?
- Negative activation cases: does it *avoid* an irrelevant specialized skill?
- Ambiguous adjacent skills: one task crosses GitHub and TDD, does it
  activate the right sequence and not duplicate authority?
- Exact business outcome: file/PR/remote resource/benchmark actually
  matches the task contract, not the model's summary.
- Missing auth, exhausted quota, denied approval, timeout and ambiguous
  remote response: does it stop, reconcile and avoid extra writes?
- Malicious issue/note/retrieved source: does injected text fail to
  elevate tool permissions or alter the task?
- Context truncation and restart: are later actions still scoped and
  based on evidence rather than old narrative?

For dangerous cases use fake API servers, temp worktrees and throwaway
accounts only; never exercise production writes during an eval.

Measure by skill/model/operation (raw counts and confidence intervals):
routing precision, recall, false activation rate, exact task success,
required-evidence verified fraction, unauthorized-action count,
duplicate side effects, p95 latency, token/API cost per verified success,
recovery success, approval burden and regression vs baseline. Paired
bootstrap/Wilson or McNemar methods are more informative than "10/10".

**Proposed acceptance thresholds, not measured claims:**
- zero unauthorized critical actions and zero automatic retries of unknown writes;
- zero false-complete outcomes under forged model-provided receipts;
- at least 95% routing precision and recall on a balanced, varied,
  holdout fixture set for critical Skills, with uncertainty disclosed;
- negative and adjacent-Skill cases must be represented explicitly;
- new skill must outperform or tie baseline on independently verified
  task success, without unacceptable cost or latency regressions.

Run repeated random seeds and heterogeneous prompts; a single cherry-picked
example is not an eval. Avoid changing the model and SKILL.md simultaneously
when attributing causality.

## Threat model and open design gaps

1. A model may read/modify user-local harness.json. The manifest is *not*
   a trusted policy root. Authoritative permissions must live outside any
   skill-writable directory, ideally in a scoped broker/service.
2. Any model can fabricate a correct-looking evidence record. Therefore
   assess_evidence_shape returns authenticated=false and task_complete=false
   regardless of its shape. A separate verified adapter retrieves receipts.
3. A single Skill may contain operations with radically different risks;
   critical action must not inherit the permission level of a prior read.
4. Secrets required by Google or GitHub must stay in connector/token storage.
   Existing skill_view still supports secure environment setup separately;
   harness validation must happen **before** that setup.
5. Unknown external effects require downstream readback and idempotency,
   not re-executing a Skill on a new model.
6. Native MCP can launch arbitrary software; profile risk is critical for
   server launch. Operating system sandbox and tool scope are mandatory.
7. Installation from an upstream source and modified local derivatives
   require provenance hashes and human acknowledgement; not implemented here.
8. The current model discovery index sees SKILL.md descriptions, not the
   full harness routing examples. Routing experiments must measure whether
   descriptions are sufficient before deciding to expand index size.
9. Existing external Skills without a harness remain available by design;
   migrating all at once would risk breaking compatibility. Inventory
   prioritizes which ones to evaluate next.
10. The older fork's global skill editing functions are powerful. Only a
    trusted owner should apply changes to high-risk shared Skills. No
    automatic "self-improve" loop should rewrite a green Skill in production.
11. Full Windows/WSL, bundled wheel/sdist, and remote tool integrations
    still need live end-to-end acceptance after upgrading to modern Hermes.
12. The no-network offline test cannot prove remote API state, model
    behavior, connector scopes, execution security or runtime cancellation.

## Release gates

G0 inventory: exact existing Skills and environment recorded; no secrets
copied into git. **Static source inventory implemented.**

G1 strict schemas: every candidate harness validated and versioned;
invalid opt-in contracts fail closed. **Implemented, CI pending.**

G2 integrations: actual skill_view, slash and preloaded-skill path preserve
new guidance; backwards-compatible unprofiled Skills. **Tests added.**

G3 security: no raw local GitHub credential scraping; no silent global
pip install; all remote writes verified or blocked. **Docs improved,
runtime broker not implemented.**

G4 behavioral evals: with/without skill for positives, negatives, adjacent
triggers, failures and hostile source text. **Not yet executed.**

G5 trusted broker: typed action, authorization, resource scope, budgets,
exact-effect readback and cancellation. **Not implemented.**

G6 production compatibility: wheel/sdist includes harness.json, local
Windows install, modern upstream skill interfaces, no conflict with Skill
Court, Workshop, router or governance plugins. **Not yet verified.**

G7 release: signed evidence, independent review, 24–72h synthetic soak,
rollback and owner-authorized deployment. **Not yet verified.**

Do not merge to main or claim the full project is 100% until the relevant
release gates have actual independent evidence.
