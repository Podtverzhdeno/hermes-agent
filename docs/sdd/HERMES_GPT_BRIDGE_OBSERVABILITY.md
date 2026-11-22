# SDD-HE-GPT-001 — Hermes ↔ GPT bridge: causal observability, recovery, multi-agent isolation

**Status:** architecture + offline diagnostic/inbox/report kernel implemented, **not** a deployed ChatGPT browser extension or autonomous runner.  
**Date:** 2026-11-22. **Baseline:** `Podtverzhdeno/hermes-agent@7e9100901819ee44c16b4ddcb79a6bcb7909f591` (`main`).  
**Owners:** GPT transport/observability integration; existing Autopilot ledger authors retain coordinator/lease ownership.  
**Target branches for interoperability:** `feat/autopilot-durable-ledger-20261122`, `feat/skill-harness-contracts-20261122`. Neither is assumed merged.  
**Confidence labels:** `OBSERVED` = inspected code or a reproducible test; `HYPOTHESIS` = plausible but unconfirmed; `PROPOSED` = architecture or acceptance target, not working behavior.

## 0. Executive decision and boundaries

The objective is an explainable, safe and *verifiably repairable* path between Hermes tasks and user-authorized GPT execution, including optional browser extension transport. The first deliverable is a **read-only trace doctor**. It consumes a strict, metadata-only JSONL event format, reconstructs five independent dimensions of each run, finds broken invariants and emits actionable diagnostics. It **never** initiates browser automation, replays a request, grants approvals or certifies an untrusted model answer.

Do **not** build a second task ledger. Reuse the durable `autopilot/ledger.py` proposed in the parallel branch after its own review, and write bridge events through a trusted adapter; use this code as an independent diagnostic projection. A task store and a transport-event store have different roles. Do **not** merge to `main` until provenance and integration are reviewed.

The local MCP writer/observer endpoints were unavailable during this audit (`Session terminated` and SSE `429`); real browser, ChatGPT UI, device processes and live logs were **not observed**. The fork currently contains `tools/browser_tool.py` (CDP endpoint support) and tests for that module; this is **not evidence** that a custom Hermes↔ChatGPT extension is installed or connected. Upstream Hermes and third-party companion extensions change over time: their features must not be assumed present in this fork.

### Hard non-goals

- No bypass of authentication, anti-bot challenges, provider restrictions, consent screens or usage metering.
- No harvesting ChatGPT conversations, cookies, tokens, raw prompts, or DOM content into telemetry.
- No autonomous completion claims based on browser content, model text or an extension's self-report.
- No cross-agent takeover of user-selected browser tabs; no silent mass submission of prompts.
- No continuously running process guaranteed by this PR; the observer is invoked explicitly on log files.
- No magic exactly-once guarantee for remote side effects.

## 1. Source audit and missing integration

| Observation | Evidence | Impact / decision |
|---|---|---|
| Hermes core loop is synchronous (`run_agent.py`) and uses tool orchestration | root `AGENTS.md` | A model turn is not a durable transaction; wrap it with task identity |
| `tools/browser_tool.py` resolves user-supplied CDP URLs | code + `tests/tools/test_browser_cdp_override.py` | CDP reachability is not a trusted execution status; audit origin/permissions later |
| Background process registry persists a checkpoint, in-memory tracking is primary | `tools/process_registry.py` | OS-process state is insufficient evidence for task completion |
| Autopilot branch has durable ledger, leases, effects, evidence and 239 lines of tests | `compare main...feat/autopilot-durable-ledger-20261122`, `docs/autopilot/ARCHITECTURE.md` | Integrate here, do not duplicate ledger or scheduler |
| Skill harness branch adds contracts and tests | `compare main...feat/skill-harness-contracts-20261122` | Preserve independent ownership and avoid editing its files |
| No GPT-specific extension source verified in main tree | recursive repo tree | Treat extension hookup as **unverified**, not as a diagnosed outage |
| Local workspace MCP was unavailable during audit | adapter errors: session terminated / 429 | No live session-level evidence; requires a separate connector health check |

### Verified external constraints

- Chrome Manifest V3 extension service workers are event-driven and may be stopped after inactivity. Persist durable state outside worker global variables; treat worker suspension as **expected lifecycle**, not automatically as failure. [Chrome lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/) and [storage](https://developer.chrome.com/docs/extensions/reference/api/storage).
- Chrome `runtime` messaging supports one-time and long-lived ports, but a port is not a durable queue. [Chrome messaging](https://developer.chrome.com/docs/extensions/develop/concepts/messaging).
- Official OpenAI Responses background execution provides response IDs, polling and webhooks; this is a better adapter when an authorized API integration is used. It is distinct from a ChatGPT web subscription/session. [Background mode](https://developers.openai.com/api/docs/guides/background) and [Webhooks](https://developers.openai.com/api/docs/guides/webhooks).
- Rate-limit and quota failures are different. Respect `Retry-After`, distinguish `slow_down` from spend/quota exhaustion, and bound retries. [API errors](https://developers.openai.com/api/docs/guides/error-codes) and [deployment checklist](https://developers.openai.com/api/docs/guides/deployment-checklist).
- Trace/span correlation and common messaging names should align with OpenTelemetry; tracing **does not imply** we can log private prompt/response contents. [OTel trace](https://opentelemetry.io/docs/concepts/signals/traces/), [messaging](https://opentelemetry.io/docs/specs/semconv/messaging/), [GenAI](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/).
- SQLite WAL has one concurrent writer; it is not a distributed, multi-host queue and must not be stored on a network share. [SQLite WAL](https://www.sqlite.org/wal.html).

## 2. System decomposition

```text
              Human-selected task or authorized API job
                                |
                    Intake / policy gate (Autopilot)
                                |
                    Durable tasks / effects ledger
                                |
                dispatcher + per-resource lease/fence
                      /                         \
       Official provider adapter          Optional browser adapter
    (OpenAI API, supported tools)         (explicit tab/user consent)
                      \                         /
                  Trusted local bridge collector
                       |            |
         append-only validated events   provider receipts / hashes
                       |            |
          causal projection + diagnostics (THIS PR)
                       |
          explicit reconcile / repair proposal
                       |
      independent verifier @ exact revision & policy
                       |
      operator dashboard / reason codes / escalation
```

**Trust boundaries:** model output, third-party web content and extension content scripts are untrusted; collector timestamps and signed actor identity are trusted only when verified by the local gateway. Browser permission does not grant permission to make irreversible external writes. An LLM cannot issue or verify its own approval or bypass the ledger. A dev-only raw JSONL import is NOT an authenticated event channel.

The browser adapter is **opt-in** and should have: user-selected tab/session, status indicator, revocation and a narrow lifetime, origin allowlist, per-run access token bound to the tab and action scope, and no remote CDP listener. When control is detached, no commands to that tab may be accepted. The bridge should bind only to loopback and authenticate origin and token; any remotely exposed version requires TLS and strict access control. Never emit session cookies or credentials to logs.

## 3. Four independent state dimensions

Do not collapse these to a single `running/finished` boolean:

| Dimension | Example states | Authority | Interpretation |
|---|---|---|---|
| Execution | queued, leased, running, cancelling, reported_completed, reported_failed, blocked | durable task ledger | Worker claim; not provider success |
| Transport | unobserved, connected, unavailable, reconnecting | bridge collector | Websocket/tab/worker availability; not task result |
| Provider | unobserved, accepted, response_completed, rate_limited, auth_failed | provider API receipt if available | May continue after a local disconnect |
| Evidence | missing, artifact_committed, verification_pending, verified_exact_revision, stale | independent verifier | Only trusted verifier may certify artifacts |
| External effect | none, reserved, acknowledged, needs_reconciliation | effect ledger + external readback | Block blind retry when status is unknown |

**Invariant:** `reported_completed` + `transport=connected` is not equivalent to `verified success`. For read-only traces, every projection uses `reported_` rather than asserting trustworthy runtime state. The source-of-truth transition to `succeeded` remains a ledger operation with authenticated evidence.

## 4. Event protocol v1 (metadata only)

The observer accepts exact keys only. Do not add arbitrary `payload`, `prompt`, `url`, `cookie`, `message`, `response`, `headers`, `reasoning`, model output or raw exception text. Proposed minimal event:

```json
{
  "schema_version": 1,
  "event_id": "evt-3a1",
  "run_id": "run-41",
  "attempt_id": "try-2",
  "emitter_id": "collector.local",
  "seq": 19,
  "kind": "effect.reserved",
  "observed_at": "2026-11-22T10:20:00Z",
  "operation_id": "op-45",
  "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "fence": 8,
  "reason_code": "request_sent"
}
```

Allowed optional keys are `operation_id`, `revision`, `fence`, `reason_code`, `http_status`, `retry_after_seconds`, `receipt_digest` (SHA-256 hex), no extras. `revision` is a full 40- or 64-character SHA hex. Stable `operation_id` must be assigned before an external call, reused for reconciliations and NEVER regenerated just because an agent/extension restarted. The event emitter's `seq` is monotonic within (`run_id`, `attempt_id`, `emitter_id`); **no global ordering** is inferred from clocks in different processes. On ingestion, the trusted collector must overwrite `observed_at` with its own UTC receive time and authenticate emitter identity. `event_id` is stable across retries of event delivery; deduplicate by authenticated emitter + event ID. If the same ID has different content, quarantine it.

### Event kinds implemented in the offline projection

- Lifecycle: `run.created`, `run.started`, `run.completed`, `run.failed`, `run.cancelled`.
- Leases: `worker.heartbeat`, `worker.lease_granted`, `worker.lease_revoked`.
- Browser/bridge: `bridge.request_dispatched`, `bridge.response_received`, `bridge.response_timed_out`, `bridge.transport_disconnected`, `bridge.transport_reconnected`, `browser.tab_detached`, `browser.service_worker_started`, `browser.service_worker_suspended`.
- Provider: `provider.request_accepted`, `provider.response_completed`, `provider.rate_limited`, `provider.auth_failed`.
- Side effects: `effect.reserved`, `effect.acknowledged`, `effect.reconciled`.
- Artifacts: `artifact.committed`, `verification.passed`, `verification.failed`.
- HITL: `operator.approval_pending`, `operator.approval_granted`, `operator.approval_denied`.

For unknown events, fail closed and revise schema intentionally with migration tests. `http_status` alone is not sufficient to tell a recoverable 429 from quota exhaustion; `reason_code` must be an allowlisted normalized category when wired to a real provider. The current observer does not parse provider text.

### Trace correlation

Additional fields proposed for an authenticated collector v2 (not yet in implementation): W3C `traceparent`, `parent_event_id`, `causation_id`, `task_id`, `parent_task_id`, `artifact_id`, `config_version`, `policy_version`, `provider_request_id` stored hashed/opaque. `span_id` and trace IDs should flow across worker -> browser/extension -> provider -> verifier. Parentage must be based on explicit IDs, never inferred solely from timestamps.

## 5. Atomicity, retries and reconciliation

The existing Autopilot branch describes reservation before side effects. Retain this invariant in the GPT bridge:

```text
claim task (fence F)
 -> verify policy, current lease & ownership
 -> reserve effect E in durable transaction
 -> dispatch via approved transport with idempotency key E (if supported)
 -> record provider receipt if confirmed
 -> if reply lost: NEEDS_RECONCILIATION, never blind replay
 -> independently check provider state (where supported)
 -> record reconciliation / block for operator
 -> commit artifact + independent verify exact revision
 -> ledger terminal transition
```

Avoid the impossible guarantee "exactly once remote call": a crash between remote success and local acknowledgment is intrinsically ambiguous without a provider idempotency/receipt mechanism. A retry of the bridge transport, HTTP request and **business operation** are different. Do not treat `timeout`, WebSocket close or MV3 worker restart as evidence that the provider did not process the operation.

For browser UI, if the provider cannot identify/retrieve an accepted request, the correct status is **unknown**, and human intervention may be required. Never auto-resubmit a prompt or edit a conversation simply because the UI lost its spinner. For authorized OpenAI API jobs, retain provider response ID and use official polling/webhook receipts to reconcile rather than a DOM heuristic. Webhook signatures must be validated, deliveries deduplicated, and missed events reconciled by polling.

## 6. Failure taxonomy and concrete triage

| Signal | Possible mechanism (hypothesis until verified) | Evidence to collect, without private text | Safe response |
|---|---|---|---|
| No event from worker but lease open | worker died, process suspended, event buffering | lease fence, last collector heartbeat, process health | probe before lease expiry/reassignment |
| MV3 worker suspended | normal extension lifecycle | Chrome lifecycle event + outstanding outbox size | persist state; resume on event, no fake failure |
| Tab detached or user paused control | explicit revocation/navigation | tab binding validity, adapter event | stop issuing browser commands immediately |
| WebSocket lost during provider call | network drop after accepted request | operation ID, dispatch and provider receipt | reconcile; never blindly replay |
| Provider response event missing | delayed response, lost message, no provider support | ack from provider, collector ingest sequence | mark unconfirmed, not failed |
| `429 slow_down` | transient load/ramp limit | HTTP code + normalized error code + Retry-After | global bounded backoff and jitter |
| `429 quota/spend` | hard account budget reached | normalized billing/quota category | blocked; request owner action |
| `401/403` | revoked/expired auth or insufficient scopes | error class, entitlement state | no auto credential recovery; operator required |
| Duplicate event ID, different body | corrupted event stream / competing writer | event IDs + source IDs + digest comparison | quarantine; diagnose integrity breach |
| Sequence gap | dropped event, partial export or delayed event | emitter-scoped seq + collector ingest index | retrieve missing range; report uncertainty |
| Sequence conflict | two writers pretending to be one emitter | attempted source identity and seq | isolate and block writer |
| Out-of-order timestamps | clock skew / buffering | collector receive time, local seq, clock health | avoid total timestamp ordering |
| Old worker emits after replacement | stale lease/fence | high-water fence and stale event | reject at tool gateway, not merely in dashboard |
| Two agents use one browser tab | resource-lock collision | tab lease owner and scoped action ID | enforce one writer, allow multiple readers |
| Duplicate effect reservation | missing idempotency transaction or replay | operation key and reservation IDs | quarantine and reconcile all possible effects |
| `run.completed` without exact evidence | model self-declaration or stale CI | artifact SHA and verifier SHA | block success and schedule independent verify |
| CI passed for prior commit | branch mutated post-check | CI head SHA vs target SHA | rerun verify for exact revision |
| Agent role/prompt changed silently | prompt drift after checkpoint | prompt/spec digest, worker version | pause until contract revalidation |
| Browser selector changed | website/UI update | **safe** accessibility selector version/check, no private DOM | fail closed, propose adapter update with human review |
| Prompt injection in page/chat | untrusted content attempts policy change | structured policy denials, no raw text | ignore untrusted instructions; no elevated actions |
| Offline host | local runner/gateway stopped | OS service health, last checkpoint | do not promise continuous execution |
| Local MCP `429` or terminated | connector throttle/auth/session problem | endpoint category, status code, last successful probe | backoff; do not say repo/Obsidian changed |
| Logs fill disk | excessive events/no retention | queue length, disk watermarks, write errors | pause automation before losing audit trail |
| Agent reports "all tests pass" | hallucination / wrong repo state | trusted CI result and exact SHA | not accepted as evidence |
| OTel exporter down | observability backend outage | local durable outbox health | keep safe local metadata; no loss by default |
| Worker canary succeeds but follow-up fails | single call nonrepresentative | end-to-end trace across all stages | run a full failure injection, not a canary-only sign-off |

The trace doctor identifies only a subset of these from the current event schema. These are **proposed diagnostic and runbook cases**, not all implemented detectors.

## 7. Many agents: coordination and ownership

For 10–100+ workers, `agent_id` is not enough: separate **run, attempt, emitter, operation, task, resource and lease** identifiers. Use parent/child DAG dependencies, one writer per resource, versioned branch/worktree per task, dedupe by task specification digest and stable operation IDs. A0 gates changes, individual agents own disjoint modules, and the verifier must not share the implementer's credentials or self-reported tool output.

**Resource keys** should include `repo:path@branch`, `github:pr#N`, `obsidian:vault/path`, and `browser:profile/tab/session` where applicable. An agent touching multiple resources must acquire them in a deterministic order or use a single transaction coordinator; otherwise deadlocks and priority inversion appear. Do not rely on in-memory Python locks across hosts. Budget tokens, dollars, request rate, browser tabs and concurrent leases per project and *entire task DAG*, not fresh for every retry/subagent. Provide queue fairness and low-priority preemption only at safe checkpoints.

**Ownership:**

| Component | Owner | Integration contract |
|---|---|---|
| Durable task/effect ledger | Autopilot parallel branch | reserve/ack/reconcile, fence, evidence pointers |
| Skills/work contracts | Skill harness parallel branch | allowed tools, outputs, verifier/schema versions |
| Bridge protocol + offline diagnosis | This SDD and trace-doctor PR | bounded metadata envelope, no side effects |
| Browser MV3 adapter | Future separate branch | user-selected tab, loopback channel, persisted outbox |
| Supported OpenAI API adapter | Future separate branch | official response IDs/webhooks/retry taxonomy |
| Independent verifier | Future separate branch | exact SHA and authenticated CI artifacts |
| Operator view | Future separate branch | axes, uncertainty, blocker runbooks, approvals |

Integration must be contract-tested and feature-flagged. No two workers should directly update the same branch/worktree or shared SDD note. Separate change proposals go through PR review; do not auto-merge from agent text.

## 8. Evaluating ideas: weighted, explicitly provisional

Use `score = 10 × (0.30 impact + 0.25 reliability + 0.20 feasibility + 0.15 evidence + 0.10 risk reduction) / 5`, where each input is a **subjective 1–5 engineering estimate**, not measured performance. `Evidence` means confidence in the mechanism from source review/standards, *not* proof of this project's success. Re-score after real failure-injection results.

| Candidate | Impact | Reliability | Feasibility | Evidence | Risk reduction | Score /10 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Metadata-only causal events & diagnostics | 5 | 5 | 5 | 5 | 5 | 10.0 | **Build phase 0** |
| Reuse durable Autopilot effects/leases | 5 | 5 | 4 | 5 | 5 | 9.6 | **Integrate after ledger review** |
| Supported provider API with IDs/receipts | 5 | 5 | 4 | 5 | 5 | 9.6 | **Preferred GPT path when authorized** |
| Ownership/fencing at tool gateway | 5 | 5 | 3 | 5 | 5 | 9.2 | **Phase 2 gate** |
| Orthogonal 5-axis run states | 5 | 4 | 5 | 4 | 5 | 9.2 | **Build phase 0** |
| Bounded multi-tenant queues/quotas | 5 | 4 | 3 | 4 | 5 | 8.4 | Phase 3 |
| Deterministic fault injection and replay | 4 | 4 | 3 | 4 | 5 | 7.8 | Phase 2 |
| Chrome MV3 authorized outbox adapter | 4 | 4 | 3 | 4 | 4 | 7.6 | Only if browser path necessary |
| Statistical anomaly detector | 2 | 2 | 2 | 2 | 3 | 4.2 | Defer; needs trustworthy training data |
| Auto-repair broken ChatGPT DOM selectors | 2 | 1 | 2 | 2 | 1 | 3.3 | Reject as correctness foundation |
| Distributed services before local hardening | 2 | 2 | 1 | 3 | 2 | 3.9 | Reject premature scale-out |

The ranking intentionally values explainability and independent evidence above superficial autonomous activity. Random retries, fake worker keep-alive tricks and automatic DOM workarounds are **not** reliability engineering.

## 9. Diagnostics included in this change

`hermes_gpt_bridge/diagnostics.py` provides strict v1 metadata validation, bounded JSONL loading, idempotent event delivery handling, per-emitter sequence checks, stale-fence detection, external-effect reservation reconciliation warnings, unconfirmed bridge-request warnings, terminal completion evidence matching, auth/rate limit visibility, transport suspension and silence *hypotheses*, and deterministic per-run snapshots. `scripts/gpt_bridge_trace_doctor.py` emits machine-readable JSON with a list of runs, blockers and event IDs. An individual finding has severity and certainty; a hypothesis is never permission to restart an external side effect.

**Usage in repo checkout**:

```bash
python scripts/gpt_bridge_trace_doctor.py path/to/safe_metadata_only_trace.jsonl --stale-after 120
python -m unittest discover -s tests/hermes_gpt_bridge -v
```

Exit codes: `0` = parsed and no *critical* finding, `1` = parsed with critical finding, `2` = input or validation error. Exit code `0` **does not mean** the run succeeded or that an extension was available. This is an offline command; the user must provide trusted, properly redacted trace events from a future collector. Tested locally without network/browser dependencies. An isolated, credential-free Python 3.11 GitHub Actions workflow has been committed; its result is tracked at the exact PR SHA. No live dashboard or browser adapter is deployed.

## 10. Acceptance tests, negative cases and release gates

**Phase 0 (this PR):**

1. Strict reject of extra fields, raw text, malformed timestamps, unknown kinds and excessive line size.
2. Duplicate-delivery idempotence versus conflicting event-ID quarantine.
3. Per-emitter sequence isolation and gaps (reported as hypotheses, not certain loss).
4. Reserved but unacknowledged effect => critical `UNKNOWN_EXTERNAL_OUTCOME`; never auto-replay.
5. Duplicate effect reservation => critical even if a later acknowledgment exists.
6. Stale-fence write => critical; stale completion does not count as success.
7. `run.completed` with missing/stale artifact-verifier revision => critical.
8. Worker/transport loss, rate limit and provider auth errors remain distinct.
9. Five-axis snapshot does not claim authenticated success from self-reported events.
10. Deterministic output and no network/browsers/side effects.

**Phase 1 (partially implemented as disconnected components):** the local HMAC-authenticated SQLite *inbox*, read-only reporting, explicit backup and quota thresholds are implemented offline. A network listener, browser outbox, key rotation, automated retention (proposal: 14-day raw metadata, 90-day aggregate), scheduled backup/restore drills and pressure-aware gateway are NOT implemented; zero raw prompt/cookie capture remains a hard requirement. Fault injection: kill extension between event enqueue/send/ack, drop response after provider accepts, duplicate events, restart gateway during effect reservation.

**Phase 2:** trusted ledger integration and fenced tool gateway; owner-scoped browser authorization; exact revision verifier. Record proof of rejection for stale-fence and unknown external effects. No automatic remote retries until reconciliation is tested.

**Phase 3:** load test 10, 50 and 100 synthetic workers; concurrent claims and competing writers; starvation and queue fairness; simulated partition and clock skew; measured p50/p95 ingestion lag, backlog, event loss, recovery latency and accidental duplicate action rate. Introduce multi-host orchestration only when one-host limits are actually measured.

**Phase 4:** optional hosted/authorized GPT adapter, official background ID polling/webhooks, safe per-provider quotas, end-to-end authenticated trace. Validate provider policy and owner permissions separately from mere technical feasibility.

**Proposed goals, not current results:** zero unapproved effects in injected tests; zero auto-replayed unknown external effects; zero reported successes without trusted exact-revision evidence; recover all acknowledged metadata events across forced restarts; no raw secrets in exported traces; 24–72-hour synthetic soak with persistent local runner and repeatable restore.

## 11. Operator runbook: stop reason without false certainty

1. Identify `run_id`, `attempt_id`, trace health and last **collector** event; inspect all five state axes.
2. If `UNKNOWN_EXTERNAL_OUTCOME`: freeze dispatch for that operation, read provider receipt/status, reconcile or escalate to operator. **Never resubmit blindly**.
3. If `STALE_FENCE_WRITE` or `SEQUENCE_CONFLICT`: quarantine stale/competing worker, recheck gateway fencing and shared resources before assigning replacement.
4. If `AUTH_BLOCKED`: halt provider calls; do not scrape, refresh or exfiltrate credentials; ask owner to repair authorized access.
5. If `PROGRESS_SILENCE`/`SESSION_CHANNEL_UNAVAILABLE`: classify as hypothesis; inspect MV3 lifecycle, actual host/bridge and queue before deciding whether a task is blocked.
6. If completion evidence missing: verify artifact and CI at exact SHA, then correct task status; do not trust a narrative saying tests passed.
7. If an event cannot be parsed: quarantine the file; do not copy raw rejected input into logs/tickets because it might contain a secret.
8. Record hypothesis, evidence, attempted fix, regression test, reviewer and exact source SHA. Fix only the narrowest verified cause; rerun the trace on the same data and on adversarial fixtures.

### Incident log template

```text
Incident ID / run / attempt / operation / resource:
Last authenticated event ID + collector time:
What is observed (not guessed):
Impact and blocked invariant:
Hypotheses with confidence + competing explanations:
Authoritative receipts/evidence and precise revision:
Containment (no silent replay):
Proposed minimal fix + code owner:
Unit test / replay / fault-injection regression:
Review decision and rollback plan:
Residual risks / unknowns:
```

## 12. Integration order / release decision

**Keep this as draft until:** the intended ChatGPT/Hermes extension repository and runtime are identified, the separate ledger PR is reviewed, a trusted event collector exists, and integration tests demonstrate crash-safe handling. The safe first increment is a small, standalone diagnostic tool in an isolated PR, not a rewrite of Hermes browser tooling.

If the owner later chooses an official OpenAI API path, prefer structured provider receipts and background responses. If the owner explicitly chooses a user-controlled browser companion, accept its weaker guarantees, MV3 lifecycle and human-intervention boundaries; never claim it behaves like a durable official API. Revisit every proposed score after data from real, authorized traces and failure injections.

## 13. Phase-0 diagnostic correction log (2026-11-22)

- **OBSERVED / FIXED:** malformed non-string event-kind input previously raised a raw TypeError; strict schema now rejects it via TraceError. Added negative regression coverage.
- **OBSERVED / FIXED:** the first trace projection could report the browser connected when only the WebSocket or service worker recovered, even if the user-selected tab was still detached. Now track WebSocket, tab authorization and MV3 worker **independently**. An explicit browser.tab_attached signal is required to clear tab-detached state. Equal-timestamp contradictory events stay conservatively unavailable pending authoritative collector order. Only when all three components have been separately observed healthy does the summary say reported_connected; intermediate case is partially_observed_connected.
- **OBSERVED / FIXED:** event IDs were compared only within a single emitter, allowing the same event ID to appear under another emitter without an EVENT_ID_COLLISION; duplicate IDs across emitters now generate a collision finding per run.
- **LIMITATION:** browser.tab_attached remains **untrusted self-report**, not browser permission proof. A trusted per-tab user-consent adapter must independently validate authorization before issuing any tool operation.
- **TESTS:** 69 offline unittest cases with no live browser, network, durable collector or permission gateway. Synthetic 100-worker input checks run isolation, **not** throughput or multi-process crash resilience. No CI, E2E or extended soak claims.

### Phase-0 bounded-ingestion hardening (2026-11-22)

**OBSERVED / FIXED:** The original JSONL reader used an unbounded Python line iterator and checked event size only after materializing the entire line; a newline-free input could allocate an arbitrarily large object. Replaced with readline(MAX_LINE_BYTES+1), a 64 MiB total input cap and a 100,000-event cap; reject invalid override limits. Added three negative regression tests. Final local test count at bounded-ingestion fix: **46 passed**. This is still an offline parser; its caps do not replace a collector-level resource quota or trusted source authentication.

## 14. Phase-1 pre-integration durable authenticated inbox (2026-11-22)

**Implemented as isolated kernel, NOT wired to a browser or API:** `hermes_gpt_bridge/inbox.py` is a standard-library SQLite WAL metadata-only durable event inbox with a per-emitter HMAC-SHA256 authentication key (runtime-only; not in the database). The operation returns an ingestion offset, not a verified task completion. A row is committed transactionally before receipt is returned. Concurrent in-process writers use SQLite BEGIN IMMEDIATE and a bounded busy timeout; no claim of distributed agreement or multi-host durability.

Replay policy: exact same (run,event_id) and semantically identical JSON content (normalized key order/whitespace) returns the same offset; changed content with the same ID is rejected; conflicting (run,attempt,emitter,seq) is rejected. Signed payload timestamps are replaced with collector UTC observation time. Authentication must not be inferred from self-declared emitter_id; signature comparison uses constant-time HMAC checks. Unknown fields, duplicate JSON keys, oversized bodies and freeform reason_code values are rejected. Secret keys are provisioned by the trusted caller and are never logged or stored in the DB.

**Security limits:** no network listener, independent artifact verifier, browser consent adapter, credential rotation, automated retention/compaction, strict filesystem quota enforcement, off-host backup/restore, authenticated read API or rate-limit gateway. A pre-ingest byte threshold is present but not a byte-perfect disk allocation cap. The isolated Python 3.11 CI workflow is tracked separately from the full Hermes suite. A malicious but authenticated emitter can still lie in a reported event; only trusted verifier receipts establish business outcome. The input path and retrieval authorization must be controlled by the owner process. The 80-event/12-thread test and 30-message replay are synthetic correctness checks, not proof of sustained 100-worker throughput.

**Verified at initial inbox stage:** 69 tests, zero real API/browser calls. Separate test_inbox.py covers insertion and restart, wrong HMAC, emitter mismatch, duplicate JSON fields, missing/false signatures, conflict and idempotency rules, concurrent writes, SQLite WAL mode and read pagination. Source and test cases are committed in the draft PR; release gates remain mandatory before live activation.

## 15. Phase-1 operator reporting, quotas, backup and Autopilot integration risks (2026-11-22)

**Implemented but NOT deployed:** Added a read-only SQLite WAL snapshot reporter (`hermes_gpt_bridge/report.py` and `scripts/gpt_bridge_inbox_report.py`), with local one-shot JSON and operator-started polling mode. It explicitly reports `provider_outcomes_trusted=false`, stable ingestion offset, per-run diagnostic findings and source-health checks. A bad path never creates a database. The watch mode runs only while the operator's process is alive; this chat cannot start or promise an on-device daemon.

**Inbox operations:** Added `EventInbox.health()` (quick_check, WAL mode, count/offset, disk/WAL byte sizes, last collector timestamp) and `backup_to()` using the SQLite Online Backup API, consistency check, temporary file and no-overwrite atomic publish. Backup must be validated by a real restore drill before unattended deployment; this code does not manage automated retention or replica keys.

**Bounded growth:** `max_records` defaults to 100,000 and `max_storage_bytes` defaults to 128 MiB. Both limits fail closed for new ingest, while accepting bytewise or canonically identical redeliveries that were already committed. Capacity exhaustion is an operator-visible blocker, not permission to drop silently or retry side effects. An unbounded log writer is a production incident.

**Additional v1 fields:** optional task_id/project_id stable IDs for correlation. They are **not authoritative**: the trusted adapter must resolve run_id and task_id to one Autopilot lease/project generation. Future replay should use durable SQLite ingestion offset; timestamps are not a total causal order for independent workers.

**Source-audited Autopilot handoff risks (from feat/autopilot-durable-ledger-20261122, unmerged):**
1. AutopilotLedger.fail() stores a truncated freeform worker reason in its own events. It must be normalized/redacted before any bridge export; otherwise the metadata-only guarantee is defeated across stores.
2. AutopilotLedger.record_evidence(..., trusted=True) is intentionally not a security boundary; only an authenticated verifier gateway may call it. A signed HMAC worker observation is still not proof of tests or provider effects.
3. AutopilotLedger.reconcile_effect() can requeue work after acknowledging an effect. Every subsequent worker must preserve the action_key history and must NEVER re-run that side effect solely because the task was requeued.
4. The project stop/generation token prevents stale workers in ledger methods, but **external tools must check the generation and fence immediately before use**; this bridge does not yet enforce that gateway.
5. Both SQLite journals are single-host WAL stores with different owners: Autopilot is authoritative for task/effect/approval; this inbox is transport evidence only. Avoid cross-DB two-phase commit assumptions; reconcile by stable operation IDs.

**Final local status for this checkpoint:** 88 unittest cases passed offline, including synthetic 80-event concurrent ingestion, restart, receipt idempotency, HMAC rejection, backup restore, capacity cutoffs, read-only snapshots and report CLI error handling. No authenticated HTTP listener, real ChatGPT extension, real provider receipt, CI result at final revision, native Windows run or long-duration soak is claimed.


## 16. Repository CI incident — exact-SHA evidence and containment (2026-11-22)

**OBSERVED:** on PR #8 head `7b080426f5edd700321b4615f0be228e58721d65`, GitHub workflow `Tests` run 45013893071, job 137181956512 concluded failure with **28 failed / 7570 passed / 171 skipped / 32 subtests passed**. Failure paths were outside the new `tests/hermes_gpt_bridge/` suite: many streaming/client tests failed on missing `OPENAI_API_KEY`/client credentials; one Codex model validation assertion, one auxiliary-vision fallback assertion and three file-read timeout failures were also observed. Supply Chain Audit passed at that SHA; Docker Publish was skipped.

These facts **do not prove** the 28 failures were pre-existing: an equivalent successful/failing baseline CI run on main was not available to compare. Do not edit unrelated Hermes modules or inject real credentials just to make the job green. Diagnose those in a separate owning scope, with fake provider credentials/mocks and timing isolation as appropriate.

**MITIGATION implemented in this branch:** `.github/workflows/hermes-gpt-bridge.yml` runs `compileall` and stdlib-only tests on Python 3.11, scoped to this bridge, with read-only GitHub token permission. A passing isolated job only certifies this suite at its **exact workflow head SHA**. The full suite must also become green or have an explicit, reviewed and documented waiver before merging. CI results at previous commits never certify later changes.

**Current local evidence:** 88 unittest cases passed in the offline runtime. Continuous user-device monitoring, vendor interoperability, secret rotation, multi-process load/soak, long-running event collection, exact-revision trusted verifier and any ChatGPT-browser extension permissions remain unverified and unimplemented.
