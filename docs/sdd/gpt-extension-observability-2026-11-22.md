# SDD: Hermes ↔ GPT integration, end-to-end observability and multi-agent recovery

**Status:** PROPOSED / partial implementation. **Date:** 2026-11-22. **Baseline:** `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591`.
**Change branch:** `sdd/gpt-observability-2026-11-22`.
**Scope:** existing Hermes OpenAI-compatible HTTP gateway in `gateway/platforms/api_server.py`, its agent-runner, tools, session state, and future integrations with GPT-facing clients. This is *not* a claim that an official ChatGPT browser extension or a ChatGPT account bridge exists.
**Owners:** architecture/A0; gateway/API; runner; persistence; security; verification. Parallel agents may implement bounded subprojects only under the coordination rules below.

## 0. Evidence and boundaries

Observed in baseline source (not inferred from runtime telemetry):
- API server exposes `/v1/chat/completions`, `/v1/responses` and SSE; runs synchronous `AIAgent.run_conversation` via a thread executor (see `gateway/platforms/api_server.py`).
- Old `_IdempotencyCache` cached only `(result, usage)` in a process-global OrderedDict; it awaited compute without reserving the key, silently overwrote key/fingerprint conflicts, and did not include session identity in the chat fingerprint. Result: duplicate execution **possible**, but not proven to have happened in production.
- Old SSE implementation swallowed a failed `agent_task` and still emitted `finish_reason=stop` and `[DONE]`; this hid execution failures from clients.
- The gateway previously allowed a configured non-loopback host with no API key. Restricting this at bind-time is a defense-in-depth change.
- `ResponseStore` uses SQLite WAL, `check_same_thread=False`, and separate `responses` / `conversations` writes. Cross-thread serializability, dangling names after eviction, and cross-process state transitions require investigation.
- Local Workspace MCP could not be probed successfully during this review (session terminated / HTTP 429). **This is an observability-channel failure, not proof that Hermes or the user's local worker has stopped.**
- No real production logs, GPT session traces, outage timestamps, model reasoning internals or stress-test evidence were available in this review.

### Explicit guarantees we DO NOT make
No guarantee of exactly-once external tool effects, cross-process deduplication, remote client liveness, access to hidden GPT reasoning, automatic browser-session replacement, or active continuous monitoring without a running collector. A model's private internal deliberation is **not** observable; only instrumented events, outcomes and declared statuses are.

## 1. Product goals and non-goals

**Goals (ordered):** G1 reconstruct a single GPT request from ingress to output/tool effect; G2 classify every failure/stop with evidence and confidence; G3 make retries bounded and safe; G4 coordinate dozens of agents without concurrent writes or stale ownership; G5 preserve privacy and the ability to diagnose a failure when logging infrastructure itself is failing; G6 propose and gate fixes through reproducible tests, not model self-ratings.

**Non-goals for current patch:** replacing Hermes runner, introducing a distributed queue into every deployment, unconstrained unattended commits to main, scraping private ChatGPT UI, logging prompts/cookies/tokens, pretending to read another agent's hidden context, or treating retries as exactly-once.

### Quality targets (proposed SLOs; not measured baselines)
- 100% of accepted API requests get a server-generated request_id; all terminal paths produce a reason_code.
- ≥99.9% of retained request events are reconstructable by correlation IDs (verified against a fault-injection replay corpus).
- For non-streaming idempotent requests within one process and TTL, 0 duplicate agent invocations under 100-way concurrent tests.
- 0 "success/stop" SSE terminal messages after known uncaught agent exceptions.
- 0 stale-lease agents allowed to **commit** writes after losing ownership, once a durable lease/fencing backend exists.
- p95 end-to-end latency overhead of telemetry-only mode <5%; background collector outages must not prevent an otherwise permitted user request unless audit persistence is explicitly set to fail closed.
- No plaintext prompt, bearer token, session content or auth cookie in standard logs and traces.

These are release gates, not claims of achieved production performance.

## 2. Target architecture (incremental, not a rewrite)

```text
GPT / OpenAI-compatible client
    | Authorization, traceparent, Idempotency-Key, optional X-Hermes-Session-Id
    v
[HTTP ingress] -- request_id; size/auth/rate/concurrency gates
    |
    v
[Run coordinator] -- run_id; attempt_id; owner_generation; canonical request fingerprint
    |         \--> append-only outbox/event ledger --> log collector + OTel exporter
    v
[Session snapshot] -- session revision, input snapshot hash, resume cursor
    |
    v
[Hermes AIAgent] -- model request ID, iteration budget, progress, usage
    |
    +--> [tool-effect ledger] -- effect_id, risk, idempotency policy, approval
    |          \--> [terminal / MCP / browser / GitHub / local workspace]
    |
    v
[Response commit] -- compare-and-swap session revision; stable response_id
    |
    v
[HTTP/SSE output] -- request_id, outcome + stop_reason
                 \--> durable checkpoint / recovery decision
```

**Deployment profiles:** P0 single-process SQLite/local logs; P1 one host multiple worker processes with durable coordinator + transactional outbox; P2 distributed fleet (PostgreSQL + queue + leases/fencing + OTel). The current patch is P0. Do not select P2 until evidence demands it; the API layer and event schema must allow later promotion.

### Causal identity contract
- `trace_id`: W3C-compatible distributed trace, generated if missing/untrusted; not a secret.
- `request_id`: unique accepted HTTP attempt, server-side; returned as `X-Hermes-Request-Id`.
- `run_id`: stable logical work item across retries/replacements; created at durable admission.
- `attempt_id`: unique execution attempt; changes on retry.
- `session_id`: logical conversation; never use a user-provided raw value as a log label.
- `agent_instance_id`: process and worker instance; `agent_generation`: monotonically increasing fencing version.
- `tool_call_id`: model/provider call ID if present; `effect_id`: dedup key for a *specific* external side effect.
- `source_revision`: code commit SHA + tool config version + prompt version + model identifier.
- `event_id`: durable unique event ID; `sequence`: strictly increasing **per run**, not a global counter.

The identity scheme must be documented before a multi-agent scheduler starts issuing work.

## 3. Atomicity, event journal and recovery

### Hard invariants
I1. A run has one authoritative owner at a time (`lease_owner`, `lease_epoch`, `lease_until`).
I2. Only a holder of the current `lease_epoch` may transition run state or commit a tool-effect/result. A stale worker may append diagnostic "stale attempt observed" information but may not commit.
I3. Every mutation uses `expected_revision` compare-and-swap; conflict => re-read and replan; never force overwrite.
I4. State update and corresponding outbox record are committed in **one database transaction**. External delivery may be at-least-once; consumers deduplicate `event_id`.
I5. `effect_id` is stable for a given side effect. If an effect's completion is unknown, mark `NEEDS_RECONCILIATION`, not `FAILED` and not blindly retry.
I6. No terminal "SUCCESS" without result persistence and response commit. No silent fallback to empty conversation history after a read failure in a durable session mode.
I7. Every terminal state has `reason_code`, `evidence_refs`, `executor_version`, `ended_at`, and `recovery_action`.
I8. A raw webhook/browser action requiring human approval never auto-resumes under a replacement agent without re-checking approval scope/version.

### Proposed states
`CREATED → ADMITTED → QUEUED → LEASED → RUNNING → WAITING_TOOL | WAITING_EXTERNAL | WAITING_APPROVAL | RETRY_SCHEDULED | PAUSED → SUCCEEDED | FAILED | CANCELLED | EXPIRED | NEEDS_RECONCILIATION`.

Any legal transition must be encoded in a transition table and tested. `UNKNOWN` is an *observation status*, not a successful or failed execution status. `CANCEL_REQUESTED` is a separate flag until cancellation is acknowledged. A subprocess killed by timeout and a tool that completed but whose ACK was lost are not equivalent.

### Concrete event envelope (v1 proposed)
```json
{
  "schema": "hermes.run.event.v1",
  "event_id": "evt_uuid",
  "observed_at": "2026-11-22T10:00:00.000Z",
  "run_id": "run_uuid",
  "attempt_id": "att_uuid",
  "request_id": "hrq_uuid",
  "agent_instance_id": "worker_uuid",
  "agent_generation": 7,
  "seq": 18,
  "phase": "tool",
  "event_type": "tool_attempt_finished",
  "state_before": "WAITING_TOOL",
  "state_after": "RUNNING",
  "reason_code": "tool_ok",
  "duration_ms": 740,
  "tool_name": "mcp.read_file",
  "effect_id": "effect_hash_or_null",
  "retry_count": 1,
  "trace_id": "w3c_hex",
  "evidence_refs": ["log://local/segment/offset"],
  "source_revision": "gitsha",
  "sensitivity": "metadata_only"
}
```

No raw prompt, tool arguments, access token, path containing user PII, request body, model private reasoning, or exception string by default. Optional restricted encrypted debug payload is separate, opt-in, scoped and TTL-limited.

## 4. Failure taxonomy and "why did it stop?"

| Code | Distinguishing evidence | Safe reaction |
|---|---|---|
| `client_disconnect` | transport close, agent may still be running | interrupt cooperatively; reconcile effects |
| `provider_rate_limit` | HTTP 429, retry_after, provider request ID | bounded jitter/backoff; global budget |
| `provider_timeout` | timeout with no committed output | unknown completion; inspect provider/effects first |
| `provider_5xx` | provider HTTP ≥500 and request ID | bounded retry if request safe |
| `auth_invalid` | 401/403 and auth policy | stop; no retry loop |
| `context_limit` | explicit token/context error | compact/split with provenance; no blind retry |
| `tool_timeout` | tool deadline exceeded | cancel; side-effect status UNKNOWN until reconciled |
| `tool_permission_denied` | authorization/policy engine rejection | wait for authorized intervention |
| `mcp_transport_unavailable` | MCP probe/channel error | mark observer unavailable, not worker dead |
| `session_store_unavailable` | DB connection/read/write fails | fail closed for stateful continuation |
| `idempotency_conflict` | same key, different fingerprint | HTTP 409, no work started |
| `idempotency_capacity` | reserved slots exhausted | HTTP 503 + Retry-After; no silent key eviction |
| `lease_expired` | missing verified heartbeats past TTL | freeze epoch; offer re-election |
| `stale_lease` | write carries outdated epoch | reject commit; worker must stop |
| `budget_exhausted` | tokens/iterations/cost/time deadline hit | checkpoint and report true stop reason |
| `user_cancelled` | signed user cancellation ID | cooperative cancellation with ACK |
| `dependency_failed` | parent requires failed prerequisite | block descendants; don't report success |
| `policy_blocked` | explicit security or human gate | no autonomous bypass |
| `partial_output` | bytes delivered, no terminal commit | mark incomplete, not success |
| `unknown_side_effect` | process crashed between tool commit and ACK | reconcile; do not auto-replay |

An LLM can *suggest* a root cause. The system must store `root_cause_hypothesis` separately from `verified_cause` with evidence. Confidence without observables is not verification.

## 5. Retry, timeout, streaming and rate limits

- One logical run may have many attempts; each attempt records its own deadline, owner epoch, errors and costs.
- Separate nested retry budgets: HTTP/OpenAI SDK retries (already enabled for certain failures), Hermes agent retries, queue retries, and tool retries. Avoid multiplicative retry storms.
- Retry only after classifying the operation as read-only, provider-idempotent, or effect-idempotent. A timed-out external write is not safe to repeat absent reconciliation.
- Respect provider `Retry-After`; exponential backoff with full jitter and a capped deadline; enforce user/project/provider token and request quotas.
- Streaming phase model: `headers_sent → first_token → tool_call(s) → final_chunk → terminal_success`; any uncaught exception before terminal success emits an error terminal event rather than `finish_reason=stop`.
- Reconnection after dropped SSE is not transparent replay. In P0, retry of *stream=true* with Idempotency-Key explicitly returns 400. In P1, resume requires durable cursor, replay buffer and stable run_id.
- Set independent time budgets for queue wait, first token, model turn, tool call, total run, and graceful cancellation. An HTTP transport timeout must not imply the tool did not commit.

## 6. Dozens of agents: explicit collaboration protocol

**Do not coordinate via dozens of mutable copies of one Markdown file or chat messages.** Use a durable task registry with one live owner per work item, revisioned evidence and append-only event history.

Minimum task record:
`task_id, spec_id, parent_task_id, owner_role, lease_owner, lease_epoch, lease_until, revision, dependency_ids, allowed_paths, read_set, write_set, acceptance_tests, evidence_refs, status, created_at, updated_at`.

### Roles
- A0 scheduler/auditor: authoritative task registry, lease allocation, conflict arbitration, final release gates.
- A1 spec/contracts: schema, user-facing behavior, threat model, compatibility.
- A2 runtime/gateway: request adapters, bounded concurrency, cancellation, idempotency.
- A3 observability/incident analysis: event producers, correlation, log hygiene, runbooks.
- A4 storage/recovery: migrations, outbox, leases/fencing, crash replay.
- A5 tests/release: fault injection, CI, reproducibility and controlled rollback.
- Additional agents: sharded feature owners; never gain authority merely by claiming a role in a prompt.

### Multi-agent handshake
1. Agent asks for task; controller grants a short-lived lease and `lease_epoch`.
2. Agent ACKs scope and base SHA. Unanswered lease expires; not proof of worker termination.
3. Every mutation carries task ID, expected file SHA / row revision and epoch.
4. Agent emits heartbeat and progress/checkpoint with evidence. Heartbeat is distinct from substantive progress.
5. On suspected failure the controller checks *two independent signals*: transport + authoritative state. Only then may it fence the old epoch and assign a successor.
6. Successor starts from a signed/context-bounded checkpoint, **not** untrusted free-form "the previous agent says done".
7. Changes land via short-lived branch + PR + checks + owner review. Repository's default branch is not an agent scratchpad.
8. Conflicting path ownership → rebase/reconcile, never last-write-wins. Cross-agent work is split by file/module or explicit lock.
9. If controller itself is partitioned, fail closed for conflicting writes. Do not create a second leader from one agent's belief.
10. Put a hard cap on simultaneously runnable agents; global per-provider cost/latency budgets are shared.

### Handoff bundle
`task_id, revision, lease_epoch, source_sha, files_changed, open_questions, tool_effects_known, tool_effects_unknown, tests_run, test_results, next_safe_step`. Every entry is validated against a durable source or labeled "agent assertion".

## 7. Security, privacy, resilience

- Unauthenticated non-loopback listening is prohibited. Local no-key mode must be documented as local-only and considered hostile if exposed through port forwarding.
- Use constant-time comparison for API keys in a later security patch; rotate secrets through secrets manager. Never store key/Authorization headers in traces.
- Do not log system/user prompts, tool payloads, file content, private user data, response text, session IDs or provider tokens by default. Redact debug logs, cap size and TTL; explicit auditing permissions.
- Distinguish `HEALTHY`, `DEGRADED`, `OBSERVER_UNAVAILABLE`, `WORKER_SUSPECT`, `STOPPED_VERIFIED`. A failed MCP/Tunnel health probe is not a process-death proof.
- Logs locally buffered on collector failure; bounded queue and dropped-log counter. If mandatory audit event cannot be persisted, fail closed for dangerous writes and mark denial.
- Protect event ledger from prompt injection: tool outputs and external issue contents are **evidence data**, never instructions overriding system policy.
- Sanitize high-cardinality metrics labels: don't label by raw session_id, request_id, prompts or paths.
- Prevent cross-tenant access to stored Responses and conversation aliases with per-principal ownership checks before deployment to multiple users; a shared bearer token is currently a shared trust boundary.

## 8. What to instrument and measure

**Traces:** ingress → gateway-auth → model request → tool dispatch → tool result → state commit → response egress. Follow OpenTelemetry GenAI `invoke_agent`, `execute_tool`, model spans where instrumented. Carry W3C `traceparent` across trusted services.

**Counters:** requests admitted, outcomes by reason_code, retries, dedup new/join/replay/conflict, tool effects reconciled, lease expiries, observer failures, unsafe retry attempts blocked, audit queue drops.

**Histograms:** time to first byte/token, queue delay, model latency, tool latency, total latency, cancellation time, event-persistence delay.

**Gauges:** active runs, in-flight tools, stale leases, unresolved unknown effects, queue depth, adapter health state, provider limit headroom.

**SLO alerts:** success-rate burn, unresolved UNKNOWN effects and high failure rate, latency saturation; human page only for actionable symptoms. Logging/monitoring failure is an independent alert.

**Per-run view (future UI):** ordered events with source/attempt/epoch, state transition, active dependency, last heartbeat, elapsed time, reason confidence, next safe action. Privacy-aware drill-down must not display sensitive payloads accidentally.

## 9. Decision matrix (scoring, not marketing)

Scored 1–5 against: **Impact 35%**, **root-cause visibility 25%**, **multi-agent safety 20%**, **feasibility 10%**, **cost/ease 10%**. Higher is better. Scores are provisional engineering judgments, not experimental results.

| Candidate | I | V | M | F | C | Weighted /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Dual-signal observer + failure taxonomy | 4 | 5 | 5 | 4 | 4 | 4.45 | P0 design; P1 implementation |
| Append-only transactional ledger/outbox | 5 | 5 | 5 | 3 | 3 | 4.60 | P1 foundation |
| Tool effect IDs + reconciliation | 5 | 5 | 5 | 2 | 2 | 4.40 | P1 security-critical |
| Durable lease/fencing + CAS | 5 | 4 | 5 | 3 | 3 | 4.35 | P1 multi-agent gate |
| Deterministic fault replay | 5 | 5 | 5 | 3 | 2 | 4.50 | P1 test infrastructure |
| Context snapshot + provenance | 5 | 4 | 5 | 3 | 4 | 4.45 | P1 recovery |
| Semantic event schema + OTel | 4 | 5 | 4 | 4 | 4 | 4.25 | P0–P1 incremental |
| Schema/contract gates in CI | 4 | 4 | 5 | 5 | 5 | 4.35 | P0 implement |
| SLO burn-rate alerting | 4 | 4 | 4 | 4 | 4 | 4.00 | P1 when metrics exist |
| AI-assisted incident hypothesis | 3 | 3 | 3 | 4 | 4 | 3.25 | P2 assist only |
| Unreviewed autonomous push to main | 1 | 2 | 1 | 1 | 1 | 1.25 | REJECT |

**Ranking caution:** high scores do not override dependency ordering. Durable event/outbox + schema precede lease enforcement; effect reconciliation precedes automatic tool retries; reliable monitoring precedes LLM-based root-cause advice. A flashy "self-healing" dashboard that lacks event causality is inferior to a small accurate ledger.

## 10. Implemented in the current branch (P0 patch)

- Per-adapter single-flight `_IdempotencyCache`: same key+fingerprint joins in-flight task, stable response object replays, mismatch is 409, full cache responds 503 and preserves pending work.
- Canonical JSON fingerprint, complete chat body plus explicit provided session ID, endpoint namespace; full Responses object/DB write is inside cached computation.
- SSE with `Idempotency-Key` is explicitly rejected rather than falsely claiming deduplication.
- API request-level correlation events (`hermes.api.event.v1` metadata-only), request ID response header and SSE header.
- SSE agent exception now emits error payload rather than a false successful final `stop`.
- Non-loopback bind without bearer key is refused.
- Added regression cases for competing in-flight calls, duplicate result IDs, cancellation of a waiter, conflict, capacity, failure cleanup and endpoint isolation.

**Current gaps:** P0 cache is lost on restart, cross-process requests are not coordinated, HTTP status does not prove an external tool effect, logging is not yet durable with event sequence/traceparent, store writes are not one atomic transaction, and the original runner remains a synchronous thread executor. New unit and integration tests require CI/live confirmation.

## 11. Staged implementation and release gates

**Gate P0 / current branch:** Python syntax and API tests pass; load tests for 1/2/10/100 simultaneous retries; error-SSE final status; no token leaks; no unauthenticated public bind; stable replay response ID. Fail gate if unknown test outcome.

**Gate P1a / lifecycle events:** instrument runner callbacks and tool dispatch with stable run/attempt IDs. Implement semantic event schema and per-run ordered event log; event-log schema migration must be reversible and versioned.

**Gate P1b / durable execution:** transactional outbox and dedup tables, crash-consistent effect-reconciliation state, leases/fencing/CAS, bounded replay. Verify crash between each step (`before write`, `after external commit`, `before ACK`, `after ACK`) using a fake tool that counts commits.

**Gate P1c / multi-agent:** run ≥50 simulated agents contending for 10 tasks with delayed heartbeats, clock skew, partitioned observer, duplicate messages, and stale epoch writes. Zero accepted stale writes; all ambiguous effects surface as UNKNOWN/NEEDS_RECONCILIATION.

**Gate P2 / operations:** shadow event collection in real deployment, 7-day SLO baseline, rollback drill, dashboard/runbooks and provenance snapshots. Autonomous fix suggestions are always behind tests + PR approval; no force merge.

**Rollback:** current isolated branch can be reverted without database schema migration. For future persistence, use expand→migrate→contract, versioned event schemas and backward-compatible readers. Never roll back by deleting unresolved effects.

## 12. Research anchors (primary sources)

- OpenAI SDK retry semantics, request IDs: https://developers.openai.com/api/reference/python
- OpenAI rate limits and Retry-After: https://developers.openai.com/api/docs/guides/rate-limits
- OpenTelemetry GenAI agent spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
- OpenTelemetry tool execution spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md
- OTel context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- Temporal durable execution and heartbeat: https://docs.temporal.io/durable-execution ; https://docs.temporal.io/activities
- Temporal idempotent activities: https://docs.temporal.io/activity-definition
- MCP Tasks Extension (2026-07-28), cooperative cancellation: https://modelcontextprotocol.github.io/ext-tasks/specification/2026-07-28/tasks.html
- Google SRE monitoring, four golden signals: https://sre.google/sre-book/monitoring-distributed-systems/
- SQLite WAL concurrency limits: https://www.sqlite.org/wal.html
- NIST SP 800-61 Rev.3 incident response records: https://csrc.nist.gov/pubs/sp/800/61/r3/final

## 13. Open questions for controlled decisions

Q1. Which exact client is the desired "GPT extension": OpenAI-compatible frontends, local GPT integration, or a separate ChatGPT browser/plugin surface? Current code changes target the proven OpenAI-compatible Hermes gateway.
Q2. Which safety classes of tools may be retried automatically, and which require reconciliation or human approval?
Q3. Single host vs multi-host deployment? This drives whether SQLite is suitable for P1 and which coordinator technology is justified.
Q4. What retention, data residency and audit access apply to event logs? **Never** defer privacy decisions until after capturing payloads.
Q5. Required availability, cost ceilings and concurrency targets? Do not infer budgets.

None of these questions blocks P0 safe corrections; they do block unsupervised production rollout of multi-worker recovery.
