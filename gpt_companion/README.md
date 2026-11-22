# Hermes GPT Companion — read-only observability prototype

**Status (2026-11-22):** offline journal + diagnosis only. It does not monitor a running GPT session until an authorized Hermes/provider adapter emits events. No browser DOM scraping, tool dispatch, automatic retry, external write, or autonomous approval.

See [SDD](../docs/sdd/GPT_COMPANION_SDD.md) for the full architecture, threat model, failure matrix and release gates.

## What the code actually does

- Validates a strictly allowlisted metadata-only event envelope (schema v1).
- Commits untrusted events to a local SQLite WAL journal; rejects conflicting replays and source-local sequence reuse.
- Detects missing sequences, unacknowledged effects, conflicting terminal reports, stale telemetry, no-progress heartbeats and unverified success claims.
- Computes an append-only SHA-256 chain to catch simple local corruption; **not** cryptographic non-repudiation.
- Produces a diagnostic state and recommended investigation step; **does not** mutate the Autopilot task ledger.

## Offline walkthrough

From an installed Hermes package or repository checkout:

```bash
python -m pytest tests/gpt_companion -q
python -m gpt_companion --db ./gpt-events.sqlite3 --run-id run-42 --jsonl ./events.jsonl
python -m gpt_companion --db ./gpt-events.sqlite3 --run-id run-42
```

Example `events.jsonl` (one event per line; no text, tokens or message bodies):

```json
{"schema_version":1,"event_id":"e-1","source":"gpt-adapter","run_id":"run-42","attempt":1,"sequence":1,"kind":"run.accepted","trace_id":"trace-42"}
{"schema_version":1,"event_id":"e-2","source":"gpt-adapter","run_id":"run-42","attempt":1,"sequence":2,"kind":"worker.started","trace_id":"trace-42"}
{"schema_version":1,"event_id":"e-3","source":"gpt-adapter","run_id":"run-42","attempt":1,"sequence":3,"kind":"run.reported_completed","trace_id":"trace-42"}
```

Expected diagnosis is `AWAITING_VERIFICATION`, **not** `SUCCEEDED`. Replaying the same JSONL is idempotent. Unknown/unapproved fields are rejected without logging their values.

## Important correctness boundaries

- A browser extension that displays a spinning indicator cannot prove whether an external API call succeeded. For `tool.effect_reserved` without a trusted receipt, ask the control plane to reconcile before retry.
- Fresh telemetry is not proof of process liveness; a late buffered event can arrive after a crash. Check OS supervisor and current lease separately.
- Different emitters' sequence numbers are not a global order. Carry `trace_id`, `action_id`, request/response IDs, and obtain independently authenticated receipts.
- This module accepts caller-supplied event metadata as **untrusted**. Production needs authenticated ingress, source-role authorization, durable outbox, redaction, rate limits, retention/backup policy, and verified OpenAI/GitHub webhook signatures.
- A test or GPT claim is not certified evidence. Only the independently authenticated Autopilot verifier may close a task at the exact intended revision.
- The unrelated `feat/autopilot-durable-ledger-20261122` branch owns task state and effect reservations. No duplicate ledger logic should be added here.

## Troubleshooting

| State | Action |
| --- | --- |
| `NOT_OBSERVED` | Inspect authenticated intake and observer connection |
| `TRACE_INCOMPLETE` | Replay missing source-local sequences from durable outbox |
| `RECENT_TELEMETRY` | Observe; do not infer task success |
| `ALIVE_NO_PROGRESS` | Check tool stage, budget, provider response and true process state |
| `PARTIAL_WORKER_OUTAGE` | Find the stale worker source; fresh gateway/other-worker events do not prove that worker is alive |
| `WORKER_UNRESPONSIVE` | Inspect supervisor and lease before replacing worker |
| `EFFECT_IN_FLIGHT` | Wait for authenticated receipt; never blind-retry writes |
| `NEEDS_RECONCILIATION` | Read back provider action by stable ID, reconcile in task ledger |
| `WAITING_APPROVAL` | Request exact human approval bound to action digest and expiry |
| `AWAITING_VERIFICATION` | Check independent artifacts and CI on the exact revision |
| `REPORTED_FAILED` | Use normalized reason and inspect provider/CI evidence |

### No persistent process by default

The CLI inspects a snapshot. A continuous monitor requires a separately deployed worker with startup supervision, heartbeat/outbox adapter, lock ownership and an operator kill switch. None is activated by this PR.

The checkout-only compatibility wrapper `python -m scripts.gpt_event_inspect` imports the same packaged entrypoint. Source-only import is not sufficient for installed-wheel usability; use `python -m gpt_companion`.

A run shared by multiple emitters returns `worker_sources_count` and `stale_worker_sources`. This is *diagnostic metadata* only. Source identities must be authenticated at the ingestion gateway; this offline journal cannot prove who sent an event.
