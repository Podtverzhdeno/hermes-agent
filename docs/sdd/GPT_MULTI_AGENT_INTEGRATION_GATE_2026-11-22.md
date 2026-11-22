# Hermes ↔ GPT: multi-agent integration gate and incident-oriented SDD

**Status:** draft design + tested offline integration-audit utility; **not deployed**. 2026-11-22.  
**Source:** `Podtverzhdeno/hermes-agent` `main` `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (dated 2026-04-01).  
**Scope owner:** PR-overlap diagnosis and release evidence only; does **not** claim ownership of `gateway/platforms/api_server.py`, ACP approval, Autopilot, GPT observer, or Chrome extension.

## 1. Executive conclusion: integration risk outranks feature count

At inspection there were **12 concurrent draft PRs**, including conflicting API handler candidates (#4, #5, #6 and dependent #11), multiple observer prototypes (#8, #9, #10, #12) and two stacked branch chains (#1→#10, #4→#11). These features are not a single approved deployed system. Their overlapping SDD proposals, API semantics, and telemetry stores must be **reconciled**, not accumulated. The fork is many months behind the modern upstream Hermes lifecycle/worker/Kanban code; production activation on the April snapshot would create a migration trap.

The requested outcome is *atomic explanation*, not a dashboard that guesses. A useful incident must answer: `what step? which owner/fence? expected evidence? last verified revision? tool effect certainty? exact root-cause hypotheses? who may safely resume?`. A closed browser tab, successful HTTP request or a model's self-report cannot independently prove agent completion.

## 2. Source and confidence ledger

| Finding | Grounding | Confidence and limit |
|---|---|---|
| April 2026 fork main; branch not protected | GitHub branch metadata `main` at `7e91009...`, `protected=false` | **Observed at inspection**; external rulesets could exist independently and need review |
| 12 draft PRs, overlapping API edit paths | GitHub PR list and `pulls/{n}/files` | **Observed at inspection**, not a transactional snapshot; heads can change immediately |
| PR #4 and #5 differ in duplicate-key policy; #11 adds keyed-SSE preflight | PR bodies and SDD branches | **Proposed, not integration-tested** |
| Existing code has OpenAI-compatible `/v1/chat/completions` and `/v1/responses` adapter | `gateway/platforms/api_server.py` on fork main | **Observed code**, not live local deployment |
| Modern upstream has durable multi-profile Kanban | `NousResearch/hermes-agent` official Kanban worker-lanes docs, upstream release | **Documented upstream**, local compatibility unverified |
| Third-party `abundantbeing/hermes-browser-extension` exists and uses companion plugin for recent Hermes | Third-party repository README, DATA-FLOW and permissions docs | **External candidate**, not proof of current local installation or suitability |
| Local extension at `C:/Users/Vadim/Tunnel/chat-launch-smoke-desktop-test/web-extension` was historically discussed | Earlier project SDD #7 | **Historical lead only**; local workspace access currently unavailable; no manifest/runtime checked in this effort |

Primary links: https://github.com/Podtverzhdeno/hermes-agent/pulls ; https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban-worker-lanes.md ; https://github.com/abundantbeing/hermes-browser-extension ; https://opentelemetry.io/docs/specs/semconv/gen-ai/ ; https://docs.github.com/en/rest/pulls/pulls .

## 3. Integration ownership: one canonical lifecycle

1. **Canonical lifecycle:** upstream Hermes Kanban in a version-pinned future runtime. Existing `autopilot/ledger.py` in PR #1 remains an experimental offline reference until migrated to a *narrow effect ledger*. It must never become a second dispatcher alongside Kanban.
2. **Execution gateway:** one API handler owner chooses **one** idempotency wire contract, with no surprise differences between `400`, `409`, in-flight coalescing and completed replay. Changes in #4/#5/#6/#11 cannot be independently merged.
3. **Telemetry:** single versioned event vocabulary and separate `diagnostic event inbox`. Select one observer implementation from #8/#9/#10/#12 after API/provenance review; do not wire all four simultaneously.
4. **Verifier:** trusted exact-SHA CI, artifact hash, effect receipt and approval evidence. Agents may propose, never self-certify their own work.
5. **Browser companion:** optional read-only/capability-controlled UI. Never make a Chrome MV3 service worker or web DOM the task ledger, auth authority, or retry initiator.
6. **Resource ownership:** one writer per path group and revision, plus compare-and-swap for GitHub/Obsidian writes. Worktrees isolate unmerged code; all writers respect PR dependency edges.

### Formal, narrow invariant set

- `I1`: No external write with `outcome_unknown` can be reissued until provider-side reconciliation proves absence, or a stable idempotency key with provider guarantee is verified.
- `I2`: Every tool write checks actor capabilities, current task fence, revocation epoch, exact action digest and approval immediately before crossing the side-effect boundary.
- `I3`: An observer event is *untrusted evidence*. It can change a diagnosis, never Kanban task status or permission.
- `I4`: `succeeded` requires verifier evidence bound to task, attempt, output hash and exact source commit. Green CI on an ancestor SHA is not valid.
- `I5`: Unknown tool outcome supersedes generic `timeout`; missing heartbeat is only a visibility suspicion.
- `I6`: Source-local sequence is ordered, but cross-worker causality requires parent/span/cause IDs. Wall clocks do not determine cross-source order.
- `I7`: Missing API pages, missing PR files or missing check runs mean `UNKNOWN/UNVERIFIED`, never `clean`.
- `I8`: Every new agent receives task role, resource owner, baseline SHA, budget, lease/fence and handoff; no agent receives another's write credentials.

## 4. Incident model: stop diagnosis as evidence, not speculation

Each incident record should include `incident_id`, `task_id`, `attempt_id`, `producer_id`, `last_progress_seq`, `observed_seq`, `lease_fence`, `source_revision`, `stage`, `effect_state`, `approval_state`, `evidence_refs`, `confidence`, `cause_candidates`, `safe_next_action`, `detected_utc`, `resolved_utc`. Only opaque correlation IDs and stable reason codes go into the shared metadata; never include prompts, model responses, raw arguments, cookies or credentials.

| Stage of failure | Discriminating evidence | Reason and initial response |
|---|---|---|
| API ingress | content-type/schema/idempotency key, dispatch count | `INVALID_REQUEST` / `KEYED_STREAM_UNSUPPORTED`: fail before dispatch |
| Provider request | model request-id, 429 Retry-After, 401/403, quota, timeout | `AUTH_DENIED` stop; `RATE_LIMITED` bounded cooldown; transport outcome remains unknown until receipt |
| Tool authorization | actor, scope, approval digest, fence, revoked generation | `POLICY_DENIED` stop; `STALE_FENCE` no write, new owner rereads |
| External tool effect | intent/reservation, provider receipt/read-back | `EFFECT_OUTCOME_UNKNOWN` isolate and reconcile; **never blind retry** |
| Browser bridge | heartbeat source incarnation, broker cursor, MV3 lifecycle | `UI_DISCONNECTED` ≠ worker stopped; reconnect only supported UI |
| Worker progress | progress vs heartbeat, stage deadline, OS supervisor | `ALIVE_NO_PROGRESS` collect state; `WORKER_UNKNOWN` verify lease/process before retry |
| PR promotion | ancestor/base SHA, changed-file overlap, exact check runs | `STACKED_BASE_STALE`, `PARALLEL_PATH_OVERLAP`, `CI_UNVERIFIED` block merge |
| Completion | external receipt + verifier result at exact revision | `AWAITING_VERIFICATION` until independently proven |

Classify `confirmed` only with direct evidence, `probable` with multiple consistent signals, `unknown` with missing evidence. Always show the counter-hypothesis (e.g. lost HTTP acknowledgment vs non-executed operation).

## 5. Implemented deterministic integration guard

`python scripts/gpt_integration_guard.py --repo Podtverzhdeno/hermes-agent --journal <local-path>/gpt-integration.sqlite`

This command is **one-shot read only** against the public GitHub REST API; `GITHUB_TOKEN` is optional and is never logged. No background monitoring is claimed. For offline repeatability, use `--snapshot <snapshot.json>` with the documented fields (`schema_version`, `repository`, `baseline_sha`, `main_protected`, `prs`: number/head/head_sha/base/base_sha/files/changed_files/checks).

- Refuses missing/invalid SHA, partial PR file enumeration, duplicated PR identifiers/heads, API pagination overflow and mid-scan PR head/base changes.
- Reports pairwise same-path edits and distinguishes stacked PR overlaps from parallel collisions; diagnoses stale stacked parent base by comparing exact `base_sha` and current parent `head_sha`.
- Flags multiple overlapping observer designs for **human design consolidation** (not automatic code deletion).
- Checks available GitHub check-run evidence for **each exact head**. No checks, wrong SHA, incomplete runs or an unavailable endpoint never mean green. A successful check list still requires reviewer interpretation and test-scope coverage.
- Reports `MAIN_UNPROTECTED` if direct branch metadata indicates no protection; this is not a complete ruleset audit.
- Optional SQLite WAL audit history uses an atomic `BEGIN IMMEDIATE`, immutable-to-tool snapshots and SHA256 digest dedup. This is a local integrity hint, **not** tamper-resistant attestation or proof of deployment.
- Exit code `0`: reviewable but **not merge-certified**; `2`: high/critical integration blockers; `3`: unknown/incomplete evidence. Never interpret `0` as production approval.

**Tool limits:** A PR head can change after its final per-PR check, and GitHub snapshots across PRs are not atomic; immediately before merge take a fresh scan, require exact-HEAD CI and repeat the critical path diff. Only the resource owner/reviewer can resolve whether overlapping edits are semantically compatible. This tool cannot see the local Windows browser extension, inspect model execution, or repair provider-side effects.

**Test evidence:** 21 offline `unittest` cases passed in isolated Python environment. They cover unverified CI, collision classes, stale base, observer duplication, incomplete files, wrong check SHA, duplicate PR/head identities, unprotected main, SQLite idempotence, invalid CLI snapshot, restricted repository selector. Network/GitHub live collection and Windows runtime are **not** exercised by those tests.

## 6. Prioritized improvements and decisions (not made-up benchmark scores)

| Priority | Proposal | Expected benefit | Distinct risk | Decision and test gate |
|---|---|---|---|---|
| P0 | Freeze overlapping API edits, appoint single integration owner | Prevents contradictory retry semantics | Slows parallel throughput | **Implement now:** read-only guard + explicit owner selection |
| P0 | Fail-closed keyed SSE preflight | Prevent duplicate side-effects on unsupported retry | Breaking client behavior | Merge only after API contract tests, exact-head CI, compat notes |
| P0 | One canonical task lifecycle (upstream Kanban) | Avoid split-brain dispatch | Version migration | Canary + crash/restart tests, no dual DB authority |
| P0 | Effect receipt/reconciliation path | Safe recovery after lost ACK | Provider-specific logic | Test crash at reserve/call/ACK boundaries before enabling writes |
| P0 | Independent verifier at exact SHA | Eliminate false completion | Auth/test infrastructure | Require check-runs + artifacts + signature/provenance policy |
| P1 | OpenTelemetry trace context with causal links | Cross-agent diagnostics | High-cardinality/privacy | Opt-in metadata schema + cardinality budget, no payloads |
| P1 | Per-stage progress deadlines & global budget | Detect stalls and retry storms | False positives | Fault injection at 1/8/32/64 agents; progress/heartbeat separation |
| P1 | Secure browser companion capability canary | UI connection without reinventing extension | Broad tab permissions; API drift | Manifest+host review; explicit user opt-in; no DOM task completion |
| P2 | Local incident dashboard with replay cursor | Explain stop reasons instantly | New monitoring surface | Read-only, RBAC and retention tests |
| P3 | Bounded repair proposals with independent QA | Reduce toil | Self-repair loops and authority escalation | Suggest PR only; no unattended merge/permission change |
| Reject | Model self-attestation, global blind retry, parallel scheduler | Superficial apparent progress | Irreversible wrong actions | Prohibited by invariants I1–I8 |

## 7. Gated staged integration, not all-at-once

1. **G0 source inventory:** exact upstream/fork and Windows extension version, manifest, native-host binding and local scope; snapshot current working tree/DB; no secrets in logs.
2. **G1 merge ownership:** select one API idempotency contract, one observer event schema, canonical Kanban owner; resolve stacked PR parents and duplicate packages.
3. **G2 smoke:** Python 3.11 + required runtime wheel tests, Windows installation and exact-run GitHub Actions; isolate a new HERMES_HOME/ports, never share live Kanban DB between old/new.
4. **G3 fault injection:** 401, 429, 5xx, cancel, lost SSE, timeout after provider write, stale fence, approval denial, DB lock/corruption and disconnected observer; each has a stable reason code.
5. **G4 concurrency:** 1/8/32/64 workers with PR path conflicts, delayed events, token quota and rate constraints; capture latency, duplicate-effect count and false-verification rate. Thresholds are set **after** baseline measurement, not invented here.
6. **G5 release:** exact HEAD check runs, independent peer review, recovery/rollback drill and owner authorization before any background or privileged deployment.

**Never silently promote a draft PR on the strength of this document or the guard's exit code.**

## 8. Verification log (2026-11-22)

- Source and branches inspected via connected GitHub API: fork main, 12 draft PRs, path overlap inventory, PR docs, `.github/workflows/tests.yml`.
- External evidence checked: upstream Kanban worker docs, third-party extension source/connection guides, OpenAI MCP tooling, GitHub REST semantics, OpenTelemetry GenAI trace conventions.
- Implemented new isolated script, offline unit tests, and this SDD. No production code path, credential, local workspace or running browser process was mutated.
- Known blockers: local MCP session unavailable, no authenticated extension runtime inspection, multiple competing unmerged draft branches, incomplete verified CI of combined integration, no live crash/recovery/soak results.
- Next reviewer needs to select the canonical observer/API contract and preserve this PR as an independent guard, not merge its conclusions as an operational guarantee.

## 9. Convergence audit: new parallel branches (2026-11-22, later inspection)

At a later GitHub inspection the open PR count rose from 12 to **26** (#1–#26). This is not an isolated incident: the **coordination tools themselves have duplicated** across PRs.

| Candidates | Actually observed | Architectural judgment |
|---|---|---|
| #14 `scripts/hermes_gpt_coordination_audit.py` | Read-only GitHub PR + unmerged-branch comparison, path and capability overlap, test workflow | Broad branch coverage is valuable; its scan currently filters only PRs targeting the chosen base. Test whether stacked PRs and 30+ changed files are fully covered. |
| #22 `scripts/gpt_pr_integration_guard.py` | Full open PR inventory, second end-of-scan listing, stacked ancestry/cycles and observer split, proposed six-hour workflow | **Preferred candidate for single scheduled PR integration watch**, subject to passing CI and review. No live monitoring is enabled until merged and workflow activated. |
| #18 `scripts/gpt_integration_guard.py` | Current PR draft adds exact `changed_files` reconciliation, per-head check-run classification, main-protection hint and local SQLite snapshot journal | Keep **as independent safety tests/reference**; port verified non-overlapping checks into the nominated #22 guard rather than deploy a second watcher. |
| #13 vs #15 | Both edit `tools/browser_tool.py`; #15 specifically protects externally owned CDP browser from cleanup | **P0 review**: choose one CDP integration owner, test ownership/cleanup at exact combined SHA. |
| #17 and #23 → #12 | Two stacked GPT Companion children both edit `gpt_companion/journal.py` and SDD | **P0 review**: choose integration order; test causal unknown-effect and terminal-state invariants together. |
| #4/#5/#6, #11→#4 | Multiple gateway idempotency wire contracts; stacked parent #4 moved beyond child #11's recorded base | **P0 hold**: no independent merge of the handler; solve keyed streaming/no-dispatch and check the parent SHA. |

### ADR-013 — One integration watch, many independent auditors

**Decision: proposed, not yet accepted.** After comparing the current PRs, nominate #22 as the **single scheduled integration observer candidate** because it includes repeat inventory and a GitHub workflow. PRs #14/#18 should supply targeted verified tests and contracts, not additional always-on monitors. A human integrator must validate this preference against exact-head CI and complete coverage before accepting. Candidate #18 remains draft and non-deployed; do not merge all three scripts merely to claim greater feature count. Run 1/8/32/64 worker and PR mutation tests before production.

**Rationale:** Multiple monitors with competing timestamps can disagree on what is blocked and hide each other's failures. One canonical read-only watch plus independently replayed deterministic test vectors gives clearer incident provenance and less operational overhead. Our script's optional SQLite record is not itself a scheduler or incident truth.

### ADR-014 — Browser extension must negotiate capabilities, not assume an API

Community extension `abundantbeing/hermes-browser-extension` has more than a static page context: current docs describe user-approved real-tab and background-task tab operations with companion plugin and authentication. Its supported integration is separate from this older fork. Before installation, require manifest host permissions, extension+host identity, per-tab allowlist/revocation, user consent, version pinning, session/message origin checks and an E2E test against an isolated current Hermes canary. Chromium MV3 service workers can be suspended; Chrome 116+ `connectNative()` may extend lifetime, but the durable workflow must remain in the native task authority. No DOM read or tab event can certify a tool side effect, and extension control must never bypass approvals.

**References:** https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md ; https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/ ; https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging ; https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09 (Internet-Draft published 2026-11-21; not an RFC).

### Hard practical bug found and fixed in our audit

GitHub's **list pull requests** REST response omits `changed_files`, even though **get a pull request** returns it. Initial code assumed it existed and would fail before producing an operator report. The correction reads per-PR details, checks files count and PR head/base invariants, re-lists all open PRs at the end, and rereads `main` HEAD. Added regression tests cover schema mismatch, a PR created during scan, head movement between list/detail and main ref movement. This is a read-only correctness fix; the report still cannot be a true atomic GitHub snapshot.

**Updated local evidence:** 21 focused offline tests pass on Python 3.13, prior to the latest GitHub commit. No claim of successful remote GitHub integration probe, production Chrome extension operation, Windows access or CI at exact commit unless subsequently verified.

## 10. Second-pass CI reliability, API contract and permissions audit

**Real defect corrected in PR #18:** The initial guard treated every `skipped` check run as failure. The fork's `build-and-push` job intentionally skips on pull requests, so that policy would produce permanent false blockers. The new repository-specific guard requires `test` and `Scan PR for supply chain risks` at the **same head SHA**, permits only `build-and-push` to be skipped, flags missing required checks, pending/failed checks and SHA mismatch. A single irrelevant green `lint` result can never replace the test suite. This is **structural evidence gating**, not a release authorization. Additional focused regression tests cover the three cases. Current isolated offline suite: **21/21 tests passed** in Python 3.13 with ResourceWarning treated as errors.

**Gateway candidate contract differences observed in GitHub PR diffs:** #4 uses an idempotency cache keyed by scoped auth/session with in-flight `409`; #5 implements per-adapter single-flight/coalescing with different conflict semantics; #6 introduces process-local uncertain-outcome quarantine and SSE error events. #11 adds strict ingress preflight stacked on #4. These implementations are NOT interchangeable. Until the single API owner chooses one contract, the exact reconciliation of `stream=true` with `Idempotency-Key`, caller identity, reuse of the key with a different request fingerprint, 409 vs 422, response identity, crash after external effect and client retry remains **blocked**. All process-local caches lose durability on restart, regardless of in-memory behavior. Do not assert exactly-once external tool writes from them.

**Coordination issue blocked:** Attempt to create an owner-level coordination issue failed with GitHub HTTP **410 Issues disabled**. The SDD and the draft PR body therefore carry the coordination log; no issue was created. Current accessible Local_WorkSpace list reports only `shelter`; no Hermes/extension workspace is exposed. This is a **scope blocker**, not a total connector outage.

**Source verification:** GitHub PR-file patch metadata for #4/#5/#6/#11; main `.github/workflows/tests.yml`, `.github/workflows/supply-chain-audit.yml`; https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09 ; https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md ; https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/ .

## 11. Security review of outbound audit networking

Supply-chain automation emitted repeated generic warnings on PR #18 because it matched `urllib.request.urlopen`. In this isolated script the actual request is `Request(..., method="GET")`, with the host built as the fixed `https://api.github.com` origin and a validated `owner/repo`; no `POST`/`PUT` or secret-payload emission exists in the reviewed read-only collection code. However a scanner alert is **not automatically dismissed**: reviewers must inspect the entire current SHA, including any new dependencies or changes.

Additional defense in depth: use an opener with `HTTPRedirectHandler.redirect_request -> None`; any 30x redirect produces an incomplete-snapshot failure instead of allowing an auth-bearing token to follow an unexpected URL. Added regression evidence checks HTTP method, exact host, bearer header scope and disabled redirect. Local Python 3.13 focused tests are now **21/21** (full Hermes CI remains unverified). For the large active PR population, the REST collector may exceed GitHub's unauthenticated hourly quota; run under a restricted read-only `GITHUB_TOKEN` with no write permissions, and treat rate limits as `UNKNOWN`, never clear.
