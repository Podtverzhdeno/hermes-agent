# SDD-HE-GPT-001 — Hermes GPT bridge: causal observability and controlled recovery

**Status:** SPECIFICATION / phase-0 offline diagnostic prototype, NOT live extension or unattended runner.
**Date:** 2026-11-22.
**Codebase baseline:** Podtverzhdeno/hermes-agent main @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591.
**Related but independent feature branches:** feat/autopilot-durable-ledger-20261122 and feat/skill-harness-contracts-20261122.

## 1. Scope and evidence

Objective: one atomic, auditable view of how dozens of Hermes workers interact with authorized GPT execution, where each task stopped, what evidence is available, alternative causal hypotheses, safe containment and fixes. The first independent implementation is an OFFLINE, SIDE-EFFECT-FREE JSONL trace doctor, distributed as a separate prototype; this specification is the merge target for the next adapter phases.

Audited fork main contains tools/browser_tool.py (CDP resolution), tools/process_registry.py (OS background processes), gateway/run.py, run_agent.py and browser regression tests. There is no verified custom Hermes-to-ChatGPT browser-extension source in the inspected main tree. The local workspace MCP failed during audit: editor returned Session terminated, and observer returned HTTP 429 on SSE probe. Consequently there is NO verified live browser session, real incident trace, continuously running monitor, user-consent status or production repair.

Do not build a second durable task ledger. The parallel Autopilot branch already proposes durable SQLite task leases, effect reservations, approval records, evidence and fencing. The skill-harness branch proposes tool execution contracts. This bridge is a **trace intake + diagnostic projection + future authorized adapter**, not an alternative scheduler, validator or agent-loop implementation.

Explicit non-goals: bypassing ChatGPT authentication, CAPTCHA, consent or usage limits; silently extracting conversation DOM, session cookies, tokens or private prompt/response bodies; assuming a paid web UI exposes a supported programmable execution API; mass prompt submission; declaring task completion from model narrative.

## 2. Distinct facts, hypotheses and decision sources

**FACT (observed):** event emitted by an authenticated collector with a specific source, ID, sequence, time, request or provider receipt, exact artifact revision. **HYPOTHESIS:** inactivity implies an agent died, a browser worker stopped, a network stalled or rate limit triggered; multiple explanations can fit the same absence. **DECISION:** policy/ledger action granted from authenticated authority; cannot be inferred from browser DOM or LLM prose.

The observer's report must mark transported facts as REPORTED until an authenticated collector and verifier attest their origin. A matching provider receipt digest alone does not prove the receipt is genuine. A successful local test is evidence only for the exact tested code revision, not a claim that the live extension runs correctly.

Five independent dimensions must be visible: task execution, transport channels, provider status, artifact evidence, external effects. Browser transport connected != provider accepted != business action executed != artifact verified.

## 3. Proposed architecture

Owner-approved task/policy -> shared Autopilot immutable task ID and ledger -> resource and budget arbiter -> scoped executor (documented OpenAI API if authorized, local Hermes tools, or explicitly user-attached browser companion when permitted) -> authenticated local collector -> persistent bounded outbox/inbox -> read-only diagnostic projection -> independently authenticated exact-revision verifier -> operator timeline and safe escalation.

No model-written result can change policy, grant its own approval, forge trusted evidence, reserve another agent's lock, or bypass fencing at the tool gateway. All trusted actions require identity verification at the adapter, not a tool prompt assertion.

## 4. Metadata-only event protocol v1

Example:
~~~json
{"schema_version":1,"event_id":"ev-123","run_id":"run-7","attempt_id":"a-2","emitter_id":"collector.local","seq":19,"kind":"effect.reserved","observed_at":"2026-11-22T10:20:00Z","operation_id":"op-45","fence":8}
~~~

Required: schema_version, event_id, run_id, attempt_id, emitter_id, seq (>0), kind (allowlisted), observed_at (UTC). Optional: operation_id, revision (exact 40- or 64-hex SHA), fence, reason_code (normalized stable ID), http_status, retry_after_seconds, receipt_digest (64-hex SHA-256). Reject all unknown fields, including prompt text, responses, URLs, headers, secrets and unbounded exception bodies. Cap per-event byte length, total events and retention. Assign authoritative collector ingestion time and monotonically increasing collector offset; do not treat timestamps from different emitters as causal ordering. Event IDs must not collide within a run across emitters; per-attempt/emitter seq is monotonic. A duplicate delivery is not a second execution.

Distinguish:
- WebSocket transport disconnected / reconnected
- User-attached tab detached / explicitly reattached
- Manifest V3 service worker suspended / started

**CRITICAL:** a WebSocket recovery does not reauthorize a tab; a worker start does not reconnect a WebSocket. Do not report whole transport connected until each necessary component has independently reported connectivity. Same-time contradictory reports are unknown/unavailable pending ordered collector evidence. An attached-tab event remains UNTRUSTED until the browser permission adapter verifies actual authorization.

## 5. Atomic effect handling

1. Acquire project resource lease with fencing token F and immutable operation_id.
2. Verify actor, tool scope, parameters, budget and consent.
3. Commit policy grant plus external-effect reservation to the durable ledger before dispatch.
4. Dispatch only through gateway re-checking live fencing and revocation; pass stable provider idempotency key if available.
5. Record provider receipt and read-back; classify external effect as acknowledged only upon trusted reconciliation.
6. Verify changed artifact independently at exact revision before task success.

Crash after reservation, connection loss after dispatch, timeout or empty browser response => UNKNOWN_EXTERNAL_OUTCOME / NEEDS_RECONCILIATION, **never blind retry**. An internal transactional ledger cannot give exactly-once semantics for a provider outside its transaction. Cancellation blocks fresh calls, not assumed undo of in-flight operations. The same operation must retain its ID across replacement agents; new attempt IDs must not reset global task budget.

## 6. Diagnostic taxonomy

| Code | Competing explanations | Safe action |
|---|---|---|
| EVENT_ID_COLLISION | duplicate ID across emitters, corrupt stream | quarantine, fetch trusted original |
| SEQUENCE_CONFLICT | competing writers, event replay | block causal reconstruction, reconcile |
| SEQUENCE_GAP | partial export, dropped event | recover missing range; do not guess |
| STALE_FENCE_WRITE | old agent resumed after replacement | refuse effect at gateway |
| DUPLICATE_EFFECT_RESERVATION | retry race, wrong idempotency | quarantine duplicate; compare provider state |
| EFFECT_CLOSURE_NO_RECEIPT | claimed completion unsupported | retain unresolved state |
| ORPHAN_EFFECT_CLOSURE | missing reservation | demand authenticated reservation/read-back |
| UNKNOWN_EXTERNAL_OUTCOME | crash between reserve and provider outcome | no replay; reconcile receipt |
| UNCONFIRMED_BRIDGE_REQUEST | transport loss, slow response or provider completion | check provider ID/receipt |
| COMPLETED_WITHOUT_MATCHED_EVIDENCE | hallucinated success, stale verification | exact revision verification |
| AUTH_BLOCKED | revoked/expired credentials | halt provider dispatch, owner intervention |
| RATE_LIMIT_WITHOUT_BACKOFF_HINT | 429, quota vs temporary throttle | bounded backoff only if allowed |
| TERMINAL_STATE_CONFLICT | competing workers, corrupted state | defer to trusted ledger |
| PROGRESS_SILENCE | host down, worker suspended, telemetry lost | probe each subsystem independently |
| SESSION_CHANNEL_UNAVAILABLE | independent WebSocket/tab/worker issue | inspect component; authorized reattachment |

These are diagnostic *classes*, NOT proof of singular root cause. Each incident needs severity and confidence separately. Do not turn hypotheses into automatic mutating fixes.

## 7. Dozens of simultaneous agents

Strong IDs: task, run, attempt, operation, emitter, artifact SHA, evidence ID, parent run, policy version, lease epoch/fence. Lock resources by repo branch/worktree/path, Obsidian note, issue/PR, browser tab/profile and provider operation. A0 independently verifies; A1–A5 execute disjoint scoped deliverables. Other agents may read the shared evidence journal but cannot self-certify. A task handoff reads durable ledger and artifact manifest, not a guessed last chat message. Stale workers never receive write authority even if still producing text.

Global quotas must apply to entire DAG: concurrent provider jobs, browser tabs, workers, tokens/spend and shared verification slots. Backpressure before dropping events. Watchdog monitors queue age and lease expiry, but can only *diagnose* an uncertain effect, not repeat it. Use jittered bounded retries for pure read operations, not unverified external writes. Keep owner-visible stop cause, next allowed action, deadlines and per-source connection health.

## 8. Candidate idea scoring (engineering estimates, not measurements)

Scoring model: 2*(0.30 user impact + 0.25 reliability + 0.20 feasibility + 0.15 evidence quality + 0.10 risk reduction); each component 1-5.

| Idea | Score /10 | Decision |
|---|---:|---|
| Metadata-only causal events and diagnostics | 10.0 | phase 0 |
| Reuse Autopilot ledger/leases/effect reservation | 9.6 | phase 1 integration after review |
| Supported OpenAI provider response IDs / webhook reconciliation | 9.6 | preferred authorized provider adapter |
| Verify fencing immediately before any side effect | 9.2 | required release gate |
| Independent multi-channel status and exact-SHA evidence | 9.2 | phase 0 and later verifier |
| Fair global multi-worker quotas | 8.3 | phase 2 |
| Deterministic crash/duplicate/fault injection | 8.1 | before deployment |
| MV3 local durable outbox with owner consent | 7.9 | only if browser bridge genuinely needed |
| ML-based anomaly model | 4.1 | defer; need labeled incidents first |
| DOM selector auto-repair as task authority | 3.0 | reject; UI is not authoritative |
| Distributed cluster before local hardening | 3.9 | reject premature scope |

## 9. Phase gates and tests

**Phase 0:** side-effect-free event schema and trace doctor in independent prototype, with deterministic tests. Tested offline: 43 unittest cases, including 100 synthetic isolated runs; this is NOT live 100-worker load validation or an integrated GitHub CI run. During testing fixed two reproducible logic classes: a non-string kind raised an uncontrolled exception, and false "reconnected" when only one of three browser channels recovered. Also corrected cross-emitter event-ID collision handling. All 43 final tests pass locally.

**Phase 1:** authenticated collector, bounded durable outbox/inbox, exact authorization, retention/redaction, collector offsets and restart recovery; integrate with shared Autopilot ledger without modifying its branch in parallel. Fault inject after event persist / before ack.

**Phase 2:** approved provider adapter, exact-SHA trusted verifier, tool gateway fencing and quotas; reconcile unknown effects, disallow replay.

**Phase 3:** optional consented browser extension adapter with explicit tab/profile isolation and MV3 service worker restart, separate from the documented OpenAI API. Never log private ChatGPT messages. Test revocation, tab closing, auth errors, provider throttling and failover.

**Phase 4:** real multi-process 10/50/100 worker synthetic load, 24-72-hour soak, incident replay, crash/corrupt backup drills, canary/rollback. These are future acceptance targets, NOT achieved results.

## 10. Incident runbook / change log contract

Each incident: UTC collector time and offset, task/run/attempt/emitter/operation IDs, exact revision, last authenticated event, observed symptoms, competing hypotheses, confidence, side-effect ambiguity, permissible containment, owner decision, fix commit, regression test and rollback evidence. For critical ambiguity escalate to human; no fabricated "fixed" from lack of alerts. Every change to this SDD should state observed evidence vs proposed scope.

## 11. References

- Chrome Manifest V3 worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome storage: https://developer.chrome.com/docs/extensions/reference/api/storage
- Chrome message passing: https://developer.chrome.com/docs/extensions/develop/concepts/messaging
- OpenAI Responses background: https://developers.openai.com/api/docs/guides/background
- OpenAI webhooks: https://developers.openai.com/api/docs/guides/webhooks
- OpenAI API error taxonomy: https://developers.openai.com/api/docs/guides/error-codes
- OpenTelemetry traces: https://opentelemetry.io/docs/concepts/signals/traces/
- OpenTelemetry messaging semantic conventions: https://opentelemetry.io/docs/specs/semconv/messaging/
- SQLite WAL: https://www.sqlite.org/wal.html

**Explicit delivery limit:** This design was researched against inspected GitHub files and relevant official technical docs, not millions of sources. The local extension runtime is inaccessible in this session. The prototype currently runs only on supplied event files; continuous device monitoring, autonomous fixing and integrations are NOT deployed by this document.
