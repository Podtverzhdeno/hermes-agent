# Hermes ↔ GPT: SDD integration gate, observer and multi-agent reliability review

**Date:** 2026-11-22. **Status:** P0 read-only observer implemented and tested offline; **not deployed, not connected to ChatGPT or a native extension**.
**Fork baseline:** Podtverzhdeno/hermes-agent main @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591.
**Adjacent SDD:** draft PR #7 (docs/gpt_bridge/SDD.md) is a design proposal, not on main; draft PR #1 owns the future durable Autopilot task/effect ledger.
**Evidence legend:** OBSERVED = code/metadata inspected at a specific revision; TESTED-OFFLINE = isolated deterministic checks; PROPOSED = unimplemented; BLOCKED = source unavailable.

## 1. Competing API drafts must not be stacked blindly

At review time seven open draft PRs exist. PR #4, #5, #6 each independently modifies gateway/platforms/api_server.py from main. A single integration maintainer must select one initial implementation, port independently valuable behavior through explicit contract tests, and revalidate CI at the final merge candidate SHA.

| PR | Observed behavior | Unresolved gate |
|---|---|---|
| #4 GPT bridge diagnostics | Inflight duplicate returns 409; payload mismatch 422; completed LRU can evict unexpired key | Define retry/conflict semantics, reject effects with unknown outcome |
| #5 atomic diagnostics | Inflight duplicate joins pending task; completed LRU may evict unexpired key | Reuse after eviction or restart cannot promise exactly-once |
| #6 GPT observability | Bounded single-flight without evicting active keys; SSE exception path sends error rather than fake stop | Failure evicts idempotency entry; session-load error becomes empty history; inspect error-valued agent result |
| #7 GPT SDD | Single ledger + read-only extension/causal event designs | Not implemented, actual local extension uninspected |
| #1 Autopilot | Proposed durable task/effect ledger and tests | Not production execution/lease enforcement |
| #3 ACP safety | Scoped permission callback changes | Independent executor race and security tests required |

**CODE FINDING API-01 (OBSERVED, PR #6):** _IdempotencyCache._on_done removes a key when the task raises. A subsequent request with the same key can rerun the computation, including external effects that may already have committed before an exception. No process-local cache can prove an external effect did not happen. If outcome is uncertain, create a durable NEEDS_RECONCILIATION record, perform independent read-back, do not blindly retry.

**CODE FINDING API-02 (OBSERVED, PR #6 and baseline):** Explicit X-Hermes-Session-Id session-read exception is logged and history becomes an empty list. This masks continuity failure as a new context. Fail closed with session_store_unavailable for explicit continuation and add negative DB tests.

**CODE FINDING API-03 (OBSERVED, PR #6):** The non-streaming code may take result["error"] as a successful assistant content with finish_reason=stop or Responses status=completed; require explicit agent-failure classification and regression tests.

**BLOCKED-01:** Local_WorkSpace returned Session terminated, fallback connector HTTP 429. This is an observability-channel failure, **not proof that Hermes or the browser extension is stopped**. The previously identified local chat-launch-smoke-desktop-test/web-extension is not present in the inspected fork, so its actual manifest, permissions, native host and browser runtime remain unverified.

## 2. Implemented P0 observer: deliberately non-authoritative

Files:
- gateway/gpt_bridge_observer.py: strict metadata-only v1 event-envelope validator and bounded causal-sequence advisory observer.
- scripts/gpt_bridge_observe.py: offline standard-input JSONL probe, emitting only aggregate counters and uncertainty labels.
- tests/gateway/test_gpt_bridge_observer.py: 38 offline unit/parameterized checks including 30 producers × 50 out-of-order events, invalid fields, bounded resource use and redaction.

Accepted v1 envelope uses per-incarnation producer_id and source_event_seq, unique event_id, run/task/attempt IDs, UTC timestamps, W3C-shape trace and span IDs, optional causation/fence/effect metadata, a finite event vocabulary, allowlisted hashes as evidence. Unknown fields, raw prompt or credentials, invalid kinds, future schemas and oversized messages fail closed without copying raw content into diagnostic output.

Ordering is **per producer**: thirty producers may all emit sequence 1. Seeing sequence 3 before 1 and 2 produces a *suspected gap*, not a dead-worker decision. The observer resolves gaps when late events arrive. A duplicate event ID or sequence collision is rejected. A parent causation reference missing within the bounded recent-event window is unresolved, not fabricated. Wall-clock time is metadata, never the authority for cross-process order.

The observer is in-memory, not thread-safe, not durable, not an authenticated event source, not a lease verifier, not a background monitor, and never retries an external tool. It cannot prove task completion or effect outcome. The real ledger must persist events atomically, keep a durable cursor/outbox, authorize producers and replay lost events on restart before the observer is used live.

### Reproduction

From the repository root, run:

    python -m pytest tests/gateway/test_gpt_bridge_observer.py -q
    python scripts/gpt_bridge_observe.py < trusted_metadata_events.jsonl

**TESTED-OFFLINE:** 38 tests passed in an isolated interpreter and compile checks passed. GitHub CI, real Windows extension, Native Messaging host, live gateway integration and 24-hour soak are **not** covered by this result.

## 3. Production invariants and crash boundaries

1. One source of truth: future Autopilot controls task state, durable effects, approvals, budgets, ownership and fences. Browser panel and logs only display observations.
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
| Transactional outbox + persisted effect outcomes | 5 | 5 | 5 | 2 | 5 | 4.70 | P1, ledger owner PR #1 |
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
P1: authenticated ledger subscription, cursor replay, safe source audit, redacted operator timeline.
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
