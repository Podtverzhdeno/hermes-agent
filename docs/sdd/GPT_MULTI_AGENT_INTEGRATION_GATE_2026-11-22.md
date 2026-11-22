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

**Test evidence:** 13 offline `unittest` cases passed in isolated Python environment. They cover unverified CI, collision classes, stale base, observer duplication, incomplete files, wrong check SHA, duplicate PR/head identities, unprotected main, SQLite idempotence, invalid CLI snapshot, restricted repository selector. Network/GitHub live collection and Windows runtime are **not** exercised by those tests.

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
