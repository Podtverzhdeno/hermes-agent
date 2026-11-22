# SDD-IC-001 — Hermes ↔ GPT integration convergence and atomic diagnosis

**Date:** 2026-11-22  
**Status:** PROPOSED / integration design; **not deployed**, **not live-verified**  
**Source snapshot:** `Podtverzhdeno/hermes-agent` `main` at `7e9100901819ee44c16b4ddcb79a6bcb7909f591`; compare results from 14 peer branches  
**Audience:** integrator, maintainers, authors of PR #1–#13, browser bridge and operator agents  
**Decision owner:** repository maintainer; this document grants no actor privileges.

## 0. What we know, and what we do not

**OBSERVED in fork `main`:** `gateway/platforms/api_server.py` has process-local `_IdempotencyCache.get_or_set()` that calls the async computation before reserving a key, silently replaces an existing key with changed fingerprint, and dispatches `stream=true` before any keyed cache check. SSE allocates an unbounded `queue.Queue()`, catches task exceptions without translating them into failure, and may emit `finish_reason=stop` / `[DONE]`. The caller-supplied `X-Hermes-Session-Id` is used to fetch stored session messages; principal ownership enforcement was not established by this source review. These are code observations, not live exploit demonstrations.

**OBSERVED in connected GitHub:** 14 branches compared against the same base; 16 paths shared by at least two branches, 16 pairs with at least one path overlap. Four branches modify `gateway/platforms/api_server.py`; five modify `pyproject.toml`. PRs #1–#13 were discoverable individually; Issues creation returned 410 (Issues disabled). Some branches are intentional stacks: #10 on #1; #11 on #4.

**BLOCKED:** Local_WorkSpace MCP responded `Session terminated`. No evidence of current browser/extension installation, Windows bridge, local logs, Obsidian state, CDP readiness, authorized ChatGPT web workflow, or actual live fault rates. Historical notes about a Windows `chat-launch-smoke-desktop-test/web-extension` and port `18763` are leads for verification, **not current facts**.

**UNVERIFIED:** Reports of green offline tests in peer PR descriptions require exact-head independent CI / fixture reproduction. No branch in this snapshot is automatically accepted as production ready.

## 1. Required outcome and negative guarantees

The operator must answer for each operation:
1. What was requested, by which authenticated principal, under which immutable requirements SHA and policy version?
2. Who accepted/claimed it, with which lease generation and bounded budget?
3. Which step and tool effect began, and what external system acknowledged it?
4. What is merely observed (transport/DOM/model text), and what is independently verified?
5. Why is it waiting, failing, uncertain, cancelling or stalled — and what action is *safe* now?
6. Which exact code SHA, test artifact and rollback path make a proposed fix reviewable?

**Never claim:** exactly-once external execution from an in-memory cache; a browser canary proves task completion; heartbeat proves progress; UI text or HTTP 200 proves provider commit; a stack overlap is automatically a textual merge conflict; an LLM can self-authorize privileges; a telemetry store can grant `succeeded`.

Safety invariants:
- One authoritative task/effect ledger. Observers and projections do not update authoritative work state.
- On network timeout after a possible external write: `NEEDS_RECONCILIATION`, never blind replay.
- All externally mutating actions use a stable effect key, an intent before dispatch, and provider-side idempotency/fencing where supported; otherwise independent read-after-write reconciliation.
- Immutable terminal record with linked correction event, not destructive history rewrite.
- Parent completion requires acknowledged child evidence and absence of unresolved effects.
- Human approval is bound to exact task, capability, target, operation digest, expiry and principal.
- No raw prompts, browser DOM, cookies, tokens, auth headers, private paths or unredacted exception messages in standard diagnostic events.

## 2. Existing candidate streams — integration ownership, not a merge order

| Area | Candidate(s) | Authority / plan | Required review |
|---|---|---|---|
| Task/effect ledger | PR #1; PR #10 stacked on #1 | #1 base + #10 delta, if accepted; no duplicate schedulers | claim CAS, crash ambiguity, effect fence, proof validation, schema migrations |
| ACP approvals | PR #3 | independent security prerequisite | concurrent ACP sessions, unknown option fail closed, noninteractive bypass |
| API request safety | PR #4, #5, #6 | **choose one** core handler/cache algorithm; cherry-pick discrete improvements | keyed concurrency, request fingerprint, stable response/session, errors, SSE |
| Request preflight | PR #11 stacked on #4 | port its validated ingress cases to selected API implementation | stream+key and malformed-body rejection *before* side effect |
| Read-only diagnostics | PR #9 / #12 / #13, plus other `gpt_bridge` proposals | choose a single canonical event envelope; source adapters may coexist | storage roles, schema/version migration, no false-positive success |
| Browser CDP | PR #13; independent Windows extension unverified | owner-authorized bridge only | MV3 restart, tab fencing, authentication, redaction, ack levels |
| Skill policies | PR #2 | advisory harness until enforceable server policy exists | path traversal, scope confusion, schema bypass |
| PR collision audit | `feat/gpt-integration-collision-gate-20261122` | candidate static pre-merge check, **not** run state oracle | ancestry, truncation, 10–100 PRs, PR head drift |
| Parallel design docs | PR #7/#8 and peer SDDs | keep competing proposals accessible; index reviewed decisions | no silent supersession of crucial invariants |

**Current disposition:** no automatic merges; do not edit peer-owned hot paths. Review at exact head SHA; choose behavior via acceptance tests, not agent confidence. GitHub's source/file CAS protects edits, but does not itself provide a runtime task claim.

### 2.1 Exact observed file collisions

- `gateway/platforms/api_server.py`: four branches (`feat/gpt-bridge-atomic-diagnostics-20261122`, `feat/gpt-bridge-observability-20261122`, `fix/gpt-bridge-request-preflight-20261122-f9ac`, `sdd/gpt-observability-2026-11-22`).
- `pyproject.toml`: five feature branches (`feat/autopilot-durable-ledger-20261122`, `feat/autopilot-observability-sdd-20261122`, `feat/gpt-bridge-observability-sdd-20261122`, `feat/gpt-companion-event-observer-sdd-20261122`, `feat/gpt-observability-sdd-20261122`).
- `autopilot/ledger.py` plus 10 related paths: overlap #1/#10 is an expected parent-child stack.
- #4/#11 share five paths as a stacked patch.

**Interpretation:** path overlap is a review trigger, *not proof of an unresolved merge conflict*. After filtering proven parent-child ancestry, independent API candidates remain mutually incompatible until a single implementation is selected.

### 2.2 Critical review of competing candidate implementations

**P0: PR #5 / `feat/gpt-bridge-atomic-diagnostics-20261122` retains no uncertainty tombstone on a failed computation.** In `gateway/idempotency.py`, `IdempotencyCache.get_or_set()` registers an in-flight task, but its `execute()` `finally` handler deletes the `_inflight` key whether `compute_coro()` succeeded or failed. Only successful executions enter `_completed`. If an external effect occurred and a late network/agent exception is raised, the same key can launch another execution. This is a source-level failure of *safe retry semantics*, not proof of an observed duplicate. **Required correction:** retain a bounded durable outcome-unknown reservation with effect ID and reconciliation owner, never automatically rerun after uncertain mutation. Reproduction: stub persists side effect, throws before HTTP reply, then same-key retry; assert effect count = 1 and `OUTCOME_UNKNOWN` until trusted reconciliation. A process-local uncertain tombstone improves same-process behavior but cannot promise restart safety.

**P0 for multi-principal use: PR #6 / `sdd/gpt-observability-2026-11-22` scopes `chat:` idempotency by raw client key but not authenticated principal.** The chat handler constructs `"chat:" + idem_key` and fingerprints body plus `provided_session_id`; this prevents cross-body duplicates but may return an existing cached payload/session to a distinct authorized caller who chooses the same key and identical body. If the deployment has only one shared principal this is a confinement limitation; if there are multiple logical principals/tenants it is a cross-principal replay risk. **Required correction:** derive identity from the authenticated principal (not user-provided Authorization text), bind to authenticated tenant and authorized session revision, and enforce session access *before* lookup/history. Test two authorized principals using the same key/request and assert no shared response/session. Also test unauthorized `X-Hermes-Session-Id` refuses access without disclosing whether the session exists.

**P1 compatibility:** PR #4 candidate returns HTTP 422 on altered fingerprint while PR #6 uses 409. Publish one client contract and run both candidates against it before choosing. `409` is the proposed interoperability target; this is a design decision, not an already-shipped guarantee.

**P1 resource bound:** Candidate #6 preserves the original unbounded `queue.Queue()` in its SSE path. Even when exception classification improves, a slow consumer can cause memory growth. Require bounded output buffer, backpressure policy, terminal failure/uncertainty reporting, and end-to-end slow-reader tests.

**Cross-check rule:** A review finding names both *file revision* and *candidate branch*. Do not assume any of these flaws are already present on `main` unless separately observed there. A new candidate is eligible for acceptance only when the relevant regression fails before its fix and passes at its exact reviewed HEAD.

### 2.3 Upstream parity overrides legacy API merge assumptions

**Additional source audit:** Current official NousResearch `main` already contains an expanded API server (about 4,080 lines vs fork's ~1,356), `/v1/runs` with status/events/approvals/unknown resolution, a SQLite run reservation store, and native CDP browser control. Important residual risks remain in upstream's *legacy* in-memory cache: same-key/different-fingerprint concurrent calls are indexed as separate tasks, and failed tasks lose their in-flight reservation; the durable run store can downgrade to memory on DB open errors. **Before integrating PR #4/#5/#6/#11, review [ADR GPT-UPSTREAM-001](2026-11-22-upstream-parity.md)** and explicitly select whether to port upstream run primitives rather than overwrite them. These are source observations requiring targeted tests, not live incident claims.

## 3. Source-of-truth and causality model

```text
owner intent + scoped policy -> ingress validation -> durable task admission
                                    |                 |
                                    v                 v
                              correlated trace    operation ledger (one authority)
                                    |                 | transaction + outbox
                                    |            per-session scheduler/lease/fence
                                    |                 |
                                    +-- agent + tools + approval + broker
                                    |                 |
                                    |             effect intent -> dispatch -> receipt
                                    |                 |                    |
                                    |                 +--- unknown? -> reconciliation
                                    |                                     |
                          observers/read-only dashboards <--- evidence verifier
                                                    |
                                                  operator
```

Model an operation as `task -> attempt -> step -> effect -> receipt -> independent verification`. A `trace_id` groups causally related spans but is not an authorization credential. A lease heartbeat measures worker availability; only a committed step transition or trusted effect receipt measures progress. Trace exporting is best effort. Ledger/outbox must survive an observer or collector crash.

### 3.1 Concurrency

- Same external session, browser tab/document epoch, Git ref or exclusive resource: one active write owner at a time, with revision CAS and fencing.
- Read-only checks can parallelize, subject to per-tenant fair capacity; provider global 429 limits require shared backoff.
- Each child inherits the **intersection** of parent capabilities, remaining budget and immutable policy. A new agent process does not create new spending authority.
- On lease expiry, revoke future commits from the stale epoch; still reconcile already-dispatched effects. Database fencing alone cannot undo browser clicks or provider writes.
- On `cancel_requested`, stop future dispatch and verify child/effect termination; don't claim `cancelled` while effects remain unknown.
- Multi-host work must not use a shared SQLite WAL folder as distributed consensus; keep one local writer or move authority to an explicitly managed transactional service.

### 3.2 Event contract (proposal; map to #1/#10 without a second store)

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "operation_id": "uuid",
  "attempt_id": "uuid",
  "step_id": "uuid-or-null",
  "effect_id": "stable-hash-or-null",
  "producer_id": "process-boot-uuid",
  "source_seq": 42,
  "causation_event_id": "uuid-or-null",
  "principal_ref": "opaque-allowlisted-ref",
  "session_ref": "opaque-allowlisted-ref",
  "lease_epoch": 7,
  "trace_id": "32-lower-hex",
  "span_id": "16-lower-hex",
  "event_type": "effect.outcome_unknown",
  "reason_code": "EFFECT_OUTCOME_UNKNOWN",
  "occurred_utc": "2026-11-22T10:00:00Z",
  "observed_utc": "2026-11-22T10:00:01Z",
  "source_revision": "40-char-sha",
  "evidence_ref": "receipt-id-or-null",
  "confidence": "observed"
}
```

Consumer MUST reject or quarantine unrecognized `schema_version`, duplicate `(producer_id,source_seq)` with nonidentical content, unknown event kinds, unknown authorities and oversized input. `producer_id` changes on process restart. Wall clocks do **not** impose a total order across workers. HMAC or opaque identities must protect low-entropy user/session IDs; unsalted hashes of email addresses are not privacy guarantees.

### 3.3 Evidence tiers — never vote a task into success

1. Independently verified, authenticated provider effect or trusted CI artifact bound to exact SHA.
2. Ledger transaction with fence/version and effect intent/outbox.
3. Reproducible fault-injection test bound to a known fixture/commit.
4. Authenticated trace/transport receipt proving only the phase it claims.
5. Browser DOM, local screenshot or model narration — *observation*, not completion.

A missing downstream ACK does not prove that a side effect failed. A duplicated ACK does not prove a second execution. Conflicting trusted receipts must trigger `EVIDENCE_CONFLICT` and operator reconciliation, not majority voting across agents.

## 4. API / GPT bridge public contract (candidate for one implementation)

| Scenario | Required outcome |
|---|---|
| Repeated same key + same authenticated principal + same canonical request | same run reference; join in flight or return explicit pending; never start another agent |
| Same key + different canonical input/session/model/tool permission | stable `409 idempotency_conflict` before execution |
| Concurrent independent session revisions | serialize or `409 session_revision_conflict`; no invisible transcript reordering |
| Keyed SSE without durable cursor/resume | explicit `400 unsupported_idempotency_mode` **before** agent dispatch |
| SSE agent exception | failure event/error envelope, not `finish_reason=stop` / silent `[DONE]` success |
| Slow SSE reader | bounded backlog/backpressure and explicit terminal uncertainty; no unbounded `queue.Queue()` |
| Aborted HTTP connection | do not infer cancellation of an in-flight external effect |
| Backend crash after effect dispatch | `NEEDS_RECONCILIATION` until independent provider read-back |
| In-memory cache eviction/restart | do not advertise durable idempotency; no unsafe replay guarantee |
| Unauthorized `X-Hermes-Session-Id` | reject without exposing session existence |
| Bad JSON, non-object messages, nonboolean flags, oversized bodies | typed `4xx` before any side effect |
| Non-loopback API binding | require server-enforced authentication, origin/CSRF policy and scoped session ownership |

Bound all queues and response sizes. Consider split `/live`, `/ready`, `/progress` rather than one "ok" endpoint. Non-empty prompt, HTTP 200, SSE completion and ChatGPT canary are not substitutes for `verified` status. Authentication, tenant and session binding must be applied **before** history is read.

## 5. Browser extension trust boundary and observability

```text
untrusted webpage -> content script (DOM observation)
                   -> extension MV3 service worker (may suspend)
                   -> authenticated allowlisted local host / bridge
                   -> Hermes broker (authorization + durable effect authority)
```

Document the deployed `manifest.json`, permissions, `externally_connectable`, allowed origins, extension ID, service worker lifespan, extension version+hash, local host listener/bind, port, transport handshake, log path and process health **before** patching browser code. Do not copy historical version or port values into an active config.

Command ACK ladder: `RECEIVED` (framed transport) -> `ACCEPTED` (validated) -> `DISPATCHED` (external effect possible) -> `PROVIDER_COMMITTED` (trusted receipt) -> `INDEPENDENTLY_VERIFIED` (state read-back). Missing ACK after `DISPATCHED` means **UNKNOWN**. The same account can have multiple tabs; `tab_id`, `document_epoch`, `conversation_revision`, `effect_id` and `owner_lease_epoch` must be checked before any write. User manual edits/Stop/Regenerate take precedence where they conflict.

Never scrape cookies, bypass CAPTCHA/MFA/approval, infer private model state or transform a signed-in web session into an unrestricted unattended API. Prefer supported API tools for orchestration; web UI integration is an explicitly authorized supplementary surface. Native Messaging is not automatically a secure privileged boundary without independent host authorization.

### 5.1 ADR GPT-EXT-001: integrate with existing Hermes browser supervisor before inventing a second owner

**Newly verified external design evidence:** Current upstream Hermes browser documentation exposes a native `browser_exec` browser session, optional `/browser connect` attachment to Chrome-family CDP, and persistent browser state across tool calls (but not Python interpreter globals). The audited fork may lag upstream; presence/behavior of these capabilities **in the deployed local fork** must be checked at its SHA and runtime. Official browser documentation: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/browser.md .

**Options comparison — independent of user profile authentication:**

| Option | Best fit | Failure boundary | Decision |
|---|---|---|---|
| Official GPT/model API with scoped credentials | programmatic requests, structured receipts, explicit rate/cost policy | API timeout or unknown external side effect | **Primary for automated workload dispatch** where supported |
| Hermes `browser_exec` with existing `/browser connect` CDP transport | owner-authorized interactive browser task with existing Hermes browser session | CDP disconnect, stale target or browser session | **Preferred reuse for browser interaction** if exact deployed version supports it |
| Separate GPT MV3 extension + native companion | owner opt-in UI status or extension-specific events unavailable in existing supervisor | extension service worker, tab/navigation, messaging host, local OS | **Observability adapter first**; allow mutations only via shared fenced browser broker with explicit approval |
| Direct unaudited DOM/CDP multi-agent writes from both paths | no defensible use | undetectable double submission / race with user's actions | **Reject** |

**Exclusive physical browser lane:** a single host/session/tab/document must have at most one write-capable owner, regardless of whether entrypoint is Hermes `browser_exec` or an extension. Use the same `browser_lane_id`, `document_epoch`, `session_revision`, `effect_id`, capability and fence through both paths; cross-path messages cannot bypass the ledger claim. If the Hermes browser backend cannot accept the fence/receipt contract, keep it observation-only or isolate it to its own temporary browser session. A standalone extension should never silently compete with Hermes' native CDP supervisor.

**Lifecycle nuance:** Chrome documentation confirms that normal MV3 workers may stop after idle, while active native messaging ports (Chrome 105+), active WebSockets (116+) and active debugger sessions (118+) can prolong worker lifetime. A kept-alive worker is *not* a durable transaction manager: crashes, updates, tab replacement and host disconnect still require replay/reconciliation. Official lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle . The Chromium security FAQ explicitly states Native Messaging is not a secure communication channel by itself and needs separate application-layer authentication where required: https://github.com/chromium/chromium/blob/main/extensions/docs/security_faq.md .

**Acceptance:** run two synthetic actors against the same browser lane using different control paths; allow one read-only observation and exactly one authorized write, reject the stale actor and prevent resubmission of an uncertain external action. Run again after MV3 suspension, host crash, Chrome update, tab navigation and manual user interference. No browser backend becomes the task authority.

## 6. Stop diagnosis: explanation not speculation

Track separate timestamps for `last_heartbeat`, `last_step_progress`, `last_provider_response`, `last_transport_frame`, `deadline_at`, plus `awaiting_approval`, `effect_uncertain`, `queue_position`, `lease_epoch`, `session_revision` and `evidence_state`.

1. **Authority check:** can the authenticated ledger be read, is schema current and operator allowed? If no: `OBSERVABILITY_UNAVAILABLE`; do not guess.
2. **Terminal check:** only verified terminal events end work; observational end-of-stream does not.
3. **Safety gate:** unresolved effect, approval or fence mismatch dominate all liveness warnings.
4. **Progress check:** heartbeat present but no committed progress beyond SLO => `STALLED_NO_PROGRESS`; heartbeat absent and lease expired => `LEASE_EXPIRED`. Both demand effect reconciliation before reassignment.
5. **Transport check:** worker active but bridge down => `BRIDGE_DISCONNECTED`; distinguish from remote model blocking.
6. **Budget/permission/provider check:** hard stop vs bounded retry, keyed to reason code and explicit next action.
7. **Ambiguity:** missing causal evidence or conflicting sources => `UNKNOWN` / `EVIDENCE_CONFLICT`, confidence stated; no speculative root-cause assertion.

Incident output fields: `operation_id`, status, `reason_code`, observed vs hypothesized causes, last durable event cursor, evidence refs, uncertain effects, safe next action, responsible owner, SHA, regression test, rollback. Retain sanitized records under explicit retention policy.

## 7. Fault-injection matrix (mandatory before rollout)

| Fault | What must remain true | Acceptance observation |
|---|---|---|
| two concurrent identical keyed HTTP calls | 1 execution, 1 stable response identity | same trace/run or explicit pending |
| same key, altered body or session | 0 extra executions | deterministic 409 |
| SSE worker crashes mid-token stream | no false success terminator | reason-coded failed/unknown |
| slow client consumes no SSE | bounded memory, no hidden unbounded queue | backpressure/policy error |
| browser MV3 worker suspends after command accepted | effect not silently repeated | reconnect by stable effect ID |
| tab navigates between selecting and clicking | stale document epoch rejected | no write |
| user enters a competing message | user input not overwritten | conflict reason and safe pause |
| provider accepts write but ACK is lost | remains uncertain until read-back | no duplicate write |
| lease expires after external dispatch | old worker cannot commit; effect reconciled | stale fence rejection |
| approval arrives after deadline | no action | expired approval rejected |
| crash between intent/outbox transaction and network dispatch | recovery shows undelivered intent | safe read-only reconciliation |
| crash after dispatch but before DB receipt | no blind replay | outcome unknown |
| one of 30 workers is noisy or looping heartbeat | fair progress and budget cap | starvation and stall visible |
| PR changes package discovery | all accepted modules installed in built wheel | imports smoke after build |
| observer receives a forged success event | no ledger success | quarantined, audit entry |
| log exporter or disk fails | no unlogged privileged side effects | fail closed where durable recording required |
| local MCP is disconnected | visible `LOCAL_MCP_UNAVAILABLE`, not `PROJECT_FAILED` | separate transport health |

Record test harness revision, fixture checksum, exact run SHA, environment, input mode, result and reproduction command. "Offline unit tests passed" does not equal "live bridge verified". Include real deployment validation only with the owner's authorized machine and a safe, reversible test task.

## 8. Ranked engineering ideas and explicit scoring

**Decision model**: score each idea 0–5 on reliability (30%), security (25%), causal visibility (20%), integration cost/effort (15%; higher=lower cost), operator usability (10%). These are expert *planning estimates*, not empirical success probabilities.

| Idea | R | S | C | E | U | Weighted /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Authority ledger + effect reconciliation | 5 | 5 | 5 | 2 | 4 | **4.45** | P0, build on #1/#10 |
| Ingress idempotency + trustworthy failure states | 5 | 5 | 4 | 3 | 4 | **4.40** | P0, choose one API implementation |
| Approval/session identity isolation | 5 | 5 | 4 | 3 | 3 | **4.30** | P0, review #3 and session binding |
| Unified event envelope + runbook | 4 | 4 | 5 | 4 | 5 | **4.30** | P0/P1, avoid competing stores |
| Per-resource owner lease + collision gate | 5 | 4 | 4 | 3 | 5 | **4.25** | P1, exact-head PR checks |
| CDP/MV3 lifecycle and synthetic fault harness | 4 | 5 | 4 | 2 | 4 | **3.95** | P1, local deployment unknown |
| Pretty dashboard before ledger/receipts | 2 | 3 | 2 | 3 | 5 | **2.70** | defer |
| Blind agent rerun after timeout | 1 | 0 | 1 | 5 | 1 | **1.35** | reject |
| Multiple independent authoritative GPT ledgers | 1 | 1 | 2 | 2 | 2 | **1.45** | reject |

Scores prioritize safety and reliability over raw throughput. Re-score after full CI, fault-injection and live authorized tests with measured costs and false positives.

## 9. Merge and rollout plan

**Gate A — freeze facts:** capture base/head SHAs of all candidate PRs, upstream diff, source ownership and changed file inventory; mark parent-child stacks explicitly. Upstream parity required before accepting old fork assumptions.

**Gate B — security first:** ACP authority fixes + session ownership, payload contracts, scrubbed errors and restricted bindings. Independent security regression reviewer.

**Gate C — one API implementation:** choose #4/#5/#6 *behavior*, integrate #11 preflight, run one common test matrix. No direct merge of multiple full `api_server.py` variants. Backpressure and lost-SSE completion tests are missing unless proven by exact-head CI.

**Gate D — one ledger:** staged #1 then #10; migrate/version database, test crash ambiguity and restore, reconcile external effects. Do not assign authority to #9/#12/#13 read-only telemetry.

**Gate E — standardized observations:** select canonical event schema and one storage/retention owner, then attach independent read-only diagnostics for API, MCP and authorized browser. Pin OTel GenAI semconv version.

**Gate F — 10/30/100 worker simulation:** fairness, memory, lock contention, stale lease, partition, conflicting PR, admission budget, no idempotency collision. Test across distinct processes, not only asyncio tasks.

**Gate G — opt-in runtime:** enforce exact merged-SHA CI + package wheel smoke + owner-authorized local deployment verification, feature flag, rollback, backup integrity and synthetic canary. Do not replace a working local version without a verified snapshot.

**Target SLOs to validate, not measured today**: zero duplicate verified external effects under injected retries; zero false terminal-success signals; 100% uncertain effects assigned explicit owner/reconciliation state; 100% terminal transitions with evidence pointer and source revision; no unbounded queue growth; all privileged writes tied to scope and approval. Alert on missing measurements rather than inventing green status.

## 10. Multi-agent handoff and ownership contract

Before edits: publish `task_id, owner, parent, target branch, base SHA, write_set, read_set, expected_revision, lease_until, dependencies, risk, budget, tests, rollback`. Resource claims are advisory until a coordinator with storage CAS enforces them; do not describe a GitHub branch name as a lock. Prefer independent worktrees and small additive contracts. Explicit parent approval before expanding capability, budget or file ownership.

After edits: publish `head SHA, changed file list, tests actually executed + environment, failing checks, evidence refs, unresolved effect state, operator decision, next owner`. If disconnected, log `OBSERVABILITY_UNAVAILABLE` and preserve current status; do not invent completion. If no owner responds, do not silently promote a child to maintainer.

Review/proposed remedies are **patch candidates**, not production fixes. Gate on independent code review and exact merged SHA. A multi-agent system should reward reporting uncertainty, not pressure workers to claim 10/10.

## 11. Engineering log (snapshot; append in linked follow-up ADRs)

- **2026-11-22 / SOURCE_AUDIT:** Found unsafe baseline in-memory idempotency, unbounded SSE queue and swallowed agent exception; examined `gateway/platforms/api_server.py`, `hermes_state.py`.
- **2026-11-22 / GITHUB_AUDIT:** 14 related branches, 16 shared paths, 16 overlapping pairs. PR #1–#13 inspected; #10 and #11 identified as stacked. Branch/PR heads may move after this snapshot.
- **2026-11-22 / CONNECTOR_FAILURE_AND_PARTIAL_RECOVERY:** First Local_WorkSpace call returned `Session terminated`. A later `list_workspaces` call succeeded but exposed only `shelter` (a scoped Obsidian workspace), not the Hermes extension directory; separate read-only `temp-folder` was unrelated. Therefore live Chrome extension/companion source, process health and logs remain **NOT VERIFIED**. The transient connector failure alone is not evidence that Hermes execution stopped.
- **2026-11-22 / WRITE_LIMITATION:** GitHub Issues creation returned HTTP 410 (disabled); use draft PR review and SDD for coordination.
- **2026-11-22 / UPSTREAM_PARITY_AUDIT:** Compared fork and official NousResearch API source; found newer run/idempotency architecture, additional legacy cache risk, and documented parity findings in GPT-UPSTREAM-001.\n- **2026-11-22 / DECISION:** no unverified runtime changes to `main`; write this isolated SDD proposal and seek integration checks. No code execution/CI success asserted by this document.

## 12. High-authority design references

- W3C Trace Context: https://www.w3.org/TR/trace-context-1/
- OpenTelemetry GenAI conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Chrome MV3 service-worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chromium extension security FAQ: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/extensions/docs/security_faq.md
- SQLite WAL: https://www.sqlite.org/wal.html
- GitHub merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- Temporal activity idempotency/retries: https://docs.temporal.io/activities
- OpenAI API Agent sessions: https://developers.openai.com/api/docs/guides/agents-api/sessions
- Hermes upstream browser guidance: https://hermes-agent.nousresearch.com/docs/user-guide/features/browser

**Change boundary:** this is a documented integration plan, not a claim of live monitoring, installed browser hooks, production fixes, or full upstream parity.