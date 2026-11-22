# Hermes ↔ GPT: Reliable Multi-Agent Bridge — Specification-Driven Design (SDD)

**Status:** design v0.1 and opt-in, offline-tested observation kernel. **Date:** 2026-11-22.
**Baseline:** Podtverzhdeno/hermes-agent main at 7e9100901819ee44c16b4ddcb79a6bcb7909f591.
**Scope delivered in this branch:** gpt_bridge/observability.py, read-only CLI, tests. NOT an activated ChatGPT browser extension, live worker monitor, authenticated ingestion server, or autonomous dispatcher.
**Parallel work:** draft PR #1 (feat/autopilot-durable-ledger-20261122) owns task ledger, leases/fencing, approvals and external-effect reservation. feat/skill-harness-contracts-20261122 owns advisory skill manifests. Do not duplicate, overwrite or merge those streams implicitly.

## 0. User need and decision

The real problem is not producing more agent messages. It is knowing what actually happened, what was merely reported, why execution stopped, whether an external action occurred, how to resume without duplication, and which specific evidence supports a correction. Scale: potentially dozens of independent agents working concurrently.

Use a **durable, typed, privacy-minimizing observation plane** joined to (but not replacing) a **separate privileged execution/control plane**. Native, documented GPT integration is preferred. Owner-authorized Chrome/CDP is optional diagnostics and is never authoritative evidence of successful business execution. An absent assistant response is not proof of failure. A heartbeat is not proof of progress. A worker's success narrative is not a verified result.

No original ChatGPT/Chrome extension source was found in the inspected fork main tree. Local Workspace MCP was unavailable during this audit (session terminated). Consequently neither an active browser monitor nor a live GPT agent was observed or repaired in this PR.

**Cross-repository source discovery (later in this audit):** the concrete WebGPT/ChatGPT extension lives in the **separate** repository [Podtverzhdeno/Tunnel](https://github.com/Podtverzhdeno/Tunnel), paths Hermes-WebGPT and chat-launch-smoke-desktop-test/web-extension. Its main manifest is version 0.6.6, while existing local-release documents reference 0.9.7; the actually loaded Windows source/extension hash was not accessible. A separate [Tunnel draft PR #13](https://github.com/Podtverzhdeno/Tunnel/pull/13) now contains read-only causal triage over the existing Relay queue and a source-specific OpenSpec SDD. **This observer remains an independent prototype; the two repos have not been integrated or activated.**

**Non-goals:** manipulating ChatGPT DOM/transcripts as the primary task API, bypassing authentication/CAPTCHA/platform permissions, auto-approving high-impact actions, secrets in logs, globally writable tunnels, unlimited retries, claims of 24/7 operation without an always-on host.

## 1. Architectural planes and trust boundaries

1. **Control:** stable task IDs, immutable request spec, dependency DAG, owner, priority, per-task and per-DAG budgets, timeouts, approvals, cancellation, lease and increasing fencing token. Owned by the independent Autopilot ledger PR.
2. **Execution:** official GPT/OpenAI APIs/SDKs, documented app/MCP adapters, Hermes or scoped CLI workers; optional consented browser diagnostics. Tool gateway checks authorization and current fencing token immediately before each external side effect.
3. **Observation (this branch):** typed append-only local events with stable identity, server receipt ordering, idempotency, producer sequences, per-tab/action correlation, conservative symptom diagnosis. Its source labels are unauthenticated claims until future gateway authentication.
4. **Evidence:** exact Git SHA, CI run and completed conclusion, test output, external receipt, independently authenticated verifier. An event that says verification passed is NOT itself trusted evidence.
5. **Diagnosis/repair:** deterministic incident state and reason; competing hypotheses, counterevidence, reproducible test, one fix owner, targeted rollback and verification.
6. **Operator:** read-only timeline, status confidence, unresolved external actions, human approval queue, kill switch, budgets, queue/backpressure, alerting, incident records.

### Trust flow

    Owner / authorized intent
             |
    Privileged Autopilot ledger / policy / approval / effect reservation
             |
    Narrow worker lease / scoped tool gateway
             |
    Native API / Hermes worker / scoped MCP / optional browser observer
             |
    Authenticated future collector -> committed local observation DB
             |                                |
    Read-only diagnosis                    Independent verifier
             |                                |
    Operator incident -> isolated proposed fix -> tests -> PR -> guarded rollout

**Separation:** observation records what an adapter claimed to see; the ledger verifies state transitions, and only an authenticated independent verifier marks task evidence trusted. No LLM can self-approve or authorize tool use by writing a log event. Do not expose ledger internals as an untrusted model tool.

## 2. Alternatives: explicit weighted design judgment

Weights: durability/recovery 30%, security/privacy 20%, concurrent correctness 20%, operational simplicity 20%, adoption speed 10%. Criteria scored 1–5; totals below are qualitative judgments, NOT measured benchmark results.

| Architecture | Estimated /10 | Decision |
|---|---:|---|
| Existing SQLite Autopilot plus typed observation plane | 9.2 | Preferred first-stage one-host design |
| Temporal workflows plus telemetry and effect adapters | 8.2 | Investigate for genuine multi-host needs |
| LangGraph checkpointing alone | 7.0 | Use within agent workers, not as side-effect ledger |
| Unstructured log parsing alone | 6.2 | Troubleshooting supplement, not state authority |
| ChatGPT DOM/CDP as durable orchestration protocol | 3.0 | Reject |

SQLite WAL serializes local writes, permits readers concurrent with a writer, and is not distributed consensus. Temporal supports durable histories but does not remove the need for idempotency and reconciliation of external activities. Chrome Manifest V3 service workers may terminate under inactivity; CDP sessions may detach. They are not proof that the model itself stopped.

Switch to distributed orchestration only after observing multi-host need, contention, queue delays, or breached recovery SLOs. Dozens of *logical* agents alone do not justify an additional distributed service.

## 3. Event contract (schema v1)

Every collector-accepted event has: event_id, run_id, task_id, agent_id, producer_id, fence, source_seq, kind, source, details, received_at, receipt sequence, previous hash and current hash.

- **event_id:** opaque stable identifier; identical replay is idempotent, conflicting replay is rejected.
- **run_id/task_id:** objective and work-item correlation, never raw prompt text.
- **agent_id/producer_id:** distinguish role from concrete process/browser context; a replaced worker must not share an unpersisted producer sequence.
- **fence:** privileged ledger epoch; observer displays most recent epoch, but does not authorize or reject tool execution.
- **source_seq:** monotonic within producer and epoch; duplicate occupancy with another event is a conflict.
- **kind/source:** fixed vocabularies, not arbitrary prose.
- **details:** only step_id, action_id, target_id, channel_id, request_id, reason_code, http_status, detach_reason, attempt.
- **received_at:** collector clock. **sequence:** committed receipt order, not necessarily real-world causal order.
- **prev_hash/event_hash:** SHA256 chain detecting accidental corruption. It is NOT a cryptographic attestation against a hostile writer with DB access.

Type-specific required identifiers: effect and approval events require action_id; Chrome debugger attached/detached requires target_id; transport connected/disconnected requires channel_id. Reattachment of tab B cannot clear a detachment of tab A. Reconciliation of external action A cannot erase unresolved action B.

Allowed event families: task lifecycle, worker heartbeat/replacement, model and tool start/end, transport connect/disconnect, CDP attach/detach, auth denial/restore, rate limit/clear, approval request/resolution, uncertain effect/reconciliation, reported verification, reported task completion. Extension reasons must match Chrome debugger onDetach values.

**Privacy:** never record API tokens, cookies, authorization headers, chat transcripts, tool arguments, raw stack traces, websocket addresses, screenshots, user email, secret paths, arbitrary URLs, or prompt contents. Opaque IDs must be generated without sensitive data. This v1 code enforces an event allowlist, NOT generalized DLP or encryption. A separately secured, time-limited forensic capture would require explicit owner opt-in and threat review.

## 4. Atomicity and recovery invariants

**I1 — Commit before ACK:** a future collector must durably commit a validated event before acknowledging it; retry duplicates with unchanged event ID.

**I2 — Reserve before side effect:** privileged ledger commits exact-action approval and effect reservation before a mutating API call. A crash after reservation is uncertain; never automatically replay without idempotency or independent read-back.

**I3 — Fencing:** stale workers cannot mutate task state or invoke external actions. Enforce in tool gateway, not by reading observer status. Cancellation and revocation block issuance of new tool calls.

**I4 — Distinguish lost observation from failed work:** silence and browser detachment can only produce reported/disconnected/stalled-suspected diagnostics. Do not auto-mark a task failed or completed.

**I5 — Exact revision evidence:** successful tests/checks for SHA A do not prove SHA B. Pending, skipped, missing or stale CI is not success unless an explicit reviewed policy permits it.

**I6 — Scope and identity:** each agent owns disjoint files/branches/worktrees and scoped tokens. An Obsidian writer may edit only its authorized folder. Source labels cannot provide authentication.

**I7 — No unlimited recursion:** attempts, wall-clock, cost, concurrent subworkers and external action budgets are bounded for the whole task DAG.

**I8 — No false integrity promise:** hash chaining alone cannot prevent actor-with-DB-access rewriting the entire chain; anchor archive hashes externally and use authenticated identity/signed receipts before production.

**I9 — No automatic high-impact actions:** credentials, deletion, production deployments, protected merges and other irreversible effects require an authorized human decision.

**I10 — No blind replacement:** restarted workers take explicit checkpoint, task revision and fence. They do not assume all previous tool effects failed.

## 5. Failure diagnosis taxonomy: observations and responses

| Signal | Possible actual cause(s) | Conservative status | Safe next step |
|---|---|---|---|
| No model reply for threshold | slow model, network stall, extension stopped, telemetry loss | suspected_stall | Check provider/request and collector independently; do not retry external writes |
| CDP onDetach target_closed | tab closed or target destroyed | integration_unavailable | Reattach only after owner-authorized reconnection; do not infer task failure |
| CDP onDetach canceled_by_user | owner/DevTools takeover or manual detachment | integration_unavailable | Stop browser automation; honor owner control |
| MV3 service worker suspended | normal browser lifecycle | unknown until replay | Persist outbox; reconnect and resend stable event IDs |
| 429 rate limit | provider throttling/usage cap | rate_limited | Honor Retry-After, bounded jitter, per-provider concurrency budget |
| 401/403 | credentials expired/invalid or access denied | auth_blocked | Escalate and reauthenticate through supported flow; do not log credentials |
| Timeout after external mutation | request may have succeeded | needs_reconciliation | Provider idempotency key or independent receipt/read-back |
| Waiting exact-action approval | no valid authorization yet | waiting_approval | Human exact-action approval, never model self-approval |
| Worker replaced while old callback finishes | stale task lease | stale callback, reject | Gateway fence validation immediately before effect and when writing result |
| Git head changes while tests run | stale evidence | verification_blocked | Re-run tests at exact intended revision |
| Conflicting editors of shared SDD | simultaneous writers | revision_conflict | Read SHA, isolate branches, merge with review; never last-writer-wins |
| Collector SQLite full or locked | storage pressure/resource contention | telemetry_unavailable | Surface alert, bounded durable queue; never claim success |
| Hash mismatch | corruption, bad restore, malicious change | integrity_suspect | Stop trust-dependent decisions, preserve snapshot, investigate |
| Authenticated webhook duplicate/out of order | provider delivery semantics | deduplicate/reconcile | Stable delivery IDs and independent provider polling |
| Lost worker heartbeat | worker crash, GC pause, laptop asleep | suspected_stall | Examine lease expiry and running effects before reassignment |
| Multiple tabs/actions in same task | incorrect cross-scope signal joins | avoid false recovery | Correlate by action_id/target_id/channel_id, never task ID alone |

**Diagnostic priority:** any unresolved external effect takes precedence over approvals; pending approvals over auth/CDP/transport/rate limits; these over reported completion or a stale heartbeat. A reported success still has confidence=reported_only and does not certify the task.

A root-cause report must include: precise observable symptom; relevant event and run IDs; evidence; at least two competing hypotheses where plausible; decisive falsifier; safe proposed intervention; owner; test; rollback; unresolved uncertainty.

## 6. Multi-agent coordination at dozens of workers

A0 is a coordination/review role, not an all-powerful executor; A1–A5 and future agents have explicit ownership. Use one stable task DAG and one privileged state machine across all workers. Each worker obtains: immutable objective; permitted tools/paths; expected artifact revision; signed lease/fence; cost/time budget; allowed effect class; acceptance tests; checkpoint manifest.

Implement per-project/per-file resource ownership, fairness and quota so a newly spawned swarm does not starve a critical verifier. Treat unknown session state as **unknown**; a replacement may do read-only investigation but may not replicate uncertain writes. Distinguish duplicate delivery from a second independent request. Limit fanout and emit only essential event transitions; sample heartbeats but NEVER sample approval/uncertain-effect/verification transitions.

Producers may be many while SQLite writes are serialized. Calculate real lock wait and ingestion lag before adopting queue DB or Temporal. Extension and browser adapters need their own producer identity and bounded persistent offline buffer. Do not combine independent agent producers into one source_seq counter without a durable allocator.

**Owner local version:** maintain an owned Git worktree with validated snapshots, scoped editor and observer. File backup, Git sync, Obsidian synchronization and external action compensation are distinct workflows. Local Workspace connection was unavailable here; mark local sync as pending, not done.

## 7. GPT/browser extension protocol and boundaries

Prefer official GPT/OpenAI APIs, webhook or background operations where supported; store provider request/response receipts in protected ledger. For browser diagnostics, require explicit owner scope and a separate profile. Chrome extension design: Manifest V3 service worker with event listeners registered on initialization, limited host permissions, local event outbox, persist-then-ACK transport, reconnect replay, debugger onDetach categorization, tab/target identity and explicit disconnect.

Do not scrape ChatGPT messages/DOM for primary control or infer hidden internal model state from UI. If a product has no supported automation interface, keep that operation manual. No network integration or actual extension is included here. The design must be validated against provider terms and permissions before implementation.

OpenTelemetry GenAI spans + W3C traceparent should be added at the future adapter boundary (no request/response body by default), with task_id, run_id, agent_id, producer_id, trace ID, step ID, elapsed time and symbolic failure codes. Avoid high-cardinality metrics labels containing user content.

## 8. Production durability, metrics, and observability

Observer v0 uses local SQLite WAL and synchronous FULL with transactional append. Do not store a live WAL DB on a network share. Back up via SQLite backup API, not by copying a live file alone. Add archive segmentation, retention limits, storage encryption, verifiable restore, external anchor for final hash, migration/version tracking and collector authentication before production.

Illustrative capacity, **not a measurement**: 50 agents × one heartbeat per minute = 72,000 heartbeat events/day. At hypothetical 512 bytes/event including index overhead that is roughly 36 MiB/day, excluding tool/model events. Measure actual file growth, WAL size and lock contention.

Dashboard should expose: task phases; blocked/unknown age; unresolved effects and approvals; current leases/fences; model queue/first token latency; tool timeout causes; CDP detach by reason and target; stale CI SHA mismatch; dedup/collision rate; ingestion latency; DB capacity and busy duration; worktree ownership contention; human escalation; budget usage and cost per **verified** deliverable. Use Google SRE latency, traffic, errors, saturation.

Candidate pre-production targets (NOT achieved):
- 100 simulated concurrent producers: no inconsistent event identity, no cross-tab/action false recovery.
- Zero acknowledged-before-commit lost event in injected collector crashes.
- No repeated unconfirmed mutating action after an ambiguous timeout.
- Exact-revision independent verifier on all completed high-impact tasks.
- Operator can always distinguish reported success from independently verified success.
- Accepted-to-query p95 under 2 s at a measured bounded local workload.

## 9. Delivery stages and acceptance gates

| Phase | Deliverable | Exit gate |
|---|---|---|
| P0, **this PR** | typed durable observer, read-only CLI, focused failure tests, SDD, incident runbook | offline tests, packaging verification, no side-effect/tool/extension activation |
| P1 | authenticated collector, durable inbox and heartbeat, read-only Autopilot mirror | crash before/after ACK, replay, auth and privacy tests |
| P2 | documented native GPT/API adapter; exact effect receipt + evidence adapter | never blind-retry effects, independent SHA verification, narrow credentials |
| P3 | consented MV3 diagnostics extension | worker suspension/reload, tab close, CDP detach, revoke, storage queue E2E |
| P4 | optional multi-host workers, signed audit archive, dashboard, SLO gates | load, restore, incident and security reviews |

No-go for production or autonomous repair: missing real extension source, no authenticated event producer, no privileged effect ledger integration, no reliable permission approval, secret-bearing telemetry, missing retention or backup restore, unverified migration, or treating a model answer as proof.

### Offline verification already performed

Focused tests pass locally (39 cases) for atomic duplicate/sequence handling, 60 concurrent writers, corruption detection, content/enum validation, ID-specific external-effect reconciliation, tab-specific CDP recovery, stale lease precedence, reported-only completion, read-only CLI and persistent reopen. These tests do **not** demonstrate a live GPT/CDP integration or service running on the owner's machine. GitHub CI and whole-repo test suite must be checked separately.

## 10. Traceability

| User objective | Proposed mechanism | Current status |
|---|---|---|
| Atomically know what happened | typed event + SQLite BEGIN IMMEDIATE + hash-chain | observer implemented; producer auth not implemented |
| Explain stoppage | reason taxonomy and status confidence | observer classification implemented |
| Fix underlying cause | RCA and regression runbook | documented, future repair agent not implemented |
| Survive lost session | leases, fences, checkpoint handoff | separate draft Autopilot PR, not integrated |
| Dozens of agents | scoped producers, ownership, budget, resource locks | observed concurrency tested; privileged locks pending |
| Extend GPT safely | native API, optional scoped MV3 diagnostics | design only, no original extension found |
| SDD collaboration | isolated PR, exact source revision, review | present SDD; no merge into main |

## 11. Change governance

Every SDD change proposes: problem evidence and affected revision; competing causal hypotheses; expected failure mode; selected ADR and rejected alternative; security and privacy impact; target owner and file scope; explicit acceptance test; rollback; verifier identity; external side-effect risk; review. Read existing file SHA before update and use one branch/PR per agent. Never silently overwrite another agent's parallel design. New empirical evidence should supersede weighted judgments, rather than presenting estimates as benchmarks.

## 12. Official/primary reference set, reviewed 2026-11-22

1. SQLite WAL concurrency — https://www.sqlite.org/wal.html
2. SQLite isolation — https://www.sqlite.org/isolation.html
3. Temporal workflows — https://docs.temporal.io/workflows
4. Chrome MV3 worker lifecycle — https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
5. Chrome debugger onDetach — https://developer.chrome.com/docs/extensions/reference/api/debugger/
6. OpenAI ChatGPT developer integrations — https://developers.openai.com/chatgpt
7. OpenAI background response operations — https://developers.openai.com/api/docs/guides/background
8. OpenAI webhooks — https://developers.openai.com/api/docs/guides/webhooks
9. OpenTelemetry GenAI span conventions — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
10. OpenTelemetry tool calls — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md
11. W3C Trace Context — https://www.w3.org/TR/trace-context/
12. Google SRE monitoring — https://sre.google/sre-book/monitoring-distributed-systems/


## 13. Critical audit correction: uncertain external effects cross lease epochs

Follow-up code review caught and fixed an unsafe projection: considering only the latest worker fence hid effects left uncertain by the previous worker. **That would produce a misleading active status after worker replacement.** Diagnostic code now scans task-global effect uncertainties across all fencing epochs, while current worker liveness, tab/transport and pending approvals remain scoped to the newest epoch.

A reconciliation from an obsolete fence that arrives *after* a newer fence was observed does not erase the unresolved effect. A new-fence reconciliation can clear it in the advisory view, though this remains **reported-only** until authenticated, independently verified receipts exist. Stable action IDs MUST be globally unique within a task; old fence activity may not authorize any new external effect. Four new cross-fence regression tests cover lost effect, valid new-epoch reconciliation, stale old-epoch reconciliation and obsolete approval, plus two subprocess crash-before/after-commit tests. Focused local suite: **45 passed**, not a full-repo or live-browser test.

## 14. Measured local contention, distinct from acceptance targets

One reproducible, non-production synthetic probe on the assistant's Linux container used 100 parallel simulated agent threads, each appending 10 durable events to a single SQLite WAL observer (1,000 events total). Result: **2.045 s** wall time, **489 events/s**, **append p50 0.78 ms, p95 731.64 ms, p99 1,340.38 ms** including lock contention and connection overhead; full hash chain verified, file size **589,824 bytes**. This is a single sample, not a statistically validated service SLO or a Windows/Edge benchmark. Long-tail waits under simultaneous writers justify measuring queue depth and tool latency before scaling, not abandoning WAL prematurely. Real profile, disk latency, storage quotas and 100-agent E2E still need testing.


## 15. Privacy hardening and cross-repository sampling (2026-11-22)

В observer schema v1 исключены символы @ и : из допускаемых opaque ID (не допускать очевидные email/URL/token-like identifiers); поле reason_code теперь не свободный верхнерегистровый текст, а фиксированный перечень REASON_CODES v1. Дополнительные регрессии отклоняют email-shaped ID, pseudo-secret ID и private-looking reason; **48 focused observer tests pass locally** (не live endpoint). Это защита от типичных случайных утечек, а не полное предотвращение PII в произвольно выбранном opaque ID. Обязателен trusted collector с source authentication и privacy review до production.

**Фактическая связь с исходником:** отдельный Tunnel draft PR #13 содержит настоящие Hermes-WebGPT read-only causal triage и опциональный incident_sampler.py. Sampler считывает только ранее очищенные метаданные через существующий queue_monitor и атомарно (одна транзакция SQLite) сохраняет baseline+incident в **другой приватной БД**; ограничивает историю 2000 записей, имеет foreground --interval, без автоматического Send/retry. **15 sampler + 29 triage synthetic tests** проверены локально; source/installed Windows runtime не подключён. Не принимать этот журнал за data-plane с аутентифицированным origin, и не объединять его с privileged Autopilot ledger без проверки идентичности и effect-reservation bridge.
