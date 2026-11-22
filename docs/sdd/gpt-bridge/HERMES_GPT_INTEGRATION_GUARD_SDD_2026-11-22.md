# Hermes × GPT — Multi-agent integration guard SDD

**Date:** 2026-11-22. **Status:** proposed / read-only implementation; not deployed to the user's Windows host. **Authority:** GitHub for PR integration; upstream Kanban for runtime tasks only after verified canary; a future trusted effect gateway for external writes.

## 0. Evidence ledger and honest boundaries

**Observed (O):** The owner's repository is `Podtverzhdeno/hermes-agent`. At inspection, `main` was SHA `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (commit 2026-04-01). The inspected open PRs were #1–#12. Distinct drafts #4/#5/#6 independently edit `gateway/platforms/api_server.py`. PR #11 is stacked on #4. #10 is stacked on #1, but its base SHA differed from the newer #1 head when examined. #8/#9/#12 create distinct observer packages. Several branch tests were pending/in progress/cancelled; a focused #6 regression success does not certify combined gateway behavior.

**Unknown (U):** Actual installed ChatGPT/GPT browser extension source, Windows version and runtime, permissions, live trace retention, local connector state, current Obsidian document revision. `Local_WorkSpace` failed with `Session terminated`; another read-only workspace probe returned a 404. Do not report live tasks as watched or local files as modified. This branch contains **no browser monitoring, model calls, tool writes, user-session automation or runtime effect gateway**.

**Hypothesis (H):** Causes of user-visible stalls are to be inferred only after acquiring trustworthy stage-specific evidence. A browser timeout alone does not prove model failure, and a model-generated “done” does not prove artifact success.

**Verified (V):** An earlier isolated 19-regression suite passed in GitHub Actions at exact commit `4f5f3eedf6ca3c43ac9b5ef0eb0435d9e59b574d`, after a missed ancestry-cycle test was corrected in preparation. The later branch includes additional 30/100-agent and rename-collision regressions that must receive their own exact-SHA CI. Neither success proves actual GPT worker behavior or safe production integration.

## 1. Nonnegotiable goal

The operator must answer, for every task, **what was last durably observed, which boundary is blocked, what evidence is missing, who owns recovery, and whether an external side effect may already have occurred**. Do not invent a cause when only the symptom is known.

There are three different correctness problems:

1. **Runtime correctness:** tasks, leases, authorized tools, retries, external effect receipts and verified outputs.
2. **Observability correctness:** causal event identity, authenticated source, collector durability, gap detection and privacy.
3. **Integration correctness:** dozens of independently authored branches must not silently duplicate scheduling, conflict in shared handlers, or overwrite another agent's patch.

This PR addresses **only integration correctness at GitHub PR metadata level**. It is explicitly not a second scheduler, event authority, trusted verifier or production monitor.

## 2. Canonical ownership contract

| Concern | Single owner | Never rely on |
|---|---|---|
| Project scope/budget/STOP | Versioned human-approved project policy | Unversioned agent summary |
| Task/lease/retry lifecycle | Modern upstream Hermes Kanban, after canary | Second Autopilot dispatcher |
| Worker execution | Scoped worker process and fixed tool policy | Chat frontend state |
| Tool/effect reservation and reconciliation | Narrow authenticated effect gateway (future) | LLM retry suggestion |
| Git revision/worktree | Git, one branch/worktree per agent | Shared uncommitted checkout |
| Branch merge/review | GitHub protections + integration owner | One agent approving own PR |
| Artifact success | Independent evidence verifier, exact revision | “Tests passed” in chat |
| Telemetry | One selected read-only projection, with authenticated events | Three competing “truth” ledgers |
| Browser transport | User-authorized supported API/extension | Assumed persistent MV3 service worker |

**Invariants:** An external effect in `OUTCOME_UNKNOWN` is quarantined until destination read-back or trustworthy provider receipt, not re-sent. A reused idempotency key with changed canonical fingerprint is rejected **before** agent/tool invocation. A STOP revocation generation is checked at every authoritative action boundary, not only in the UI. A green check applies only to its exact tested SHA and required suite. A worker cannot mark its own output independently verified.

## 3. Current PR integration decision matrix

| PRs | Observed conflict | Proposed action |
|---|---|---|
| #4, #5, #6 | Independent modifications of one API handler: keyed retries, SSE failure signaling, ingress validation, logs | Nominate one gateway integrator; compare contracts and failure tests, then create one combined candidate branch; do not blind-merge |
| #11 → #4 | Stacked API ingress preflight | Refresh from current parent head before testing; verify rejection occurs before any agent spawn |
| #10 → #1 | Stacked ledger changes; parent moved during the audit | Rebase/update child with exact parent SHA and rerun exact-head tests |
| #8, #9, #12 | Three separate event collectors/SQLite diagnostics | Choose ONE versioned read-only event schema and one projection based on security, Windows, crash and data-retention tests |
| #1, #9, #12 | `pyproject.toml` packaging registration conflicts | Reconcile package list explicitly, run wheel install smoke |
| #2 | Advisory skill harness, not an OS sandbox | Keep policy enforcement at privileged gateway |
| #7 | Independent bridge SDD | Consolidate terminology/authority, do not spawn a new scheduler |

No open PR is pre-approved by this document. A "blocker" is a **metadata-backed merge risk**, not proof that Git could never mechanically merge.

## 4. Read-only PR integration guard

`scripts/gpt_pr_integration_guard.py`:
- GitHub GET-only REST metadata collection of default HEAD, open PR head/base SHA, changed/renamed file paths and collection time. Redirects are rejected before token forwarding; no tokens/prompt text are output. A source-provenance field distinguishes live non-atomic API reads from unverified offline replay.
- Bounded pagination; absent/malformed API response, truncation, duplicate PR numbers or cyclic branch dependencies -> `INCOMPLETE` with nonzero exit; never “zero conflicts”.
- Second PR listing after file retrieval to catch concurrent parent/head movement; this reduces race windows but does NOT make remote GitHub APIs atomic.
- Unique-base stacked ancestry and stale-parent detection; ambiguous branch names produce blockers rather than fictitious ordering.
- File identity checks include BOTH the renamed source path (`previous_filename`) and new destination path. Independent executable/config overlap -> blocker; doc overlap -> review; stacked overlap -> review. Missing rename origin rejects the entire metadata snapshot rather than falsely reporting no collision. A separate **heuristic** compares Unicode-NFC+casefold path identities within and across PRs to flag potential case-insensitive Windows checkout aliases, even when GitHub paths differ byte-for-byte. In addition, a metadata-only `WINDOWS_UNREPRESENTABLE_PATH` blocker flags Win32 device-name, trailing-dot/space, reserved-character and empty/path-traversal component risks. These are not proof that every Windows volume collides; exact NTFS checkout must verify.
- Semantic heuristic for read-only observer package duplication in `gpt_companion/`, `gpt_bridge/`, `hermes_gpt_bridge/` and `gateway/gpt_bridge_diagnostics.py`, even when paths differ.
- Versioned JSON evidence report and Markdown operator summary; `--strict` exit 2 on blockers. Normal scheduled mode is **observational** and does not block PR pipelines merely because unrelated PRs exist. Snapshot/report/summary are each fsynced to same-directory temporary files and atomically `os.replace`d; an optional **final** SHA-256 receipt `--manifest-out` identifies a consistent bundle. Separate `--verify-manifest` verifies each role, byte length, digest, source mode, HEAD SHA and collection timestamp **offline** before a consumer trusts a bundle. It does not authenticate GitHub or guarantee a three-file transaction, so verified provenance remains `metadata-only`, never runtime health.
- Pure-stdlib synthetic regression tests cover concurrent 30-worker collisions, 100-worker disjoint inventory, 101-worker rejection, renamed source-path collisions, ambiguous/fork lineage, incomplete input, cyclic branch dependency and misleading successful-collection states.

`.github/workflows/gpt-pr-integration-watch.yml`:
- Offline regressions on relevant pull requests, **without supplying a GitHub API token to untrusted PR code**.
- Read-only collection on manual trigger or six-hour schedule after the workflow is merged/enabled on `main`.
- Preserves timestamped JSON snapshot/report and Markdown summary in GitHub Actions artifacts, with 30-day configured retention.
- The schedule can run late, be disabled in a fork or fail due to API rate limits. No claim of real-time monitoring. No auto-fix, approval, merge, browser action or external side effect.

## 5. Stop taxonomy: do not confuse symptoms and causes

A task status has at least `symptom`, `last_trusted_event`, `stage`, `evidence_gap`, `possible_causes`, `recovery_owner` and `evidence_revision`. The cause may remain `unknown`.

| Reason code | Minimum evidence | Default safe response |
|---|---|---|
| `PR_HEAD_DRIFT` | Child base SHA != current parent SHA | Refresh child; rerun exact-head checks |
| `PR_FILE_COLLISION` | Two independent open PRs edit same path | Quarantine blind merge; nominate owner |
| `OBSERVER_AUTHORITY_SPLIT` | Multiple observer implementations | One event contract; no competing dispatcher |
| `AUTH_REJECTED` | Provider 401/403 | Halt automatic calls, authorized recovery, redact |
| `RATE_LIMITED` | Provider 429 / Retry-After | Central cooldown with bounded jitter; avoid worker stampede |
| `BROKEN_SSE` | Headers sent but terminal event unconfirmed | Record stream incomplete; don't emit false success |
| `WORKER_NO_PROMPT` | Task claimed, model request never emitted | Inspect IPC/worker spawn and bounded reclaim |
| `WORKER_STALLED` | Lease present, no progress/effect receipt | Check last stage and effect state before retry |
| `TAB_LOST` | Authorized tab/session gone | Reattach only with permission; never infer effect outcome |
| `EXTERNAL_EFFECT_UNKNOWN` | Reserved/sent but no trusted receipt | Freeze replay, read destination and reconcile |
| `STALE_FENCE` | Old lease epoch attempts effect | Reject at gateway, record incident |
| `CI_SHA_MISMATCH` | Green check SHA != candidate SHA | Rerun appropriate suite |
| `REVIEW_EVIDENCE_MISSING` | Task claimed done without artifact proof | Keep blocked/review |
| `SCOPE_VIOLATION` | Tool or path not approved | Deny, audit and review permission |
| `MONITOR_UNAVAILABLE` | GitHub/Local MCP inaccessible | Record observation gap, never imply healthy |

## 6. Future GPT connector event contract (NOT implemented)

Use a versioned allowlisted event envelope: `schema`, `event_id`, `producer_id`, `producer_seq`, `project_id`, canonical `task_id`/`run_id`/`operation_id`, `parent_event_id`, W3C `trace_id`/`span_id`, `phase`, `reason_code`, `outcome`, collector receipt time, monotonic `lease_epoch`, `artifact_revision` and optional authenticated `evidence_digest`. No prompt bodies, cookies, raw tool arguments, browser session secrets, access tokens or unfiltered URLs in telemetry.

**Transport stages must remain distinct:** request prepared -> sent -> provider accepted -> model stream started -> tool proposed -> policy authorized -> effect reserved -> effect sent -> receipt reconciled -> artifact committed -> exact revision independently verified -> task completed. A received SSE chunk or collector ACK is NOT proof of a tool effect or artifact success.

Recommended production ingestion: authenticated producer -> bounded durable outbox -> authenticated collector inbox with event-id dedupe and per-producer sequence gaps -> observer-only projections. Collector durability and ACK must be transactional. A late heartbeat must never masquerade as task progress. Clock-skew must not override lease fencing.

For browser integration, prefer a supported OpenAI-compatible API bridge and documented permissions. A Chrome Manifest V3 service worker is not a durable control plane. Native messaging/HTTP must enforce exact origin, user consent, installation-scoped identity and message-level authorization. Never assume a ChatGPT tab/DOM can be a privileged API or that hidden internal model reasoning is accessible.

## 7. Conservative recovery sequence

1. Append event with source timestamp and collector timestamp; mark gaps if collection failed.
2. Correlate canonical task/run/operation IDs with GitHub PR, exact head, local artifact and independent verifier.
3. Classify **before retry**: `NO_EFFECT_DISPATCHED`, `EFFECT_CONFIRMED`, `EFFECT_UNKNOWN`, `AUTH_BLOCKED`, `POLICY_BLOCKED`, `CI_BLOCKED` or `TRANSPORT_UNKNOWN`.
4. When external outcome unknown, do **not** re-send; reconcile through authorized destination reads/receipts.
5. Create a minimal reproducer and regression test in an isolated worktree. Never overwrite the shared live working directory.
6. Independent reviewer checks exact candidate HEAD, security, tool authority, Windows/WSL behavior and rollback.
7. Permit deployment only after human approval and test gates; preserve previous working build and backup.
8. Link incident evidence IDs to PR and SDD; add one regression scenario for each confirmed root cause.

## 8. Prioritized ideas (reasoned design ranking, NOT measured ROI)

| Priority | Idea | Justification / evidence state |
|---|---|---|
| P0 | One canonical Kanban lifecycle, no second dispatcher | Eliminates split-brain task status; requires upstream canary verification |
| P0 | Read-only PR overlap + stale stack SHA guard | Directly confirmed risk in active PRs; implemented in this draft |
| P0 | External outcome-unknown quarantine and policy-bound approvals | Prevents duplicate effects after timeout; future trusted gateway |
| P0 | Exact-revision independent completion proof | Prevents hallucinated/stale success; future integration |
| P1 | Select one authenticated event format / observer | Three competing drafts exist; comparison gate needed |
| P1 | Stop taxonomy with evidence-gaps UI | Explains stoppage without invented root causes |
| P1 | Windows prompt-delivery, transport, STOP and crash chaos tests | Local environment unverified; cannot waive these tests |
| P1 | Side-by-side upstream Hermes migration canary | Modern Kanban could replace duplicate Autopilot work |
| P1 | GitHub + scoped Obsidian evidence checks | Stops false sync/cross-agent drift when access restored |
| P2 | 30-agent budget, fairness, bounded queue and dashboards | Performance/cost optimisation after correctness |
| P2 | Read-only causal timeline replay | Improves operator diagnosis without replaying effects |

## 9. Protocol for dozens of agents

Each agent's task manifest must bind: project, exact base SHA, allowed file paths, forbidden paths, owner, reviewer, dependencies, budget, run ID, max attempt count, stop generation and acceptance evidence. Changes to `gateway/platforms/api_server.py`, authorization, task lifecycle or SQLite schema require a nominated integration owner and independent reviewer.

Use distinct Git worktrees and optimistic file/branch preconditions. Reserve the user's original working Windows version; draft features do not auto-deploy. Re-check overlap **at assignment** and **immediately before merge**. Reviewers check actual CI at the exact commit SHA, not reported confidence. A successful supply-chain-only or skipped workflow must not count as gateway regression pass.

The event-plane reporter has **zero task authority**. The publisher/verifier must not be the author of the same effect/artifact. A project STOP requires revocation at every gateway path and prevention of cron/webhook resurrection, not merely closing a chat.

## 10. Acceptance and abort gates

- **G0**: exact baseline SHA, scope, read-only permissions and source repository independently confirmed.
- **G1**: Python 3.11–3.13 offline test matrix green on exact candidate head, no credentials in reports.
- **G2**: current PR snapshot collected twice without observed head movement; artificial 30-PR and 100-PR pagination tests.
- **G3**: integration owner resolves API #4/#5/#6, stacked child #11 and parent drift #1/#10.
- **G4**: one observer contract selected; package build/Windows smoke completed.
- **G5**: actual Chrome extension source and consented integration verified on local host (currently blocked).
- **G6**: exact-head gateway/stream/retry/STOP/effect recovery E2E pass; independent review and explicit promotion approval.

Any failing gate blocks automation/promotion. The guard intentionally does not auto-fix external systems: suggested fixes are **proposals** until approved by an authorized controller.

## 11. Commands and operator interpretation

Offline: `python -m unittest discover -s tests -p test_gpt_pr_integration_guard.py -v`; `python scripts/gpt_pr_integration_guard.py --snapshot-in snapshot.json --report-out report.json --markdown-out report.md`; `--strict` returns exit code 2 for blockers.

Live read-only, after trusted workflow merge/enabling: GitHub Actions `GPT PR Integration Watch`, manual trigger or six-hour schedule. Reports carry a collection timestamp. If absent/stale, the correct state is “monitor unavailable”, never “all healthy”.

### GitHub rename semantics and immutable schema revision

In schema `hermes.pr.snapshot.v3`, each PR contains `paths` (current names), `renamed_from_paths` (old names for `status=renamed`), `changed_files` (number of GitHub file records), fork-qualified head/base and exact SHAs. The `changed_files` cardinality applies to current names only. Corrupted or unsupported v2 snapshots must fail closed; they cannot silently inherit v3 safety guarantees. Pairwise overlap compares the union of current and previous paths. A scanner cannot prove executable semantic non-conflict from path disjointness; it remains `REVIEW_ONLY` without an exact-SHA independent gate.

## 12. Reference standards and source links

W3C Trace Context: https://www.w3.org/TR/trace-context-1/ ; OpenTelemetry GenAI agent spans: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/ ; Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle ; HTTP Idempotency-Key draft (November 2026): https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09 ; Hermes upstream Kanban: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban ; current fork PRs: https://github.com/Podtverzhdeno/hermes-agent/pulls .

## 13. Audit/work log (2026-11-22)

- **O:** Inspected GitHub main commit, 1592-path recursive tree, PR #1–#12 metadata, changed paths and selected PR SDD descriptions.
- **O:** Confirmed common gateway handler edits, multiple observers and moved stacked-parent SHA.
- **O:** Inspected GitHub Actions mixed states; no blanket green CI claim.
- **O:** Local_WorkSpace MCP was initially unavailable and later reconnected, but its declared accessible root was only the unrelated `shelter` Obsidian workspace. The local Hermes extension path remained inaccessible; no Windows install or Obsidian changes were performed.
- **V (offline only):** Ten standalone regression tests passed after fixing missed ancestry cycle detection.
- **D:** Created a separate read-only integration guard branch; no gateway, scheduler, model, browser or permission-enforcement changes.
- **Open:** Exact head CI, Windows host source discovery, integration reconciliation and adoption remain pending independent verification.
