# Hermes GPT Companion — read-only observability prototype

**Status (2026-11-22):** offline journal + diagnosis only. It does not monitor a running GPT session until an authorized Hermes/provider adapter emits events. No browser DOM scraping, tool dispatch, automatic retry, external write, or autonomous approval.

See [SDD](../docs/sdd/GPT_COMPANION_SDD.md) and [agent mandate](../docs/sdd/GPT_COMPANION_AGENT_MANDATE.md) for the full architecture, threat model, failure matrix and release gates.

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
| `CLOCK_SKEW_DETECTED` | Check server clock/time sync; do not diagnose a dead worker from invalid timestamps |
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

## Opt-in read-only status watcher (NOT a live GPT connector)

The watcher polls this local journal; it does **not** subscribe to a browser or provider, and no process is installed or started automatically. It records changed diagnoses in a **separate** SQLite status DB for restart-safe audit and prints each new transition once per DB fingerprint. A causal `event_position` watermark rejects late stale observer decisions, including after upgrading an older status DB. The status DB is not trusted task/effect evidence.

```bash
# One read-only snapshot of up to 500 run IDs (default one cycle)
python -m gpt_companion.watch --db ./gpt-events.sqlite3 --status-db ./watch-history.sqlite3 --all

# Explicit opt-in local watcher; must be supervised/stopped by the operator
python -m gpt_companion.watch --db ./gpt-events.sqlite3 --status-db ./watch-history.sqlite3 --all --interval 10 --max-cycles 0
```

The process prints only state transitions. A crash between persisting an alert and printing it means stdout can miss a line; the durable `transitions` table still contains the event. Neither polling interval nor event freshness proves that the user's GPT account/browser is alive. There is no external action, retry, repair, webhook, push notification, or auto-approval path.


## Дополнительные защитные инварианты (проверены offline)

- Поздние события старого attempt могут выявить **незавершённые внешние эффекты** после запуска нового worker; вывод `NEEDS_RECONCILIATION` имеет приоритет перед «новый worker жив».
- Cross-source `effect_acknowledged` или `approval.resolved` не доказывает причинность; дублирующиеся reservations/terminal reports нельзя считать завершением.
- История и диагностические запросы ограничены: по умолчанию 10 000 events текущей попытки и 10 000 старых effect-событий. Превышение — `TRACE_WINDOW_LIMIT_EXCEEDED`, без частичного успешного результата. `StatusWatch.history(limit=1000)` возвращает только последние состояния.
- `worker.stopped` в multi-worker run является событием **одного worker**, не всей задачи.

Локальный тест `python -m pytest tests/gpt_companion -q`: **74 passed** (Python 3.13.5); реальная GPT-телеметрия, авторизованный ingestion, long-running deployment и GitHub CI на финальном SHA **не подтверждены**.
