# Hermes GPT API compatibility ADR — converge #4/#5/#6/#11 before any merge

**ADR-API-2026-11-22** · Status **PROPOSED / P0 merge gate** · evidence from three distinct `gateway/platforms/api_server.py` branch snapshots on 2026-11-22. Do not interpret source-level review as tests running on merged code. No production API implementation was changed by this ADR.

## 1. Confirmed inconsistent contracts

| Endpoint/behavior | PR #4 | PR #5 | PR #6 | Required integration decision |
|---|---|---|---|---|
| Chat duplicate same in-flight key | 409 `idempotency_in_progress` | Join shared in-flight task | Join shared in-flight task | Select one client-visible behavior |
| Chat same key, different body | 422 `idempotency_payload_mismatch` | 409 `idempotency_key_conflict` | 409 `idempotency_conflict` | One status+error-code contract |
| Nonstreaming cache level | process-local module global | per-api-instance process-local | per-api-instance process-local | Never claim durable cross-process exactly-once |
| Chat key scoping | hash Authorization+provided session+raw key | endpoint prefix+raw key, fingerprint includes session | endpoint prefix+raw key, fingerprint body | Auth principal/session design decision |
| `/v1/responses` key | raw unscoped key | `responses:` + raw key | `responses:` + raw key | Scoped auth principal and endpoint |
| `/v1/responses` digest | handpicked subset of body keys | full JSON body | full JSON body | Whole effective normalized request |
| `/v1/responses` replay | reuses model result, regenerates response ID, persists again | caches built response+ID+store side effect | caches built response+ID+store side effect | Stable response ID and durable idempotent storage |
| `/v1/responses` conflict exception | caught as generic 500; error string may be exposed | typed 409 | typed 409 | Explicit fixed-safe errors, no exception-body echo |
| SSE agent failure | branch-specific failure signaling | catches agent exception, then `finish_reason=stop` and `[DONE]` | specific in-stream error / non-success termination | NEVER emit success on known exception |
| Keyed SSE | check branch-specific behavior | branch-specific behavior | explicit 400 before dispatch | Consistent preflight, no halfway mutation |
| Unknown external outcome | branch-specific process-local marker | no durable effect proof | process-local sticky unknown until restart | Effect ledger required; never blind retry |
| Overloaded in-flight cache | branch-specific | bounded 503 | bounded 503 | Shared rate/queue budget, observable 503 |

These differences are **source observations**. The user-facing HTTP policy needs gateway-owner ratification and test data for each endpoint; do not choose by PR number or a model's self-rating.

## 2. P0 source-level correctness/security findings

**API-01 — PR #4 `/v1/responses` cross-client cache alias risk.** Chat endpoint scopes its key using `scoped_idempotency_key`; Responses passes raw `idempotency_key` directly to process-global cache and hashes only selected request fields. Under multiple authenticated clients/principals this can alias independent requests, including response content. Scope by **authenticated principal** (trusted identity established by auth middleware), endpoint and relevant session/conversation, not by self-declared `client_id` or a plaintext bearer token. Exact regression: two principals, same raw key and body, different permitted context; they must never share a cache result.

**API-02 — PR #4 partial request fingerprint.** `_make_request_fingerprint(body, keys=[input,instructions,previous_response_id,conversation,model,tools])` omits effective behavior-changing fields such as `store` and `truncation` or future options. A changed request can be incorrectly treated as identical. Canonicalize and hash the **entire effective validated request** (including versioned defaults and relevant session context), with stable JSON and `allow_nan=False`; reject unknown/invalid values at the boundary.

**API-03 — PR #4 response ID stability.** Cache stores `(result,usage)` only; outer handler generates a new `response_id` and response-store write on each replay. Exact duplicate response should retain the original ID, created timestamp, status, token accounting and conversation mapping. Avoid writing side effects twice during "cached" output construction.

**API-04 — PR #4 error classification and disclosure.** Responses catches idempotency-specific exceptions under broad `except Exception as e` and returns generic 500 including `{e}` text; chat endpoint handles typed exceptions explicitly. Conflicts and "unknown outcome" must be stable typed errors; never return raw exception details to clients or unsafe logging sinks.

**API-05 — PR #5 false SSE success.** In `_write_sse_chat_completion`, an exception raised by `await agent_task` is swallowed, then `finish_reason="stop"` and `data: [DONE]` are emitted. A failed agent must not appear completed. Test an exception after initial partial tokens are sent. Distinguish a client disconnect from a provider/runner error. This is a confirmed code path, not a confirmed production incident.

**API-06 — all branches' memory-local guarantee.** A process-local cache or an HTTP client connection cannot prove exactly-once external tool effects after process restart or loss of ACK. For mutating operations, route reservations through the ledger and current lease fence. If outcome unknown, require read-back/reconciliation before any new effect attempt.

## 3. Proposed normalized API idempotency contract

The following is **a candidate**, not a committed compatibility promise:

| Input scenario | Proposed response | Required invariant |
|---|---|---|
| First valid key for nonstreaming endpoint | Execute; record stable `run_id` and response id | One admitted logical run within supported scope |
| Exact same key/body while still running | JOIN same task, bounded wait; alternatively 409 if clients cannot safely join | No duplicate invocation; choose once per API version |
| Exact same key/body after success | Return original response bytes/ID or semantically identical canonical object | No repeated output persistence or tool calls |
| Same key but changed effective body/session/principal | 409 `idempotency_conflict` (recommended, subject to owner) | Never return unrelated cached result |
| Same key with prior uncertain outcome | 409 `execution_outcome_unknown` + correlation ID | No auto-reissue; reconcilable ledger state |
| At capacity | 503 `idempotency_capacity` + valid `Retry-After` | Do not evict a running or unknown effect to make room |
| Malformed/oversized key or request | 400 typed error before agent dispatch | No partial side effect |
| `stream=true` with keyed dedupe unsupported | 400 typed error before dispatch | No silent downgrade or half-open replay |
| SSE runner exception after stream started | Explicit protocol error and close; **no normal finish marker** | Client must not mistake the stream for success |
| Client disconnect after any tool effect reserved | Transport stops; task outcome stays ledger-observed/unknown | Retry only after reconciliation and fence validation |
| Server restart | Persisted task/effect ledger decides resume | In-memory cache is not authority |
| New authenticated principal with same raw key | Independent identity namespace | No cross-client response leakage |

**Causal ID rule:** `request_id` is different for each HTTP attempt; `run_id` identifies the logical work across retries; `attempt_id` changes only when the authoritative ledger starts a new execution attempt. Do not use raw token, user-provided session string, opaque prompt or IP as a public metrics label. Logs carry allowlisted bounded identifiers and reason codes.

**Fingerprint rule:** `HMAC(server_secret, version | principal_id | endpoint | effective_session | canonical_validated_body | raw_idempotency_key)` is an illustrative way to keep secrets out of logs and reduce aliasing; exact durable schema and key-rotation policy must be approved by the security/API owner. Comparing only raw string keys or a selected-field digest is insufficient.

**Outcomes:** `succeeded` requires trusted completion and persistence, `incomplete` is not success, `failed` requires confirmed failure, and `needs_reconciliation` means an effect may have happened. Do not emit a `finish_reason=stop` when the runner failed, even if a partial stream was already sent. For disconnected clients, a separate authenticated status query is required for definitive post-disconnect reconciliation.

## 4. End-to-end acceptance matrix (all branches run same fixtures)

| Test | Setup and decisive assertion |
|---|---|
| IDEM-01 | 100 concurrent identical nonstreaming requests: one runner invocation for chosen event loop/scope, one response identity |
| IDEM-02 | same key, modified temperature/store/truncation/tool settings: typed conflict, no stale output |
| IDEM-03 | same key, distinct authenticated principals: independent execution and no cross-principal read |
| IDEM-04 | same body but changed verified session/conversation revision: conflict or approved scoped new run |
| IDEM-05 | duplicate after completion: same response ID/created timestamp, no additional ResponseStore write |
| IDEM-06 | duplicate in-flight disconnect: shared execution lifecycle respects owner policy, no premature cancellation |
| IDEM-07 | original runner exception after effect reserved: unknown quarantine, no blind retry |
| IDEM-08 | runner returns `{"error":...}`: no `completed` or `stop` success |
| IDEM-09 | HTTP keyed SSE request: deterministic preflight before task starts |
| IDEM-10 | SSE tokens then agent exception: no success finish chunk, failure reason observable |
| IDEM-11 | SSE client closes while tool running: client disconnect is not inferred remote failure |
| IDEM-12 | simulate process crash after external effect but before ACK: no repeated write until read-back |
| IDEM-13 | 2 processes with same key + separate in-memory caches: integration must not claim cross-worker exactly-once |
| IDEM-14 | 30 workers provider 429 simultaneously: shared cooldown and finite bounded retries |
| IDEM-15 | oversized, empty, non-UTF8 and maliciously duplicated JSON fields: early rejection, no secret echo |
| IDEM-16 | 401/403 or denied tool approval: do not repeat under a new worker |
| IDEM-17 | stable trace/request/run/attempt IDs across retry, no raw auth in logs |
| IDEM-18 | 1000 in-flight capacity boundary: protect unknown effects, return bounded 503 |
| IDEM-19 | response-store concurrent writes/restarts: revision CAS; no inconsistent conversation mapping |
| IDEM-20 | final integrated SHA after combining selected PRs: test suite rerun against exactly that artifact |

## 5. Integration owner and rollback gates

One reviewer from API, one from agent-runner, one from security, one independent tester. Change only the selected API implementation in a single isolated integration branch. Merging distinct branches into `main` one by one without a combined dry-run is unacceptable at this conflict density.

A green review badge on a constituent PR does not establish combined compatibility. Preserve a known-good main SHA, schema migration plan, audit backup, explicit owner-authorized rollout and rollback. Externally committed tool effects cannot be undone by code rollback.

## 6. Source provenance

- PR #4 `gateway/platforms/api_server.py` current branch audit; cross-agent comment on #4 posted.
- PR #5 `gateway/platforms/api_server.py` current branch audit; cross-agent comment on #5 posted.
- PR #6 `gateway/platforms/api_server.py` current branch audit.
- PR #11 is stacked on #4 and also touches the API ingress.
- Repo: https://github.com/Podtverzhdeno/hermes-agent/pulls
- HTTP semantics and OpenTelemetry source protocol decisions remain subject to gateway owner review.

**Status at authoring:** none of IDEM-01..20 has been claimed as passing on the combined API integration. The 46 passing isolated metadata-inspector tests do **not** test this API contract.


**Contract evidence update:** 60/60 offline JSONL diagnostic tests passed separately; none of IDEM-01..20 API integration gates are thereby satisfied. The separate event auditor does not authenticate even self-declared `independent_verified` success. The API adapter must perform real scoped verifier lookup.
