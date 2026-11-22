# Observability, stop-reason diagnosis and failure injection

**Status**: target contract, not evidence of implementation.

## 1. Evidence hierarchy

In descending reliability:
1. Provider-signed or authenticated receipt of the external effect, correlated
   with a stable effect key (and independently read back when possible).
2. Durable internal state transition committed with its outbox event and epoch.
3. Hermetic integration test with captured provider stub and fault injection.
4. Distributed trace/span with monotonic timing, version and correlation IDs.
5. Browser DOM observation / screenshots / model narration.

A model's assertion "I completed the job" is NOT a completion receipt.
A 200 HTTP response is NOT proof that a tool side effect committed. A missing
UI response is NOT proof of failure. Keep these distinctions in the dashboard.

## 2. Normalized event contract (versioned)

Required fields:
```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "operation_id": "uuid",
  "step_id": "uuid-or-null",
  "parent_step_id": null,
  "agent_id": "agent-01",
  "worker_instance_id": "host-process-boot",
  "session_id_hash": "sha256",
  "trace_id": "32lowerhex",
  "span_id": "16lowerhex",
  "seq": 71,
  "attempt": 3,
  "lease_epoch": 7,
  "event_type": "STEP_BLOCKED",
  "state_from": "RUNNING",
  "state_to": "WAITING_APPROVAL",
  "reason_code": "APPROVAL_REQUIRED",
  "reason_class": "intentional_pause",
  "severity": "info",
  "observed_at_utc": "2026-11-22T10:00:00Z",
  "elapsed_monotonic_ms": 1283,
  "component": "tool.dispatch",
  "provider": "opaque-provider-id",
  "code_commit_sha": "gitsha",
  "policy_version": "sha256",
  "tool_schema_version": "v1",
  "payload_digest": "sha256",
  "artifact_refs": ["redacted-receipt-ref"],
  "next_action": "WAIT_FOR_OPERATOR",
  "redaction_version": "r1"
}
```

Never include cookies, OAuth tokens, Authorization headers, native-host secret,
user prompts, file bodies or full browser DOM in ordinary events. Hash session
IDs with a keyed function if they might be guessable; plain unsalted SHA-256
of user identifiers is not a privacy boundary. Separate encrypted evidence
storage requires explicit authorization, access logs, retention and deletion
support.

**Event invariants:** event ID globally unique; sequence strictly increasing
per operation; no duplicate terminal event; causal parent exists; actual
`state_from` equals stored state; epoch and owner match the writer; version
of schema explicitly checked by consumers; unknown event versions go to a
quarantine queue rather than being silently interpreted. No event implies
success without result evidence. Local event payload and distributed trace
need a shared `operation_id` but tracing must not be the canonical store.

## 3. Trace/span tree

```text
operation.run           (one trace per user-intent)
  ingress.validate      (authn/authz, body size, origin, policy)
  operation.claim       (queue wait, lease epoch)
  session.load          (cache/db, session revision)
  agent.run             (model/provider, prompt cache info)
    gen_ai.client.inference  (model request; OTel GenAI conventions)
    agent.plan          (plan ID, not raw reasoning text)
    gen_ai.execute_tool (tool name, tool schema rev, attempt)
      approval.wait     (operator decision ref)
      tool.dispatch     (effect key and remote request ID)
      effect.verify     (receipt or uncertainty reason)
  state.commit          (ledger tx, outbox row, version)
  delivery.send         (transport, ack status, retry)
```

Propagate W3C `traceparent` and `tracestate` to trusted services; do not
propagate arbitrary browser-derived baggage or secrets. Follow pinned OTel
GenAI semantic-convention versions; these conventions evolve. Do not send
tool arguments, prompts or outputs to telemetry collectors unless separately
approved and redacted. Record `trace_id` even when spans are sampled out.
Sampling must keep 100% of failure/uncertainty events in the durable ledger;
tail-based tracing may retain complete traces of failed operations within
privacy quotas.

## 4. Stop-reason taxonomy

| Code | Class | Symptom | Safe operator action |
|---|---|---|---|
| APPROVAL_REQUIRED | intentional_pause | authorization gate opened | wait; display approver, expiry, scope |
| APPROVAL_EXPIRED | blocked | operator approval timed out | request fresh approval, never synthesize |
| USER_CANCELLED | terminal | operator explicit cancel | verify child/tool stop, don't call success |
| BUDGET_EXHAUSTED | terminal | iterations/tokens/cost/time cap | pause for new budget authorization |
| PROVIDER_RATE_LIMIT | transient | HTTP 429 | honor Retry-After with jitter |
| PROVIDER_UNAVAILABLE | transient | 5xx/network | bounded retry if effect is safely retryable |
| PROVIDER_TIMEOUT_EFFECT_UNKNOWN | uncertain | tool timed out after dispatch | read-only reconciliation; no blind repeat |
| STREAM_INTERRUPTED | uncertain | SSE interrupted without terminal receipt | resume by cursor or reconcile |
| BROWSER_CONTEXT_LOST | uncertain | tab/worker restarted, DOM gone | re-identify session and effect state |
| BROWSER_SELECTOR_DRIFT | deterministic_failure | stale selector / changed UI | stop, snapshot metadata, human review |
| NATIVE_HOST_DISCONNECTED | transient_or_uncertain | messaging pipe closed | reconnect + reconcile, not assume no-op |
| AUTH_EXPIRED | blocked | 401/session expired | authenticated re-login by user |
| PERMISSION_DENIED | terminal | scope/policy rejects requested action | request explicit scope; no retry |
| SESSION_REVISION_CONFLICT | concurrency | two agents wrote same context | serialize, replay against new revision |
| LEASE_EXPIRED | coordination | heartbeat lost | fence old epoch, reconcile external effects |
| ORPHANED_CHILD | coordination | parent ended, child still active | parent recovery, inspect child status |
| DB_BUSY | transient | SQLite write contention | bounded jitter retry; queue pressure |
| DB_CORRUPT | terminal | integrity/checksum mismatch | stop writes, restore verified backup |
| DISK_FULL | terminal | durable event commit cannot complete | stop side effects, raise urgent alert |
| INSTRUMENTATION_FAILED | telemetry_gap | log/span exporter failed | fall back local outbox, signal gap |
| QUEUE_STARVATION | coordination | healthy actors but no scheduling | fairness enforcement, priority audit |
| CIRCUIT_OPEN | intentional_pause | provider circuit breaker active | probe after cooldown; no storm |
| EXTERNAL_CONFLICT | business | 409 remote state changed | read state; human or conflict resolver |
| EFFECT_ALREADY_APPLIED | reconciled | duplicate was verified | acknowledge without second dispatch |
| INVARIANT_VIOLATION | critical | impossible transition detected | freeze operation, page owner |

Do not represent all pauses by generic `stopped`, `error` or `timeout`.
An incident report must include: observed fact, causal chain, alternative
hypotheses, test to disprove each hypothesis, effect uncertainty, owner,
remediation, verification and regression link.

## 5. Health model

**Liveness**: can receive operations and renew worker leases.
**Readiness**: dependencies are reachable, policy loaded, DB writable, queue
below hard limit, receipts can be persisted.
**Progress**: newly committed step effects or transitions within expected
budgets. 'Worker alive' is not enough.
**Correctness**: no unexpected duplicates, stale-epoch commits, unverified
terminal success or capability violations.
**Durability**: event commit and backup checks survive crash/restart.
**Delivery**: outbox acknowledgements and dead-letter aging.

Record quantitative metrics:
- `hermes_operation_started_total{transport,kind}`
- `hermes_operation_completed_total{terminal_state,reason_class}`
- `hermes_step_retries_total{reason_code,tool_class}`
- `hermes_effect_uncertain_total{provider_class}`
- `hermes_stale_epoch_rejections_total`
- `hermes_idempotency_conflicts_total`, `hermes_idempotency_cache_hits_total`
- `hermes_outbox_pending`, `hermes_outbox_oldest_seconds`
- `hermes_lease_expiry_total`, `hermes_approval_wait_seconds`
- `hermes_queue_wait_seconds`, `hermes_tool_duration_seconds`
- `hermes_db_busy_retries_total`, `hermes_telemetry_gap_total`

Avoid unbounded metric cardinality: `operation_id`, `agent_id`,
`session_id`, `trace_id`, raw exception messages are log/trace fields, NOT
metric labels. Sampling strategy and histogram buckets must match actual
latency and volume measured in test, not arbitrary global thresholds.

## 6. Fault injection and expected evidence

| ID | Fault injected | Expected state/evidence | Automatic recovery? |
|---|---|---|---|
| F01 | same key + same body, concurrent | one execution and identical response identity | yes (one event loop) |
| F02 | same key + different body | 409 with conflict code | no |
| F03 | same body + changed session ID | distinct fingerprint | not shared |
| F04 | client disconnect while work running | durable status remains queryable | yes after reconciliation |
| F05 | process SIGKILL before claim commit | no claim; safe retry | yes |
| F06 | SIGKILL after claim, before tool dispatch | expired lease, no effect | yes after expiry |
| F07 | SIGKILL after external dispatch, before receipt | EFFECT_UNKNOWN | no blind retry |
| F08 | lost SSE `response.completed` | STREAM_INTERRUPTED, cursor known | controlled |
| F09 | duplicate provider response | one verified effect key | dedup |
| F10 | stale worker returns after lease expiry | epoch mismatch rejects update | yes |
| F11 | old worker tries to send tool action | broker denies stale epoch | no |
| F12 | SQLite busy during commit | bounded jitter and metric | conditional |
| F13 | disk full | no fabricated success; stop writes | no |
| F14 | DB damage or missing WAL | integrity failure, restore drill | no |
| F15 | outbox publish succeeds, ack lost | resend same event ID, dedup | yes |
| F16 | trace exporter offline | durable ledger remains intact | yes |
| F17 | browser MV3 service worker suspends | reconnection from ledger, not memory | yes |
| F18 | tab navigates while a tool acts | BROWSER_CONTEXT_LOST | reconcile |
| F19 | DOM selector changes | BROWSER_SELECTOR_DRIFT | no |
| F20 | native host pipe disconnect | NATIVE_HOST_DISCONNECTED | conditional |
| F21 | auth token expires mid-operation | AUTH_EXPIRED, no fallback bypass | no |
| F22 | 429 Retry-After plus network jitter | bounded delayed retry | yes |
| F23 | provider returns malformed JSON | contract failure + redacted sample hash | no |
| F24 | parent agent cancelled, child running | ORPHANED_CHILD, cleanup policy | conditional |
| F25 | 30 agents write same file | ownership/CAS conflict, no lost update | no auto-overwrite |
| F26 | 30 agents share one browser tab | session lease serializes writes | yes |
| F27 | approval remains unanswered | WAITING_APPROVAL with deadline | no |
| F28 | repeated identical heartbeat, no progress | STALLED after adaptive threshold | investigation |
| F29 | hidden provider-side success after timeout | read-back confirms effect, no repeat | reconcile |
| F30 | malicious page message asks for shell | denied capability and audit event | no |
| F31 | response ID cached, retry new request | original response+session IDs | yes |
| F32 | restart with in-memory idempotency only | limitation exposed; durable ledger required | no guarantee |

For all 32 cases, store seed, commit hash, worker versions, expected event
sequence, observed event sequence, validation result, and full redaction audit.
A green model evaluation is not a substitute for a fault-injection run.

## 7. Operator UI / forensic timeline

Each operation timeline must show:
```text
10:00:00  RECEIVED            by gpt-bridge, request req_1
10:00:01  VALIDATED           policy p_14, session revision 5
10:00:01  CLAIMED             agent 03, lease epoch 9
10:00:03  TOOL_INTENT         effect eff_6, capability read_file
10:00:03  TOOL_DISPATCHED     tool version 3, provider request id ...
10:00:09  PROVIDER_TIMEOUT    effect state unknown, receipt missing
10:00:09  NEEDS_RECONCILIATION cause=PROVIDER_TIMEOUT_EFFECT_UNKNOWN
10:00:11  EFFECT_VERIFIED     read-back confirms applied [example only]
10:00:11  SUCCEEDED          receipt attached, outbox acknowledged
```
**Illustrative sequence, not a real Hermes run.** Real timelines show
elapsed time, parent/child DAG, code revision, provider request/response
digests, state revision, last successful step, current accountable actor,
confidence, and only allowed next actions. Use red/yellow operational alerts
for incidents, not as unexplained decoration.

A root-cause panel must show both:
- **proximate cause**: where the execution stopped;
- **underlying cause**: e.g. concurrent mutation after stale session revision.

No single model can approve its own RCA closure. Human owner or independent
test verifier confirms the proposed fix against the failing case.

## 8. Incident response playbooks

**Unknown effect**: mark uncertain → freeze retries → collect last intent,
provider request ID, receipt and ledger events → read-only probe →
verify applied / verified absent / still uncertain → only then change state.

**High duplicate rate**: disable automatic destructive retries; isolate
transport and session; examine idempotency key scope, worker epochs,
multi-process deployment and repeated delivery; inject regression test.

**No progress**: compare worker heartbeat against real step evidence.
Check parent-child deadlock, approval gate, queue fairness, provider hold,
DB write contention and tool deadline; never reset everything as the
first response.

**Partial instrumentation outage**: keep ledger as source of truth; buffer
redacted events with quota; log `INSTRUMENTATION_FAILED` once per bounded
window; reconstruct traces from event IDs after recovery.

**Security incident**: disable affected capability, rotate credentials
through approved mechanism, preserve minimal evidence, isolate extension
origin, notify operator, audit other agents' capabilities.

## 9. Sources and rationale

- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OTel GenAI agent/tool conventions: https://github.com/open-telemetry/semantic-conventions-genai
- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- SQLite WAL: https://sqlite.org/wal.html
- Temporal error handling/idempotency patterns: https://docs.temporal.io/encyclopedia/retry-policies

References provide design patterns, not proof that Hermes currently supports
every feature described above.
