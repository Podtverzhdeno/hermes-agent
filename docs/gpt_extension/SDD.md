# Hermes ↔ GPT Extension — System Design Document

**Revision:** 2026-11-22 / proposal v0.1  
**Baseline:** Podtverzhdeno/hermes-agent at main 7e9100901819ee44c16b4ddcb79a6bcb7909f591.  
**Parallel work:** draft PR #1 at bc66ef436253e552d5b206f5b4d757f0214ed92d implements an unactivated Autopilot SQLite coordination kernel. This document must not duplicate that ledger.  
**Activation:** No live GPT worker, browser automation, production watchdog, remote write adapter, or persistent auto-dispatch is activated by this document or diagnostics PR.

## 1. Engineering decision and goals

A Hermes GPT extension must be an **observable, versioned worker adapter over one authoritative durable task state machine**, not a web-chat polling script. It must explain what happened to each task and every stop, survive agent/session replacement, prevent unsafe retries and coordinate tens of workers with independently authenticated approvals and verification.

Accepted initial architecture:
- Single durable Autopilot ledger for task identity, attempt, owner, lease, fence, action reservations, approvals, exact-revision evidence and ordered events.
- Bounded admission and resource ownership before any worker launch; a task is not a live UI session.
- Typed GPT Responses API stream adapter and independent Hermes ACP adapter, both reporting provider lifecycle events and capability limits.
- Policy-enforced, fenced tool gateway, external-effect reservation and independent reconciliation before replay.
- Read-only diagnostic projector and incident timeline. Model text and UI responses are *not* the authority.
- Per-project Git worktree and optional scoped local runner/Obsidian synchronization with hash receipts.
- Independent verifier, cost/deadline/attempt budgets inherited by the entire task DAG.

Non-goals: bypass client limits or authentication, circumvent MFA/CAPTCHA, assume a ChatGPT DOM reply certifies success, force-merge experimental changes, imply a permanent daemon is running, replace the draft Autopilot control plane.

## 2. Verified source audit and hypotheses

| Observed code | Risk / failure mode | Status |
|---|---|---|
| acp_adapter/events.py:27–40 waits up to 5 s per session_update, exceptions DEBUG-only | Slow UI can stall agent callback, obscuring delivery failures | Code-backed risk, incident unverified |
| acp_adapter/server.py:57–59 global ThreadPoolExecutor max_workers=4 | Tens of prompts queue even when provider is healthy | Code-backed capacity limit |
| acp_adapter/server.py:~263–315 mutates a module-global terminal approval callback per prompt | Concurrent requests could cross-contaminate approval routing | Race hypothesis, needs reproducible test |
| acp_adapter/events.py:~59–85,126–149 pairs same-name tool starts/completions by FIFO | Out-of-order completion could be attributed to another call | Conditional hypothesis, test callback ordering |
| acp_adapter/server.py:~287–344 packages agent exceptions as text Error: ... | A failure may appear as end_turn to ACP caller | Source-backed classification risk |
| gateway/stream_consumer.py:~57–93 uses unbounded queue.Queue | Slow delivery can grow memory while model streams | Source-backed risk, load test missing |
| Autopilot PR #1 has ledger but no runner/typed GPT adapter | Safety kernel is not an active watchdog | Verified PR contents |
| Local Workspace MCP returned Session terminated | Live host/Obsidian monitoring unavailable this run | Observed connector error |

The fork main is dated April 1, 2026. Upstream may differ; do not merge/rebase without reviewing both heads and exact changed files. Code-backed hypotheses are not reproduced production bugs.

## 3. Required contracts and test gates

| ID | Requirement | Acceptance |
|---|---|---|
| F01 | Immutable task ID, request key, manifest and SHA | Duplicate request deduplicated; conflicting request rejected |
| F02 | Stage, attempts, owner/fence, heartbeat, budgets and reason code | Trusted read-only task snapshot can explain waiting and stoppage |
| F03 | Trace across GPT/ACP -> tool -> connector -> verifier -> local sync | Same correlation ID, attempt and fence in events |
| F04 | Multi-worker isolation, resource locks, bounded queue | Stale worker rejected; conflicting file writes blocked |
| F05 | Independent exact-action approval | Identity, target, parameters digest, expiry and reviewer verified |
| F06 | Durable reservation before external side effect | Crash with unknown outcome blocks blind retry |
| F07 | Independent trusted evidence at exact source SHA | No success on stale, missing or untrusted checks |
| F08 | Parent-global token/time/cost/attempt budget | Child retries cannot reset the budget |
| F09 | Redacted audit and bounded retention | No secret/prompt content in default telemetry |
| F10 | Separate observed symptom from inferred root cause | No model-crash claim solely from UI silence or expired lease |
| F11 | Supported transport-capability contract | No unsupported ChatGPT browser or app assumptions |
| F12 | Local worktree/Obsidian sync proofs | Expected SHA, write receipt and readback; disconnected remains pending |

Targets are unmeasured release goals, not service statistics: no unauthorized effects in fault injection; no unknown reserved action auto-replayed; no terminal success without trusted evidence; no duplicated task claim under concurrent tests; recover safe tasks after a forced restart. A 24–72h synthetic soak is a release gate, not work already performed.

## 4. Control-plane layout

```text
Approved intent / scheduled occurrence
    -> Validate immutable task contract, risk policy, budget, dependencies
    -> ONE Autopilot durable ledger <--> read-only status/diagnosis/incident API
    -> Admission (worker quota, provider quota, project file locks)
    -> Leased/fenced worker:
         official GPT Responses API | Hermes ACP | supported adapter
    -> Policy-enforced tool gateway:
         exact approval -> reserve external effect -> invoke
          -> verify receipt/readback -> reconcile/ack
    -> Versioned output manifest -> independent exact-SHA verifier
    -> Durable terminal outcome -> optional local runner/Obsidian sync
```

Trust boundary: the LLM sees task context and may propose actions, but must not approve itself, mark evidence trusted, alter permissions, bypass fencing or directly manipulate ledger state. Only an authenticated service can do that. The audit stream is not a second permission store.

## 5. Task status, stages and causes

Durable statuses inherit Autopilot's states: queued, running, verifying, retry_wait, waiting_approval, needs_reconciliation, blocked, failed, cancelled, succeeded.

Within running/verifying, observe finer stages:
intake; admission; dispatch; worker_boot; provider_request; provider_stream; tool_validation; approval_wait; effect_reserved; effect_call; effect_reconcile; workspace_write; test_run; remote_ci; artifact_sync; human_review.

Each stage has started/progress/stopped with typed outcome. An accepted update is not a completed task. A disconnected UI does not terminate a worker. Distinguish provider response.completed, response.failed, response.incomplete, network disconnect, token stream delta and function-call arguments completion. Persist provider response ID and supported event ordering information.

Typed reason codes (versioned, reviewable): lease_expired, worker_unreachable, queue_backpressure, connector_unavailable, provider_rate_limited, provider_auth_failed, provider_timeout, provider_stream_ended_unknown, tool_timeout, tool_permission_denied, tool_result_unknown, approval_wait, approval_denied, budget_exhausted, dependency_blocked, resource_lock_conflict, evidence_stale, verification_failed, operator_cancelled, schema_incompatible, state_inconsistent, unknown.

An expired lease proves only that a lease expired, **not** why; zero output might indicate backpressure, a slow model, lost transport, missing instrumentation or a crashed worker. The diagnostic cause field must say unknown unless independent evidence exists.

## 6. Durable event envelope and atomicity

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "task_id": "stable opaque identifier",
  "trace_id": "correlation",
  "span_id": "span",
  "parent_span_id": null,
  "source": "worker:api:1",
  "source_seq": 12,
  "ledger_seq": 506,
  "attempt": 2,
  "fence": 7,
  "stage": "provider_stream",
  "kind": "stage.progress",
  "reason_code": null,
  "subject_revision": "git-SHA",
  "occurred_at_utc": "2026-11-22T10:00:00Z",
  "received_at_utc": "2026-11-22T10:00:01Z",
  "elapsed_ms": 900,
  "artifact_refs": [],
  "payload_digest": "sha256:...",
  "redaction_policy_version": "v1"
}
```

Ingest is idempotent by event_id and source-local sequence, assigns ledger sequence transactionally. State transition and its event commit atomically, before ACK. Durable inbox ACK means received, **not verified**; use outbox for reliable notification. Deduplicate webhook delivery IDs, tolerate event reordering, detect source gaps and reject unrecognized mandatory schema versions. Separate wall-clock UTC timestamps from monotonic same-process elapsed time. Never log auth tokens, user session cookies, raw prompts, private file contents or full model outputs by default. Store digests or safe references.

External APIs are not universally exactly-once. Committed reservation before side effect, stable idempotency token where supported, independent readback and block on ambiguous outcome. For SQLite WAL use local filesystem, coherent transaction/checkpoint and SQLite backup API, not blind copy of a live DB.

## 7. Concurrency, backpressure and worker replacement

- A stable task ID outlives every GPT or ACP session; new worker receives manifest, checkpoint, lease/fence and scoped allowed tools.
- A single parent DAG budget bounds child spawning, tokens/cost, wall time, attempts and provider concurrency. Detect DAG cycles and repetitive repair loops.
- Exclusive file ownership, separate worktrees and compare-and-swap on expected file hashes. If another worker updates the resource, block or re-plan.
- Reserve capacity for verification/watchdog work; use priority ageing to avoid starvation.
- Check fence immediately before side effects; an old worker's prior model text cannot override revocation.
- Fix ACP global approval callback isolation and slow UI updates before increasing max_workers beyond 4.
- Bound transport queues; coalesce display-only deltas under pressure without dropping authoritative status/effect events.
- Keep read-only observer and scoped editor physically separate. A locally running program is not updated merely because GitHub or Obsidian changed.

## 8. Failure scenarios and safe recovery

| Evidence | Interpret without guessing | Allowed next action |
|---|---|---|
| No ACP update | UI transport may be down; agent may still run | Check trusted ledger heartbeat and provider/tool spans |
| ACP callback waiting 5s | Display delivery blocked | Instrument queue and transport, never label “GPT crash” |
| Four ACP threads occupied | Capacity reached | Throttle intake and expose admission delay |
| Lease expires | Ownership validity lost, reason unknown | Fence worker, retry only known-safe tasks |
| Reserved external effect times out | External result ambiguous | No automatic replay; provider receipt/readback |
| GPT stream closes without terminal event | Provider completion unknown | Preserve response ID; reconcile if supported |
| HTTP 429 | Provider throttled | Respect Retry-After/jitter and inherited budget |
| CI success for old SHA | Stale evidence | Reject and reverify exact head |
| Approval denied or expired | Action not authorized | Block, never rephrase and retry silently |
| Two writers target one file | Resource conflict | Lock/rebase/re-plan on owned branch |
| Obsidian MCP disconnected | Document sync incomplete | Persist pending sync; do not claim note changed |
| DB full/busy/corrupt | Trusted control plane unavailable | Fail closed on effects; restore backup and reconcile |
| User cancels while tool runs | New actions forbidden | Stop dispatch; reconcile in-flight effects |
| Model reports “tests passed” | Untrusted narrative | Require independent test/CI receipt |

Do not conflate a dashboard's lack of messages, a thread timeout, and provider completion status. The incident report separates the first **observed** fault, untested plausible causes, evidence gaps and safe next step.

## 9. Risks and priorities (estimated, not measured)

The weighted score is 0.35 risk reduction + 0.25 diagnostic value + 0.20 near-term feasibility + 0.20 long-term fit; each dimension 1–5. Scores are qualitative judgments.

| Initiative | R | D | F | L | Score | Priority |
|---|---:|---:|---:|---:|---:|---|
| One ledger + transactional event log | 5 | 5 | 4 | 5 | 4.80 | P0 — reuse Autopilot |
| Pure diagnosis + credible heartbeat/stages | 4 | 5 | 5 | 5 | 4.65 | P0 — module supplied |
| Fencing + effect reconciliation | 5 | 4 | 3 | 5 | 4.35 | P0 — review/integrate |
| Exact-revision independent verification | 5 | 4 | 3 | 5 | 4.35 | P0 — trusted adapter |
| Bounded UI transport + failure counters | 4 | 5 | 4 | 4 | 4.25 | P1 |
| OTel spans + measured SLOs | 3 | 5 | 4 | 5 | 4.10 | P1, not source of truth |
| Read-only operator dashboard | 3 | 4 | 4 | 4 | 3.65 | P2 |
| Uncontrolled ChatGPT DOM polling | 1 | 1 | 2 | 1 | 1.20 | Reject |

SQLite local WAL is a reasonable initial pilot store because Autopilot proposes it and it can be independently tested. For multi-host durable execution, evaluate Temporal against measured volumes and operational cost. Do not introduce distributed consensus before demonstrating a requirement for it.

## 10. Isolated implementation and tests

This branch supplies gpt_extension/diagnostics.py as a **pure, read-only** deterministic classifier accepting a frozen snapshot: task status, attempts/max, lease deadline, event recency, connector availability, external effect status, required evidence and trusted exact-SHA verification.

Safety precedence:
1. Uncertain reserved external effect or needs_reconciliation, independent of misleading success flags.
2. Claimed success without a verification policy, or with missing/stale/untrusted evidence: critical.
3. Cancellation, approval, missing/expired lease, budgets and terminal non-success.
4. Connector down, progress silence, queue eligibility and pending verification.
5. No observed blocker never asserts running health or successful completion.

A local isolated run of python -m unittest discover -s tests/gpt_extension -q passed 22/22 synthetic tests including empty required-evidence contract, wrong SHA, uncertain reserved effect, expiry, connector outage and ambiguous progress. This does **not** prove Hermes integration, real-model execution or GitHub CI success. A future trusted snapshot reader and permission service are required; this module cannot enforce external authorizations.

## 11. Planned integration in distinct ownership lanes

P0: SDD, static diagnosis, regression tests, engineering log, runbook — this PR.  
P1: Review/merge Autopilot PR #1 independently; expose authenticated read-only ledger snapshot projection; test schema and policy invariants.  
P2: Typed GPT Responses SSE adapter and ACP adapter conformance; bounded async telemetry; eliminate global approval callback race, reproduce out-of-order same-name completion.  
P3: Fenced tool gateway, effect receipts, exact approval; single sandboxed worktree worker; owner-authorized local runner.  
P4: File ownership/DAG scheduling for tens of agents, quota and budgeting, independent verifier and exact-SHA CI.  
P5: SQLite disaster recovery, webhook replay, provider throttling, host shutdown, injected external failures and 24–72h soak; stage a canary/rollback only after proven gates.

Agent work contracts must include parent ID, role ownership, expected artifact hashes, exact base SHA, explicit allowed paths, resource locks, required tests and budget. No model-generated test results can promote to trusted evidence. Integrators reconcile conflicts instead of silently overwriting. A0 policy review must be technically and credential-wise independent of the worker.

## 12. Operator visibility and incident narrative

Every task view should expose: task ID, project, manifest digest, exact SHA, owner, attempt/fence, last ledger event, active stage, queue delay, lease deadline, provider response ID, tool call ID, reserved effects, unknown outcomes, approval requirements, remaining budget, independent CI artifact and local/Obsidian sync hash.

An incident combines first observed fault, known timestamps, competing hypotheses explicitly marked **unknown**, effect safety state, bounded recovery/rollback route and independently checkable references. Deduplicate alert storms by stable incident fingerprint; never strip task identifiers or turn a symptom into a proven root cause.

Example (illustrative, not observed): effect.reserved -> connector.timeout -> lease.expired -> needs_reconciliation. Correct status: “External result unknown; reconcile before retry”, not “GPT stopped”.

## 13. Mandatory test matrix before active deployment

Fake GPT SSE terminal / failed / incomplete / disconnect; duplicate and reordered events; ACP slow client and cancellation; concurrent approvals and same-name out-of-order calls; 10–100 synthetic workers with bounded admission and no external actions; stale fence after reclaim; external effect crash before/after remote commit; GitHub CI wrong-SHA and webhook duplicate; local and Obsidian offline/reconnect; SQLite busy/full/WAL restore; injected malicious prompt/forged verifier; budget/kill switch; 24–72h soak with cost/latency measurement.

No daemon, persistent automation, model calls, shared file changes or high-impact external effects are enabled by the isolated diagnostics branch.

## 14. Grounded evidence and external references

Repository baseline:
- https://github.com/Podtverzhdeno/hermes-agent/blob/main/acp_adapter/events.py
- https://github.com/Podtverzhdeno/hermes-agent/blob/main/acp_adapter/server.py
- https://github.com/Podtverzhdeno/hermes-agent/blob/main/gateway/stream_consumer.py
- https://github.com/Podtverzhdeno/hermes-agent/pull/1

Standards/engineering references:
- https://developers.openai.com/api/docs/guides/streaming-responses
- https://developers.openai.com/api/reference/resources/responses/streaming-events
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/
- https://www.sqlite.org/wal.html
- https://docs.temporal.io/durable-execution
- https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

**Accuracy boundary:** this is a source-based SDD, not an assertion that millions of sources were searched, an hour of wall-clock experimentation elapsed, or a live 24/7 monitor was deployed.
