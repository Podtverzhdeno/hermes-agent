# Source-level Hermes Kanban → GPT observer parity and fencing design

**Date:** 2026-11-22. **STATUS:** SOURCE-AUDITED DESIGN; never integrated into a running Windows extension.
**Pinned upstream release:** NousResearch/hermes-agent v0.23.3, published 2026-11-20 UTC, release target `caafe5389ae585ef77387a962aee05b1bcf17029`.
**Files inspected:** `hermes_cli/kanban_db.py` blob `4e61aeece34b2c17a6e5f3aa729ddd4516cf05c5`; `hermes_cli/kanban_db_dispatch.py` blob `dc3eab65e9931961efcb1a56916f35f1ce3543cd`.
**Target fork main:** SHA `7e9100901819ee44c16b4ddcb79a6bcb7909f591`, commit timestamp 2026-04-01T18:41:32Z. The fork is not the upstream release. This document is **not** a fork upgrade plan ready to execute.

## Verified upstream invariants we should REUSE

1. `kanban_db._claim_and_open_run` (near lines 2124–2170) uses CAS on task status + `claim_lock`, inserts an owned `task_runs` record and appends a `claimed` event in the caller's DB transaction. `claim_task` wraps the operation in `write_txn`.
2. `_append_event` (near line 1846) inserts task_id, run_id, kind, **payload JSON** and integer created_at into `task_events`, within the caller's transaction. It does not emit a W3C trace envelope or authenticate external browser producers.
3. `complete_task` (near lines 2640–2738) checks live-claim ownership: `expected_run_id` or explicit operator `force=True`. It writes done status, closes run and appends completed event inside `write_txn`. New assistants must not recreate this guard from scratch.
4. `block_task` (near line 3125) writes blocked/triage routing and its event in a transaction; it distinguishes dependency, needs_input, capability and transient.
5. `kanban_db_dispatch.py` already implements heartbeat, stale/crashed-worker recovery and orphan reconciliation. Do not add an independent GPT watchdog that claims it can authoritatively rewrite task state.
6. `gc_events` (near line 4013) can delete events for done/archived tasks according to retention, while retaining certain decomposition events. An observer cursor that missed a retention interval cannot silently claim full replay.
7. Completion can call `recompute_ready` in a separate transaction after the parent completion, so a short parent-done/child-not-ready window is possible. This is not evidence of corruption.
8. `task_events` has per-board auto-increment integer `id`, task_id, nullable integer run_id, kind, JSON payload, integer created_at. It has **no** canonical event UUID, per-producer source_event_seq, source trust assertion or cryptographic content digest.

## Non-equivalent concepts that MUST NOT be conflated

| Upstream source | Proposed GPT observer field | Correct handling |
|---|---|---|
| Per-board `task_events.id` INTEGER AUTOINCREMENT | `source_event_seq` | Stable ordered cursor *only within one board DB incarnation*. Deletions and restores require loss/epoch semantics. |
| `task_events.task_id` | `task_id` | Preserve as opaque task ID plus board identity; no cross-board aliasing. |
| `task_events.run_id` nullable integer | `attempt_id` | Namespaced run identity; task-scoped events remain task-scoped, not a fake worker attempt. Canonical schema must support nullable run. |
| `tasks.claim_lock` string host:pid:UUID | `lease_fence` integer | **Not interchangeable**. Use independent monotonic per-task fence epoch or checked current_run_id plus board incarnation at every write, enforced by the trusted tool gateway. |
| `task_events.created_at` integer seconds | UTC timestamps | Informational; never global causal authority or ordering across board DBs. |
| `task_events.kind,payload` | symbolic kind and reason code | Explicit versioned mapping; refuse unknown event classes. No blind inclusion of payload JSON in telemetry. |
| `task_events.id` used to synthesize a UUID | `event_id` | Deterministic namespacing using persistent board ID + **restore/clone epoch** + event id; prove collision semantics. |
| `task_events` row transactionally appended | durable observer cursor/outbox | Need separate authenticated subscriber/outbox checkpoint and retention gap detection. A projection read is not a durable ACK. |
| Kanban `completed` event | verified artifact success | Completion was **reported by Kanban**; independent exact-SHA/receipt verifier still required for externally visible success. |

### Required adapter protocol (proposed)

1. Acquire a read-only SQLite snapshot of a named board and its durable event cursor; do not read unsafely across multiple separate DB transactions when correlating task_runs and task_events.
2. Bind a trusted local producer identity to a pinned board DB identity and epoch. A worker-provided `source` JSON field is not authenticated evidence.
3. Convert events to strictly allowlisted metadata. Any `payload` field containing user messages, summaries, tool arguments or log text is excluded by default. Use only symbolically mapped status/reason and hashes of independent receipts. This is particularly important because upstream `_append_event` stores payload JSON.
4. Define task-scoped and run-scoped events separately; do not invent a run for events whose upstream run_id is NULL. Update the proposed schema/observer before integration.
5. Attach stable event identity based on board epoch + row ID, not row ID alone. If DB is restored/cloned or a cursor is older than event retention, mark **HISTORY_GAP / BOARD_EPOCH_CHANGED**, require snapshot reconciliation and never claim uninterrupted evidence.
6. Persist the last applied source ID and adapter ACK in one local transaction with the observer's event inbox. After restart, replay from the last ACK. This is at-least-once delivery with idempotent dedup, **not** exactly-once external tools.
7. Keep task truth in Kanban. The observer emits hypotheses and evidence pointers only; no CLI `kanban_complete`, `kanban_unblock`, direct DB status writes or hidden browser control.
8. At every external tool write, use a trusted adapter to compare canonical board identity, expected current_run_id, exact claim_lock and a separate monotonic effect-fencing generation if required. Reserve effect_key durably **before** side effect. On lost reply mark UNKNOWN and use remote read-back / idempotency receipts.
9. Enforce maximum queue/backpressure and privacy defaults. If audit persistence is unavailable, high-risk side effects fail closed; read-only status may show degraded with gaps.
10. Prove rollback/restore and prune behavior with forced-crash tests. No migrations or desktop extension writes until the upstream code and local runtime are compared at exact SHA.

### Test matrix before integration

| Test ID | Setup | Accept only if |
|---|---|---|
| K-01 | Two workers claim same task | One CAS succeeds, one loses; one canonical run ID |
| K-02 | Task marked done, child recompute transaction delayed | Observer reports transient lag, never starts independent dispatcher |
| K-03 | Task-scoped event with NULL run ID | No fake worker ownership in converted envelope |
| K-04 | Board A and board B use same integer event row ID | No event ID collision thanks to scoped board identity |
| K-05 | Restore old SQLite DB then write new events at reused IDs | Epoch changes; old cursor invalidated; incident required |
| K-06 | Observer offline longer than retention, `gc_events` prunes | Detect permanent history gap, never fill with invented events |
| K-07 | Stale worker keeps old `claim_lock` after retry | Trusted gateway rejects side effects even if worker still alive |
| K-08 | Tool write commits, ACK lost and worker exits | UNKNOWN effect survives, no blind retry |
| K-09 | Malicious event payload includes user prompt/credential | Strict metadata projection drops or rejects private content |
| K-10 | CLI/REST status differs from browser panel | Kanban wins; browser status flagged stale/partial |
| K-11 | 30–100 workers produce duplicate, late and out-of-order updates | Bounded observer projection with exact source cursor; no loss asserted as success |
| K-12 | CI status green at old SHA, new commit changes adapter | Acceptance blocked until same SHA CI/receipt verifier passes |

### Engineering conclusion

The highest-value upgrade is **not** another observer or another task scheduler: it is a versioned Kanban-to-metadata adapter with replay/epoch/retention semantics and an independently fenced effect journal. The current standalone PR #16 observer is an offline candidate and explicitly does **not** yet implement a board epoch, nullable task-scoped events, persistent inbox or live producer auth. These are open, hard integration gates. Source-code audit proves the upstream's local atomic task+event write path, but not atomicity of arbitrary external tools or the owner's older fork.
