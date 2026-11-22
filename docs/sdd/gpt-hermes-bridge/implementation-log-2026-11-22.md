# Implementation and audit log — 2026-11-22

This is a factual, append-only audit diary for the current engineering pass.
Plans, examples and unrun tests are labelled accordingly. All dates use UTC
where shown. This log is a durable reference for agents continuing the work;
it is not a live monitoring service.

## Scope and baseline

- Account/repository: `Podtverzhdeno/hermes-agent` (connected GitHub).
- Original `main` HEAD: `7e9100901819ee44c16b4ddcb79a6bcb7909f591`.
- Working branch: `feat/gpt-bridge-atomic-diagnostics-20261122`.
- Draft PR: https://github.com/Podtverzhdeno/hermes-agent/pull/5
- Github PR status from API at audit: open, draft, mergeable=true, mergeable_state=clean; no review approval yet.
- Workstation Local_WorkSpace call `list_workspaces` failed:
  `INVALID_ARGUMENT / Session terminated`. This does NOT prove Hermes or
  extension is broken; only means that this tool path was inaccessible.
- No source/manifest of a dedicated ChatGPT/GPT extension was located in
  inspected repository paths. No browser runtime logs or CDP session inspected.
- **Important**: source `main` commit dates in the retrieved history are
  2026-04-01. We have not confirmed whether this fork tracks a newer upstream.

## Evidence-backed diagnosis (pre-fix)

### BUG-01: duplicated work for concurrent idempotent HTTP requests

- Source: `gateway/platforms/api_server.py` original
  `_IdempotencyCache.get_or_set()`.
- On a cache miss, code awaited `compute_coro()` before putting key in the
  cache. Two simultaneous requests can both miss and invoke a tool/LLM.
- Consequence: duplicate external tool actions and cost, particularly at
  high agent fanout. The actual incidence rate in production is unknown.
- Same class silently recomputed a mismatched fingerprint for the same key.
  This is a contract error; should be explicit conflict.
- Caching only `(result, usage)` caused retries to generate a new
  `completion_id`, `created`, and `X-Hermes-Session-Id` response identity.
- Global `_idem_cache` shared all APIServerAdapter instances.

### BUG-02: possible secret in API 500 response

- Source: `_handle_chat_completions()` returned `str(e)` directly
  to clients in internal server error envelope.
- Potential impact: sensitive backend exception text returned to clients.
  No observed production leak has been established.

## Patches actually committed on branch

| Path | Change | Commit |
|---|---|---|
| `gateway/idempotency.py` | event-loop single-flight, explicit conflict, capacity, canonical fingerprint | `0182c4fae3ff0436667fbee6d5456e99eaa90aae` |
| `gateway/platforms/api_server.py` | use adapter cache; original request/session/created IDs; 409 and 503; safe 500 | `29f70e03f7c9b20b79b44acee49b6d622df4cd7c` |
| `tests/gateway/test_api_idempotency.py` | 7 cache unit cases, 3 endpoint cases for dedup, 409 and errors | `fa6a1af89041e9c2b32323b30316dd925a77268a` |
| `docs/sdd/gpt-hermes-bridge/README.md` | scope, verified/unknown, gate index | `234fdb4e3caea2c14c331ca39ff1b6852b534323` |
| `docs/sdd/gpt-hermes-bridge/architecture-and-runtime.md` | durable ledger, state machine, epochs, outbox | `bbfea3c7d757663ea03fbc4023bf87abefedfc47` |
| `docs/sdd/gpt-hermes-bridge/failure-injection-and-observability.md` | event taxonomy, OTel, 32 fault-injection scenarios | `add30386675aadb2f9632f63bb5b3d13a9b2de1a` |
| `docs/sdd/gpt-hermes-bridge/decision-record-and-rollout.md` | weighted options, 20 ranked ideas, ADRs, 25+ agents | `78a4441bb491672eed22556888ef0a24b2f79f18` |

This log itself was committed after the table entries.

## Verification ledger

**Passed**:
- Seven isolated cache unit tests, executed in a local mirror of the new
  `gateway/idempotency.py` algorithm and unit tests, without a complete
  Hermes installation:
  `python -m pytest -q test_idempotency.py` -> `7 passed in 0.06s`.
  This result does not validate HTTP integration or entire Hermes repo.
- GitHub PR is **mergeable=clean** at one check; that only proves GitHub's
  three-way merge calculation, not runtime correctness.
- No reviewer approval recorded when checked.

**Not yet verified**:
- `python -m pytest tests/gateway/test_api_idempotency.py -q` in a complete
  Hermes environment (aiohttp imports and platform setup).
- Full existing `tests/gateway/test_api_server.py` regression suite.
- GitHub Actions test pass for this PR's exact head SHA.
- Multi-process, multi-host, shutdown, restart or real browser integration.
- Authentication/authorization under multiple tenants and browser origins.

**Risks remaining**:
- The patch is event-loop-local. A process restart clears cache. Multiple
  gateway replicas can still duplicate a write. Streaming requests do not
  pass through this non-streaming cache.
- Cancellation of an HTTP waiter intentionally does NOT terminate a started
  action; the operation remains in-flight. A future durable-operation query
  and explicit cancellation API are required to make this safe for users.
- Last-known response is cached only after success; partial external effects
  that precede an exception cannot be deduplicated by the cache. These need
  effect-specific idempotency keys + reconciliation.
- No ability to prove from browser UI alone whether an external action
  committed. Treat tool timeouts after dispatch as uncertain.
- The response store and SessionDB have separate state models; consistency
  under concurrent access/restarts requires dedicated tests.
- Potential security risk needing separate review: a caller-supplied
  `X-Hermes-Session-Id` controls which stored conversation history is loaded.
  Check server binding, authentication and tenant/session ownership before
  exposing the API beyond trusted local clients. This is a threat hypothesis,
  not a demonstrated exploit.
- The current `connect()` does a port preflight check, then binds; this
  check is inherently racy (TOCTOU). The actual bind error must remain the
  source of truth; current surrounding exception handler logs failures.
- `AGENTS.md` reports ~3000 tests; don't use that documentation estimate as
  a count of executed tests in this pass.

## Next accountable actions (in order)

1. **Independent PR code review and CI**: run the entire gateway API suite
   against the exact commit SHA; resolve reproducible failures before merge.
2. **Extension discovery**: reconnect the local workspace, locate extension
   manifest and host, obtain actual logs/recorded browser failures.
3. **G0 threat model**: verify trust boundary and integration mode before
   adding page scripts/native messaging.
4. **Ledger prototype**: first add storage migration, CAS, effect-intent and
   outbox tests; only then opt-in integrate with API.
5. **Instruments**: add versioned step events, correlation IDs and
   reason-coded stop/timeout/cancel telemetry without prompt leakage.
6. **Chaos & scale**: run F01–F32, check 10/30/100 agent contention and
   rollout canary; independently verify no duplicated effects.
7. **Policy**: keep draft PR pending independent approval; no automatic merge.

## Engineering discipline

Whenever a later agent works on this task, append a dated subsection with:
base/head SHA, claimed scope, code paths, minimal redacted evidence, exact
tests/results and exit codes, known limitations and a proposed next owner.
Do not change an earlier agent's failure assessment without linked new
evidence. Never write log content based on invented tool execution.
