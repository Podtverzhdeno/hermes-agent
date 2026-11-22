# Hermes ↔ GPT Bridge: observable, recoverable, multi-agent execution (SDD v0.1)

**Date:** 2026-11-22. **Status:** design proposal + implementation gate; NOT a claim of production readiness.
**Owner area:** GPT interface/transport, observability, failure diagnosis. Other workstreams own `autopilot/ledger.py` and `agent/skill_harness.py`; do not duplicate them.
**Base:** `Podtverzhdeno/hermes-agent` main at `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (observed 2026-11-22). Separate in-progress branches: `feat/autopilot-durable-ledger-20261122` and `feat/skill-harness-contracts-20261122`.

## 0. Evidence and constraints

Verified code: `gateway/platforms/api_server.py` supports OpenAI-compatible Chat Completions and Responses, SSE streaming, `X-Hermes-Session-Id`, and best-effort agent interruption on SSE disconnect. `run_agent.py` runs the synchronous core; `_run_agent()` offloads it into an executor. `api_server.py` has an in-memory global idempotency cache, and the SSE handler currently ignores exceptions from the task before sending a normal end-of-stream marker. See tests in `tests/gateway/test_api_server.py`.

Observed control-plane limitation: Local_WorkSpace MCP returned a terminated session; separate read-only MCP returned HTTP 429 on 2026-11-22. These are *connector-observed errors*, not evidence that Hermes itself failed. No live Chrome/ChatGPT tab, user browser runtime, user log history, or production process list was inspected.

Distinguish two modes:
- **API mode (preferred production path):** supported OpenAI API/client and Hermes API adapter, authenticated/authorized provider usage, explicit request IDs, deterministic request/response contracts.
- **UI mode (optional, explicitly user-authorized local browser integration):** extension/CDP uses a user's own open tab under explicit consent. Treat DOM changes, page reloads, debugger detach, service worker suspension, message edits, human approvals, and uncertain send acknowledgment as normal failure classes. Never extract session cookies or bypass platform controls. UI mode must NOT be a prerequisite for core reliability.

Never infer `exactly-once` from a successful HTTP response. With external effects, the achievable goal is *at-least-once delivery + dedupe + effect verification + human reconciliation of uncertain outcomes*.

## 1. North-star invariant

For every accepted request, an operator can answer within a bounded time:
1. Who owns the work, where did it start, and which exact model/transport/agent version acted?
2. What was the last **durably confirmed** state, and what step is currently awaited?
3. Is it working, waiting, retrying, blocked, human-paused, cancelled, failed, or unknown?
4. What evidence supports the inferred root cause, and what evidence contradicts it?
5. Can it be safely retried, resumed from a checkpoint, rolled back, or escalated?
6. Did an irreversible external effect occur? If unknown, prohibit an automatic duplicate.
7. Which version and test demonstrated that the fix works?

**Invariants**: no silent terminal success on an exception; no execution without an identifiable run; no mutable side effects without idempotency/effect evidence; no two writers for one leased step; no unbounded retries; no sensitive prompt/cookie/token content in default logs.

## 2. Architecture and boundaries

```text
GPT UI extension (optional) ─┐
                            ├── Gateway ingress / protocol normalization
OpenAI API/SDK client ──────┘          │
                                      v
                           Trace + command envelope
                          [run_id, trace_id, step_id,
                           attempt, deadline, idem_key]
                                      │
                           Durable command ledger*
                          (atomic claim / CAS / lease)
                                      │
                           Scheduler / admission gates
                      [quota, concurrency, permission, human]
                                      │
                          Hermes AIAgent + tools + LLM
                                      │
                             Effect verifier / outbox
                                      │
                           Checkpoint + result publication
                                      │
                           Diagnostics / incident log / UI

* Reuse autopilot/ledger.py after its API and tests are reviewed; no
  premature import of another agent's unmerged implementation.
```

Event publication and effect commit require an outbox/reconciliation protocol; merely writing a log *after* calling a tool leaves a crash gap. Store command + intent before dispatch; record acknowledgment and observable external effect afterward. If the process dies between these, mark `OUTCOME_UNKNOWN`, not `FAILED` and never blindly replay.

Core components and ownership:
- `gateway/platforms/api_server.py`: HTTP input, auth, SSE lifecycle, error signaling. This branch may patch narrowly here.
- `gateway/gpt_bridge_diagnostics.py`: structured, content-free operational events; a compatibility adapter, NOT source of durable truth.
- `autopilot/ledger.py` (other branch): proposed durable execution store, pending review of exact schema and transaction guarantees.
- Browser bridge (later): extension background/content-script/Native Messaging or trusted local process; no direct untrusted origin access to a CDP endpoint.
- Operators: `hermes doctor`, future `hermes runs explain <run_id>` and `hermes runs resume <run_id>` only once backed by verified state.

## 3. Atomic event contract

A canonical event is immutable and has:
```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "run_id": "uuid",
  "trace_id": "32 lower-case hex W3C trace id",
  "span_id": "16 lower-case hex W3C span id",
  "parent_span_id": null,
  "session_hash": "sha256 prefix, never raw session ID",
  "agent_id": "opaque stable worker ID",
  "step_id": "stable logical operation identifier",
  "attempt_id": "unique physical attempt identifier",
  "idempotency_key_hash": "sha256 or null",
  "transport": "api|browser_ui|mcp|tool",
  "state": "RUNNING",
  "event_type": "stage.started",
  "reason_code": null,
  "ts_utc": "RFC3339",
  "monotonic_ms_since_start": 1274,
  "lease_epoch": 12,
  "resource_version": 43,
  "code_revision": "git SHA",
  "model_route": "provider/model alias; omit secrets",
  "evidence_refs": ["redacted artifact pointer"],
  "payload_sha256": "hash of canonicalized payload, never payload"
}
```
For initial instrumentation, a subset is acceptable if fields are explicitly null/unsupported and diagnostics remain **non-authoritative**. Persist with a database transaction, unique `event_id`, and `UNIQUE(run_id, step_id, attempt_id, event_type, event_sequence)` or an equivalent unique sequence. Use W3C Trace Context on network boundaries; do not trust external `traceparent` blindly, validate length/format and avoid injecting untrusted `tracestate` into logs.

No prompt/response body, API key, OAuth token, browser storage, cookie, screenshot, raw tool arguments, or personal data by default. Debug payload capture: explicit opt-in, field-level redaction, encryption at rest, TTL, operator access audit.

## 4. State machines (authoritative ledger design)

Execution:
```text
CREATED -> VALIDATED -> QUEUED -> LEASED -> RUNNING
RUNNING -> WAITING_TOOL | WAITING_MODEL | WAITING_HUMAN | CHECKPOINTING
WAITING_* -> RUNNING
RUNNING -> SUCCEEDED | FAILED | CANCELLED | OUTCOME_UNKNOWN
RUNNING -> RETRY_SCHEDULED -> QUEUED
LEASED/RUNNING without valid heartbeat -> SUSPECT -> RECOVERING
RECOVERING -> QUEUED | WAITING_HUMAN | OUTCOME_UNKNOWN
```
Terminal states immutable except through a new compensating run linked to the original. `SUSPECT` is not failed. `OUTCOME_UNKNOWN` is an explicit terminal/parked state requiring reconciliation. UI display must differentiate "no heartbeat", "client disconnected", "agent interrupted", "provider failure", "no permissions", and "completed result not delivered".

Every transition: compare-and-swap `(run_id, version, lease_epoch, state)`, append event, update aggregate, and outbox record atomically in one transaction. Reject stale lease epochs (fencing token) even if worker finishes late. Agents cannot directly override another agent's state.

A *heartbeat* means progress of the executing worker only; do not treat it as external effect acknowledgment. Use bounded per-stage deadlines, monotonic in-process timing for duration, wall clock only for cross-machine timestamps.

## 5. Failure taxonomy + diagnostic evidence

| Code | Observable evidence | Automated response |
|---|---|---|
| `AUTH_REQUIRED` / `AUTH_EXPIRED` | 401 / provider credential exception, not raw credentials | Pause, request reauthorization; never loop |
| `PERMISSION_DENIED` | 403 / denied tool scope | Human action, no auto retry |
| `THROTTLED` | 429 + retry-after / rate limit; distinguish quota | Bounded jitter/backoff, queue admission; no account rotation |
| `UPSTREAM_UNAVAILABLE` | 502/503, connection reset | Retry read-only or idempotent calls only |
| `MODEL_REJECTED` | context limit / invalid model / validation | Adapt input or fail with explicit reason |
| `BROWSER_TARGET_LOST` | CDP detach, target close / navigation | Re-discover authorized tab; reconcile prior send |
| `EXTENSION_SUSPENDED` | MV3 worker restarted, missing heartbeat | Recover from durable checkpoint; re-handshake |
| `DOM_CONTRACT_CHANGED` | selector/landmark/assertion mismatch | Stop writes; capture redacted structural evidence |
| `SSE_CLIENT_GONE` | write failure / reset / cancellation | Interrupt agent best effort; reconcile still-running executor |
| `WAITING_HUMAN` | explicit approval checkpoint | No timer-driven bypass |
| `DEPENDENCY_UNAVAILABLE` | MCP SSE 429, connector session terminated | Circuit-break & retry probe with budget; verify local process separately |
| `IDEMPOTENCY_CONFLICT` | same key, different fingerprint | 422; operator/caller correction |
| `IN_PROGRESS` | duplicate in-flight key | 409 + later retry; no duplicate dispatch |
| `SIDE_EFFECT_UNCERTAIN` | tool called but ack lost | Verify external world or require human |
| `WORKER_STALLED` | deadline passed and no stage progress | Suspect + lease/fencing check; then recover |
| `STREAM_FAILED` | backend task raises after SSE headers sent | Emit a structured error event; NEVER report normal stop |
| `UNKNOWN` | insufficient evidence | Preserve evidence, do not invent root cause |

Classify 429 as **symptom**, not universally transient. Observed Local Workspace 429 is `DEPENDENCY_UNAVAILABLE` with `root_cause=unverified`. Provider 429 may be quota, burst rate, or other policies.

## 6. Multi-agent coordination: tens of concurrent agents

- Each worker publishes `agent_id`, version/capabilities, per-step owner, lease expiry, heartbeat, parent request. Registration and lease renewal are transactional.
- Every task has precisely one logical owner at a time; parallel reviewers are independent children with read-only capability unless explicitly assigned distinct files.
- Merge strategy: one feature branch/PR per bounded ownership area, revision-pinned base, CODEOWNERS/merge queue, required CI and contract checks; no blind commits to `main`.
- Claims must use lease epochs and optimistic concurrency; stale workers cannot produce a final state. External tool effects need their **own** idempotency/reconciliation.
- Log causality: `requested_by`, `delegated_to`, `depends_on`, `blocked_by`, `supersedes`. One agent's text summary is not evidence without artifact/commit/test identifiers.
- Fairness/backpressure: bounded queue per source/tenant, explicit concurrency ceilings, reserved diagnostic capacity; prevent an incident storm from consuming all workers.
- A failed worker is replaced only after lease expiry *and* recorded outcome reconciliation. Replacing a chat agent is not the same as retrying a side-effecting step.
- Observer vs executor separation: the critic can publish findings; it cannot silently repair permissions, secrets, user approvals, or irreversible actions.

## 7. Recovery playbooks

1. **Ingress**: allocate run id, authenticate, validate request, register deadline and fingerprint; reject malformed inputs without executing tools.
2. **Dispatch**: atomically claim step; checkpoint `INTENT_COMMITTED`; invoke model/tool. Capture upstream request IDs, tool name (not args), deadlines.
3. **Progress**: append event at every boundary: received, queued, started, request_sent, first_token, tool_requested, tool_approved, tool_started, tool_finished, checkpointed, response_published.
4. **Timeout**: inspect current wait stage and last evidence; differentiate genuine provider wait from lost observer. Do not retry a speculative side effect.
5. **Restart**: rebuild projection from ledger, detect leased orphan work, fence prior lease, reconcile unresolved external results, then resume.
6. **Delivery**: result committed != result delivered. A client disconnect after commit is delivery failure, not model failure. Reconnect reads result by run id; no duplicate execution.
7. **Operator action**: each incident has `symptom`, `evidence`, `hypothesis`, `confidence`, `test`, `fix`, `rollback`, `verification`.

## 8. Specific existing-code hazards to address

**H-01: idempotency race (high, verified).** `_IdempotencyCache.get_or_set()` checks memory then awaits the computation **before** inserting a result. Two concurrent equal keys may execute twice; a reused key with a changed payload also executes. Scope keys by caller/session, canonicalize full request, detect 409 in-flight and 422 mismatch; persist idempotency before promising cross-process guarantees. Current cache remains per-process only.

**H-02: false SSE success (high, verified).** `_write_sse_chat_completion()` swallows task exceptions and still emits `finish_reason=stop` + `[DONE]`. Consumer cannot know why the work stopped. Emit a machine-readable error envelope with run id and classified code; never send normal completion on failure.

**H-03: cancellation ambiguity (high, verified by architecture).** `agent_task.cancel()` cancels the asyncio wrapper but cannot guarantee a synchronous `run_in_executor` worker/tool stops immediately. Record `CANCELLATION_REQUESTED` distinct from `CANCELLED_CONFIRMED`, and never immediately recycle a leased side-effecting step.

**H-04: no durable shared run truth (high, observed scope).** In-memory cache/queue is not sufficient across process death or dozens of workers. Reuse ledger branch after interface review; avoid a second datastore.

**H-05: page/runtime lifecycle (high, conditional UI mode).** Chrome Manifest V3 workers may be suspended; CDP targets may detach; automation needs durable re-handshake and clear `OUTCOME_UNKNOWN` semantics. Not a claim that this happened in the user's browser.

**H-06: hidden sensitive data (critical, design).** Provider SDK traces, exception text, tool output and UI screenshots may include personal data. Use no-payload logging by default and explicitly test redaction.

## 9. Prioritized work scoring (not measurement of actual production incidents)

Use weighted utility per candidate: 30% severity/risk reduction, 25% evidence confidence, 20% time to verifiable implementation, 15% compatibility, 10% operating cost. Score 1–5 each; subtract a 1–5 blast-radius penalty as a separate review dimension. Design-priority ranking:

| Idea | Sev | Evidence | Feasibility | Compat | Cost | Weighted /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| H-02 explicit SSE failure signaling + correlation | 5 | 5 | 5 | 4 | 5 | 4.85 | P0 implement/test |
| H-01 in-flight idempotency conflict | 5 | 5 | 4 | 4 | 5 | 4.65 | P0 implement/test |
| Atomic durable ledger + fencing | 5 | 4 | 2 | 4 | 3 | 3.80 | P0 after other branch API review |
| Payload-free structured trace schema | 5 | 4 | 4 | 5 | 4 | 4.45 | P0 |
| Diagnostic "why stopped" projection | 5 | 4 | 3 | 5 | 4 | 4.25 | P1 |
| Browser UI adapter checkpoints | 4 | 2 | 2 | 3 | 3 | 2.85 | P2 conditional |
| Automatic AI root-cause fixer with write permissions | 3 | 1 | 2 | 1 | 1 | 1.80 | Reject until bounded/authed |

Scores are editorial planning estimates; not empirical benchmarks. No external claims of universal best practice are made from these scores.

## 10. Verification, falsification and release gates

Safety tests:
- 32+ simultaneous duplicate requests to one key -> **1 execution at most** inside one adapter process; concurrent duplicate receives 409 or safely joins.
- Same key, different content -> deterministic 422, no execution.
- Cancellation of the HTTP waiter does not silently mark effect cancelled; a running thread's outcome remains observable.
- Tool exception after first SSE byte -> explicit terminal error, no false `stop`.
- Stream client disconnect -> observed disconnect and separate cancellation-requested outcome.
- No auth/session ID/prompt/token/raw tool arguments in log strings, even with exception text containing secrets.
- Two workers attempt same lease -> exactly one wins; late-fenced worker's commit rejected.
- Kill at every execution boundary -> no irreversible double side effects without reconciliation.
- Synthetic 401/403/429/503/CDP-detach/MV3-restart/timeout/partial-stream and recovery paths.
- Retry budget exhaustion and customer cancellation produce distinct terminal diagnoses.
- Cross-version schema readers skip unknown optional fields; fail on incompatible major schema.
- 10/30/100-agent load: bounded memory, queue latency and no starvation, p95 checkpoint-to-diagnosis and recovery metrics measured, not assumed.

Metrics to implement and baseline **before** setting targets: `hermes_run_active`, `hermes_run_terminal_total{status,reason}`, `hermes_stage_duration_seconds`, `hermes_lease_expired_total`, `hermes_duplicate_suppressed_total`, `hermes_undetermined_outcome_total`, `hermes_sse_false_success_total` (goal: zero), `hermes_gpt_bridge_recovery_seconds`. Do not label these as measured yet.

Staged rollout: offline unit contract -> integration with mocked gateway -> fault-injection run -> opt-in canary on one profile -> concurrent workers in shadow mode -> feature-gated production. Every rollout has explicit rollback, version pin, migration rehearsal and acceptance record.

## 11. Diagnostic log / evidence journal

| UTC date | Evidence | Status | Inference confidence | Required follow-up |
|---|---|---|---|---|
| 2026-11-22 | Local_WorkSpace list_workspaces: `Session terminated` | Observed tool error | High symptom; low cause | Probe tunnel/MCP with credentials checked locally; do not expose secrets |
| 2026-11-22 | temp_folder_readonly list_workspaces: MCP SSE HTTP 429 | Observed tool error | High symptom; low cause | Inspect retry-after, server logs, connector budget and process state |
| 2026-11-22 | GitHub main 7e91009, separate active feature branches | Observed source state | High | Avoid conflicting edits; integrate via PR after checks |
| 2026-11-22 | API idempotency awaits compute before saving result | Verified static defect H-01 | High | Fix and concurrency test |
| 2026-11-22 | SSE suppresses backend error and emits stop | Verified static defect H-02 | High | Fix and regression test |

Next operator record must include SHA, test command, result counts, and limitation. Do not label an unexecuted test "passed".

## 12. Primary technical references (retrieved 2026-11-22)

- W3C Trace Context: https://www.w3.org/TR/trace-context-1/
- OpenTelemetry GenAI semantic conventions: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
- OpenAI Agents SDK tracing privacy: https://openai.github.io/openai-agents-python/tracing/
- OpenAI API request ID and error handling: https://developers.openai.com/api/reference/overview
- IETF HTTPAPI Idempotency-Key draft -09 (Internet-Draft, NOT an RFC): https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09
- Temporal durable execution/idempotent Activities: https://docs.temporal.io/durable-execution and https://docs.temporal.io/activity-definition
- Chrome MV3 service worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome DevTools Protocol: https://chromedevtools.github.io/devtools-protocol/

## 13. Decision log

**ADR-001 (accepted for this branch):** Treat OpenAI-compatible API mode as primary baseline; do not assume access to a live authenticated ChatGPT tab.

**ADR-002 (accepted):** Diagnose with structured content-free run and step events; keep event types independent from proprietary models.

**ADR-003 (provisional):** The existing `autopilot/ledger.py` branch should be the authoritative durable layer after code review. No duplicate ledger in this branch.

**ADR-004 (accepted):** Use one GitHub feature branch per parallel agent area, PR-based integration and explicit ownership/rebase.

**ADR-005 (proposed):** Prefer 409 for concurrent in-flight idempotency and 422 for fingerprint conflict; follow evolving IETF HTTPAPI draft, with compatibility behavior documented. Never promise cluster-wide at-most-once until a shared store and effect verification exist.

**ADR-006 (accepted):** A GPT integration may not infer a successful tool action merely from transport success or absence of exceptions.

**Implementation snapshot (2026-11-22):** Branch now adds `gateway/gpt_bridge_diagnostics.py`, extends `gateway/platforms/api_server.py` with 409/422 rejection, `X-Hermes-Run-Id` and explicit `hermes.error` SSE event on execution failure, plus `tests/gateway/test_gpt_bridge_diagnostics.py`. Test results are **not yet verified** here; this note is not an assertion that the branch is deployable.

**Unresolved:** Exact extension deployment/package (Chrome MV3, VS Code, local native bridge, or API client), current process topology, production logs, user consent prompts for browser UI control, and security/compliance constraints. These must be established from actual workspace evidence rather than assumed.
