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
- `tests/gateway/test_api_server_idempotency.py`: 27 test functions (some parametrized); a separate targeted CI successfully ran the whole affected suite.
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
- 2026-11-22: initial 15 targeted test cases added; subsequently expanded to 27 test functions, including parametrized runner outcomes, 100 concurrent requests and SQLite transaction fault injection.
- 2026-11-22: target gateway regression CI on commit 753a1dda581fdcb1a078a041f6ef77cc2d411f4a completed successfully: 136 passed (run https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013927978). No production stress test, no local browser runtime data and no external-agent health verification.
- Release status: **TARGETED GATE PASSED; FULL GATE NOT PASSED / DO NOT AUTO-MERGE**. Local browser and multi-process E2E not verified; PR #4/#5/#6 own same source file. Full-suite baseline initially red for multiple unrelated causes.


## Follow-up evidence — independent CI and new failures

| # | Type | Evidence | Fix / disposition |
|---|---|---|---|
| E17 | OBSERVED_CI | Full suite on initial patch commit d0369dcb8a2a1b32a87ece6644c0609b0d8faf98: 7510 passed, 34 failed, 171 skipped. 5 SSE-disconnect tests failed while logging a MagicMock request ID, and 1 prior test asserted leaked raw exception string. | Normalize the log ID and assert error redaction; subsequent targeted tests pass. Many remaining failures derive from unset provider credentials or unrelated Codex/file tools; not attributed to this patch without main-baseline comparison. |
| E18 | OBSERVED_CODE | A failed agent call after an external effect may be retried under the same key after old cache eviction, duplicating writes. | Preserve unknown result in process-level cache; HTTP 409 `execution_outcome_unknown` on retry. Regression simulates ACK lost after committed effect. **Still NOT durable across restart.** |
| E19 | OBSERVED_CODE | Hermes runner explicitly distinguishes `failed`, `interrupted`, `completed=False` but API adapter previously returned `finish_reason=stop` unconditionally. | Normalize runner outcome; SSE emits error or `length`, Chat returns outcome header/appropriate finish reason, Responses returns incomplete status/reason. |
| E20 | OBSERVED_CODE | `ResponseStore.put` and `set_conversation` committed separately. Deletion and LRU eviction left aliases to nonexistent responses. | One SQLite transaction for response+alias+eviction, clean dangling aliases on delete/evict; regression creates SQL trigger failure and verifies rollback. Concurrent updates of the SAME conversation remain future P1 work. |
| E21 | OBSERVED_CI | Targeted CI https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013927978 on 753a1dda581fdcb1a078a041f6ef77cc2d411f4a passed **136** tests. | Verified for that head only, not entire repository or local Chrome. |
| E22 | OBSERVED_UPSTREAM | Community Hermes Browser Extension README (v0.4.1) includes own tab leases, 20 tab tools, 7 context/journal tools, per-profile plugin after Hermes 0.22.5. | [Upstream-vs-custom SDD](gpt-browser-upstream-reuse-2026-11-22.md). Prefer negotiated thin adapter over another standalone browser controller. Neither ownership of the user's installed extension nor local compatibility is confirmed. |
| E23 | EXTERNAL_FAILURE | Local Workspace MCP: Session terminated. Secondary local probe: HTTP 429. | Treat observer status as unknown; do not mark Hermes worker dead or overwrite local files without verified access. |
| E24 | OBSERVED_PR | PR #4, #5, #6 independently alter `gateway/platforms/api_server.py`. | Cross-agent review ADR and comments on PR #4/#5/#6. No automatic merge, select one canonical idempotency implementation. |

### Logs, sources and freshness
- Initial broad test job: https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013031713
- First targeted pass: https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013406772 (**115 passed** on earlier SHA).
- Later targeted pass: https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013927978 (**136 passed** on SHA 753a1dda...).
- Current branch may have later commits; **never transfer a past green CI result to a new head SHA**. The exact SHA must be checked independently.
- Chromium MV3 reference: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Companion plugin reference: https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md
