# ADR GPT-API-002 — Exactly-once *admission*, stable replay identity and outcome uncertainty

**2026-11-22 source audit; PROPOSED, NOT DEPLOYED.** Applies to the Hermes fork's API, official upstream APIs and the GPT companion. A successful non-streaming reply or transport ACK is not evidence that all external tool effects committed. External effects cannot be made exactly-once by an HTTP cache alone.

## 1. Sources and lineage

Fork `main` was `7e9100901819ee44c16b4ddcb79a6bcb7909f591`. Several competing candidate branches independently edit `gateway/platforms/api_server.py`. These findings are tied to the following observed blobs, not names that may subsequently move:

| Candidate | Endpoint source blob | Key observations | Merge decision |
|---|---|---|---|
| `feat/gpt-bridge-observability-20261122` (PR #4) | `048c2ed7e5bc846d0c94bffce39fd7e6d34dd79c` | Chat namespace hashes raw Authorization + untrusted client session, caches stable Chat ID; **Responses uses raw unscoped key, maps conflicts to raw 500 and generates response ID outside cache** | BLOCK pending identity + replay proof |
| `fix/gpt-bridge-request-preflight-20261122-f9ac` (PR #11, stacked on #4) | `b4d78d0e9a1cc271f70552a6f9132d55e1c6fd24` | Useful early rejection for keyed SSE, but inherits PR #4 Responses issues | Port preflight test, not full handler |
| `feat/gpt-bridge-atomic-diagnostics-20261122` (PR #5) | `6dfe64f54a209220f5696b8188b8c0220e22f945` | Single-flight on same-loop key, but `gateway/idempotency.py` drops failed task in `finally`; re-execution after possible side effect | BLOCK pending durable uncertain-effect tombstone |
| `sdd/gpt-observability-2026-11-22` (PR #6) | `6a5335c49e5df0ee06395a447024106675f91751` | Stronger same-process unknown-effect tombstone, atomic task registration, but `"chat:"+idem_key` lacks authenticated principal and SSE queue is unbounded | Evaluate algorithms/test cases, not raw merge |
| official `NousResearch/hermes-agent` `main` | `api_server.py` `8e4213ac727d87ec1094f7b59b01bb1dcec133d2`; run store `423437733abb3e434f2990935899c9db6a05aaba` | Has `/v1/runs` with SQLite scoped reservations, run events, approvals and explicit unknown resolution. Legacy in-memory Chat/Responses cache may accept concurrent same key/different fingerprint; store may fall back to volatile memory. | **Investigate upstream run admission first**; preserve its broader API |

## 2. New source-backed P0 finding: duplicate Response identities from one cached execution

PR #4 (and unchanged stacked PR #11) caches `(result, usage)` for `/v1/responses`, but constructs `response_id = "resp_" + uuid...` **after** the idempotency lookup. On each replay, code also `self._response_store.put(response_id, ...)` and can `set_conversation(conversation, response_id)`. This means a single expensive model execution can leave multiple externally visible Response IDs and extra conversation pointer changes. Even without a second *agent* invocation, this is not stable keyed response replay. The Chat route separately returns original `completion_id`, `session_id`, and `created` from the cache; the discrepancy can be proved with one direct endpoint regression.

**Required invariant:** admitted `(principal, route, authorized session revision, key, fingerprint)` maps to an immutable `operation_id` and one stable public `response_id`, `session_id`, `created_at`, `effect_set` and transcript/snapshot revision. Retrying returns the *same logical result* and must not advance conversation/store state again.

## 3. New source-backed P0 finding: cross-principal key namespace across endpoints

PR #4/PR #11 `/v1/responses` calls `_idem_cache.get_or_set(idempotency_key, fp, compute)`, while `/v1/chat/completions` uses `scoped_idempotency_key(idempotency_key, request.headers.get("Authorization", ""), provided_session_id)`. Both refer to the same process-global cache, with two incompatible namespaces. A second authorized logical principal using an identical raw Responses key/body can receive a cached response associated with the first. There is also no route prefix in raw Responses keys, so a raw key can collide with arbitrary (hashed) Chat key strings if chosen deliberately; practical exploitability is unverified. A cache key **must** derive identity from a trusted authenticated principal and service-side authority, not just supplied text in HTTP headers; use HMAC over principal IDs where secrecy is needed.

PR #4/PR #11 also catch idempotency conflict and outcome-unknown as a generic exception in Responses, return HTTP 500 and may expose exception message. Clients cannot safely distinguish a key collision (never dispatched) from an uncertain already-dispatched effect (must reconcile). Common error contract: `409 idempotency_conflict`, `409 outcome_unknown`, documented `409/202 in_progress`, `503 durable_store_unavailable` for workflows demanding persistence, and generic redacted `500 agent_internal_failure` for truly unexpected errors.

## 4. Three atomicity boundaries, no false guarantees

**A. Admission:** atomically persist authenticated identity, key, fingerprint, session revision, run ID, deadline and budget *before* executing any effects. Unique DB constraint on `(authority_scope, route, idempotency_key)` plus transactional compare-and-insert. All steps have a monotonically increasing fence epoch. An in-memory coroutine lock is acceptable only as optimization inside one worker, never authoritative across processes/restarts.

**B. External effects:** persist intent (including effect key/provider target and scoped capabilities) in authoritative store and transactional outbox before dispatch. Dispatcher may run at least once; enforce provider-side idempotency when supported, otherwise use human-approved reconciliation/query. A lost ACK after dispatch means `UNKNOWN`, not `FAILED_NOT_EXECUTED`. A provider receipt proves only the operation acknowledged by that provider.

**C. Completion:** record verified result and public response identity in one durable state transition with evidence digest and session revision CAS. Replayed requests return the persisted identity and exact result/status, and never call `set_conversation()` again. Subscriber SSE cursor and run events can be retransmitted, but streaming transport does not itself commit effects. A client disconnect is not automatic cancellation/rollback.

### 4.1 State machine (data-plane)

```text
NEW --atomic reserve--> ADMITTED --lease/fence--> EXECUTING
        |                  |                         |
        +--payload drift--> CONFLICT                  +--effect intent--> EFFECT_RESERVED
        |                                                    |
        +--duplicate--> SAME_RUN_ID                           +--dispatch--> EFFECT_SENT
                                                                  |
                                       trusted provider receipt --+--> RECEIPT_OBSERVED
                                                timeout/partition +--> EFFECT_UNKNOWN
                                                                  |   [NO BLIND RETRY]
                        independent verifier <------------------+--> EFFECT_VERIFIED
                                                                      |
                                                                      v
                                            outcome+identity+CAS ---> VERIFIED_TERMINAL
```

`UNKNOWN` is not an automatic retry state. `CONFLICT` does not mean an already committed action should be undone. `NO_EFFECT` is a claim requiring trusted evidence if a write was ever dispatched.

### 4.2 Multi-agent shared budgets and parent/child safety

Use parent `run_id` + child `attempt_id` + effect-local idempotency ID. A supervisor restarting a child does not allocate a fresh global key for a previously dispatched write; the durable effect reference follows across child attempts. Capability attenuation: child scope = intersection(parent grants, task policy, resource owner scope). Budget reserve/debit must be atomic per task group. Human-controlled browser sessions cannot silently acquire a write lease via retries or arbitrary authorization headers. Concurrent revisions of one session require CAS; browser manual edits take precedence.

## 5. Required contract regression set

| Test | Input / fault | Expected outcome |
|---|---|---|
| R01 Same-key replay | Repeat a successful Chat request | Exactly 1 agent run, identical `completion_id`, `session_id`, `created` |
| R02 Stable Responses replay | POST identical Responses key twice | Identical `response.id` and `created_at`; exactly 1 stored response and 1 conversation pointer advancement |
| R03 Collision in-flight | Same key, two different bodies concurrently | Exactly one admitted operation, other typed `409`; never both effects |
| R04 Principal separation | Same Responses key/body by two distinct authenticated principals | No response/session/object crosses principals |
| R05 Cross-route isolation | Use identical key/body in Chat and Responses | Independent scoped operation IDs, no accidental cross-route cache hit |
| R06 Session ownership | Guess another principal's `X-Hermes-Session-Id` | Reject before loading history/cache; no existence leak |
| R07 Unknown after effect | Record externally visible write then lose receipt/raise | `NEEDS_RECONCILIATION` persists over retries and restart; effect count remains 1 |
| R08 Browser disconnect | SSE aborted while effect in flight | Status stays uncertain until trusted outcome, no second dispatch |
| R09 Stream with key | No durable streaming replay cursor available | Reject before calling model; type `400 unsupported_idempotency_mode` |
| R10 Capacity | Full cache / ledger or slow SSE consumer | Backpressure, bounded memory, safe non-success status; no eviction of unknown effect |
| R11 Persistence fallback | SQLite path read-only, corrupt or locked | Refuse durable-required write, do not silently use in-memory cache |
| R12 Store crash boundary | Kill process before/after dispatch/commit | Result remains either replayable or explicitly unknown, never silently replayed |
| R13 Stale worker | Old lease executes after reassignment | Fence/CAS blocks commit; uncertain effects reconciled |
| R14 Sensitive exception | Exception string contains fabricated secret marker | Response and normalized events redact marker; only error class/correlation ID |
| R15 Terminal mismatch | LLM reports `completed` but a tool receipt is missing | `AWAITING_VERIFICATION`, not success |
| R16 Auth rotation | Credential changes, old key reused | No stale cached response crosses new principal/session binding |
| R17 Loopback trust boundary | External local process sends forged events | Event rejected unless authenticated; observer cannot mint trusted provider receipt |

Run at least R01–R09 across **all candidates and upstream** using same test harness; run R01–R17 on merged exact SHA with at least two workers, then child process crashes and read-back. On owner-authorized Windows integration, add Chrome MV3 suspension/tab navigation and attached-CDP arbitration. Store every test's `commit_sha, environment, authority version, fixture digest, command, result, evidence_link`; CI success at unrelated SHA does not count.

## 6. Scoring and integration recommendation

Among legacy *candidate API* implementations **at source level only**, the safer failure-retention behavior is PR #6's in-memory unknown-outcome marker; PR #4/#11 have better Chat identity and preflight behavior; PR #5 offers a small single-flight cache but dangerously loses uncertain effects. None is an acceptable authoritative cross-process durable effect protocol as-is, and none should wholesale overwrite current upstream's `/v1/runs` APIs. Favor upstream run-admission primitives with scoped safe persistence, then targeted backports of observable behavior/closed loopholes. Re-score after tests; no invented reliability percentages.

**Gate:** Do not mark PR #4/#5/#6/#11 merge-ready until R01–R09 are red/green at exact branch commit and a preflight/upstream parity reviewer signs off. This ADR is not a live defect report and should not trigger unapproved auto-remediation.

## 7. Observation log

- **OBSERVED / fork baseline:** API cache race, stream bypass/false success, unbounded queue — see `2026-11-22-hermes-gpt-convergence.md`.
- **OBSERVED / PR #4 and PR #11:** Responses key unscoped, cache returns `(result,usage)` but response ID and store mutation occur after replay, exceptions mapped to generic raw 500. PR #4 review comments recorded.
- **OBSERVED / PR #5:** failed computation removes in-flight reservation (unknown effect can retry). PR #5 review comment recorded.
- **OBSERVED / PR #6:** same-process uncertainty tombstone but no authenticated multi-principal key, SSE remains unbounded. PR #6 review comment recorded.
- **OBSERVED / official upstream:** durable `/v1/runs` scoped SQLite reservation available, but `durable=false` when memory fallback; legacy compatibility cache retains concurrent-key risks.
- **NOT OBSERVED:** deployed browser extension, user-local logs, production duplicated writes, and exact remote API client behavior under these failures. The scoped Local_WorkSpace connector has no Hermes source root.

## 8. Public source pointers

- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_openai_routes.py
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_run_idempotency.py
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server_runs.py
