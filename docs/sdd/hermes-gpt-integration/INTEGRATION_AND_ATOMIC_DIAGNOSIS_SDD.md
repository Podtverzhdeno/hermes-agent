# Hermes ↔ GPT — Integration Governance & Atomic Stop Diagnosis (SDD Addendum)

Revision: 1.0, 2026-11-22. Status: DESIGN / SOURCE-AUDITED / NOT DEPLOYED.
Fork baseline: Podtverzhdeno/hermes-agent main @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591 (2026-04-01).
Upstream reference: NousResearch/hermes-agent v0.23.3, released 2026-11-19.
Related artifacts: isolated collision audit code, offline tests, evidence log in this PR. The local browser/Windows extension has not been inspected.

## 1. Decisions that must NOT be bypassed

1. **Canonical task lifecycle is upstream Hermes Kanban.** The current upstream already has durable Kanban boards, worker lanes, dispatcher, task/run identities and review gates. Do not activate the prototype Autopilot ledger as a second top-level queue. Reuse only its effect/approval/evidence invariants after reconciliation with the actual upstream release.
2. **Verified GPT transport is the fork's OpenAI-compatible API adapter.** The optional ChatGPT browser companion is a *proposed adapter*, not an observed deployment. Historical connectivity canaries do not prove continuous operation, UI reliability, or external action success.
3. **No parallel implementation may self-certify merging.** Each capability has one integrator, a declared reference revision, an independent verifier and a single acceptance contract. Competing PRs are alternatives or test sources, not blindly stackable changes.
4. **Unknown remote outcome is a distinct state.** A crashed HTTP client or worker may have sent an irreversible action. No automatic retry is allowed without supported remote idempotency or independent reconciliation.
5. **STOP is revocation, not prose.** The project generation must stop future claims, scheduled triggers, model dispatch and tool effects across all boards and workers; in-flight results require a separate uncertainty policy.
6. **Instrument facts, not private reasoning.** Structured metadata, timestamps, causal links, error classes and trusted receipts are allowed; raw prompts, private tool arguments, session cookies, bearer tokens, screenshots and unredacted exception payloads are prohibited by default.

## 2. What is observed versus unknown

| Fact | Evidence level | Notes |
|---|---|---|
| The inspected fork main is the April 2026 commit | VERIFIED_SOURCE | exact SHA above |
| 12 preexisting branches had 13 pairs of overlapping paths in the November 22 audit | POINT_IN_TIME | changed-file metadata; not a persistent total |
| Three branches touched gateway/platforms/api_server.py; five touched pyproject.toml | POINT_IN_TIME | merge and semantic review mandatory |
| Draft PR #4, #5 and #6 all change API integration | VERIFIED_PR_METADATA | choose an implementation only after comparative tests |
| Latest checked stable upstream is v0.23.3 | VERIFIED_PUBLIC_SOURCE | release 2026-11-19 |
| Hermes Kanban owns multi-agent task lifecycle | DOCUMENTED_UPSTREAM | source: official Kanban/worker lane docs |
| Local Workspace reads can access the extension | BLOCKED | connection returned Session terminated; fallback observer 429 |
| The actual browser extension has been tested on Windows | UNKNOWN | no inspected source, manifest, runtime log, or E2E run |
| Proposed idempotency patches are production-ready | UNKNOWN | full CI and runtime evidence not established |

Evidence levels are not interchangeable. A source-code finding is different from a live incident, a unit test is different from a deployment test, and a green API response is not proof of an external effect.

## 3. Single-authority design

~~~text
Owner request + policy revision
           |
           v
Hermes Kanban task / run  ---------------------------> Independent verifier
           |                                                   ^
           v                                                   |
Bounded worker lane -- trusted tool adapter -- effect receipt --
           |
           +--> GPT/OpenAI API adapter
           +--> scoped GitHub / Obsidian / worktree
           +--> optional browser companion (non-authoritative)
           |
           v
Append-only diagnostic event stream -> incident classifier -> operator
~~~

Source-of-truth separation:

- Kanban: task state, lease, dependency and dispatcher truth.
- Project policy: versioned permissions, per-project budgets and revocation generation.
- Action journal: effects reserved / confirmed / unknown / reconciled, tied to canonical task/run.
- Adapter: client request/response delivery and stream-state truth.
- Verification system: accepted artifact, exact commit SHA, CI check and external receipt truth.
- Browser companion: user-visible status only; never completion authority.

An agent may write a hypothesis to diagnostics; it cannot promote an unverified action to completed, mint its own approvals, increase budgets or alter its lease generation.

## 4. Multi-agent ownership registry

Any task that will create a PR needs: capability_id, project_id, kanban_task_id, owner_role, base_sha, head_sha, precise file scope, acceptance_test_ids, risk level, dependencies, conflicting proposals and rollback reference.

| Capability | Proposed canonical integrator | Competing branches | Required action |
|---|---|---|---|
| gpt.api.idempotency | API integrator | PR #4/#5/#6 | select ONE after common regression tests |
| gpt.api.sse-terminal | API integrator | PR #4/#6 | unify failure/end-of-stream contract |
| gpt.run.observation | Observability integrator | gpt_bridge/gpt_extension/gpt_companion | one event schema; multiple read-only adapters may remain |
| task.lifecycle | upstream Hermes Kanban | two Autopilot variants | do not introduce parallel dispatcher |
| tool.external-effects | trusted tool publisher | proposed ledgers | fence + reconcile against Kanban identity |
| release.pyproject | integration captain | five branches | one packaging integration commit |
| gpt.pr.coordination | integration QA | this PR | read-only audit, no merge authority |
| user.browser.companion | browser/extension owner | local source missing | block modifications until inspected |

For 30–100 agents: unique immutable task identities; bounded queue per tenant; leases with monotonically increasing fencing tokens; independent worktrees; branch protection; capability-specific write ownership; reviews by different principals; and a single responsible release integrator. A named role is not an OS security boundary; trusted tools must enforce permissions.

Two agents can independently investigate a problem, but two agents must not simultaneously own writes to the same canonical service. Rejected or alternate solutions become test assets and review notes, not redundant production modules.

## 5. Atomic observability envelope

Design schema v1, *not yet a runtime implementation*:

~~~json
{
  "schema_version": 1,
  "event_id": "UUID",
  "project_id": "canonical-project",
  "kanban_task_id": "canonical-task",
  "kanban_run_id": "canonical-run",
  "worker_instance_id": "boot-UUID",
  "attempt_id": "UUID",
  "lease_fence": 17,
  "trace_id": "W3C-32-hex",
  "span_id": "W3C-16-hex",
  "producer_seq": 233,
  "causation_event_id": "UUID-or-null",
  "phase": "TOOL_AWAIT_RESULT",
  "reason_code": "EXTERNAL_OUTCOME_UNKNOWN",
  "evidence_ref": "allowlisted-opaque-receipt",
  "source": "trusted-adapter",
  "occurred_at_utc": "ISO8601",
  "observed_at_utc": "ISO8601"
}
~~~

Invariants: unique event ID and (worker instance ID, producer sequence); atomic persistence before acknowledgment; per-producer and causal ordering rather than wall-clock global ordering; no sensitive payload by default; failed or unknown events never auto-advance a Kanban task; trace IDs enable correlation but are not authentication. All event sources must be authenticated and schema-checked; cross-version unknown required fields fail closed.

### 5.1 Where exactly can work stop?

| Phase | Required evidence | Block class |
|---|---|---|
| Intake | auth, policy revision, accepted payload digest | AUTH_DENIED, INVALID_CONTRACT |
| Enqueue | task identity, idempotency key | STORE_UNAVAILABLE, DUPLICATE |
| Claim | run, worker, fence | CLAIM_CONFLICT, NONSPAWNABLE |
| Spawn | PID/host/workspace/profile | SPAWN_FAILED |
| Prompt delivery | worker acknowledgement for task digest | PROMPT_NOT_DELIVERED |
| Provider request | provider request ID, start/deadline/first-byte | 401, 429, TIMEOUT |
| Streaming | chunk sequence, last persisted chunk, final status | STREAM_INTERRUPTED |
| Tool intent | effect key, auth policy, approval generation | POLICY_DENIED, WAITING_APPROVAL |
| Tool effect | reservation, receipt or uncertainty | EXTERNAL_OUTCOME_UNKNOWN |
| Verification | revision-specific artifact and CI receipt | STALE_SHA, TEST_FAILED |
| Publish | committed result versus client delivery ack | DELIVERY_UNKNOWN |
| Checkpoint | durable cursor + producer sequence | CHECKPOINT_GAP |
| STOP | revocation generation and cancellation acknowledgements | STOP_INCOMPLETE |

Absence of a heartbeat alone produces SUSPECTED_STALL; if the observer is disconnected the diagnosis is OBSERVATION_GAP, not AGENT_DEAD. Never claim to access hidden GPT reasoning. Reasons are derived from observable process boundaries and receipts only.

### 5.2 Strict diagnosis rules

- HTTP 401/403 -> AUTH_BLOCKED; manual authorized repair only.
- HTTP 429 + Retry-After -> RATE_LIMITED; bounded backoff and quota coordination.
- Human approval outstanding -> AWAITING_HUMAN, not RETRYABLE_ERROR.
- SSE exception after partial output -> STREAM_FAILED_PARTIAL; never emit a normal success marker.
- Worker shutdown before model start -> WORKER_STOPPED; safe retry only if no effect reserved.
- Client disconnect after remote action dispatch -> EXTERNAL_OUTCOME_UNKNOWN until reconciled.
- Client disconnect after committed response -> DELIVERY_UNKNOWN; replay persisted response without rerunning model.
- Lease expired and process status unknown -> ORPHAN_SUSPECTED; fence before reassignment.
- Project STOP advanced -> STOP_REQUESTED; block new actions and enumerate in-flight uncertain effects.
- Missing trace / incomplete observer logs -> INSUFFICIENT_EVIDENCE, do not guess a cause.

Each incident must capture symptom, primary evidence, alternative hypotheses, confidence class, allowed next action, owner, fix commit, exact test evidence and rollback.

## 6. Fault injection matrix: minimum acceptance suite

| Scenario | Why naive recovery fails | Correct action |
|---|---|---|
| 100 concurrent duplicate Idempotency-Key requests | await-before-cache races | one adapter invocation; dedup |
| same key, changed body | incorrect reuse | deterministic 409, no execution |
| client cancels while thread still runs | task cancellation != side effect cancellation | mark requested, retain reservation |
| crash before effect reservation | action not sent | safe policy-controlled retry |
| crash after reservation before send | outcome ambiguous | reconcile |
| remote commit then response lost | second attempt duplicates mutation | remote receipt check before retry |
| client gone after response persisted | duplicate model billing | replay response |
| worker heartbeat lost | observation loss misread as death | check observer first |
| two workers claim task | duplicate execution | fence loser |
| stale worker submits late commit | old run may overwrite work | reject by fence/SHA |
| long SQLite WAL readers | checkpoint starvation | investigate readers; bounded checkpoint |
| partial SSE error | false terminal success | error frame, no false stop |
| provider 429 storm | each agent retries independently | global backpressure |
| provider token revoked | automatic security workarounds | block, require authorized repair |
| malformed/oversized body | unhandled server error | reject pre-dispatch |
| Chrome MV3 service worker stops | in-memory progress lost | persist cursor outside JS globals |
| CDP target detached | lost action result | reconnect, preserve uncertain state |
| browser native host gone | UI cannot establish truth | failure state, no side effects |
| duplicate extension event | two status transitions | event ID dedup |
| 30 agents touch same file | mutually incompatible patches | integration HOLD |
| stale CI on previous SHA | proof doesn't bind code | rerun on exact HEAD |
| STOP while mutating tool runs | cancel does not undo remote action | revoke, reconcile |
| STOP while cron still active | task auto-restarts | disable scheduled ingress |
| retry budget exhausted | unbounded agent replacement | BLOCKED_BUDGET |
| upstream Kanban already installed | duplicate dispatcher | discard parallel scheduler |
| GitHub 403/429 inventory | absent file list looks clean | fail audit closed |
| comparison API truncates at 300 files | false no-conflict conclusion | manual incremental review |
| Windows worker claimed but prompt not delivered | DB status falsely implies work | end-to-end prompt delivery probe |

**End-to-end exactly-once is NOT promised.** Process-local idempotency prevents some duplicate invocations, not independent-host effects after restart. Trusted remote idempotency keys and reconciliation are mandatory where possible; otherwise an uncertain effect blocks automatic replay.

## 7. Integration collision gate in this branch

Artifacts:
- scripts/hermes_gpt_coordination_audit.py — read-only GitHub inventory or offline JSON snapshot; exact baseline and head SHAs, changed-path overlap and semantic-capability signals.
- tests/coordination/test_hermes_gpt_coordination_audit.py — offline standard-library regression suite.
- .github/workflows/hermes-gpt-coordination.yml — compile/tests on Python 3.11, 3.12, 3.13; manual live branch scan and artifact export.

Outputs:
- HOLD: exact path conflict. Do not auto-integrate.
- REVIEW: probable capability duplicate without direct path collision.
- NO_COLLISION_FOUND_NOT_MERGE_APPROVAL: this *one gate* found no conflict; still require CI/security/revision check.
- INCOMPLETE_AUDIT: missing SHA, truncation, API outage, invalid inventory; never green.

The gate is intentionally read-only: it cannot merge PRs, call models, write to the user's machine, approve permissions, or schedule work. Example:

    python scripts/hermes_gpt_coordination_audit.py --repo Podtverzhdeno/hermes-agent --base main --output report.json
    python -m unittest discover -s tests/coordination -p "test_*.py" -v

Proposed merge sequence for existing drafts:
1. Freeze exact PR HEAD IDs and required API contract.
2. Compare #4/#5/#6 using one common test matrix; pick one correct implementation, do not merge all.
3. Reuse unique regression tests from rejected alternatives after review.
4. Integrate one canonical source of event schemas, not three mutually authoritative diagnostic modules.
5. Consolidate pyproject.toml changes in one integration-owned commit.
6. Run tests after merge at the final SHA, security review, CORS/SSE abuse and secret redaction.
7. Canary modern upstream v0.23.3 in an isolated HERMES_HOME; verify Kanban worker prompt delivery on actual Windows/WSL host.
8. Verify project STOP, restore, rollback and local persistent-worktree promotion before operator-approved deployment.

## 8. Ranked ideas — planning estimates, not empirical measurements

Weighted score = 0.30*impact + 0.25*evidence + 0.20*feasibility + 0.15*compatibility + 0.10*operating-cost (1 worst to 5 best). No score substitutes for tests.

| Idea | Impact | Evidence | Feasible | Compatible | Cost | Score | Action |
|---|---:|---:|---:|---:|---:|---:|---|
| PR overlap and ownership gate | 5 | 5 | 5 | 5 | 4 | 4.90 | implement read-only |
| Verified API/SSE retry contracts | 5 | 5 | 4 | 4 | 4 | 4.55 | choose one patch |
| Atomic explainable stop diagnostics | 5 | 4 | 3 | 5 | 4 | 4.25 | next canonical integration |
| Distributed STOP/fence/reconciliation | 5 | 4 | 2 | 4 | 3 | 3.80 | canary first |
| Browser companion | 4 | 2 | 2 | 3 | 3 | 2.85 | wait for inspected source |
| Unbounded autonomous fixes/approval | 1 | 1 | 2 | 1 | 1 | 1.20 | reject |

Change priorities only with incident frequency, measured MTTR, observed replays, checkpoint loss and cost. Avoid invented precision.

## 9. Explicit release gates

G0: current extension repository, manifest and runtime identified; if absent, API-only.
G1: all related PR bases/heads recorded with SHA, reviewers and capability ownership.
G2: one canonical task owner and one GPT adapter implementation; no competing scheduler.
G3: collision report complete; any HOLD has a documented resolution.
G4: 100-way duplicate, mismatch, stream error, cancellation and security regression tests pass.
G5: all failures have accurate reason or INSUFFICIENT_EVIDENCE; no false success.
G6: no sensitive user data in default logs; redaction adversarial tests pass.
G7: Windows/WSL prompt delivery and detached browser checkpoints tested on exact deployment.
G8: STOP across worker/cron/tool paths prevents post-revocation actions and reconciles uncertainties.
G9: CI + independent review tied to merged HEAD; restore/rollback test; owner approves promotion.

**Current verdict: NOT READY for unattended production.** No local browser state, live runtime trace, modern upstream canary, full CI evidence or long soak has been verified in this audit. The isolated coordination gate is a candidate tool, not a deployed agent service.

## 10. Selected primary references

- Hermes Kanban lifecycle: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- Hermes worker lanes and ownership: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
- Hermes v0.23.3: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
- GitHub PR files API and 3000-file cap: https://docs.github.com/en/rest/pulls/pulls
- GitHub compare API and 300-file cap: https://docs.github.com/en/rest/commits/commits
- GitHub REST rate-limit guidance: https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- W3C trace context: https://www.w3.org/TR/trace-context/
- OpenTelemetry GenAI agent-harness instrumentation, 2026-11-12: https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/
- OpenTelemetry privacy guidance: https://opentelemetry.io/docs/security/handling-sensitive-data/
- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- SQLite WAL: https://www.sqlite.org/wal.html
