# ADR GPT-UPSTREAM-001 — Upstream parity before GPT API integration

**2026-11-22 / OBSERVED (source review)**. This is a design audit and gate, **not** a live test or authorization to deploy.

## Source-level delta

| Module | Fork main blob | NousResearch main blob | Why it matters |
|---|---|---|---|
| `gateway/platforms/api_server.py` | `2059a1aa6bcc5b88dd7bfaef269bc841281e029d` (~1,356 lines) | `8e4213ac727d87ec1094f7b59b01bb1dcec133d2` (~4,080 lines) | Upstream delegates Chat/Responses, adds `/v1/runs` status/events/approvals/stop/unknown resolution; monolithic old fork handlers not equivalent |
| `gateway/platforms/api_server_run_idempotency.py` | not found during fork audit | `423437733abb3e434f2990935899c9db6a05aaba` | SQLite `RunIdempotencyStore` with atomic scoped reservation |
| `gateway/platforms/api_server_openai_routes.py` | not found during fork audit | `ea8a9d18bc759bbf3724c7977ce78bf60b57b799` | OpenAI-compatible routes and SSE semantics |
| `gateway/platforms/api_server_runs.py` | not found during fork audit | `868ed43adf99e0024c9bd31e655a2a1e201cf4d9` | Run status/event publication, subscriber limits, approval and unknown resolution |
| `website/docs/user-guide/features/browser.md` | fork version may lag | `27c7631900eba834f15d1f5ad8c69637723475a9` | Hermes `/browser connect` and CDP already exist upstream |

Note: the old fork path absences above are review limitations, not a comprehensive tree assertion. The file-size delta is source divergence, NOT proof that `git merge` fails.

## P0 integration choice

Do not cherry-pick a legacy 1,400-line replacement over the current 4,000-line API without semantic audit. Prefer adapting the upstream versioned `/v1/runs` run-admission and status contract **if** the exact fork target can take it safely. Preserve permissions, session ownership, process lifetime tracking, durable replay, SSE, logs and backwards compatibility. A full effect-intent / external-provider receipt ledger may still be missing — `/v1/runs` is not automatically the entire Autopilot authority.

## Independently observed risks in newer upstream code

1. **Legacy Chat/Responses cache key race:** upstream `api_server.py` `_IdempotencyCache.get_or_set` indexes in-flight tasks by `(key,fingerprint)`, not by key alone. Concurrent same-key/different-fingerprint requests can execute twice because they have different in-flight entries. After successful caching, a changed fingerprint also proceeds to compute instead of an explicit conflict. Test two parallel calls with identical authenticated scope and key but different body; expect one admitted action and a deterministic `409` conflict. Upstream `/v1/runs` has its own atomic reservation; distinguish paths.
2. **Unknown external effects:** on exception, upstream legacy `_clear_inflight` drops the key. Retrying could rerun an action that already committed before losing ACK. Require persistent unknown-effect outcome and read-back, or prohibit mutation via unsafe compatibility path.
3. **Persistence downgrade:** upstream `RunIdempotencyStore` catches disk open errors and falls back to `:memory:`, with `durable=false` advertised via `/v1/capabilities`. For owner workflows needing crash-safe replay, **block mutating run admission** when no durable authority is available; a logged downgrade alone is not a durability guarantee.
4. **Exception output:** upstream `api_server_openai_routes._run_idempotent` may construct client 500 from `f"Internal server error: {e}"`. Test redaction and sensitive details for all modern endpoints.
5. **Browser ownership:** don't build a competing CDP mutation lane in extension; reuse existing `browser_exec`/supervisor with shared fence or isolate extension to read-only observation.

These are **code-based risks**, not observed production incidents, and need independent tests on an exact SHA.

## Revised gate sequence

G0: capture upstream SHA and old-fork baseline; verify endpoint/capability drift and current tests; include build package checks.
G1: choose exactly one authoritative run/effect ownership model; prohibit duplicate schedulers and ambiguous fallback semantics.
G2: run common test suite across upstream/selected candidate with multi-principal key collisions, unknown effect after timeout, session revision conflict, SSE slow client and error.
G3: integrate browser extension as authenticated, owner-authorized observer first; test native CDP lane arbitration, MV3 crash/reattach.
G4: execute fault matrix under multiple processes/agents; only opt in on known good commit plus rollback, local snapshot and consent.

## Sources

- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_run_idempotency.py
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_openai_routes.py
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_runs.py
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/browser.md

**Owner decision required for actual release:** fork synchronization/compatibility strategy, API-vs-browser boundary and server permission model. The SDD can recommend a path, not grant access or perform a live deployment.
