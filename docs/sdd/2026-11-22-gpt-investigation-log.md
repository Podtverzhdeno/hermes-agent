# Hermes/GPT: investigation and implementation log, 2026-11-22

## Evidence levels
- **OBSERVED_CODE:** directly inspected in `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591`.
- **PATCHED_UNVERIFIED:** modified isolated branch; tests authored but no successful CI or runtime evidence yet.
- **HYPOTHESIS:** plausible failure class; no incident sample.
- **EXTERNAL_FAILURE:** observing tools unavailable; does not imply Hermes agent unavailable.

No access to private model deliberation, live production traces, user's local runtime logs or ChatGPT session internals. This is a source-level investigation with separate local infrastructure limitations.

## Investigation chronology

| # | Evidence / step | Finding | Severity | Root-cause hypothesis / action | Status |
|---|---|---|---|---|---|
| E01 | GitHub source `gateway/platforms/api_server.py`, baseline lines 244-279 | Idempotency cache not reserving pending keys; two same-key calls may both run agent | P0 | Await-before-insert race; add one pending task per key | PATCHED_UNVERIFIED |
| E02 | Same source | Different payload on same Idempotency-Key silently replaces/invalidates prior result | P0 | Missing fingerprint comparison; return HTTP 409 | PATCHED_UNVERIFIED |
| E03 | Same source chat endpoint | Cache previously stored only `(result,usage)`, recreated response/session IDs, so retry response was not stable | P0 | Cache complete HTTP result, including IDs | PATCHED_UNVERIFIED |
| E04 | Same source | Global process cache shared endpoint keys without session header in fingerprint | P1 | Per-adapter cache, explicit endpoint namespace, incorporate explicit session ID | PATCHED_UNVERIFIED |
| E05 | SSE `_write_sse_chat_completion`, baseline ~689-708 | Uncaught agent error swallowed, then successful SSE stop emitted | P0 | Expose error frame and never issue success terminal on known exception | PATCHED_UNVERIFIED |
| E06 | Adapter `connect`, baseline ~1270-1318 | No API key requirement on non-loopback bind | P0 | Refuse non-loopback bind without auth key | PATCHED_UNVERIFIED |
| E07 | `_CORS_HEADERS` | Browser preflight omitted X-Hermes-Session-Id and browser couldn't read session/request header | P1 | Allow + expose headers explicitly | PATCHED_UNVERIFIED |
| E08 | JSON parser paths | Non-object JSON reaches `body.get()`, likely unhandled error | P1 | Validate body type before dispatch | PATCHED_UNVERIFIED |
| E09 | API auth helper | Direct string equality on bearer secret | P2 | Constant-time compare to reduce timing signal | PATCHED_UNVERIFIED |
| E10 | `ResponseStore` | Response and conversation alias saved in separate commits; eviction does not clean aliases | P1 | Transactional append + alias CAS, test crash/eviction boundaries | HYPOTHESIS (IMPLEMENTATION OPEN) |
| E11 | In-memory cache only | Restart or two processes can independently execute same external side effect | P0 production gate | Durable idempotency/effect ledger and fencing, manual reconciliation if ambiguous | HYPOTHESIS (IMPLEMENTATION OPEN) |
| E12 | Source `_run_agent` thread executor | Async cancellation may not interrupt already-started sync worker in all races | P1 | Cooperative cancel state, agent_refs, heartbeats, test early disconnect | HYPOTHESIS (IMPLEMENTATION OPEN) |
| E13 | No durable per-tool event ledger in API flow | Root cause and side effects cannot be reconstructed from one atomic trace | P1 | Durable transactional outbox and sequenced event schema | HYPOTHESIS (IMPLEMENTATION OPEN) |
| E14 | `mcp__Local_WorkSpace__list_workspaces` | Session terminated; couldn't read local Hermes logs/SDD | P1 observability | Diagnose tunnel/MCP separately; do not conclude agent dead | EXTERNAL_FAILURE |
| E15 | `mcp__temp_folder_readonly__list_workspaces` | MCP SSE probe returned HTTP 429 | P1 observability | Backoff and inspect separate health states | EXTERNAL_FAILURE |
| E16 | Existing `tests/gateway/test_api_server.py` | API basic behavior tests exist but lacked explicit idempotency race coverage | P1 | Add 15 new targeted regressions including SSE, CORS, key conflict, safe log content | PATCHED_UNVERIFIED |

## Changed files and audit provenance
- `gateway/platforms/api_server.py`: bounded per-adapter single-flight cache; HTTP 409/503; stable replay; metadata-only request tracing; distinct SSE failure; bind guard; CORS; malformed request validation; timing-safe auth comparison.
- `tests/gateway/test_api_server_idempotency.py`: 15 targeted tests; all newly authored this session; they must run under GitHub Actions before they are considered passing.
- `docs/sdd/gpt-extension-observability-2026-11-22.md`: architecture, invariants, failure taxonomy, research, dependency gate ordering, weighted proposals, multi-agent lease/fencing protocol.

Code branch `sdd/gpt-observability-2026-11-22`; baseline `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591`. Every write has a corresponding Git commit. The branch is intentionally isolated from default `main`.

## Operational triage checklist

1. Identify immutable `request_id`, `run_id` (future), `attempt_id` (future), timestamp and code revision.
2. Check ingress auth, body limit, CORS, rate limit before blaming the model.
3. Determine whether the runner started; collect latest *evidenced* progress event rather than free-form agent assertion.
4. If tool call began but no ACK arrived: classify effect as UNKNOWN; do **not** replay until reconciled at target system.
5. Differentiate agent crash, observer/tool transport outage, cancellation requested, and user disconnect.
6. For LLM calls collect provider response code / request ID / token limit / retry headers where available; do not log credentials or raw prompts.
7. For concurrency verify owner lease, session revision, idempotency fingerprint and effect ID.
8. Reproduce in isolated test/synthetic fault injection; implement minimal patch; run regression tests.
9. Keep release on PR until unit/integration tests, threat model and rollback are checked.

## Validation ledger
- 2026-11-22: inspected GitHub baseline code, tests, architecture; static review completed.
- 2026-11-22: 15 pytest regression cases added, not yet executed.
- 2026-11-22: no production stress test, no local runtime data and no external-agent health verification.
- Release status: **NOT VERIFIED / DO NOT AUTO-MERGE** until CI and runtime evidence.
