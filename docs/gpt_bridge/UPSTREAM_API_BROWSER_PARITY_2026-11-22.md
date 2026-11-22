# Hermes GPT bridge — upstream v0.23.3 API and browser compatibility risk

**Source audit:** 2026-11-22 UTC. **Status:** DOCUMENTED, NOT PORTED, NOT E2E-TESTED.

## Pinned comparison

| Area | Older fork main (2026-04-01, 7e910090…) | Upstream NousResearch/hermes-agent v0.23.3 (2026-11-20) | Migration decision |
|---|---|---|---|
| GPT compatible API | `gateway/platforms/api_server.py` legacy single adapter; proposed PRs #4/#5/#6/#11 modify it independently | Same entrypoint evolved heavily; related logic split into `api_server_runs.py`, `api_server_run_idempotency.py`, `api_server_response_admissions.py`, `api_server_response_identity.py`, `api_server_openai_routes.py`, `api_server_authority_runs.py` | Source-parity audit first; cherry-pick **tests/invariants**, not blind replacement |
| API run idempotency | PR #4/#5 propose process-local keyed single-flight + LRU; PR #6 adds unknown quarantine | `RunIdempotencyStore` has per-scope key reservation in SQLite via `BEGIN IMMEDIATE`, status/ack and selective terminal pruning; `POST /v1/runs` durable admission | Do not add a second competing cache as authority; test fallback-to-memory and crash windows |
| Unknown execution | Draft #6 quarantine without persistent ledger | `api_server_authority_runs.resolve_unknown_run` resolves an exact unknown run admission, matched by admission ID and generation | Reuse authority's unknown reconciliation; never treat a timeout as failed execution |
| SSE response transport | Parallel patches #4/#6/#11 to old adapter | `api_server_openai_routes.py` contains dedicated SSE stream implementation, response adapters, status classification and snapshots | Port E2E failure tests at pinned current source SHA |
| Browser cleanup | PR #15 adds logic/tests to legacy `tools/browser_tool.py` | v0.23.3 `tools/browser_tool.py` is a 12-line compatibility stub; browser is now `browser_exec` via `tools/browser_use_cli.py`, `tools/browser_session_lifecycle.py`, `tools/browser_session_cdp.py` and `tools/browser_cdp_tool.py` | PR #15's path is obsolete in new upstream; translate intent to actual owner-scoped lifecycle and test harness |
| Task/worker lifecycle | New Autopilot ledger proposals | Built-in durable Kanban/dispatcher/worker claims | Exactly one task authority: Kanban, no duplicate scheduler |

**Source blobs checked:** upstream v0.23.3 `gateway/platforms/api_server.py` = `8e4213ac727d87ec1094f7b59b01bb1dcec133d2` (~229k chars); `api_server_run_idempotency.py` = `423437733abb3e434f2990935899c9db6a05aaba`; `api_server_authority_runs.py` = `c1b599dfe5127e42f8aebf98eb5a99955c895e1a`; `tools/browser_tool.py` = `a7c3bc83fbd4bbf69d1bae996fe2167b4c72ed85` (12 lines). These are current **release** source files, not the old fork.

## High-priority failure mode in upstream: durability degradation

`RunIdempotencyStore.__init__` attempts a SQLite DB under the configured home, but **falls back to in-memory SQLite if opening the file raises**, with a warning and `durable=False`. This may be acceptable for a degraded low-privilege interactive response but **must not silently satisfy any guarantee of crash-safe replay or irreversible external effects**.

The upstream `_idempotency_capabilities` exposes `durable` and retention. Define a gate:
- API/bridge telemetry must record `IDEMPOTENCY_DURABILITY_DEGRADED` when `durable=False`, without sensitive paths or raw exceptions.
- Protect high-risk effect reservations at a trusted tool gateway. If the durable action ledger is inaccessible, deny *new external mutations*, not just print a warning; retain read-only status if possible.
- Test disk read-only/full, SQLite permissions, process death after remote write, multi-process races, and restart with same Idempotency-Key.
- Verify retention: `_prune_stale_terminal_locked` prunes **terminal** entries after retention; unknown/nonterminal rows should remain for reconciliation. A privileged external-effect journal needs its own stricter retention policy, not merely the 24-hour HTTP replay cache.

This is a design release gate, not a confirmed production exploit. Code inspection alone cannot establish whether a higher-level authority already enforces the required fail-closed policy in all routes.

## API/extension contract for atomic diagnosis

Each run needs immutable `task_id`, `run_id`, admitted request fingerprint and scope, `attempt_id`, board epoch, lease owner/fence, transport session and response cursor; every external effect has a reserved stable key, independently verifiable receipt and UNKNOWN state after any lost ACK.

The browser/native companion must never equate HTTP 200, SSE closed, `finish_reason=stop`, CDP disconnect or tab disappearance with Kanban completion. The server's existing `POST /v1/runs/{id}/stop` and `resolve-unknown` paths are distinct operations; stop requests can race with executing effects and require observation of final state.

### Pre-upgrade regression corpus

1. Fork #4/#5/#6/#11 comparative keyed request and SSE terminal tests on legacy fork.
2. Replay equivalent expectations on upstream v0.23.3 *without* reimplementing existing services.
3. Windows browser harness owner cleanup from #15, mapped to `browser_session_lifecycle.cleanup_browser` and shared launcher ownership, not stub path.
4. SQLite read-only/full -> `durable=False`; block privileged tool write and show operator incident.
5. Two concurrent agents same task, divergent Idempotency-Key scopes, cancellation after remote write, unknown resolution requires exact admission ID and generation.
6. Test task store/outbox changes at same commit with exact SHA CI and independent receipt.
7. Annotate failed negative tests with source blob SHA and distinct authority; no green claim from conceptual parity.

## User-visible conclusion

It is unsafe to merge the draft API/browser fixes to a seven-month-old base and only then "upgrade Hermes." The better sequence is to compare against *pinned modern upstream*, preserve working native Kanban/authority semantics, port only missing features and the valuable regression tests, then certify the local extension against those interfaces. All actual local runtime, browser manifest and Native Messaging integrations remain outside the scope of this source-only audit.
