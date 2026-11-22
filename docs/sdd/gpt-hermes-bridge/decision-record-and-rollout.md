# Decision analysis, agent governance and staged rollout

**Baseline**: repository snapshot of 2026-11-22. Scores are analytical judgments
with explicit assumptions, not measured production performance.
**Decision principle**: optimize recoverability and provable correctness before
UI polish, agent count, automatic patching or autonomous execution scope.

## 1. Alternatives, weighted and falsifiable

Criteria weights: reliability .25, security .20, observability .20,
implementation practicality .15, client compatibility .10,
operational risk/manageability .10. Each criterion is 1–5, higher is better.

| Option | Reliability | Security | Observability | Practicality | Compatibility | Manageability | Weighted /5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A. ChatGPT DOM/CDP only | 1 | 2 | 2 | 3 | 2 | 1 | **1.80** |
| B. Chrome MV3 + authenticated native host + ledger | 3 | 3 | 4 | 2 | 4 | 3 | **3.15** |
| C. Existing Hermes OpenAI API + durable ledger + optional extension | 5 | 4 | 5 | 4 | 4 | 4 | **4.45** |
| D. Provider API only, no GPT browser UX | 5 | 5 | 5 | 3 | 3 | 4 | **4.40** |
| E. API + managed durable workflow platform | 5 | 4 | 5 | 2 | 4 | 3 | **4.05** |

Interpretation:
- **Select C as architectural direction**, subject to Gate 0 discovering
  the extension and testing provider-specific compatibility.
- A is fragile because page layout, tabs, browser lifecycle and CDP sessions
  are not reliable operation records. Keep A only as an explicitly optional,
  human-controlled adapter where the API cannot cover the task.
- B remains useful as UI/transport but NOT as the state authority. Chrome MV3
  workers can suspend; native messaging does not automatically provide strong
  identity and capability validation.
- D is intrinsically strong for backend tasks, but does not meet UI extension
  requirements. API-compatible Hermes is not the same thing as controlling
  the ChatGPT website; never claim otherwise.
- E is attractive at high scale but introducing a workflow cluster before
  workload evidence adds cost and failure modes. Design for adoption later,
  do not mandate Temporal at prototype stage.

**Sensitivity test**: If reliable, approved browser UI control is essential,
increase client-UX compatibility weight and re-score B/C; still keep durable
operations on the server. If the system crosses hosts/regions, central
transactional storage and managed workflows move up.

## 2. Ranked improvement candidates

Value scale: 1–5. P0 is a blocking correctness/security requirement; P1
is next foundational work; P2 is planned only after trace data establishes
value. Evidence 'repository' means inspected code; 'external pattern' means
reference designs, not current Hermes behavior.

| ID | Priority | Improvement | Expected value /5 | Confidence /5 | Evidence | Hard gate |
|---|---|---|---:|---:|---|---|
| I01 | P0 | In-process single-flight, 409 conflicts, stable IDs | 5 | 5 | repository race, unit test | G1 |
| I02 | P0 | Durable operation/event/outbox ledger | 5 | 4 | repository lacks ledger contract | G2 |
| I03 | P0 | Effect keys + reconciliation before retries | 5 | 4 | distributed-systems patterns | G2 |
| I04 | P0 | Permission scopes and untrusted page boundary | 5 | 5 | Chrome native messaging docs | G4 |
| I05 | P0 | Session serialization + epoch fencing | 5 | 4 | cross-agent write races | G2/G5 |
| I06 | P0 | Redaction policy and testable log contract | 5 | 5 | security/data minimization | G4 |
| I07 | P1 | Stop taxonomy and RCA evidence dashboard | 5 | 4 | operator mission requirement | G3 |
| I08 | P1 | Trace Context + OTel agent/tool spans | 4 | 5 | W3C/OTel documented | G3 |
| I09 | P1 | Crash & fault injection (32-case matrix) | 5 | 4 | design-level matrix | G2/G5 |
| I10 | P1 | Streaming cursor + explicit terminal receipt | 4 | 4 | SSE interruptions in API | G3 |
| I11 | P1 | Bounded queues/cost + fair tenant scheduling | 5 | 4 | dozens of agents | G5 |
| I12 | P1 | Approval inbox with expiry and scope | 5 | 4 | safety boundary | G4 |
| I13 | P1 | Independent outcome/evidence verifier | 4 | 4 | false-positive completion risk | G3 |
| I14 | P1 | Profile-specific WAL monitoring/backup drill | 4 | 5 | existing SessionDB | G2 |
| I15 | P1 | GitHub CODEOWNERS, tests, review & merge queue | 4 | 5 | GitHub documented | G6 |
| I16 | P2 | UI auto-repair/selectors via LLM | 2 | 2 | unverified UI harness | G0/G5 |
| I17 | P2 | Automatic SDD/code changes by agents | 3 | 2 | needs independent verifier | G6 |
| I18 | P2 | Managed workflow engine migration | 3 | 3 | more ops burden | G5 |
| I19 | P2 | Long-term adaptive stop threshold model | 3 | 2 | needs incident dataset | G3 |
| I20 | P2 | Semantic search over redacted incidents | 3 | 3 | must meet privacy gate | G4 |

Strict selection rules:
- Never implement a lower-priority convenience feature while an open P0 can
  silently duplicate an irreversible effect, leak a secret or erase evidence.
- Changes must include threat model, failure-mode analysis, backward
  compatibility and measurable validation. A low-confidence high-impact idea
  requires a targeted experiment, not wholesale adoption.
- Re-score after observed incidents and test results; no permanent '10/10'
  confidence claims based only on the authoring agent's self-review.

## 3. Architecture decision records (ADRs)

### ADR-001: Hermes API is primary; browser is optional
**Accepted provisionally.** The existing API adapter is the only verified
integration boundary. A browser extension should submit durable commands to
that boundary rather than become its own job scheduler. Revisit if the
specific GPT product provides a different approved API surface.

### ADR-002: Single-writer local prototype → central transactional store
**Proposed.** Start with profile-isolated SQLite and short transactions. If
multi-host scheduling or high write contention is confirmed, migrate
operation ledger to Postgres using dual-read verification/cutover.
Do not share SQLite WAL databases over network filesystems.

### ADR-003: At-least-once transport + dedup, not mythical exactly-once
**Accepted principle.** Internal transition and outbox insertion are atomic
within the database. External APIs require effect-specific idempotency and
read-back verification. Without them, an unknown outcome remains unknown.

### ADR-004: Reconciliation precedes automatic recovery
**Accepted principle.** Timeout after dispatch cannot trigger blind retry.
A watchdog may expire a lease, not guess that the remote action failed.

### ADR-005: Fail closed for privilege and capability, fail visibly for logs
**Accepted principle.** Missing identity, expired policy, untrusted extension
origin and credential mismatch block execution. If remote metrics fail but
local journal works, continue only within bounded buffered quota; if the
durable journal itself cannot commit, stop unsafe side effects.

### ADR-006: Prompt-level autonomy never bypasses code review
**Accepted principle.** Agents may propose fixes, run tests and create
branches/PRs, but protected code and capability-policy changes require
independent verification. Never make the same model both the author and
sole approver of its own high-impact change.

## 4. Governance for dozens of concurrent engineering agents

Each worker must have `agent_id`, `run_id`, `task_id`, purpose,
token/time/cost budget, immutable commit base, allowed paths/capabilities,
lease duration and a specific deliverable.

Recommended specialist lanes (can multiply without changing governance):
- A00: architecture/SDD gatekeeper, no unilateral merge;
- A01–A03: browser bridge protocol, extension UI, native host;
- A04–A06: API compatibility, SSE, session consistency;
- A07–A09: durable ledger, outbox, reconciliation;
- A10–A12: tool effect adapters and per-session scheduler;
- A13–A15: security, sandbox, credential/privacy audit;
- A16–A18: tracing, metrics, incident UI;
- A19–A21: test harness, chaos & load validation;
- A22–A24: release engineering, CI/CD, rollback;
- A25+: independent auditors and domain-specialized adapter owners.

For each work item, preserve:
```yaml
task_id: HERMES-BRIDGE-001
owner: agent-A07
reviewer: agent-A19
base_commit: <sha>
branch: feat/agent-A07-ledger-001
paths_owned: [gateway/ledger/**, tests/gateway/test_ledger*]
acceptance_test: tests/gateway/test_ledger_recovery.py
dependencies: [HERMES-BRIDGE-000]
lease_until: <RFC3339>
progress_ref: docs/sdd/gpt-hermes-bridge/runs/<task_id>.md
state: CLAIMED
next_action: implement_transactional_claim
blocked_reason: null
```

Ownership conventions:
1. No two workers write the same path on the same branch concurrently.
2. GitHub SHA/version check before overwrite; re-read and reconcile conflicts.
3. Each worker uses its own branch/worktree with parent issue and test gate.
4. Changes to shared contracts and policy require the designated maintainer.
5. Dependency waits have explicit blocker and owner; no silent long-running
   'still thinking' state.
6. A worker timeout does not imply the worker's external effect failed.
   Recover operation/effects before spawning replacement agents.
7. Reject stale/duplicate review artifacts by commit SHA and gate evidence.
8. Keep SDD decision history append-only by new ADR revisions; do not erase
   rejected rationale because a later agent has a different opinion.
9. A merge queue/branch protection gate should test the actual integrated
   commit, not each agent's isolated branch alone.
10. An agent may inspect its own prompt and suggest revisions, but revised
    prompts must be versioned and independently regression-tested.

**Agent interaction**: a message queue is a notification mechanism, not
authoritative work state. Acknowledgements include operation ID, parent step,
artifact digest and validation status. A replacement agent resumes from a
durable checkpoint, not from an unverified prose summary.

## 5. Staged implementation plan

**M0 — Discovery/baseline.** Locate real GPT extension source and runtime;
capture manifest, host, protocol, permissions, tests and actual failure
corpus. Record immutable baseline, reject scope gaps. Complete G0.

**M1 — Correctness patch.** In-process idempotency single-flight and
fingerprint conflict; stable retry identity; protect 500 body from internal
exception details. Run unit/endpoint tests; document explicit limitation
across restarts. This branch contains initial M1 work; G1 not yet fully
approved until CI and fault runs are inspected.

**M2 — Durable operations.** Implement ledger/outbox/epoch in isolated
modules; integrate with API adapter behind feature flag; add effect intent,
receipts and reconciliation; dual-run read-only monitoring before writes.
Chaos F01–F16 and F29–F32 must pass; complete G2.

**M3 — Trace and bridge.** W3C/OTel spans, reason-coded stop events, operator
timeline and alerting. Optional browser bridge only after G0, with consent,
native-host identity, reconnection and capability tests. Complete G3/G4.

**M4 — Scale and release.** Real 10/30/100-agent load; queue fairness,
storage contention, crash drills, backups, independent review, canary and
rollback rehearsals; complete G5/G6. Publish measured SLOs and remaining
unknowns.

## 6. Required artifacts for every change

- A proposal with hypothesis and alternative explanations.
- Failing test (or incident replay) proving the pre-change defect.
- Smallest safe patch behind backward-compatible contract.
- Unit/integration/chaos tests with exact command and exit code.
- Security/privacy assessment, perf measurement and rollback plan.
- Linked GitHub PR, source SHA and independent reviewer decision.
- SDD delta, revised risk, follow-up owner and next observable action.

## 7. Sources

- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chromium Native Messaging security FAQ: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/extensions/docs/security_faq.md
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OTel GenAI conventions: https://github.com/open-telemetry/semantic-conventions-genai
- SQLite isolation: https://sqlite.org/isolation.html
- Temporal error handling: https://docs.temporal.io/encyclopedia/retry-policies
- GitHub branch protection/merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
