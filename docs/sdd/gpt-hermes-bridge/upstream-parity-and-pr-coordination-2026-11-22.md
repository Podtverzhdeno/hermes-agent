# Upstream parity audit — 2026-11-22 (critical architectural revision)

**Status:** Verified source comparison; migration proposal only.
**Fork:** `Podtverzhdeno/hermes-agent`, `main` at `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (2026-04-01).
**Upstream:** `NousResearch/hermes-agent`, main at `da8e7d71abe4ac165760cd813c0c18c53e697b90` (2026-11-22 10:20 UTC).
**Upstream release:** `v0.23.3` published 2026-11-20:
https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3.
Release notes state it contains approximately 370 merged PRs since v0.23.2.
This means the April fork is substantially stale.

**Decision update: ADR-007** — For the GPT/Hermes integration, use the modern
upstream **native /v1/runs and Kanban** as authoritative owners for execution
and task lifecycle. Do **not** ship a parallel scheduler, run ledger or new
session authority based solely on the April fork. Bridge/client features may
be developed as adapters and conformance tests after upstream parity.
This supersedes the implicit assumption in the original SDD that the April
API adapter was the target baseline.

## 1. Evidence matrix: what modern upstream already implements

| Requirement | Confirmed upstream file/module | Implication |
|---|---|---|
| Durable run submission | `gateway/platforms/api_server_runs.py` | `POST /v1/runs` returns run ID; use this rather than inventing `/operations` |
| Run status | same module + `api_server_authority_runs.py` | `GET /v1/runs/{run_id}`; state projection includes ongoing approvals |
| Run event stream | `api_server_runs.py` | `GET /v1/runs/{run_id}/events`; map existing events into UI |
| Stop/steer/control | `api_server_runs.py` | `POST /v1/runs/{id}/stop`, `/steer`, `/approval`, `/clarify` |
| Unknown-effect reconciliation | `api_server_runs.py` | `/v1/runs/{id}/resolve-unknown` handler exists; validate permissions and semantics |
| Runtime capabilities | `gateway/platforms/api_server.py` | `GET /v1/capabilities` and advertised feature flags; use discovery not version guessing |
| Durable run idempotency | `api_server_run_idempotency.py` | Scoped SQLite `BEGIN IMMEDIATE`, persistent reservation; note fall back to in-memory on DB failure |
| Session turn serialization | `gateway/turn_lease.py` | Per resolved session ID; fail-closed timeout; do not implement a second lease map |
| Session stall signal | `gateway/session_stall.py` | Uses `AIAgent.get_activity_summary()` as sole progress source; distinguish heartbeat and progress |
| Delivery recovery | `gateway/delivery_ledger.py` | Persists delivery obligations; explicitly handles ambiguous delivery and duplicates |
| Gateway death forensics | `gateway/lifecycle_ledger.py` | Startup sentinel detects previous unclean exits; enrich rather than duplicate |
| Multi-agent Kanban lifecycle | `hermes_cli/kanban_db.py` | SQLite WAL, `BEGIN IMMEDIATE`, CAS claim lock, task/run/event tables |
| Worker isolation/admission | `gateway/session_worker_reservation.py` | Identity-checked process reservation, worker fencing |
| Kanban dispatch/notifications | `gateway/kanban_watchers.py` | Dispatcher + terminal event notifier + cursor/retry |
| PR-based acceptance | `hermes_cli/kanban_pr_acceptance.py` | Exact-head GitHub checks, assignee-scoped credentials, receipt proof |
| API worker cap | `gateway/platforms/api_server_runs.py` and `api_server.py` | `gateway.api_server.max_concurrent_runs`, default 10 noted in code |
| Agent/session/profile authority | `persistence/authority/`, `persistence/workers/` | Existing authority model; avoid adding incompatible ownership/identity |

This table documents **source availability**, not proof that the user's local
installation runs the same version or that each path passes production tests.

## 2. Important behavior and caveats in inspected upstream source

### /v1/runs

`api_server_runs.py` defines routes for:
```text
POST /v1/runs
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/approval
POST /v1/runs/{run_id}/clarify
POST /v1/runs/{run_id}/steer
POST /v1/runs/{run_id}/resolve-unknown
POST /v1/runs/{run_id}/stop
```
Check `GET /v1/capabilities` from the *actual deployed gateway* first.
The advertised feature list and actual route policy may differ by configuration
or version; never assume a run control is enabled solely from a file name.

### Persistent idempotency

`RunIdempotencyStore` uses a unique `(scope, idempotency_key)` record and
`BEGIN IMMEDIATE` transaction. A `409` is available for conflicting
fingerprints. Some paths fall back to process memory when the database cannot
be opened, explicitly weakening durability. The bridge must surface an
`idempotency.durable` indicator, reject high-risk unattended writes when
false, and verify behavior after crash and reconnect.

### Stop and unknown outcomes

The upstream routes include `stop` and `resolve-unknown`. An API request
accepted does not mean a remote effect finished. The bridge should poll run
status and consume SSE events; when missing a terminal outcome, it should
query status and *only then* offer an authorized resolution path. Never
manufacture a terminal state on browser-tab close.

### Kanban

`kanban_db.py` already implements a board DB, event trail, claim lock, task
links/dependencies, retries, stale-claim recovery, and run events. The
`kanban_watchers` dispatcher/notifier explicitly manages terminal messages.
Implementing another operation owner in the April fork creates split-brain
authority and multiple sources of truth. Extend using adapters/events rather
than adding an independent persistent task queue.

### Shared OS/system constraints

Modern upstream has distinct profile and owner authorities; old fork does
not implement the same contract. Do not copy arbitrary new modules into an
April runtime and assume imports remain compatible. Windows support has also
changed from earlier WSL-only fork packaging; validate Windows, WSL and
desktop capability explicitly with the target environment.

## 2A. Confirmed event-stream durability gap (new source finding)

The *modern* `gateway/platforms/api_server_runs.py` still has a specific
observability limitation, even though its run ID reservation/status layer is
durable:

- `_RunStream` is an **in-memory** `deque` with `BACKLOG_LIMIT=1000`.
- Each subscriber has `SUBSCRIBER_QUEUE_LIMIT=256` (plus replay headroom).
  Slow subscribers are detached after overflow.
- `Last-Event-ID` and `last_seq` support replay **only from current
  memory**. If the requested sequence is older than the retained backlog,
  upstream emits `replay.truncated` with `oldest_retained_seq`.
- `GET /v1/runs/{run_id}/events` returns not-found if there is no live
  `_run_streams[run_id]` entry after its short registration wait.
  In contrast, GET run status can recover a scoped persisted status.
- Events can be truncated/lost on restart even when final status survives;
  a client must never infer a continuous step trace solely from a terminal
  status or the existence of SSE reconnect support.

**Revised observability design (derived, not a competing run authority):**
1. Connect to `/v1/runs/{id}/events` as close to run admission as practical.
2. Decode bounded SSE frames. Record `seq`, safe `event` category,
   timestamps and a **redacted** causality key; discard raw free-text args,
   previews, answers and tool payloads by default.
3. Persist each received event + last-confirmed sequence to a local durable
   append-only index. Track `replay.truncated`, sequence gaps, queue
   overflow, disconnect, reauth and event-source restart separately.
4. On reconnect, send `Last-Event-ID` and reconcile
   `GET /v1/runs/{id}` before deciding whether another attempt is safe.
5. If upstream no longer has the event backlog, display
   `EVENT_HISTORY_GAP` and the authoritative *status only*. Do NOT invent
   missing tool steps or auto-close the incident.
6. The GPT extension may show progress from this index, but it cannot mutate
   Hermes Kanban/run state. A server-side transactional event hook is
   required for stronger no-gap guarantees across gateway crashes.

**Acceptance criteria** for future SSE observer:
- 1001+ generated events: `replay.truncated` produces explicit gap alert.
- Subscriber queue overflow: client notices disconnect, retries with cursor,
  and preserves an explicit missing-range record.
- Gateway SIGKILL then restart: persisted run status remains distinguishable
  from lost event history; no fabricated 100%-complete trace.
- Duplicate `Last-Event-ID` replay: exactly one observational row per
  `(run_id, seq)` in the derived index; previously confirmed events do
  not appear as new actions.
- SSE stream reports terminal then status lacks terminal: flag contradiction,
  resolve against authoritative persisted state.
- Raw SSE payload contains a credential/prompt: redaction test proves it is
  not written to the derived index.
- 30 independent run streams: test event lag, storage backpressure and
  observer crash/recovery; note backend hard concurrency caps separately.

The current `scripts/hermes_gpt_run_observer.py` is intentionally a
**status-only read-only probe**. It does NOT ingest SSE, retain per-step
events, or satisfy the above criteria. Its own log records `state_observed`
only for changed status/last-event category and explicitly labels stalls
as *suspected*.

## 3. Updated target architecture

```text
GPT UI / authorized browser extension / backend client
      |
      | endpoint discovery (/v1/capabilities),
      | authn, scope, origin validation, request ID
      v
Bridge transport (thin, stateless where possible)
      |
      +-- POST /v1/runs with idempotency key
      +-- GET /v1/runs/{id} for status after reconnect
      +-- GET /v1/runs/{id}/events for progress
      +-- POST .../approval, .../stop or .../steer with consent
      v
Modern Hermes API authority + durable run idempotency
      |
      +-- Canonical session/turn lease
      +-- Kanban board/run/task events (if many engineering agents)
      +-- Existing delivery ledger / worker reservations
      v
Existing Hermes tools / remote side effects
      |
      v
Diagnostic correlator and redacted timeline index
```

**Ownership boundaries:**
- Hermes run authority owns run/status/cancellation/approval.
- Hermes Kanban owns multi-agent tasks, claims, dependencies and completion.
- Bridge owns browser lifecycle, consent UX, client request IDs, capability
  negotiation, reconnection cursors, and a derived diagnostics index.
- Derived trace/telemetry must not authoritatively rewrite Hermes run state.
- An external-effect verifier may enrich a run, but cannot self-grant approval.
- A third-party executor must declare its effect/idempotency contract before
  the bridge can claim replay safety.

## 4. Reuse-vs-build decision table

| Capability | Use upstream | Extend only if measured gap | Do not duplicate |
|---|---|---|---|
| Work scheduling | Kanban dispatcher | fairness policy, per-project ownership | new autonomous queue |
| Run admission | `/v1/runs` | client UX, backoff, auth negotiation | April fork handler |
| Idempotency | `RunIdempotencyStore` | durability health, effect-specific receipts | another in-memory cache as source-of-truth |
| Session serialization | `turn_lease.py` | cross-process constraints if needed | a second session lock table |
| Operator progress | run SSE, `session_stall` | causal correlation and stop classification | isolated heartbeat-only watchdog |
| Gateway forensic signals | lifecycle sentinel | cross-component RCA and privacy-safe evidence | new competing lifecycle authority |
| Final delivery | delivery ledger | external browser acknowledgement mapping | separate replay policy |
| PR acceptance | `kanban_pr_acceptance.py` | local environment/Windows evidence | trusting model success narration |

## 5. Migration and verification plan

1. Inventory user's actual Hermes build/version, extension ID/manifest, local
   MCP, native-messaging host/broker and gateway config. Do not expose secrets.
2. Branch from a pinned *current upstream tag/commit* in an integration worktree.
   Generate exact diff against April fork; preserve user-specific changes.
3. Run dependency, storage schema and profile-identity migration dry-run,
   then backup and restore rehearsal. No in-place profile DB upgrade without
   a verified rollback path.
4. Test `GET /v1/capabilities`, `POST /v1/runs`, status/events, cancel,
   approval, idempotency conflict, unknown effect, 10/30/100 agents.
5. Build the GPT bridge client as a protocol adapter; log correlation
   IDs, but treat Hermes state as authoritative.
6. Use official Kanban for agent work, with per-path branch/worktree ownership,
   exact-head CI receipts and independent reviewers.
7. Only after E2E parity, consider deleting old fork-specific cache changes
   or cherry-picking isolated regression tests that modern upstream lacks.
8. Release with explicit feature flags, canary and rollback. No automatic
   migration based solely on this document.

**Hard release gate:** No changes from PR #1, #4, #5 or #6 that create a
second scheduler, run store or API idempotency contract may merge until the
upstream parity architecture is reviewed. Other agent branches may contain
useful tests and diagnostics; extract, don't blindly merge.

## 6. Conflict inventory in current fork

| Fork PR | Scope | Potential conflict |
|---|---|---|
| [#1](https://github.com/Podtverzhdeno/hermes-agent/pull/1) | prototype durable Autopilot ledger | duplicates upstream Kanban authority |
| [#2](https://github.com/Podtverzhdeno/hermes-agent/pull/2) | skill harness contracts | coordinate eventual tool permissions |
| [#3](https://github.com/Podtverzhdeno/hermes-agent/pull/3) | ACP permission isolation | valuable security patch; review independently |
| [#4](https://github.com/Podtverzhdeno/hermes-agent/pull/4) | API idempotency + SSE diagnostics | modifies same April `api_server.py` |
| [#5](https://github.com/Podtverzhdeno/hermes-agent/pull/5) | API idempotency + deep SDD | modifies same April `api_server.py`; tests may be reused |
| [#6](https://github.com/Podtverzhdeno/hermes-agent/pull/6) | API idempotency, SSE, security + SDD | modifies same April `api_server.py`; broadest April patch |

These branches are not interchangeable. For the April fork, PR #6 currently
covers more API behaviors than #4/#5, but breadth is **not** a pass: its CI
and security/compatibility analysis are still required. Modern upstream
already contains many equivalent features, so upstream migration must take
precedence over selecting an April implementation for production.

## 7. Exact verification references

- Official release: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
- Modern run API:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_runs.py
- Idempotency store:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_run_idempotency.py
- Capabilities and API:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py
- Kanban:
  https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/kanban_db.py
- Kanban PR acceptance:
  https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/kanban_pr_acceptance.py
- Run/session lease:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/turn_lease.py
- Progress:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/session_stall.py
- Delivery:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/delivery_ledger.py
- Process lifecycle:
  https://github.com/NousResearch/hermes-agent/blob/main/gateway/lifecycle_ledger.py

At audit time, current upstream main was `da8e7d71abe4ac165760cd813c0c18c53e697b90`.
Link URLs using `/blob/main/` will move over time; use the pinned SHA
for repeatable revalidation.
