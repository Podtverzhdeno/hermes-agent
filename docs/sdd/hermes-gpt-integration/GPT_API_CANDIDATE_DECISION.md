# GPT API Integrator Candidate Decision Record

Date 2026-11-22. Status: PROVISIONAL SOURCE-ONLY evaluation; do not merge or deploy based on this record.
Repo: Podtverzhdeno/hermes-agent main baseline 7e9100901819ee44c16b4ddcb79a6bcb7909f591.

## 1. Problem

Three independent Draft PRs target the same gateway/platforms/api_server.py. They propose overlapping single-flight caching, failure semantics, SSE, observability and security improvements. Simultaneously merging them is not a valid integration strategy. The appropriate process is to compare behavior against the same acceptance contract and select one implementation, importing unique tests only after review.

## 2. Re-inspected implementation inventory

| Candidate | Source revision inspected (blob SHA) | Behavior / strengths | Important blockers |
|---|---|---|---|
| PR #4, feat/gpt-bridge-observability-20261122 | gateway/gpt_bridge_diagnostics.py blob 6bc3dee65deabb06bc917564a9fa79c484ee92ac | Request fingerprint of full body, caller/session-scoped key, 409 in-progress, 422 mismatched key, short-lived UNKNOWN tombstones, diagnostic event logger; tests include SSE, logs, CORS | UNKNOWN tombstone expires after default 300 s and can be evicted by size cap; remote effect can be retried after tombstone expiry; no durable cross-process journal |
| PR #5, feat/gpt-bridge-atomic-diagnostics-20261122 | gateway/idempotency.py blob bf98f9ff6422dc0a318c0e9ba35a572ae2932690; API adapter blob 6dfe64f54a209220f5696b8188b8c0220e22f945 | Bounded in-flight single-flight with shield, full-body fingerprint, both endpoints now use per-adapter cache, full Responses result replay, sanitized HTTP 500; source corrections made after review | Failed compute deletes in-flight reservation and caches only successes; a tool may have committed before exception, thus immediate same-key retry can repeat effect. Existing test "error is not cached" should be reconsidered. TTL/restart remain unsafe for effects |
| PR #6, sdd/gpt-observability-2026-11-22 | API adapter blob 6d5e7b526a1249683ee0107e5bc7553f5c7c60ff | Per-adapter single-flight and full-response identity, rejects keyed streaming until replay-safe, treats failed tasks as OUTCOME_UNKNOWN and refuses same-key replay, trace IDs, CORS, auth gate, large targeted test inventory, Responses alias tests | UNKNOWN tombstones occupy bounded 1000-entry cache indefinitely until restart; no protected reconciliation API; endpoint-prefixed key lacks explicit caller/principal namespace; process-local only, cross-restart unguarded; full CI and upstream compatibility required |

Important re-review: The original PR #5 Responses handler had a global cache/subset fingerprint and an error string echo; a later source read shows those two problems corrected. Its remaining after-exception retry ambiguity is a DIFFERENT issue. Avoid stale diagnosis.

## 3. Provisional assessment rubric

Use 1 (weakest) to 5 (strongest) for planning only; this is NOT measured reliability.

Weights:
- 35% prevention of ambiguous external effect replay;
- 20% consistency across public GPT API endpoints and response identity;
- 20% breadth of relevant regression tests;
- 15% bounded operational failure mode and recoverability;
- 10% ease of integration with modern Hermes upstream.

| Candidate | Effect safety | API consistency | Test breadth | Operational bounds | Upstream fit | Weighted total / 5 |
|---|---:|---:|---:|---:|---:|---:|
| PR #4 | 3 | 4 | 3 | 3 | 3 | 3.15 |
| PR #5 | 1 | 4 | 4 | 4 | 3 | 2.85 |
| PR #6 | 4 | 4 | 5 | 2 | 3 | 3.80 |

Scores reflect read code + test INVENTORY, not an actual common test-run pass rate. The most important concern is safety after a provider/tool exception. Short-lived cache tombstones are helpful but not a guarantee against a remote commit followed by a lost local acknowledgment.

**Provisional integration preference: PR #6, conditional on fixing/or explicitly accepting capacity and principal scope and on passing the same tests on exact HEAD.** PR #4 contributes caller/session key derivation and a strict in-progress contract; PR #5 contributes a clean separate idempotency module and additional endpoint tests. These features can be reused selectively by an integration owner after design reconciliation. Do not merge entire rewrites together. If a common E2E test shows a different candidate materially better, this preference must change.

## 4. Non-negotiable common safety tests

T1. 100 concurrent identical same-key calls => underlying model/agent invocation at most one per adapter process; stable response/session IDs.

T2. Same idempotency key, changed payload or supplied session => conflict without invoking model.

T3. Different auth principals sharing a service => no accidental response/session cross-exposure; specify what a "principal" actually is.

T4. Agent performs a synthetic irreversible-effect receipt, then throws. SAME KEY retry must return OUTCOME_UNKNOWN or previously recorded receipt, never invoke effect twice.

T5. Agent raises before any effect reservation. Retry policy must be explicit and use trusted evidence, not generic exception text.

T6. Process dies at reservation boundary, after remote commit and before ACK; durable recovery must not duplicate mutation.

T7. Client cancellation does not cancel a running thread or remote tool by assumption; no false confirmed-cancel status.

T8. SSE yields a chunk, then throws: terminal error and no normal "stop" success. Streaming key either rejected or made replay-safe.

T9. Responses API returns identical IDs on retry and consistent response alias/durable state even across DB error.

T10. Capacity: 1000+ unique uncertain effects must not violate safety; operators can reconcile safely and capacity behavior is bounded/documented.

T11. All public errors and logs are content-free by default: no raw prompt, token, auth header, cookie, tool argument, exception text or sensitive response.

T12. Bind non-loopback without credentials must fail; a localhost listener is not equivalent to owner authorization for mutating tools.

T13. Exact HEAD PR and post-merge queue SHA tests, not a previously successful cancelled/skipped job.

T14. Run same tests after porting to a fresh isolated modern Hermes v0.23.3 canary, with worker-lane and Windows/WSL integration.

T15. Rate-limit storm under 30/100 simulated agents; one retry budget authority across gateway, extension and provider; coordinated backoff with jitter and an explicit retry deadline.

## 5. What a completed integration MUST prove

- The canonical Hermes Kanban remains the task/run authority; no duplicate Autopilot scheduler created.
- All request/result/effect identities are correlated; default no private content in diagnostics.
- At most one effect is authorized under a stable action key/fence; unknown remote outcome is persisted and reconciled.
- No endpoint can report success on interrupted/failed agent execution.
- The selected implementation is source-compatible with current upstream, with no API semantic regression.
- A merge queue (if active) runs checks on the actual merge_group commit as well as PR heads.
- Recovery does not require the original ChatGPT UI session to remain alive.

## 6. Open questions with an evidence-based disposition

1. What should happen when 1000 uncertainty tombstones occupy the process cache? Reject new mutations and enter controlled recovery, not delete uncertainty arbitrarily. The eventual durable effect ledger needs a reconciliation procedure with authenticated identity and remote receipts.
2. Who owns a cache key: shared API deployment, tenant, independently authenticated user, or single project? Declare the credential model. A caller-supplied header by itself is not identity.
3. What is the public status code for mismatched and in-progress keys? Freeze a versioned contract and conformance tests; avoid relying on one arbitrary draft's precedent.
4. Can the API adapter promise exactly-once external actions? No. Local process cache cannot survive host restart or remote ambiguity. It can guarantee only limited same-process single-flight, with explicit uncertain outcomes.
5. Does a browser extension substitute for an authenticated worker? No. It is an optional read-only companion; native host actions require trusted policy.

## 7. References

AWS durable retries and external effects: https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/
AWS retry storm mitigation: https://docs.aws.amazon.com/wellarchitected/latest/framework/rel05-bp03.html
Temporal Activity idempotency/retry: https://docs.temporal.io/activity-definition
GitHub required checks bound to latest SHA: https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
GitHub merge queue: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue

This is a planning decision, NOT permission to merge, and scores must be revisited after independent end-to-end tests.
