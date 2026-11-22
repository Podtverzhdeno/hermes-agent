# Architecture / runtime protocol — GPT ↔ Hermes

**Status**: design proposal, 2026-11-22. No implementation claim for the components described here.

## A. Causal chain

```text
User / GPT client / Chrome extension
       | request_id, transport, origin, capability
       v
Authenticated ingress (origin + token scope + request size + rate limits)
       | validate and persist operation command
       v
Operation ledger (SQLite local prototype; Postgres for multi-host deployment)
       | outbox (same transaction), idempotency, owner epoch
       +--> tracing/metrics pipeline (derived, never source-of-truth)
       v
Per-session ordered scheduler --- global fair capacity limiter
       | claimed step, fencing epoch, deadline
       v
Hermes AIAgent adapter -- delegate/subagent -- tools
       |  tool intent / approval / dispatch / result / verification
       +--> human approval inbox (separate WAITING_APPROVAL)
       +--> external API / local browser / CDP / MCP
       v
Delivery outbox -> user/GPT client (dedup at receiver when possible)
       v
Evidence verifier -> final state + explanation
```

The existing `gateway/platforms/api_server.py`, `hermes_state.py`,
`tools/process_registry.py`, and `tools/delegate_tool.py` remain execution
substrates. Avoid reimplementing session persistence or tool dispatch.
Introduce the ledger behind an opt-in feature flag; do not append diagnostic
tokens to the LLM's cached system prompt.

## B. Operation state machine

```text
RECEIVED -> VALIDATED -> QUEUED -> CLAIMED -> RUNNING
                 |                     |       |
                 v                     v       +-> WAITING_APPROVAL -> QUEUED
               REJECTED        LEASE_EXPIRED   +-> WAITING_EXTERNAL -> QUEUED
                                               +-> RETRY_SCHEDULED -> QUEUED
                                               +-> BLOCKED_DEPENDENCY -> QUEUED
                                               +-> STALLED -> NEEDS_RECONCILIATION
                                               +-> SUCCEEDED
                                               +-> FAILED
                                               +-> CANCELLED
                                               +-> NEEDS_RECONCILIATION
```

There is no general `STALLED -> RUNNING` shortcut. A monitor may detect
staleness but must reconcile in-flight external effects before attempting
another dispatch. `CANCEL_REQUESTED` is an event, NOT proof of cancellation.
Every transition is version-checked and accompanied by an append-only event.
Terminal states are immutable except an audited operator correction to a new
linked operation, not retroactive rewriting.

### Step-level status versus operation-level status

An operation may be RUNNING while one step is WAITING_APPROVAL and another is
COMPLETED. A parent must not infer completion from the last child update.
A child must send an explicit parent-ack carrying its step ID and digest.
Dependency DAG completion is by acknowledged outputs, not a natural-language
claim of 'done'. A terminal operation has no unaccounted open tool intent.

## C. Durable schema proposal (SQLite prototype)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE operations (
  operation_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  state TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  claimed_by TEXT,
  lease_epoch INTEGER NOT NULL DEFAULT 0,
  lease_expires_ms INTEGER,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE steps (
  step_id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES operations(operation_id),
  parent_step_id TEXT,
  state TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0,
  effect_key TEXT,
  owner_agent_id TEXT,
  FOREIGN KEY (parent_step_id) REFERENCES steps(step_id)
);

CREATE TABLE operation_events (
  event_id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES operations(operation_id),
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  state_from TEXT,
  state_to TEXT,
  reason_code TEXT,
  severity TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  lease_epoch INTEGER,
  trace_id TEXT,
  span_id TEXT,
  redacted_payload_json TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  UNIQUE (operation_id, seq)
);

CREATE TABLE delivery_outbox (
  outbox_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE REFERENCES operation_events(event_id),
  destination TEXT NOT NULL,
  state TEXT NOT NULL,
  send_attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_ms INTEGER NOT NULL
);

CREATE TABLE external_effects (
  effect_key TEXT PRIMARY KEY,
  step_id TEXT NOT NULL REFERENCES steps(step_id),
  kind TEXT NOT NULL,
  intent_digest TEXT NOT NULL,
  provider_request_id TEXT,
  dispatch_at_ms INTEGER,
  observed_at_ms INTEGER,
  verification_ref TEXT,
  state TEXT NOT NULL
);

CREATE INDEX idx_ops_recovery ON operations(state, lease_expires_ms);
CREATE INDEX idx_outbox_ready ON delivery_outbox(state, next_attempt_ms);
CREATE INDEX idx_events_time ON operation_events(created_at_ms);
```

Operationally important points:
- All SQL arguments must be bound parameters, no SQL constructed from model output.
- A single local SQLite writer serializes commits; WAL improves reader/writer concurrency but does not permit unlimited writers.
- Prefer `BEGIN IMMEDIATE` for short read-modify-write transactions and bounded busy retries with jitter. Never hold a transaction across LLM, browser, filesystem, or network calls.
- Store event payload metadata only: hashes, safe categorical attributes and encrypted references. Default is no raw prompts/outputs. No cookies/session tokens in tables.
- Schema migration must be transactional, versioned and rollback-tested. Backups must be consistent snapshots, not blind copies of active WAL files.
- Use per-profile DB under `get_hermes_home()`; for multi-host transition to a central transactional store (Postgres) rather than SQLite on shared network filesystem.
- Event retention, erasure and archival require an explicit privacy policy. 'Append-only' is an application invariant, not permission to retain personal data forever.
- `UNIQUE(tenant_id,idempotency_key)` enforces durable request identity. A mismatched `payload_digest` is an explicit `409`, not a new operation.

## D. Atomic claim / fencing example

All write statements below belong to **one DB transaction** with optimistic
revision checks:

```sql
BEGIN IMMEDIATE;
UPDATE operations
SET claimed_by = :worker,
    lease_epoch = lease_epoch + 1,
    lease_expires_ms = :now_ms + :lease_ms,
    state = 'CLAIMED',
    version = version + 1,
    updated_at_ms = :now_ms
WHERE operation_id = :operation_id
  AND version = :expected_version
  AND state IN ('QUEUED', 'RETRY_SCHEDULED')
  AND (lease_expires_ms IS NULL OR lease_expires_ms < :now_ms);
-- Require changes() = 1; otherwise rollback and retry a fresh read.
-- Read new lease_epoch. Append OP_CLAIMED event with next per-op seq.
-- Append outbox record linked to the same event.
COMMIT;
```

Renewal requires `claimed_by = :worker AND lease_epoch = :epoch`.
Every subsequent mutation requires the same epoch AND version. Expired owners
cannot commit results. **Fencing the ledger alone cannot prevent an already
dispatched external effect**. Either: pass epoch/idempotency to a provider that
enforces them; dispatch exclusively through a fenced broker; or mark the step
NEEDS_RECONCILIATION and require read-after-write verification.

Heartbeat is not a proxy for meaningful progress. Track separately:
- `last_agent_heartbeat`: worker liveness.
- `last_step_progress`: successful new evidence or acknowledged state.
- `last_provider_byte`: network transport activity.
- `last_operator_action`: approvals or cancellations.
- `deadline_at`: independent total-budget enforcement.

A worker sending the same heartbeat forever is alive but may be STALLED.
Alerting must not conflate idle-by-design with genuinely stuck.

## E. Effect protocol and retries

1. Validate capability, origin, tenant, actor, branch/version and budget.
2. Persist `EFFECT_INTENT_CREATED` + effect key derived from operation/step
   **before** invoking external tools.
3. Where supported, use provider idempotency key; persist request ID and a
   redacted receipt; never persist access credentials.
4. Persist `EFFECT_DISPATCHED`; provider timeout means `EFFECT_UNKNOWN`,
   not `EFFECT_FAILED`.
5. Probe provider read-only status by effect key/request ID.
6. If verified applied, emit `EFFECT_VERIFIED`; otherwise either retry only
   when safety is proven, or request operator reconciliation.
7. Persist terminal step event + outbox record in the same transaction.
8. A delivery consumer may resend; the recipient should dedup event ID.

Retry policy is a **typed** decision:
- Automatic retry: DNS/transient network, 429 honoring Retry-After, 503,
  known idempotent read, or provider-confirmed not-applied write.
- Do not blindly retry: login challenges, approvals, conflicting writes,
  changing DOM selectors, malformed contract responses, unknown side effects,
  budget exhaustion, lost authorization, or auth errors.
- Use exponential jitter, total attempt budget, deadline and circuit breaker;
  a retry is not a new business operation.

## F. Session and agent ordering

The scheduler serializes mutations within the **same external session**.
Read-only subtasks can run concurrently; all writes require a session lease.
Independent sessions can execute concurrently under per-tenant fair quotas.

Parent agents are coordinators, not unrestricted superusers. A parent may
delegate only the intersection of its granted capabilities and child policy.
The child receives immutable `policy_version`, `context_ref`, `step_id`,
and a bounded budget, not the parent's credentials or raw log history.
Cross-agent files have owner labels; artifacts use a content digest.
Conflicting changes become isolated PRs, never best-effort overwrite.

## G. Optional browser extension boundary (not yet verified in this repo)

```text
untrusted page / content script
      |
      | typed command, sender validation
      v
MV3 service worker (ephemeral, not a durable job runner)
      |
      | allowed_origins + permission checks
      v
native messaging host (allowlisted extension ID; mutual challenge)
      |
      | authenticated local transport
      v
Hermes broker / operation ledger
```

MV3 workers may suspend and restart; keep only transient UI context there.
Persist operations in Hermes ledger, then reconcile using stable operation
IDs on reconnect. Chrome `storage.local` is not a transactional business
ledger and `storage.session` is not crash-durable. Native Messaging is not
by itself an authenticated privileged IPC channel. Validate `sender` on
every message, keep secrets in native host only, and require explicit human
approval for destructive or external effects. If a page is navigated or
closed, report `BROWSER_CONTEXT_LOST`, do not infer success.

## H. Reconcile algorithm (pseudocode)

```text
for operation with expired lease and nonterminal state:
    claim_reconciliation_epoch_by_CAS()
    enumerate open step effects and their durable intent keys
    if effects have unverified dispatch:
        perform provider read-only lookup
        if confirmed applied: persist receipt and advance
        elif confirmed absent and idempotent: requeue with bounded retry
        else: NEEDS_RECONCILIATION + alert + frozen evidence
    elif WAITING_APPROVAL and approval not expired: preserve waiting state
    elif cancellation requested: propagate and verify termination
    else: requeue only if step restart semantics are safe
```

A watchdog that merely restarts dead workers can produce duplicate external
effects; recovery must reconcile effects first.

## I. Compatibility notes

- `/v1/chat/completions` non-streaming currently has **in-process** cache;
  it is not a durable ledger and cannot guarantee no duplicates on restart.
- Streaming cannot be treated as idempotent on an HTTP-response cache:
  persist event sequence/cursor, support reconnection and terminal receipt.
- Existing `ResponseStore` uses SQLite `check_same_thread=False` without an
  explicit store lock; concurrent access must be assessed before reuse.
- Keep provider prompt cache stable; add telemetry as out-of-band callback,
  not injected system messages.
- Authentication header, CORS, origin checks and host binding are distinct:
  an allowed browser origin must not automatically grant a business capability.
