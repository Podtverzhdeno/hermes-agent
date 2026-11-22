# Hermes ↔ GPT: Causal Observability and 50-Agent Reliability (SDD addendum)

**Date:** 2026-11-22. **Status:** reviewed architecture and offline prototype; **not deployed**.
**Parent design:** draft PR #7 (`docs/gpt_bridge/SDD.md`).
**Source baseline:** fork `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591`; rebase against modern upstream required.
**Isolation:** this workstream MUST NOT edit `gateway/platforms/api_server.py`, `autopilot/ledger.py`, ACP callback code or other agents' branches. Do not merge without review and exact-SHA tests.

## ADR-01: one state authority, many evidence readers (ACCEPT)

Current upstream Hermes provides durable Runs API and Kanban worker lanes. Upstream must be reviewed as the lifecycle owner. A new GPT extension must **not** introduce its own task queue, approvals, leases or authoritative success state. Browser UI is a non-authoritative observer; optional explicit, user-approved interaction is a separate capability. The fork's prototype Autopilot PR #1 must be compared to upstream, not blindly layered as a second scheduler.

```
Owner instruction -> versioned run/task contract -> upstream Hermes Runs/Kanban
                                                  -> trusted tool + effect gateway
                                                  -> independently verified receipts
         +-- authenticated, bounded event adapter -> diagnostic event journal
                                                       -> causal projection
                                                       -> operator / optional MV3 UI
```

For an external write, `prepare -> effect reserved -> remote call -> verified receipt` has crash windows. A timeout after reservation means **UNKNOWN OUTCOME**, never an automatic repeated write. Persist the ledger reservation and outbox atomically in the authoritative system. The read-only observer below cannot enforce authorization or exactly-once effects.

## ADR-02: heartbeat is not progress (ACCEPT)

Upstream issue https://github.com/NousResearch/hermes-agent/issues/100971 documents active heartbeats during a stuck tool loop. Track four dimensions independently: `transport_connected`, `worker_recent_heartbeat`, `verified_progress`, `authoritative_task_succeeded`. A model's "done" message, a heartbeat or a ChatGPT spinner disappearing cannot complete a task.

Detect repeated *same* operation fingerprint within one producer/task/attempt/fence/revision since the last independent matching verifier event. An unrelated task's verification or an earlier successful batch must never suppress a later loop. This bug was discovered and fixed during the second independent review. Four new adversarial tests cover cross-task, cross-attempt, wrong-revision and post-verifier repeated-intent cases. Classify as **NO_VERIFIED_PROGRESS / suspect**, not a proven hang. A legitimate workflow may repeat the same operation. No restart or cancellation solely from this heuristic.

## ADR-03: append-only causal event envelope (ACCEPT, prototype)

An event records `schema_version=1`, canonical `event_id`, `producer_id`, positive `source_event_seq`, `run_id`, `task_id`, `attempt_id`, `lease_fence`, allowlisted `kind`, optional `effect_key` and `operation_fingerprint` as SHA256 digests, `target_revision` full Git hash, <=8 content-addressed `evidence_refs`. Maximum 4096 encoded bytes; unknown keys and raw prompts, cookies, credentials and tool arguments are rejected.

**Trust comes from an independently authenticated adapter**, never a model-supplied event flag. Correlation IDs are not authorization; SHA256 hashes alone are not evidence of correctness. Use one producer incarnation ID per process boot; its sequence is global across runs. Event ordering across producers is partial, not chronological. Durable event ingest must be atomic, deduplicating by `event_id` and `(producer_id, source_event_seq)`. Conflicting redelivery is an error, never an overwrite or trust upgrade. SQLite WAL is a **single-host** prototype, not a distributed consensus service or shared-network filesystem database.

The isolated candidate implementation + 33 offline tests are in the companion audit archive. It is not connected to the live extension, production Hermes or GitHub CI. `authoritative_task_state` remains null by design.

## ADR-04: deterministic reason precedence and recovery

| Priority | Reason | Evidence / operator action |
|---|---|---|
| 0 | EFFECT_OUTCOME_UNKNOWN | Reservation without verified matching receipt; quarantine write, independent downstream read-back, NO blind retry |
| 1 | OBSERVABILITY_GAP | Missing per-producer sequence; fetch from durable cursor; do not infer missing events |
| 2 | NO_VERIFIED_PROGRESS | Same repeated tool intent, no trusted new artifact; investigate loop, don't treat heartbeat as progress |
| 3 | POLICY_DENIED | Authenticated denial; stop, no paraphrase/permission bypass |
| 4 | RATE_LIMITED | Authenticated throttling; shared quota, jitter and Retry-After managed by official scheduler |
| 5 | UNKNOWN | Insufficient evidence; inspect authoritative task and worker health |

Retain secondary diagnoses alongside the highest-priority safety action. A stale observer process is **not** evidence the worker crashed. In a UI send bridge, distinguish accepted/prepared/submit-attempted/sent-observed/response-running/response-complete; any disconnect after clicking Send requires reconciliation before retry. MV3 worker shutdown must not erase work; Native Messaging identity and OS ACLs require review.

## ADR-05: competing GitHub PRs and single-writer ownership

| Branch/PR | Current evidence | Merge decision |
|---|---|---|
| #1 Autopilot | SQLite prototype, not deployed | Compare against upstream Runs/Kanban and retain only missing invariants |
| #3 ACP permissions | Isolated callback correction proposal | Independent authorization CI and concurrency gate |
| #4 GPT API | General Tests **failed** (7,513 passed, 29 failed, 171 skipped); log contains one API response contract failure plus numerous missing OpenAI credentials | Diagnose independently, do not merge as-is |
| #5 GPT API | General Tests cancelled | Collides with #4/#6 |
| #6 GPT API | Targeted GPT Gateway Regression passed; general Tests cancelled | Best integration candidate, NOT fully verified |
| #7 SDD | Design-only PR; general Tests cancelled | Reference architecture, not proof of deployment |
| This branch | Causal diagnostics SDD / independent proof-of-concept | No contested API or agent execution changes |

#4 has a concrete test mismatch: `test_agent_error_returns_500` expects raw "Provider failed", while code now returns a generic error with run ID. Keep production response redacted; update tests deliberately, don't disclose internal errors to satisfy old assertions.

Each of 30–50 workers has a unique producer incarnation, immutable task and requirements revision, scoped worktree, resource lease/fence at the **trusted effect adapter**, inherited parent budget, explicit approval identity and independent verification. A read-only observer never promotes a task to success. No model marks its own evidence trusted.

## ADR-06: ranked improvements (expert estimates; NOT measured results)

Weights: expected impact 35%, security 25%, upstream compatibility 20%, testability 10%, simplicity 10%; 1–5 ratings, converted to 0–100. These estimates are only prioritization hypotheses, recalibrated against measured failure-injection data.

| Proposal | Score/100 | Decision |
|---|---:|---|
| Reuse current durable Runs/Kanban / exact-SHA completion | 98 | P0 |
| Strict gateway auth + per-session approval isolation | 94 | P0 |
| Effect reservation + independent receipt reconciliation | 90 | P0 |
| Causal journal + reason/evidence projection | 89 | P1 |
| Shared 50-agent quotas + bounded fan-out | 89 | P1 |
| Progress watchdog independent of heartbeat | 87 | P1 |
| MV3 read-only status panel with native host | 67 | P2 |
| Controlled auto-fixes with external verifier | 60 | P3 |
| Duplicate distributed scheduler | 31 | REJECT |
| Unattended DOM scraping as task authority | 29 | REJECT |

## QA gates and fault matrix

Offline prototype checks: duplicate concurrent events (30 threads + two SQLite connections), sequence redelivery conflict and trust-upgrade rejection, reordered events/gap healing, producer reboot, cross-run sequence correctness, heartbeat-active repeated-intent loop, fake verifier and fake task completion, missing/mismatched external-effect ack and fence, strict metadata rejection, 50 producers x 20 events (1,000 events). **Isolated Python 3.13.5: 33/33 tests PASS**; no claim of integration, continuous monitoring or production reliability.

Unverified and REQUIRED for promotion: Python 3.11/3.12 package imports in actual Hermes; true authenticated adapter; server crash/disk-full failure gate; 100 simultaneous request/retry load, 429 storm, old CI SHA mismatch, suspended MV3 service worker, browser navigation after click, lost Native Messaging ack, wrong ChatGPT conversation, local Obsidian optimistic-hash collision, 24–72-hour synthetic soak, reboot/backup restoration and user Stop. No secrets or sensitive browser data may appear in telemetry.

## Operator incident runbook

1. Capture run/task/attempt/fence, exact branch SHA, reporter identity, wall-time observation and independent evidence IDs.
2. Read authoritative Runs/Kanban state **before** any diagnostic projection; inspect outstanding external-effect reservations.
3. Query deduplicated per-producer sequences, missing events, last independently verified artifact and repeated fingerprints.
4. Separate verified facts, hypotheses and unknowns; identify first missing acknowledgment and competing explanations.
5. Choose read-only retry, scoped isolated patch + independent review, or human decision; prohibit blind replay of unknown writes.
6. Record pre-fix and post-fix SHA, test command, CI run ID, failures and rollback. Verify persistent owner worktree separately.
7. Close incident only after exact-SHA verification and effect reconciliation; a passing unit test is never proof of deployed extension behavior.

## Evidence log — 2026-11-22

- OBSERVED: `Podtverzhdeno/hermes-agent` main remains old fork; multiple overlapping draft API PRs. #6 targeted CI green; #4 full Tests failed. The full failure log includes many missing OpenAI-key errors, and a specific API test mismatch; not all 29 failures have been independently classified.
- OBSERVED/BLOCKED: Local_WorkSpace returned `Session terminated`. The Windows extension under the historically reported `chat-launch-smoke-desktop-test/web-extension` and bridge process were **not freshly inspected**, no local files updated and no live monitoring performed.
- TESTED OFFLINE: 25 isolated diagnostic tests passed; this is a proof-of-concept only, not mainline Hermes CI or a deployed observer.
- NEXT OWNER: verify extension manifest/files SHA, actual transport and local logs after connector recovery. Integrate official task feed with authenticated producer and durable cursor **only after** upstream source parity and security review.

## Primary references

- https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md
- https://github.com/NousResearch/hermes-agent/issues/100971
- https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- https://opentelemetry.io/docs/specs/semconv/general/events/
- https://sqlite.org/wal.html
- https://docs.temporal.io/encyclopedia/retry-policies

## ADD-008: CI cancellation is not a test failure

The fork's main `.github/workflows/tests.yml` sets `concurrency.group: tests-${{ github.ref }}` and `cancel-in-progress: true`. When a second commit advances the same PR, a previous workflow can be cancelled even though no test assertion failed. Do not infer that a cancelled workflow proves a code failure, a stopped Hermes agent or successful completion.

Categorize `CI_SUPERSEDED_BY_NEW_SHA` (cancellation correlated with newer commit/run on same ref); `CI_CANCELLED_UNEXPLAINED` (cause unknown); `CI_TEST_FAILURE` (assertion failure with test ID); `CI_INFRA_FAILURE` (dependency, credential, runner, setup); `CI_SKIPPED` (not evidence); and `CI_PASSED_AT_OLD_SHA` (invalid for current head). Every category requires exact current head SHA and run ID; verify cause from logs/check metadata, not the icon color.

PR #4's general workflow had 7,513 passed, 29 failed, 171 skipped; many errors report missing OpenAI credentials, and `test_agent_error_returns_500` expects provider error text now deliberately redacted by the API. Do not restore sensitive error output simply to pass the outdated assertion. PR #6's targeted GPT Gateway Regression passed but its general run cancelled, with no full-suite green conclusion.

The dedicated observer offline CI uses `cancel-in-progress: true` to coalesce obsolete same-PR checks and avoid a 50-agent runner stampede. Distinct PR refs retain distinct concurrency groups. The latest exact-SHA successful test is the only eligible test evidence. This is a verified workflow setting and a **possible**, not universally confirmed, explanation of the cancelled runs.

## ADD-009: Durable wall-clock audit and bounded read-only timeline

The initial journal only stored monotonic receive time and observer process incarnation. That cannot reconstruct the wall-clock timeline after a workstation reboot. The hardened module now writes **server-observed UTC ISO8601** per new event, while retaining monotonic age checks solely within the active observer incarnation. A transactional SQLite schema migration adds `received_at_utc`; legacy rows are marked `unknown` (not backfilled from guesswork). A bounded `timeline(run_id, limit<=500, after_producer, after_seq)` provides metadata-only read pagination and explicit per-producer ordering; it NEVER asserts cross-producer causal order or authoritative task completion. The timeline is **not a network endpoint**; future adapters must authenticate read access and enforce privacy/retention quotas.

Four additional negative/positive tests validate timestamp presence, 2-producer cursor pagination, invalid cursor/limit input and schema migration without fabricated historic timestamps. Offline suite total: **33/33 PASS on Python 3.13.5**. GitHub CI at current exact PR SHA remains a separate independent gate; do not equate this with deployment. No production observer or browser host is active.

Important remaining privacy caveat: event string identifiers are syntactically bounded, not cryptographically pseudonymized by this module. The authenticated adapter MUST map user/session identities to opaque random identifiers before ingestion. Content-derived hashes may be dictionary-guessable; do not hash raw private prompts into event fingerprints. Prefer keyed HMAC over canonical allowlisted operation metadata when sensitive; keys must not be held in extension content scripts.
