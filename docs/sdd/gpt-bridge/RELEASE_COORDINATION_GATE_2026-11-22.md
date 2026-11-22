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

Local test evidence: 27 offline stacked guard tests passed under Python 3.13, including invalid inventory, stale parent, divergent body, missing proof, nested overlap, fail-closed CLI, pagination, no redirect, exact HEAD checks and no write requests. Another comparative generic scanner prototype had 18 passing offline tests, but is intentionally NOT added here due to PR #14 ownership. The total 45 passing tests are local simulation, not end-to-end Hermes/browser or GitHub CI proof. Full Python 3.11 packaging/CI at this PR's exact commit still required.

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


## 11. Additional hardening, exact-SHA evidence and sourced transport notes

The remote branch was updated after the initial review to reject malformed GitHub PR and comparison response shapes before any green result and to detect a cycle in stacked PR base dependencies. Even two branch refs temporarily pointing at identical commits must not make a circular stack appear mergeable. Three new negative tests cover the above; the offline local comparison suite is now 45/45 passing (27 stack guard tests in this PR, 18 generic prototype tests kept local). These are source-level and offline test claims; CI must run on the **latest** commit SHA, not the original PR creation SHA.

API workers should distinguish:
- OpenAI Responses background mode provides provider-managed long-running response IDs and retrieval in supported cases. This is different from persisting Hermes tool outcomes and must not silently substitute for an action ledger. See https://developers.openai.com/api/docs/guides/background .
- OpenAI webhook delivery may repeat; verify webhook authenticity before parsing and deduplicate by the documented event identifier, with durable inbox acknowledgment. See https://developers.openai.com/api/docs/guides/webhooks .
- Chrome MV3 can terminate idle service workers; behavior depends on browser version and active APIs, and chrome.debugger sessions have extended lifetime rules since Chrome 118. Never depend on an in-memory interval as a durable worker. See https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/ .
- OpenTelemetry GenAI tool spans provide a model for instrumentation without logging sensitive arguments/results by default. The error.type attribute should remain low-cardinality. See https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md .

The practical product objective should be stated as a measurable rollout gate: in a representative fault-injection suite, every accepted run has an explainable last trusted state and explicit unknown status on ambiguous effects; no false SUCCEEDED, no duplicate unapproved effect, no irreversible write on stale fence, and no release approval from stale CI evidence. This is a **proposed criterion**, not an achieved production SLO.



## 12. Live GitHub stacked PR incident — exact parent drift

Read-only connector queries around 2026-11-22T10:55Z, repeated against exact current refs, found:
- PR #17 child HEAD f3e313f7dcbc36ff9a1399d78387e7d60730fefc vs PR #12 parent HEAD 5812f615d0deef4cab7fe9c29c30e0c5086f1fd4: GitHub compare returned status=diverged, behind_by=8, ahead_by=14. Therefore #17 lacks eight current parent commits at that snapshot. Invalidate any acceptance evidence that assumes it includes the latest #12; reconcile and run exact combined-head tests. A targeted GitHub PR #17 comment recorded this finding (comment id 7078121235). This does not prove a production failure or authorize merging.
- PR #23 child HEAD fac05bb452f4aee70fc02d421376f85a64b9a4ee vs #12 parent HEAD 5812f615d0deef4cab7fe9c29c30e0c5086f1fd4: status=ahead, behind_by=0, ahead_by=1. No missing-parent ancestry evidence at that pinned pair; NOT a release pass.
- PR #11 child HEAD b104938fea428669fa6f11a513d7c42de8254193 vs #4 parent HEAD f2373ed5551fe47168b014b08d63560a6bb0d68a: status=ahead, behind_by=0, ahead_by=6. NOT proof that the gateway can merge safely.
- PR #10 targets the intentionally isolated snapshots/autopilot-ledger-6c0d2e-20261122 branch rather than an open PR. Its PR description explicitly documents that choice. PARENT_NOT_IN_SNAPSHOT means manual graph review for eventual integration, not an accusation of bad code.

Open Draft PR count reached 30 in the later connector scan. These are deliberately *revision-pinned, time-local findings*. Re-run all comparisons after parent/child updates; do not promote stale findings into global status.



## 13. Upstream feature parity and current browser extension evidence

The inspected fork main is version 0.6.0. Upstream Hermes v0.23.3 (released Nov 19, 2026) ships functionality that should NOT be reinvented without a migration audit:
- Its durable Kanban stores tasks and handoffs and has exact-PR completion contracts, verifying required GitHub checks for the current revision with independent acceptance. https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md
- Its API distinguishes canonical durable admission identities from legacy process-local idempotency and has /v1/runs, typed cancelled/error/incomplete terminal responses, and controlled streaming replay. Therefore old-fork "reject keyed SSE" applies only while canonical durable admission is unavailable, not to every future Hermes version. https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md
- Community Hermes Browser Extension v0.4.1 (MIT) already supports explicit page-context consent, per-tab and per-controller leases, capability diagnostics with state/reason/source/age, Browser Context Protocol v2 and deliberate **no automatic resend** after an uncertain HTTP response. Firefox has restricted control. Its companion-plugin requires a compatible Hermes gateway; this old fork cannot be presumed compatible. Extension v0.4.1 reports that it does not use nativeMessaging. Prefer leveraging its compatible permissions and browser protocol rather than inventing broad new transport privileges. https://github.com/abundantbeing/hermes-browser-extension/blob/main/README.md

Security finding (static, configuration-contingent): The old fork gateway _check_auth explicitly returns success when API_SERVER_KEY is absent, yet API_SERVER_HOST can be configured for non-loopback binding. This can expose tool-capable APIs without authentication if a user deploys it with an externally reachable listener. The default host is loopback; no evidence that this user's instance is exposed. Gate any non-loopback bind on strong authentication and restrict CORS/origin; do not merge broad network exposure into gateway candidate fixes.

### Owner-reviewable periodic monitor

Added .github/workflows/gpt-stack-guard.yml on this isolated Draft PR:
- Offline Python 3.11 unit tests on relevant PR changes (no secrets).
- An optional 4-hour schedule or workflow_dispatch read-only GitHub PR graph scan using read-only token, posting structured JSON artifact retained 14 days.
- No automatic code writes, merges, or remediation. Non-green audits fail the job, not silently certify safety.
- Scheduled GitHub Actions only run from the default branch after an owner-reviewed merge; this workflow is **not yet running periodically from the draft branch**. Four-hour checks are a recency/cost compromise, not continuous per-second detection.

Priority after PR #29 review: migrate to modern Kanban and canonical API admission where compatible; then instrument exact authorized tool effects and independent verification. The extra scheduled scanner does not replace an always-running local Hermes/GPT runtime watcher; this was not deployed because the local Workspace connection terminated.


## 14. Cross-field GitHub compare evidence consistency hardening

A final reviewer check found that it is unsafe to interpret behind_by=0 as clean ancestry if GitHub compare status=ahead/behind/diverged/identical and ahead_by/behind_by values are internally contradictory or missing. An incomplete/mock JSON response must not produce an apparently positive ancestry verdict. The read-only stack guard now binds together three fields: exact status, ahead_by and behind_by. Valid pairs are identical=(0,0); ahead=(ahead>0, behind=0); behind=(ahead=0, behind>0); diverged=(ahead>0, behind>0). All other combinations downgrade to INVALID_COMPARE_EVIDENCE, never success. Four extra offline tests cover contradictory diverged, missing ahead_by, invalid identical and legitimate identical.

Latest deterministic local Python 3.13 result: **45/45** tests including 27 published ancestry-guard tests and 18 deliberately unpublished generic comparative tests. Because this SDD edit creates another head SHA, any earlier GitHub CI success is historical and must not be presented as the latest SHA's test status. A final exact-head check after publication is mandatory.


## 15. 100-agent graph regression (offline simulation, not live throughput)

Two additional regression tests synthesize 100 distinct agent-owned PRs arranged into 10 stacks with 90 parent/child edges. Under complete consistent synthetic compare evidence, analyze() must produce the same sorted report regardless of inventory order, while its verdict still says NO_STACK_ISSUES_NOT_MERGE_APPROVAL. A second fixture injects a stale-parent compare result for just one of the 90 edges: even in a 100-agent inventory the finding is exactly PR #52, parent PR #51, PARENT_ADVANCED_REBASE_REQUIRED, with nonzero review status. This is useful for coordination scale but does NOT measure CPU/memory/SLA or any actual Hermes worker concurrency.

Current local Python 3.13 combined offline suite: **45/45** (27 published stack-guard checks, 18 separate generic scanner prototype checks deliberately omitted from this PR to preserve #14 ownership). Exact-head GitHub CI must independently pass after this final revision; do not quote earlier commit checks as current evidence.


## 16. Second concurrent-agent integration snapshot (32 open PRs)

A subsequent fresh read-only GitHub snapshot found **32 open PRs** (versus 30 in the earlier sampling) and four open PRs targeting other open PRs' feature branch plus one intentionally isolated snapshot target. Exact pinned compare results:

| Child -> parent | Parent SHA | Child SHA | GitHub compare | Outcome |
|---|---|---|---|---|
| #32 -> #2 | 73fa315b1d8b8158c884bbed0c7291136ef30f3f | 1b3224dc3bcdd6246ca7e6b57684af0b1cbf8872 | diverged; behind=5; ahead=3 | PARENT_ADVANCED_REBASE_REQUIRED; GitHub comment 7078294357 |
| #23 -> #12 | 89f56daeb2dc0d790e1e27c08a4453fb923a42ca | 36d5c236f99f3b4043ec5a8b2efa6153ca2b760b | diverged; behind=7; ahead=28 | PARENT_ADVANCED_REBASE_REQUIRED; GitHub comment 7078294033 |
| #17 -> #12 | 89f56daeb2dc0d790e1e27c08a4453fb923a42ca | b3bd8ce2c64e22694bbd008986e0c6857b2b73cc | diverged; behind=15; ahead=34 | Previously warned on #17; still behind after further commits |
| #11 -> #4 | f2373ed5551fe47168b014b08d63560a6bb0d68a | 6c529778fb69107986f47310612b02fe7aab74bc | ahead; behind=0; ahead=9 | No ancestry deficit at pinned SHA, NOT merge approval |
| #10 -> snapshot branch | intentionally separate | exact history to be reconciled later | parent PR not in open-parent inventory | No automatic main-target integration |

These values may become stale immediately under parallel work: always report both pinned commit hashes and when measured. A review comment records an actionable observation; it does not take ownership of another agent's branch or prove a runtime failure.

**Important coordination lesson:** a code change on a child branch can increase both ahead_by and behind_by over time while the parent's separate owner lands additional changes. Even a child with hundreds of green unit tests may have to rerun on an integrated merge candidate. The release reviewer must never count isolated child check runs as a proxy for integration tests. No auto-fix that force-pushes to another owner's branch is permitted.
