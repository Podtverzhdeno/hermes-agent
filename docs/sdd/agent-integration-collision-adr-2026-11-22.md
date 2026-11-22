# ADR-014: Cross-agent integration, GPT Companion boundary, and merge arbitration

**Date:** 2026-11-22. **Status:** PROPOSED. **Owner:** A0/integration review, not an exclusive software owner. **Baseline:** `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591`. **Safety mode:** no automatic merge/deploy. Evidence is live GitHub PR metadata and reviewed source; no workstation/browser runtime observed.

## Superseding architecture note — upstream-first, 2026-11-22

**Higher-priority decision for production than any custom coordinator proposed below:** this repository's `main@7e910090...` is from 2026-04-01; modern upstream Hermes v0.23.3 (release 2026-11-19) already has **Kanban** (multi-agent durable work lifecycle and worker lanes), **canonical Runs API** with run status, sequenced/replayable SSE, session turn ownership, durable keyed admission and unknown-run resolution. These capabilities are **not present** in the inspected April fork's `gateway/platforms/api_server.py`; that source exposes no `/v1/runs` route. The user has not authorized or verified any deployment migration. <https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3>, <https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md>.

**Authority rule:** On a modern, canary-verified Hermes install, **upstream Kanban** is authoritative for task/worker lifecycle; **native Runs** is authoritative for run status, stop/cancel, sessions and progress sequencing. PR #1's `autopilot/ledger.py` is an **unmerged, isolated effect/approval/evidence prototype**, not an additional production scheduler. Its own audit [UPSTREAM_PARITY_AUDIT_2026-11-22.md](https://github.com/Podtverzhdeno/hermes-agent/blob/sdd/autopilot-reliability-2026-11-22/docs/autopilot/UPSTREAM_PARITY_AUDIT_2026-11-22.md) explicitly says not to run two schedulers. The browser plugin's event journal is observation-only. Only a narrowly scoped external effect-reconciliation layer may supplement the upstream Kanban/Run authority after trusted integration tests.

**Preferred order:** (1) backup/inventory and isolated v0.23.3 canary with distinct `HERMES_HOME`, ports, profiles, database and credentials; (2) verify native Kanban worker prompt delivery on actual Windows host, run creation, SSE cursor replay, stop/unknown resolution and browser-plugin capability handshake; (3) port only demonstrably missing safety invariants from this PR, resolving #4/#5/#6 conflicts; (4) integrate effect ledger with canonical upstream run/task IDs; (5) expand to 50-agent fault injection and explicit owner-approved rollout. **Never `git pull` an unreviewed upstream main into the user's active workspace.**

The current PR #6 is an **interim April-fork API safety patch**, not a recommended replacement for modern upstream's already-implemented native lifecycle. CI on the old fork does not establish modern upstream compatibility.

## 1. Concurrent development is already happening

At review time the same GitHub repository carried these **draft** PRs:

| PR | Scope observed in changed-file list | Owned paths / intended authority |
|---|---|---|
| [#1](https://github.com/Podtverzhdeno/hermes-agent/pull/1) | Experimental effect/approval/evidence ledger, upstream Kanban parity audit | `autopilot/` is a prototype; upstream Kanban is modern authoritative task owner |
| [#2](https://github.com/Podtverzhdeno/hermes-agent/pull/2) | Skill harness metadata, manager guard, contracts | `agent/skill_harness.py`, `tools/skill_manager_tool.py` |
| [#3](https://github.com/Podtverzhdeno/hermes-agent/pull/3) | ACP approval isolation | `acp_adapter/`, `tools/approval.py` |
| [#4](https://github.com/Podtverzhdeno/hermes-agent/pull/4) | GPT bridge diagnostics module, extension SDD, gateway changes | `gateway/gpt_bridge_diagnostics.py`, browser/transport SDD |
| [#5](https://github.com/Podtverzhdeno/hermes-agent/pull/5) | Per-process dedup module, gateway changes, API retry tests | `gateway/idempotency.py`, canonical dedup API |
| [#6](https://github.com/Podtverzhdeno/hermes-agent/pull/6) | Correlated HTTP diagnostics, SSE error, security, dedup alternative, SDD | `gateway/platforms/api_server.py` conflicting; unique trace/security/CORS behavior |
| [#7](https://github.com/Podtverzhdeno/hermes-agent/pull/7) | Additional GPT bridge SDD and work log | `docs/gpt_bridge/` |

**Observed collision:** #4, #5, #6 all edit `gateway/platforms/api_server.py`; #5 and #6 implement the same in-process single-flight problem using independent cache classes. A green mergeability result against `main` **does not** mean these PRs can be merged in arbitrary order. Approval by the same agent that wrote the change is not independent verification. At least three competing docs trees could become inconsistent without an index/ADR.

### Merge and ownership decision recommended

- Declare a single code owner for `gateway/platforms/api_server.py` for integration window, with one active merge candidate; other PRs stay draft until plan and test matrix are complete.
- Prefer #5's isolated `gateway/idempotency.py` interface as the **single candidate implementation** of per-process retry dedup. This is an engineering preference based on module isolation, **not** a measured quality claim. Review its tests and policies before acceptance; review #4 and #6 variants as alternatives.
- Transplant unique #6 security/observability behavior only after rebase and targeted test execution: metadata-only request ID, failed SSE error envelope, error redaction, CORS exposed session/request headers, 400 non-object JSON, timing-safe bearer key compare, fail-closed non-loopback binding.
- Consider #4's `gateway/gpt_bridge_diagnostics.py` as a **diagnostic helper**, not a second idempotency authority or durable effect ledger. Reconcile event names/IDs with #1's task owner and the GPT Companion journal contract before integration.
- Treat `autopilot/ledger.py` #1 only as candidate external-effect state after integration with upstream Kanban's single scheduler, not as a second live task owner; `gpt_companion/journal.py` (from separate GPT Companion proposal) may independently collect observational evidence, but **must never issue writes, grants or `succeeded`**. Diagnostic event producer cannot certify its own output.
- Preserve #2's skill contracts and #3's human-approval checks as dependencies of tool execution, not parallel permission systems.
- Consolidate SDD using a canonical `docs/sdd/README.md` that maps contracts and "supersedes" lineage. Never delete divergent docs without reviewing every invariant and linking source.
- Any agent changing overlapping files must add an ownership claim with base/head SHAs, a test list, failure semantics, and rollback path; GitHub CAS on blob sha protects file revision but does NOT substitute task lease.

## 2. Request/API compatibility decision table

| Question | #4 candidate | #5/#6 candidates | Proposed stable contract |
|---|---|---|---|
| Duplicate key+same body while still running | return IN_PROGRESS conflict | join same in-flight task | Join only when same authenticated principal + same session + same canonical input, with bounded client wait. If latency exceeds HTTP deadline, return explicit status referencing run without triggering another tool. |
| Duplicate key+different body | payload mismatch 422 | conflict 409 | Choose a single error code (recommend 409 for currently shipped tests), publish `idempotency_conflict` structured code and add consumer compatibility tests. Do not silently recompute. |
| Cache scope | global or module object | per adapter/event loop | Per adapter for P0, per tenant/principal + durable store for P1. Never assume server restarts preserve keys. |
| Failure + retry | errors may or may not cache | failed task evicted | **External side effects are not assumed absent after exception.** Cache eviction permits retry of an agent run only for proven read-only/no-effect tasks. With unknown external effect, hold `NEEDS_RECONCILIATION` in authoritative ledger; do not blindly rerun. |
| `stream=true` + Idempotency-Key | current behavior varies | #6 rejects explicit unsafe combination | No silent pseudo-idempotency. Until durable SSE cursor/receipt exists, reject with documented 400 or return verified in-progress run ID with no second execution. |
| Session continuation with parallel independent keys | no session revision gate | no session revision gate | Reject concurrent writes or serialize per session under lease/CAS; report `session_revision_conflict`, never silently reorder. |
| Browser bridge send timeout | not proven live | not covered by gateway fix | Do not resend ChatGPT composer action until message receipt and current document/chat revision are reconciled. |

**Unresolved until integration:** complete request fingerprint across headers, tenant, model settings and auth; cache TTL, memory pressure, cancellation semantics, error code; effect-safety category. Tests must cover all cases.

## 3. Verified extension *history* vs live unknowns

PR #4 documents historical local extension root `%USERPROFILE%\Tunnel\chat-launch-smoke-desktop-test\web-extension` and files `manifest.json`, `background.js`, `background_content.js`, `content.js`, `core.js`, `popup.js`, `same_chat_bg.js`, `same_chat_loop.js`. Its own source explicitly cautions that this is historical owner context, **not a current file-list or verified installation**. Historical bridge port `18763` and stale extension v0.6.6 are also unverified today. The unavailable local MCP cannot be used as a browser status oracle.

**Pre-implementation checks:** exact `manifest_version`, extension `version`, JS file sha256, declared `permissions` and `host_permissions`, externally_connectable policy, CSP, service worker type/lifetime, content-script match patterns, native messaging host registration, bridge bind address, auth and TLS, runtime log location, restart policy, process owner, allowed Chrome versions, and explicit interaction permissions. Compare source/config against deployed extension before patching.

### Browser/GPT companion failure domains

1. **Hermes coordinator:** task admission, budget, lease, effect grant, cancellation.
2. **Local bridge/tunnel:** transport connected vs authenticated vs ready. Loss of link does not mean task did not commit.
3. **Extension service worker/background:** MV3 suspension, deactivation, duplicate message listeners, queued message loss, volatile memory on restart.
4. **Tab/document/content script:** navigation, re-render, chat switch, DOM changes, identity of intended composer and latest submitted message.
5. **Provider execution:** token, model, approval, quota, context, policy, generated result.
6. **Human activity:** manual message edits, Stop/Regenerate, chat switching, approvals, concurrent input; human action wins where conflicts arise.
7. **Observer:** dropped telemetry, delayed network, stale sequence, local clock skew; cannot certify worker status from absence of messages.

### Command/receipt contract (future implementation; not deployed)
```json
{
  "schema_version": 1,
  "command_id": "cmd_uuid",
  "task_id": "task_uuid",
  "effect_id": "sha256_authorized_action_digest",
  "expected_session_revision": 19,
  "expected_document_epoch": "tab-navigate-counter",
  "owner_lease_epoch": 7,
  "deadline_monotonic_ms": 45000,
  "capabilities_required": ["observe.gpt.connection"],
  "approval_id": null,
  "payload_ref": "encrypted_local_ref"
}
```
```json
{
  "schema_version": 1,
  "command_id": "cmd_uuid",
  "receipt_id": "rec_uuid",
  "event": "command_observed",
  "status": "RECEIVED_NOT_EXECUTED",
  "document_epoch": "tab-navigate-counter",
  "bridge_authenticated": true,
  "evidence_digest": "sha256_no_raw_content"
}
```

**ACK tiers:** `RECEIVED` (transport saw frame) ≠ `CLAIMED` (worker accepted) ≠ `DISPATCHED` (effect may occur) ≠ `COMMITTED` (provider receipt) ≠ `VERIFIED` (independent read-back). Never use `COMPLETED` without a tier; a browser click/DOM update is not evidence that an external effect committed.

The bridge must reject unknown capability, wrong tab/document epoch, expired request, stale lease/fence, missing human approval, mismatched `command_id`, and unauthenticated origins. No cookie scraping, CAPTCHA bypass or hidden ChatGPT model state extraction. If official supported API cannot establish a receipt, mark `UNKNOWN` rather than infer success.

### MV3 lifecycle test plan
- Service worker suspended after accepting but before posting ACK.
- Tab navigates between selecting chat and sending; stale document ID must reject dispatch.
- User presses Stop or submits own message during pending automated action.
- Bridge disconnects after tool dispatch; reopening must reconcile `effect_id` rather than resend.
- Background/content script duplicate port connections; only one owner may write.
- Partial model response, truncated stream, token/context limit and UI stall must be different diagnostic codes.
- Extension update changes permissions/matches and breaks handshake; fail closed.
- Incognito, multiple Chrome profiles, sleep/restart, cache and observer clock skew.
- Transport `200` but browser did not send; visible DOM reply without trusted provider receipt.

Tests require explicit user-authorized local environment or a synthetic browser harness; no such runtime was available here.

## 4. Task-claim and anti-conflict contract for 10–100 agents

Before any code mutation:
```
TASK CLAIM:
id | project | owner | owner_generation | base_SHA | resource_keys
read_set | write_set | expected_revision | lease_until
dependencies | budget | approval_tier | acceptance_tests | rollback
```

Admission algorithm: validate session / task ownership, prove capabilities, check dependency DAG, check per-project cap and resource lock, grant time-bounded lease epoch. Two agents may read a file, but only one may hold a write grant for the same `repo:branch:path` or `Obsidian:vault:note`. On source SHA mismatch, return CONFLICT and recompute plan, not force overwrite. On agent silence, status is SUSPECT until worker supervisor confirms task lease expiration and effect ledger is reconciled; never auto-assign a second writer without fencing.

Use an append-only review/progress stream. No agent overwrites another agent's SDD conclusions without provenance; contradictory root-cause hypotheses get separate IDs and independent tests. The coordinator does not gain a right to approve its own risky fixes merely because it holds role A0.

**Identity and trust:** repository URL, exact commit, code review/check run and provider receipt are evidence; assertions in comments, prompts and tool output are untrusted input. Protect GitHub source diff and prompt-sourced suggestions from instruction injection.

## 5. Measurable acceptance and release blockers

**Block merge** if any of these hold:
- Incompatible gateway idempotency/cache implementations remain active, or API semantics differ without documented migration.
- Targeted API suite, existing SSE cancellation suite or security contract fails.
- Any canary secret appears in ordinary log output, including exception strings.
- A successful `finish_reason=stop` is emitted after a known agent exception.
- Ambiguous external write is retried without reconciliation.
- An unapproved remote listener, browser script or external write is activated.
- Stale lease writes are accepted.
- No independent evidence of the claimed result on exact head SHA.
- Inability to identify which branch owns a changed file or migration path.

**Do not conflate:** one passing mock-based unit test with full E2E acceptance; a successful PR CI with deployment; a local probe 429 with Hermes worker death; a browser screenshot with provider receipt.

## 6. Independent CI observed after PR #6

Initial full suite for PR #6 on head `d0369dcb8a2a1b32a87ece6644c0609b0d8faf98`: **7510 passed, 34 failed, 171 skipped**, failure in job `137179292992`, 2026-11-22. From actual logs:
- 5 failures in `tests/gateway/test_sse_agent_cancel.py`: our diagnostic logger attempted to JSON-serialize test `MagicMock` request IDs (a confirmed regression).
- 1 failure in `tests/gateway/test_api_server.py`: existing test expected raw exception message leaked to HTTP client; new generic error intentionally redacts it. Update legacy test to assert safe code and no leaked string.
- Many unrelated failures were due to missing OpenAI API test credentials in CI; additional failures included Codex refresh/model string, file-read timeout, auxiliary pool configuration. These are **not** proof the GPT patch caused them; require baseline comparison and independent fixes.
- All 15 newly introduced tests were not listed as failed in the summary, but broad CI remained red; this does not prove all regressions are absent.

Code and test corrections for the first two failure classes are committed after that initial run; a targeted workflow has been added. Treat new results as pending until the new exact head checks finish.

## 7. Authoritative downstream documents

- [GPT API/gateway observability SDD (PR #6)](gpt-extension-observability-2026-11-22.md)
- [Incident evidence log (PR #6)](2026-11-22-gpt-investigation-log.md)
- [GPT Extension component contract in PR #4](https://github.com/Podtverzhdeno/hermes-agent/pull/4)
- [Per-process retry baseline in PR #5](https://github.com/Podtverzhdeno/hermes-agent/pull/5)
- [Autopilot durable effect ledger in PR #1](https://github.com/Podtverzhdeno/hermes-agent/pull/1)

This ADR is a coordination proposal; it does not assign permissions or merge authority automatically.


## 8. Upstream browser extension discovery and compatibility decision

Public Hermes Browser Extension v0.4.1 already supports scoped browser control on Chromium, seven observational context/journal tools, an authenticated optional companion plugin with 20 `tab_*` tools, and MV3 lifecycle handling. Versions after Hermes 0.22.5 require external plugin registration instead of former built-in control; group-bot page context may be unreliable. **This is reference research, not evidence that the owner's locally installed extension is the same project.**

See [reuse-vs-rebuild SDD](gpt-browser-upstream-reuse-2026-11-22.md), based on primary docs https://github.com/abundantbeing/hermes-browser-extension/blob/main/README.md and https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md.

**Proposed acceptance decision:** single owner for browser control, reuse upstream `tab_*` / read-only journal where available, thin event adapter only, and authoritative multi-agent task/effect state in #1 ledger. Do not duplicate browser permissions, per-tab leases, dynamic content script workers or plugin routes. Require exact extension SHA/manifest and authorized local runtime before claiming browser fix.

**Privacy:** avoid putting owner-identifying absolute Windows paths in future public SDD. Prefer `%USERPROFILE%` placeholders.
