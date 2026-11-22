# Hermes ↔ GPT: SDD integration gate, observer and multi-agent reliability review

**Date:** 2026-11-22. **Status:** P0 read-only observer implemented and tested offline; **not deployed, not connected to ChatGPT or a native extension**.
**Fork baseline:** Podtverzhdeno/hermes-agent main @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591.
**Adjacent SDD:** draft PR #7 (docs/gpt_bridge/SDD.md) is a design proposal, not on main; draft PR #1 provides a *candidate* durable Autopilot ledger, but it is **not approved as a second task dispatcher**. Current upstream Hermes has an existing durable Kanban system and worker lanes. Integration must preserve exactly one authoritative task lifecycle; reuse future Autopilot components only for missing effects/receipts after a code-level parity audit.
**Evidence legend:** OBSERVED = code/metadata inspected at a specific revision; TESTED-OFFLINE = isolated deterministic checks; PROPOSED = unimplemented; BLOCKED = source unavailable.

## 1. Competing API drafts must not be stacked blindly

At review time seven open draft PRs exist. PR #4, #5, #6 each independently modifies gateway/platforms/api_server.py from main. A single integration maintainer must select one initial implementation, port independently valuable behavior through explicit contract tests, and revalidate CI at the final merge candidate SHA.

| PR | Observed behavior | Unresolved gate |
|---|---|---|
| #4 GPT bridge diagnostics | Inflight duplicate returns 409; payload mismatch 422; completed LRU can evict unexpired key | Define retry/conflict semantics, reject effects with unknown outcome |
| #5 atomic diagnostics | Inflight duplicate joins pending task; completed LRU may evict unexpired key | Reuse after eviction or restart cannot promise exactly-once |
| #6 GPT observability | Bounded single-flight, SSE failure path; **later revision now quarantines failed keyed operations as unknown and classifies reported agent failure** | Explicit session-load exception still becomes empty history; no durable cross-process effect fence |
| #7 GPT SDD | Single ledger + read-only extension/causal event designs | Not implemented, actual local extension uninspected |
| #1 Autopilot | Proposed durable task/effect ledger and tests | **Must not compete with upstream Kanban**; isolate effect/approval/evidence semantics after upstream parity review |
| #3 ACP safety | Scoped permission callback changes | Independent executor race and security tests required |

**CODE FINDING API-01 (HISTORICAL, fixed in newer PR #6 revision):** Earlier _IdempotencyCache._on_done removed a failed key, permitting a duplicate attempt after a possibly committed external effect. **Rechecked** gateway/platforms/api_server.py blob 2baea1ec40d381440b4df7d77794b16469bbe5b6: failed keyed operations now retain state outcome_unknown and retries raise IdempotencyUncertainOutcome. Good local fix; still not durable after process restart and does not reconcile external effects. Independent crash/restart tests remain necessary.

**CODE FINDING API-02 (OBSERVED, PR #6 and baseline):** Explicit X-Hermes-Session-Id session-read exception is logged and history becomes an empty list. This masks continuity failure as a new context. Fail closed with session_store_unavailable for explicit continuation and add negative DB tests.

**CODE FINDING API-03 (HISTORICAL, fixed in newer PR #6 revision):** Earlier error-valued runner results could be reported as a successful assistant content. Recheck found _agent_run_outcome and AgentReportedFailure paths in chat, SSE and Responses. Verify their test coverage independently on the current PR head; do not assert runtime validation from code inspection alone.

**BLOCKED-01:** Local_WorkSpace returned Session terminated, fallback connector HTTP 429. This is an observability-channel failure, **not proof that Hermes or the browser extension is stopped**. The previously identified local chat-launch-smoke-desktop-test/web-extension is not present in the inspected fork, so its actual manifest, permissions, native host and browser runtime remain unverified.



## 1a. Recheck after simultaneous agent activity (important correction)

The repository changed during this review: draft PRs #8–#15 appeared after the original seven were inspected. Drafts #8 (hermes_gpt_bridge), #9 (gpt_bridge/observability), #12 (gpt_companion/journal), and this PR #16 (gateway/gpt_bridge_observer) **each implement a different event schema and observer strategy**. These must not all be activated as authoritative event sources; event IDs, sequence partitioning and status vocabulary would diverge. PR #14 introduced a coordination gate, and #15 changes CDP browser cleanup. Convene **one integration/schema owner** and issue a canonical contract (producer incarnation, version, event ID, per-source seq, task/run/attempt/fence, effect receipt and trust provenance) plus migration adapters. Prefer merging only components that satisfy a shared contract and independent CI/fault tests. This PR intentionally remains draft and serves as a strict parser/fault-test candidate, not a replacement for PR #12's persistent journal or upstream Kanban. PR #1 is a candidate for subordinate durable-effect primitives only.

Correction of evidence precedence: earlier findings about PR #6 are **revision-specific**, not permanently true. Rechecks must cite latest blob/commit and distinguish repaired behavior from remaining unverified crash windows.


### Architecture correction from independent upstream verification

The official Hermes documentation describes a durable Kanban multi-agent board and worker lanes, with the board DB as the shared task authority. The latest GitHub release API returned **v0.23.3** (published 2026-11-20 UTC). The owner's fork main still points to a much older April commit, and these upstream capabilities are not present there. **Integration order is now:** upgrade/parity diff and classify collisions against upstream Kanban → agree canonical lifecycle and event contract → implement only missing effect reservations, approval/fences and observer adapters → verify before enabling automatic repair. Do not infer that the current fork already has the Kanban kernel, and do not merge stale fork fixes without a porting review.

Sources:
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
- https://api.github.com/repos/NousResearch/hermes-agent/releases/latest

**New source-audit issue for PR #14:** Its coordination script's CAPABILITY_PATHS gpt-observer tuple detects gpt_bridge/, gpt_extension/, gpt_companion/ and gateway/gpt_bridge*, but does **not** detect hermes_gpt_bridge/ introduced in PR #8. The naming difference can under-report semantic overlap. The coordination gate must normalize capability IDs, not just path prefixes; a file collision audit alone also misses incompatible shared event schemas.

## 2. Implemented P0 observer: deliberately non-authoritative

Files:
- gateway/gpt_bridge_observer.py: strict metadata-only v1 event-envelope validator and bounded causal-sequence advisory observer.
- scripts/gpt_bridge_observe.py: offline standard-input JSONL probe, emitting only aggregate counters and uncertainty labels.
- tests/gateway/test_gpt_bridge_observer.py: 45 offline unit/parameterized checks including 30 producers × 50 out-of-order events, invalid fields, bounded resource use and redaction.

Accepted v1 envelope uses per-incarnation producer_id and source_event_seq, unique event_id, run/task/attempt IDs, UTC timestamps, W3C-shape trace and span IDs, optional causation/fence/effect metadata, a finite event vocabulary, allowlisted hashes as evidence. Unknown fields, raw prompt or credentials, invalid kinds, future schemas and oversized messages fail closed without copying raw content into diagnostic output.

Ordering is **per producer**: thirty producers may all emit sequence 1. Seeing sequence 3 before 1 and 2 produces a *suspected gap*, not a dead-worker decision. The observer resolves gaps when late events arrive. A duplicate event ID or sequence collision is rejected. A parent causation reference missing within the bounded recent-event window is unresolved, not fabricated. Wall-clock time is metadata, never the authority for cross-process order.

The observer is in-memory, not thread-safe, not durable, not an authenticated event source, not a lease verifier, not a background monitor, and never retries an external tool. It cannot prove task completion or effect outcome. The real ledger must persist events atomically, keep a durable cursor/outbox, authorize producers and replay lost events on restart before the observer is used live.

### Reproduction

From the repository root, run:

    python -m pytest tests/gateway/test_gpt_bridge_observer.py -q
    python scripts/gpt_bridge_observe.py < trusted_metadata_events.jsonl

**TESTED-OFFLINE:** 45 tests passed in an isolated interpreter and compile checks passed. GitHub CI, real Windows extension, Native Messaging host, live gateway integration and 24-hour soak are **not** covered by this result.

## 3. Production invariants and crash boundaries

1. One source of truth: **upstream Hermes Kanban**, once ported and verified at a pinned SHA, owns task/worker state, dispatch and work lanes. Draft Autopilot PR #1 must *not* become a second top-level task queue. Add durable effects, scoped approval, budgets and fencing as integrated Kanban extensions or explicitly subordinate modules. Browser panel and logs only display observations.
2. A task state transition and its event outbox entry must commit in one DB transaction. Unique event ID and per-producer sequence protect against replay; producer identity must be authenticated.
3. Tool gateway must validate approval scope, active lease fence, expected revision and effect key **immediately before every external write**.
4. Reserve each external effect durably before calling the provider. Crash after the provider write and before the ACK results in NEEDS_RECONCILIATION, not FAILED and not an automatic new write.
5. An API request/stream transport close, a missing heartbeat, a lost MCP session, a stopped MV3 worker and a terminated task are distinct facts. Each requires an independent evidence path.
6. With explicit session continuation, read errors must not become empty history; same-session writes from parallel agents require version checks.
7. Global provider 429 cooldown, parent budgets, lease epochs and path locks must be shared among 30+ agents. Do not let retries multiply independently by SDK/agent/job layer.
8. P0 single-host SQLite WAL is not a distributed lock service; it must not be placed on a network filesystem. Measure writer contention and backups before multi-host scale.
9. A verifier must check exact artifact digest / CI SHA / provider receipt. The implementing agent's own success text is not independent evidence.
10. Logging is allowlisted metadata only. No raw prompts, user messages, tool parameters, cookies, Authorization headers, private filesystem paths or hidden model reasoning in standard logs.
11. Native Messaging (if chosen) requires allowed extension ID, OS ACLs, pairing, schema/size bounds and anti-replay. ChatGPT web DOM is not a supported durable agent queue.
12. Privileged mutation must fail closed if mandatory audit persistence fails. Read-only observability may degrade with explicit bounded loss counters.

## 4. Failure-injection matrix (release gates, not tests already passed)

| Injection | Expected verified behavior |
|---|---|
| 30 producers begin at seq=1 | independent cursors; no global conflict |
| Event seq 3 arrives before 1 and 2 | gap suspected then resolved, never auto-stop |
| Same event_id / producer sequence collision | reject; preserve evidence of inconsistency |
| Producer restart reuses ID + seq | stale or collision, require new producer incarnation |
| Raw prompt/access token or >4 KiB event | reject, no payload in normal output |
| Observer disconnected while worker continues | OBSERVER_UNAVAILABLE; task ledger remains authoritative |
| Provider wrote remotely but HTTP reply lost | NEEDS_RECONCILIATION, receipt read-back before retry |
| Stale lease worker reaches tool write | reject at tool gateway despite worker heartbeat |
| SSE partial output then agent exception | terminal failure or incomplete, never verified success |
| Two writers modify one Obsidian note/branch | expected SHA check, conflict/rebase, no last-write-wins |
| Host reboot between reservation and ACK | replay ledger, reconcile unknown outcomes |
| CI green for previous HEAD | reject as CI_REVISION_MISMATCH |
| Parent cost or deadline exhausted | stop all child retries/dispatch with recorded reason |
| Collector down before R2/R3 mutation | fail closed and create reviewable incident |

## 5. Ranked improvement options (unmeasured design estimates)

Weighted axes: impact 30%, root-cause visibility 25%, multi-agent safety 25%, ease 10%, risk reduction 10%. Each axis scores 1–5. Totals computed from those weights; priority also depends on prerequisites.

| Initiative | I | V | S | E | R | Score /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Transactional outbox + persisted effect outcomes | 5 | 5 | 5 | 2 | 5 | 4.70 | P1, integrate with Kanban; PR #1 only a candidate source |
| Read-only protocol and causal gap diagnostics | 4 | 5 | 4 | 5 | 4 | 4.35 | P0 tested offline here |
| Fenced effects + provider receipt reconciliation | 5 | 5 | 5 | 2 | 5 | 4.70 | P1 after durable reservation |
| Exact SHA + independent CI/evidence verifier | 5 | 5 | 5 | 4 | 5 | 4.90 | P1 integration gate |
| MV3 durable cursor + pinned native messaging | 4 | 4 | 4 | 3 | 5 | 4.00 | P2 after real manifest audit |
| Shared quotas, fair queue and parent retry limits | 5 | 4 | 5 | 3 | 4 | 4.45 | P1 scale gate |
| Session CAS and fail-closed history restore | 5 | 5 | 5 | 3 | 5 | 4.80 | P1 before parallel writes |
| AI root-cause hypothesis, never final authority | 3 | 3 | 2 | 4 | 3 | 2.85 | P3 advisory |
| Unlimited automatic retries / unreviewed self-merge | 2 | 1 | 1 | 2 | 1 | 1.40 | REJECT |

## 6. Collaboration contract for dozens of agents

A0 coordinator grants a bounded, revisioned task lease with a path write set and epoch. Agent ACKs scope and immutable requirements revision, edits only isolated worktree, produces patch + tests + log + PR. Independent verifier checks exact SHA and external effect receipts. One integrator owns overlapping gateway changes. Leases expire with fencing, not merely absence of ChatGPT text; successor reads durable checkpoint and unknown effects, not predecessor self-summary. Two agents editing the same file must rebase/replan rather than last-write-wins. Human approval remains necessary for privilege expansion, billing and irreversible effects.

Every incident log record must contain: incident ID; project/task/run/attempt IDs; source and target revisions; last durably acknowledged event; missing sequence/observation gaps; possible and verified causes distinguished; approval/effect ambiguity; next safe action; patch SHA; tests and CI at same SHA; remaining unknowns. An LLM explanation is a hypothesis until externally supported.

## 7. Rollout sequence and stop criteria

P0: offline schema/sequence validator, no new transport or write authority.
P1: upgrade and validate upstream Kanban lifecycle first; authenticated canonical ledger subscription, cursor replay, safe source audit, redacted operator timeline. No second competing dispatcher.
P2: only after access to the real Windows extension, inspect MV3/native-host manifest, pairing and lifecycle; test suspension/restart.
P3: one sandbox worker with durable effect reservations, fencing and crash testing before any tool write automation.
P4: 30-worker contention, rate limit, file collision, host reboot, multihour synthetic soak and measured SLO denominators.
P5: guarded auto-repair limited to known safe operations, operator go/no-go for anything irreversible.

Any unknown external effect, unverified approval, audit outage before privileged writes, unsupported schema, stale fence, conflicting file revision or uncertain auth boundary **stops mutation and produces an operator-visible incident**. No production activation is justified merely by these offline tests.

## 8. Primary references (not an exhaustive literature claim)

- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- OpenTelemetry GenAI conventions: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- SQLite WAL constraints: https://www.sqlite.org/wal.html
- OpenAI Responses streaming: https://developers.openai.com/api/reference/resources/responses/streaming-events
- OWASP AI Agent security: https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
- GitHub SHA-based checks: https://docs.github.com/en/rest/checks/runs

**Engineering conclusion:** reconstructing causality and making missing evidence explicit is feasible as a read-only offline component. True atomicity and safe self-repair are separate, harder integration projects requiring durable controls and independent evidence.

## 9. Independent parser self-audit

A changed event with the same event ID and source sequence is **not** a valid replay. The first offline version compared only IDs/sequence and thus could not distinguish a modified payload from identical delivery. This was found in a second review and repaired: the observer now records SHA-256 of the entire validated canonical event alongside identity, rejects payload collisions and has an explicit regression test. The CLI also rejects duplicate JSON object keys, which otherwise could change the apparent event meaning using last-key-wins parsing. **45 tests pass in an isolated Python environment**; these claims are limited to the standalone observer, not end-to-end Hermes/GPT or Windows. For an authenticated durable observer, persist the digest in a transactional event store rather than rely on this bounded in-memory cache.

## 10. Source-matched adversarial verification (latest offline facts)

New regression classes were found and fixed **in this candidate's own observer**:
- Causal gap starvation: the first implementation refused valid later events after a full cache of missing-parent links. The repaired bounded reverse child→parent index removes unresolved links on eviction and never conflates incomplete evidence with observer death.
- Causation cycles: even correct UUIDs/sequence numbers can encode A→B→A or A→B→C→A. The repaired bounded ancestor walk rejects cycles visible within retained evidence *before* committing an event; cycles beyond history are **unknown**, never certified absent.
- Concurrency: cursor updates and snapshots are now guarded by one process-local lock; tests use 30 threads and 3,000 events.
- Input ambiguities: replay ID plus changed full payload is rejected using canonical SHA-256, and duplicate JSON keys are rejected by the CLI.

**Current isolated test result:** 45/45 passed plus Python compile checks. A dedicated per-PR GitHub Actions workflow now runs the same contract independently. This is not a claim about a native browser extension, authenticated producer, persistent outbox or live external effects.

### Synthetic 100-agent stress (local environment; informational, not SLA)

| Case | Producers | Events | Threads | Elapsed | Observed throughput | Bounded recent cache |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic shuffle in 8-event batches, 1000 each | 100 | 100,000 | 1 | 2.246 s | 44,533 events/s | 8,192 |
| Ordered events, 500 each, 32-thread pool | 100 | 50,000 | 32 | 1.589 s | 31,467 events/s | 8,192 |

Both tests ended with 100 independent producer cursors, zero pending sequence gaps and no rejected events. Shared-process peak RSS measured around 99–105 MiB **including Python interpreter and imported Hermes modules**; this is not observer-only heap usage. These numbers came from one local CPU/process run, no persistent storage, no browser, no provider delays, no cryptographic source auth and no live network; therefore **they must not be used as production capacity promises**. Measure confidence intervals, tail latency, crash recovery and data loss under a production-like host before deciding concurrency or SLA limits.

### CI gate and evidence integrity

Earlier full-suite GitHub job [45015318217](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45015318217) reported **28 failing / 7,543 passing / 171 skipped** outside this observer's tests, including missing mocked OpenAI credentials, Codex fallback expectations and three 30-second tool-read timeouts. A baseline run on the same environment must determine which are pre-existing; do not label all as unrelated regressions merely because filenames differ. Do not add real provider secrets to unit CI and do not disable those general tests. The dedicated 45-case observer contract is an additional *component gate*, while the overall suite stays an independent release gate.

**Decision:** continue keeping this PR draft until task/observer schema convergence, upstream Kanban parity, actual extension source/runtime E2E, crash/restore/fencing and full-suite green or explicitly approved baseline exception. The purpose is to prevent a diagnostic subsystem from creating new failures or false success signals.
