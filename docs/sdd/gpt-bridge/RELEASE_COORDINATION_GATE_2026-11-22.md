# SDD — Hermes / GPT: Causal Observability, Safe Recovery, and Multi-Agent Integration

Revision: 2026-11-22. Draft design + isolated read-only engineering contribution. NOT production acceptance.
Source baseline: Podtverzhdeno/hermes-agent main at SHA 7e9100901819ee44c16b4ddcb79a6bcb7909f591, older fork release 0.6.0.
Owner scope: scripts/gpt_pr_stack_guard.py, tests/scripts/test_gpt_pr_stack_guard.py, this document. No main branch, live CDP, browser session, Hermes daemon, task dispatcher, or gateway source changed.

## 1. Problem statement and observed facts

User objective: tens of independently running GPT/Hermes agents whose every real state transition, pause, external effect, and interruption can be explained, reconciled and verified; automatic repairs permitted only if proven safe under owner policy.

An LLM answer does not prove task completion; SSE [DONE] proves stream termination at most; heartbeat does not prove progress; tool transport failure does not prove a remote side effect did not happen; a successful check for SHA A cannot certify SHA B.

Two GitHub source inspections on 2026-11-22 observed 12 then 16 open draft PRs, with rapidly moving heads. Not a globally transactional inventory. Competing implementations edit the same gateway/platforms/api_server.py (#4/#5/#6/#11). Stacked #11 targets #4, and #10 targets an Autopilot-parent branch (which subsequently changed). Packaging pyproject.toml and tools/browser_tool.py are also contested. Five proposed observer implementations in #8/#9/#12/#13/#16 threaten conflicting state semantics.

Static source findings on main:
- Malformed root JSON array or non-object messages can reach .get() without type checks, potentially returning 500 rather than 400; stacked #11 proposes preflight validation.
- stream=true enters agent dispatch before non-stream Idempotency-Key cache path; a keyed stream may trigger a second external effect under retry. Reject keyed stream until a durable resumable protocol is implemented.
- SSE handler catches and suppresses backend exceptions and then writes ordinary stop/[DONE]; a client can incorrectly report successful completion. PR #4 and #6 offer competing repairs.
- Non-stream handler can encode a run error as successful 200 completion text, not a trustworthy terminal outcome.
- Process-local idempotency caches cannot enforce exactly-once external effects across crash/restart or replicas.
- A disconnect attempts to interrupt a synchronous agent executing in an executor. This is best-effort, not proof a tool stopped before an external write.

Evidence limitations: Local_WorkSpace MCP returned Session terminated. No live user-owned Windows browser extension or CDP session, local bridge, production Hermes logs, authenticated provider effects or running workers were inspected. Connectivity canaries from another point in time do not establish continuous operation.

## 2. Architecture decisions

ADR-001 — Single lifecycle authority. Review current upstream NousResearch/hermes-agent Kanban (v0.23.x) as the canonical dispatcher/task/lease/worker authority, rather than creating a second Autopilot scheduler from #1/#10. Reuse approval/effect-verification design proposals through a narrow adapter after real parity testing.

ADR-002 — One canonical event contract, multiple projections. Diagnostic observers are read-only, not authorities to set succeeded. Canonical task state resides in trusted control-plane; independent verifier owns completion evidence. Distinct gpt_bridge, gpt_companion, gpt_extension and hermes_gpt_bridge stores may be competing implementations until one contract is selected.

ADR-003 — Intent before effects. A trusted adapter commits normalized target, action digest, scope, approval and idempotency identity before mutating a remote resource. If a crash occurs after intent and before acknowledgment, mark OUTCOME_UNKNOWN and reconcile via provider receipts/read-back. Never blind-replay an uncertain write. Database transactionality alone is not exactly-once externally.

ADR-004 — Authenticated owner STOP. STOP increments a project revocation generation; the tool adapter checks that generation and fencing epoch immediately before every new effect. A stale agent cannot authorize itself by prompt. Active tools may still complete after cancellation; those effects must be reconciled.

ADR-005 — Per-agent isolation. Each worker has distinct task/run/attempt, role, lease/fence, input and source SHA, scoped worktree, budget inherited from parent DAG, per-capability ownership and time-limited privileges. Review by a different trusted principal. No global credential sharing or self-approved high-impact changes.

ADR-006 — No duplicate collision service. PR #14 (scripts/hermes_gpt_coordination_audit.py) is the proposed owner of generic PR file/capability collision audits. Its main-base PR filtering does not replace exact stacked-parent ancestry verification. This workstream contributes only the complementary stacked PR graph and drift guard, not another generic auditor.

ADR-007 — Explicitly separate API from browser. Official supported APIs/SDKs are preferable for unattended work. A Chrome extension is optional and requires owner consent and origin-scoped permissions. Content scripts/DOM status cannot certify external effects. Preserve externally attached user-owned CDP browser; recover from MV3 service-worker shutdown; no session cookies, prompts, credentials, screenshots or raw tool arguments in default telemetry.

## 3. Atomic event and incident contract (design proposal, not runtime implementation)

Required event metadata v1: schema_version, event_id, project_id, task_id, run_id, attempt_id, source_id, source_epoch, source_seq, trace_id, span_id, parent_span_id, causation_event_id, event_kind, phase, lease_fence, target_revision, effect_id, reason_code, occurred_at_utc, receiver_generated_received_at_utc, evidence_refs.

Validation: authenticated sender identity bound outside envelope; closed metadata-only allowlist, bounded size, strict types and enum values, nonzero W3C trace/span hex, monotonic sequence per sender epoch; identical replay accepted, conflicting replay rejected; source-local gaps reported, cross-source causal order requires edges rather than arrival time. Never trust a worker-supplied received timestamp, claimed verifier authority, or an arbitrary completed event.

No raw prompts/messages, user identity, token values, authorization headers, tool params, browser DOM, model output or raw exceptions in operational logs. Use opaque references and keyed hashes only when needed for correlation. Local WAL/log-chain guards against some accidental corruption, not malicious tamper without external anchoring. When buffer/volume is exhausted, declare OBSERVABILITY_DEGRADED; keep critical cancellation functioning.

Canonical incident record:
- incident_id and detection time
- current project/task/run/attempt/fencing epoch and exact input/source SHA
- last trusted durable transition and last observed heartbeat/progress
- observed symptom and timestamp, stage/deadline
- candidate root causes, confidence, contrary evidence, verified/unverified distinction
- external effect IDs, receipts, outcome unknown or reconciled
- safe operator action, approval requirements, owner/next check
- proposed fix SHA, regression tests, verifier SHA and rollback.

Never claim root cause simply because an LLM narrative supplies one. A missing heartbeat might mean disconnected connector, paused service worker, rate limit, process crash or tool wait; those remain hypotheses until corroborated.

## 4. Lifecycle and permission invariant C1

ACCEPTED -> CLAIMED (CAS lease + global budget) -> RUNNING
RUNNING -> WAITING_APPROVAL (exact digest/expiry/target)
RUNNING -> EFFECT_RESERVED (trusted committed intent)
EFFECT_RESERVED -> EFFECT_CONFIRMED (provider read-back) OR OUTCOME_UNKNOWN -> NEEDS_RECONCILIATION
RUNNING -> REPORTED_DONE -> VERIFYING -> VERIFIED -> SUCCEEDED
Each active state -> CANCEL_REQUESTED; prevent new effects immediately, reconcile in-flight action, then CANCELLED.

A task cannot be SUCCEEDED unless required independent evidence exists for the exact intended revision, final required checks are successful (not pending/skipped/neutral), source effects are settled, and a current policy-authorized writer commits success. Lease timeout does not prove process death. Fencing must be enforced at tool entry, not just within the planner.

## 5. Failure taxonomy, cause verification and safe recovery

| Reason | Grounded observation | Default policy |
|---|---|---|
| INVALID_INPUT | Malformed schema before dispatch | HTTP 400; no agent work |
| SSE_FALSE_SUCCESS | Agent task exception masked by finish/stop | Typed stream failure; negative test |
| STREAM_DISCONNECTED | HTTP transport closed while tool in flight | Best-effort interrupt; effect read-back |
| IDEMPOTENCY_UNCERTAIN | Same key but remote effect receipt missing | No blind repeat |
| WORKER_UNRESPONSIVE | Last trusted heartbeat expired | Check actual process and lease; cause unknown |
| ALIVE_NO_PROGRESS | Heartbeats continue but no stage progress | Inspect deadlines, tool waits, locks, quota |
| TRACE_GAP | Missing producer seq, conflicting duplicate | Backfill; mark incomplete |
| LEASE_FENCED | Old epoch tries a tool action | Reject at adapter |
| APPROVAL_PENDING | Exact action authorization absent | Human decision or block |
| EXTERNAL_OUTCOME_UNKNOWN | Committed intent, no independently confirmed result | Reconcile provider |
| CI_STALE_SHA | Checks run for prior head | Revalidate exact merge SHA |
| PARENT_ADVANCED_REBASE_REQUIRED | Parent head not ancestor of stacked child | Rebase/retest, invalidate prior evidence |
| PARENT_ANCESTRY_UNVERIFIED | Parent/child graph lacks pinned compare proof | Block integration pending proof |
| PARENT_NOT_IN_SNAPSHOT | Cross-base PR lacks represented parent | Require manual branch ancestry audit |
| STOP_PENDING | Cancellation cannot establish effect outcome | Prevent new effects, reconcile pending |
| OBSERVER_UNAVAILABLE | MCP/session/telemetry disconnected | Degrade confidence; do not infer Hermes failure |

## 6. Complementary stacked PR ancestry guard (implemented here)

The read-only scripts/gpt_pr_stack_guard.py queries ALL open PRs irrespective of base, unlike main-target-only PR filters. For same-repo child base matching another open PR's head ref it:
1) verifies each child HEAD SHA before and after fetching PR file lists;
2) compares exact parent HEAD SHA to exact child HEAD SHA, rejecting missing/stale evidence;
3) reports parent moved from child's ancestry, stacked same-file edits and unknown parent branches;
4) fails closed on malformed entries, duplicate heads/numbers, unsafe paths, pagination cutoff and GitHub access errors;
5) refuses redirect of an auth-bearing GitHub request to a different host and does not issue mutating API requests.

Examples (read only):
    python scripts/gpt_pr_stack_guard.py --repo Podtverzhdeno/hermes-agent --output stack-report.json
    python scripts/gpt_pr_stack_guard.py --snapshot saved-revision-pinned-fixture.json
    python -m pytest tests/scripts/test_gpt_pr_stack_guard.py -q -o addopts=''

Exit 0 = NO_STACK_ISSUES_NOT_MERGE_APPROVAL; exit 1 = REVIEW_REQUIRED; exit 2 = AUDIT_INCOMPLETE. No output implies it can merge. GitHub has no globally atomic PR snapshot in these separate API calls: rerun against exact candidate refs just before a merge, perform final merged-tree CI, and re-check policies.

Local test evidence: 18 offline stacked guard tests passed under Python 3.13, including invalid inventory, stale parent, divergent body, missing proof, nested overlap, fail-closed CLI, pagination, no redirect, exact HEAD checks and no write requests. Another comparative generic scanner prototype had 18 passing offline tests, but is intentionally NOT added here due to PR #14 ownership. The total 36 passing tests are local simulation, not end-to-end Hermes/browser or GitHub CI proof. Full Python 3.11 packaging/CI at this PR's exact commit still required.

## 7. Multi-agent governance and integration queue

Capability owner candidates:
- Generic file collision inventory: PR #14, after independent review.
- Stacked parent ancestry: this draft PR, no general audit duplication.
- GPT API parse, SSE, idempotency: select ONE integrated handler from #4/#5/#6, apply compatible #11 preflight.
- Canonical task lifecycle: upstream Hermes Kanban, migrate old fork deliberately.
- Effect verification: trusted, narrowly scoped adapter with reconciliation.
- Observer: select canonical schema, make existing #8/#9/#12/#13/#16 compatible readers or reject alternatives.
- Browser connector: reconcile #13 and #15, preserve externally owned browser.
- Packaging: single integrator resolves pyproject.toml changes.
- Final verification: independent, revision-bound exact-head CI/check provenance and owner acceptance.

Each task owns immutable work item, capabilities, changed paths, base SHA, proposed head SHA, budget, risk class, expected artifacts, negative tests and cancellation semantics. Competing agents may investigate independently but only one designated integrator may write canonical handlers. No auto-merge of a Draft PR on local tests or model assurance.

## 8. Prioritized engineering decisions (qualitative scores)

Scores are proposed reasoning, not measured production performance. Impact / feasibility / integration risk each 1–5.

1. P0: prevent false success and keyed SSE duplicate actions (5/5/2) — integration of existing gateway PRs.
2. P0: collision + stacked ancestry + exact revision verification (5/5/1) — this guard complements PR #14.
3. P0: one Kanban lifecycle and enforced revocation STOP (5/3/3) — migration project, not second scheduler.
4. P0: durable effect intent/receipts and reconciliation (5/3/4) — must precede autonomous writes.
5. P1: causal event envelope, typed failure reason codes and read-only operator timeline (4/4/2).
6. P1: heartbeat/progress/lease separated, bounded retries and whole-DAG quotas (4/4/2).
7. P1: narrow agent capability ownership, worktree isolation, security tests (5/3/3).
8. P2: optional owner-authorized Chrome MV3 extension adapter after actual runtime/source inspection (4/2/4).
Reject: second independent scheduler, universal unsupported UI scraping, arbitrary credential capture and automatic merging based on a chatbot response.

## 9. Failure-injection acceptance matrix

Inject: non-object JSON/message; empty stream key; keyed stream retry; two concurrent duplicate requests; idempotency collision; lost SSE connection mid external effect; worker crash before/after remote call; ambiguous receipt; stale lease after reassignment; healthy heartbeat with zero progress; out-of-order, duplicate and missing event IDs; invalid producer clock; log disk full; telemetry corruption; no trusted verifier; stale/skipped CI; user STOP during tool action; expired approval; malicious untrusted content claiming owner permission; 30-agent file contention; parent stack branch moves after child tests; GitHub pagination/API 429; MV3 service worker sleep, CDP detach and externally attached browser cleanup. For every negative test: no false SUCCEEDED, no unauthorised tool mutation, evidence retained, safe next action explicit.

Release requires independently reviewed source, complete branch inventory, provenance-bound expected checks at exact merged result SHA, Python 3.11 full tests, wheel packaging if modules added, authority-separated verifier, no unresolved unknown external effects, rollback plan and owner approval. Diagnostic audit exit 0 cannot replace any of those gates.

## 10. Reference ledger

Sources and further verification:
- Repository state: https://github.com/Podtverzhdeno/hermes-agent
- Generic PR #14: https://github.com/Podtverzhdeno/hermes-agent/pull/14
- API alternatives: pull/4, pull/5, pull/6, stacked pull/11
- Chrome browser alternatives: pull/13, pull/15
- Upstream Kanban: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- OpenTelemetry GenAI conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Google SRE monitoring: https://sre.google/sre-book/monitoring-distributed-systems/
- Temporal activity semantics (comparison, not adoption): https://docs.temporal.io/activities

This SDD records the complexity and quality bar for subsequent workers. It does NOT claim persistent autonomous monitoring is deployed or that a chat instance will operate after the turn ends.
