# Hermes/GPT — Evidence and Investigation Journal, 2026-11-22

State: SOURCE AUDIT + ISOLATED PATCH; NOT a live browser deployment or ongoing monitor.
Repo: Podtverzhdeno/hermes-agent. Baseline: main @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591 (2026-04-01).

## Evidence grading

OBSERVED_SOURCE = read a named code revision; OBSERVED_METADATA = GitHub source/check result; HYPOTHESIS = plausible explanation not confirmed by test; PATCHED = written isolated branch; VERIFIED_CI = successful exact-SHA CI run; BLOCKED = subsystem cannot be reached; NOT_VERIFIED = no valid evidence. These are not interchangeable.

## Facts and decisions

| ID | Evidence / finding | Root cause or response | Status |
|---|---|---|---|
| E01 | Fork main HEAD 7e910090... source Apr 1; official upstream Hermes v0.23.3 released Nov 19 | Separate modern-upstream canary needed, no uncontrolled in-place pull | OBSERVED_METADATA |
| E02 | Upstream Hermes Kanban/worker-lanes docs | Kanban must remain sole canonical task lifecycle owner; do not run prototype Autopilot as parallel scheduler | DOCUMENTED_UPSTREAM |
| E03 | Local_WorkSpace.list_workspaces() returned Session terminated | No live Windows/browser extension, runtime log, local SDD or Obsidian access | BLOCKED |
| E04 | temp_folder_readonly.list_workspaces() returned HTTP 429 | No second local read source; no legitimate inference that Hermes stopped | BLOCKED |
| E05 | 12 pre-existing feature branches, 13 pairwise path overlaps on snapshot | Parallel agents risk conflicting or duplicative changes | OBSERVED_METADATA |
| E06 | pyproject.toml edited in 5 branches; gateway/platforms/api_server.py in 3 | Central release integrator and API owner needed | OBSERVED_METADATA |
| E07 | Draft PR #4/#5/#6 all propose related GPT API fixes | Do NOT merge all implementations. Pick a correct candidate using same tests | OBSERVED_METADATA |
| E08 | PR #5 branch feat/gpt-bridge-atomic-diagnostics-20261122, gateway/platforms/api_server.py near lines 830-845 | Responses API uses global _idem_cache plus a subset request fingerprint, versus adapter-local full fingerprint in Chat Completions | OBSERVED_SOURCE |
| E09 | Same PR #5 Responses error handling | Returns Internal server error plus raw exception text in HTTP 500; disclosure risk; replace public error with fixed code | OBSERVED_SOURCE |
| E10 | PR #6 branch sdd/gpt-observability-2026-11-22 | Adapter-local single-flight exists, but unknown-outcome entries may saturate bounded cache and caller key scope needs review | OBSERVED_SOURCE + HYPOTHESIS |
| E11 | PR #4 incompatible public retry semantics | 409 in-progress and 422 mismatch diverge from competing proposals; normalize shared API contract | OBSERVED_SOURCE |
| E12 | New feature branch feat/gpt-integration-collision-gate-20261122 | Read-only PR/branch collision gate, no runtime task queue or broker | PATCHED |
| E13 | scripts/hermes_gpt_coordination_audit.py commit 17b058ea9fc5d6fd93098382b1fedec1586424ed | Exact commit SHA checks, overlapping path/capability review, incomplete inventory fails closed | PATCHED |
| E14 | tests/coordination/test_hermes_gpt_coordination_audit.py commit eaeeb66a339385bc4b7b8bdc44d520aab426eca8 | 13 stdlib unit tests: 3 severities, semantic overlap, corrupt head/base/path, duplicate ID, deterministic ordering, read-only collection, incomplete source | PATCHED |
| E15 | Actions run 45013638222 on head 2b8c279569e154a83684a34b806e11af0a38060d | Python 3.11 job 137181164083, 3.12 job 137181164055, 3.13 job 137181163910: all contract check SUCCESS | VERIFIED_CI for the cited SHA |
| E16 | Job log 137181164055 | Actual line: Ran 13 tests in 0.001s; every case reports ok. Not live GPT E2E | VERIFIED_CI for cited SHA |
| E17 | Draft PR #14 and later workflow trigger fix commit f2d2629e40d2eae9a52b1df8bb22cfa6846d7c03 | PR must remain draft; latest-head CI needs independent confirmation | PATCHED |
| E18 | Source review comments on PR #5 (id 7077970951), #6 (id 7077971277), #4 (id 7077971632) | Findings shared with concurrent agents without editing their branches | APPLIED |
| E19 | Full generic Tests workflow on old head was cancelled by superseding updates | CANCELLED does NOT mean pass. Do not use obsolete checks as merger evidence | OBSERVED_METADATA |
| E20 | Chrome MV3 service worker and native messaging official docs | UI worker lifetime is not guaranteed; checkpoint/handshake and source-of-truth separation required if browser extension identified | DOCUMENTED_WEB; NOT_VERIFIED_LIVE |
| E21 | PR #3 fix/acp-approval-session-isolation-20261122, acp_adapter/server.py prompt path | Prompt's first 100 characters appear in INFO log, exception text is returned to client; overlapping same-session turns can change agent callback state unless serialized or protocol forbids them | OBSERVED_SOURCE + HYPOTHESIS for concurrency |
| E22 | PR #3 review comment id 7078018227 | Requested metadata-only logs, sanitized errors and same-session concurrency test; ContextVar fix in executor thread appears correctly scoped | APPLIED |

## Source discrepancies requiring canonical integration

PR #5 Responses endpoint uses a module-level cache and a request fingerprint limited to a list of request fields, whereas the modified Chat Completions path uses adapter-scoped cache and full-body/session fingerprint. Thus it has conflicting consistency assumptions across endpoint implementations. Code observation is sufficient to request regression tests, but not sufficient to claim a live exploit. Also the Responses handler constructs an HTTP 500 message using the original Python exception string; this is a concrete unsafe pattern. Both concerns were posted to PR #5 for its owner.

PR #6 has a more comprehensive adapter-scoped cache, and the source keeps unknown outcomes in memory rather than evicting them. That is safer against replay but may exhaust capacity after many uncertain outcomes. Distinguish a deliberate safety rejection from a deadlocked worker; provide protected reconciliation and test volume/partitioning. Shared API keys versus independent authenticated tenants must determine the actual idempotency scope. PR #4 independently chooses different public HTTP conflict codes. One compatibility contract must win before merge.

## ACP concurrency and privacy finding, not a live incident

On the in-review ACP session-isolation PR #3, the terminal approval ContextVar is explicitly installed inside the executor thread, which is correct for thread-local context propagation. However, the prompt handler still logs a preview of raw user text and returns raw exception text to an ACP client in multiple error branches. Separately, callbacks are assigned to a shared agent instance per session before executor execution. If simultaneous prompts are permitted for the same session, a second prompt may overwrite callbacks/history before the first completes. This concurrency risk needs protocol-contract verification and an explicit regression test, not an unqualified defect claim. Review comment 7078018227 sent to PR #3 owner; no direct changes to their branch.

## Failure-to-evidence map

| Symptom | Evidence to inspect | Safe response |
|---|---|---|
| No observer events | observer intake health / last cursor / producer sequence | OBSERVATION_GAP, do not label worker dead |
| Task claimed, no model request | worker PID, prompt acknowledgment, config/profile | PROMPT_NOT_DELIVERED |
| Long wait with approval request | trusted approval intent and expiry | WAITING_APPROVAL, not automatic retry |
| Model 429 | response code and Retry-After | coordinate bounded backoff |
| Model 401/403 | authorized identity and credential validity | pause, require owner repair |
| SSE partial output then error | last chunk, worker outcome, success terminator | STREAM_INCOMPLETE, never report success |
| HTTP disconnect after mutating tool dispatch | effect reservation and remote receipt | EFFECT_OUTCOME_UNKNOWN, reconcile before retry |
| HTTP disconnect after durable response | response ID and delivery ack | DELIVERY_UNKNOWN, replay data not execution |
| Worker lease expired, old worker still running | fence token + process identity | reject stale commits, reconcile |
| STOP requested | project revocation generation across workers/cron/tools | deny new actions, trace in-flight uncertainty |
| CI passed different SHA | check target SHA vs current head | reject stale success |
| GitHub listing truncated or HTTP error | total inventory proof | INCOMPLETE_AUDIT, never report green |

## Current decisions and hard boundaries

- Single source of task state: modern Hermes Kanban. Event stream is read-only from task lifecycle perspective.
- Single integration owner for GPT API, packaging and effect-journal authority. Competing patches are tests/review sources until selected.
- Causal event identity per project/task/run/worker-attempt, not one textual transcript; record event order, stage, reason code, trusted receipt and missing evidence.
- An unknown external side-effect outcome must never be auto-retried without trusted remote reconciliation.
- Browser extension must use supported interfaces, explicit per-action authorization and durable checkpoint cursor; not a covert programmatic queue or DOM-completion oracle.
- Never log private prompts, tool arguments, auth tokens, cookies, private files or hidden model reasoning.
- No unattended self-fix may alter permissions, approvals, project STOP or unrelated worktrees.

## Required verification not completed

1. Latest PR #14 head CI, not an older SHA.
2. Live GitHub inventory against all open PRs and independent branches, with truncation handling.
3. Common HTTP API, 100 concurrent duplicate requests, 409/422 semantics, SSE partial failure, cross-session, process-restart, overload and secret-redaction tests on one selected patch.
4. Modern upstream v0.23.3 isolated canary with Windows/WSL Kanban prompt delivery, cancellation and rollback.
5. Inspect actual extension repository/manifest/native host, test MV3 worker restart, page navigation, host dropout and persisted checkpoint.
6. 30/100 simulated agents, lease-fence recovery, STOP propagation, sustained soak and operator-approved promotion.

This investigation was synchronous and source-based. Nothing here constitutes ongoing monitoring or a claimed repair of the user-installed browser extension.

Related: INTEGRATION_AND_ATOMIC_DIAGNOSIS_SDD.md and draft PR #14.
