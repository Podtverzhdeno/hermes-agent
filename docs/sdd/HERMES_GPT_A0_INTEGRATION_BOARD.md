# Hermes GPT Integration Board — single source of blocker and proof

**Canonical location:** `docs/sdd/HERMES_GPT_A0_INTEGRATION_BOARD.md` on branch `sdd/gpt-observability-2026-11-22`.
**Status:** OPEN/DRAFT; no local browser E2E evidence; no automatic merge.
**Last updated:** 2026-11-22. **Evidence baseline:** `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591` (2026-04-01).
**Repo limitation:** GitHub Issues is disabled (`410 Issues has been disabled in this repository`); the PR comments and this board are the durable coordination surface until a trusted upstream Kanban is available. A Markdown board is **not** a distributed lock manager.

## 0. Decision order: what is actually authoritative?

- **Task scheduling/worker lifecycle (modern target):** upstream Hermes Kanban, **after** isolated v0.23.3 canary passes Windows tests. This is not active in inspected fork.
- **Run, owner, progress and resume cursor (modern target):** native `/v1/runs` and its status/SSE, not a newly improvised API.
- **External-effect authorization/unknown-result reconciliation:** narrow trusted effect ledger; `autopilot/ledger.py` in PR #1 is **only** a prototype until real tool gateway integration.
- **Browser observation/control:** verified installed extension + upstream companion-plugin `tab_*` if compatible; exactly one controller per tab; no second CDP worker by default.
- **P0 old-fork API compatibility:** draft PR #6 has isolated HTTP retry/error/correlation fixes with targeted CI. It is not modern Hermes production readiness.
- **Read-only diagnostics/SDD:** observational only, never authorized to claim a task or make an external write.
- **Operator/human:** only authorized operator may approve deployment, browser permissions or reconcile effects with real evidence.

## 1. Evidence labels (strict)

`OBSERVED_CODE` = exact SHA inspected; `TESTED_CI` = named run on exact SHA; `TESTED_LOCAL` = executed local runtime with redacted artifact and documented version; `HYPOTHESIS` = no reproduction; `BLOCKED_INFRA` = dependency absent or disconnected; `NOT_STARTED`; `PROPOSED`. Never translate "model inferred" into TESTED_LOCAL.

## 2. Workstream ledger

| ID | Priority | Scope, proof required | Status | Dependency / owner-of-record | Evidence |
|---|---|---|---|---|---|
| H-000 | P0 | No competing writers to `gateway/platforms/api_server.py`; choose one retry module and error contract | **BLOCKED_CONFLICT** | Integration owner; PR #4/#5/#6 | [ADR](agent-integration-collision-adr-2026-11-22.md) |
| H-001 | P0 | Old-fork HTTP same-key join, stable IDs, invalid JSON, safe logs, SSE no false stop, SQLite atomic alias; test at exact head | **TESTED_CI** on code SHA `2a2321526399f799fc402c283bfc73b39c32a85c`; later SDD commits need recheck | PR #6 isolated gateway | [139 passed targeted](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45014284181) |
| H-002 | P0 | Full regression suite no PR-caused failures; red baseline failures compared to main on same toolchain | **UNVERIFIED_FULL** | Release verification owner | [Initial full job](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013031713) 7510 passed, 34 failed, 171 skipped; 6 confirmed patch-related failures fixed later |
| H-003 | P0 | Inspect actual local Chrome extension manifest, source SHA, profile, permissions, plugin/bridge, version handshake | **BLOCKED_INFRA** | Authorized local-runtime operator | Local Workspace MCP session terminated / backup observer HTTP 429 |
| H-004 | P0 | Build side-by-side upstream v0.23.3 canary with separate config/DB/ports and verified rollback | **NOT_STARTED** | Runtime integration owner | [Upstream v0.23.3](https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3), [PR #1 audit](https://github.com/Podtverzhdeno/hermes-agent/pull/1) |
| H-005 | P0 | Verify native Runs admission/poll/SSE `Last-Event-ID`/unknown resolution across restart; no duplicate side effects | **NOT_STARTED** | Runs API owner, H-004 | [Native API specification](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md) |
| H-006 | P0 | Verify upstream Kanban dispatch on actual Windows agent: claim→prompt delivered→model→artifact→independent receipt→task terminal | **NOT_STARTED** | Kanban/worker owner, H-004 | [PR #1 parity](https://github.com/Podtverzhdeno/hermes-agent/pull/1) |
| H-007 | P0 | Canonical external-effect reservation (commit before call), fencing, unknown-status reconciliation, authorized retry | **BLOCKED_INTEGRATION** | Native run/task owner + trusted publisher, H-005/006 | [PR #1 ledger](https://github.com/Podtverzhdeno/hermes-agent/pull/1); no live dispatch wired |
| H-008 | P1 | Extension compatibility/migration decision, single controller per tab, documentId, MV3 restart and UI Stop receipt | **PROPOSED** | Browser owner, H-003/004 | [Extension reuse SDD](gpt-browser-upstream-reuse-2026-11-22.md) |
| H-009 | P1 | Full Causal Trace: `run_id/attempt_id/request_id/lease_epoch/tool_effect_id` with sequenced, durable and privacy-safe events | **PARTIAL_P0** | Gateway trace + native Runs adapter | [Gateway SDD](gpt-extension-observability-2026-11-22.md); current gateway only logs request and idempotency events |
| H-010 | P1 | 50+ synthetic agents, partition, stale fencing, duplicate browser send, loss ACK, cancel, crash and observer outage | **NOT_STARTED** | Fault-injection owner, H-007/008/009 | Acceptance matrix in SDD |
| H-011 | P1 | Project STOP affects Kanban, browser actions, model calls, cron jobs, tools, alerts; no orphan after timeout | **NOT_STARTED** | Trusted control-plane owner, H-004/007 | [PR #1 STOP audit](https://github.com/Podtverzhdeno/hermes-agent/pull/1) |
| H-012 | P1 | Privacy, permissions, secret retention, audit log replay and backup/restore drill | **UNVERIFIED_RUNTIME** | Security/owner approval | [ADR](agent-integration-collision-adr-2026-11-22.md) |
| H-013 | P2 | Operator dashboard reconstructs any run and shows why it stopped, evidence source and recovery next action | **PROPOSED** | Observability UX, H-009 | Event taxonomy SDD |

**Acceptance rule:** a mock/unit-test PASS is not browser E2E. A CI success on code SHA N is not success on N+1. A model saying "done" is not evidence that an external action committed. A disconnected observer is not proof an agent stopped.

## 3. Agent claim protocol (no imaginary distributed locks)

Before touching code, document a claim in a *separate* `docs/sdd/agent-claims/<task_id>-<owner>.md` or PR comment:
```
claim_version: 1
task_id:
owner_role:
base_sha:
write_paths:
read_paths:
lease_epoch: not_yet_enforced
lease_until: not_yet_enforced
dependencies:
approval_scope:
external_effects: read_only | reversible | irreversible
acceptance_tests:
expected_source_sha:
rollback_plan:
```
Until an **actual** trusted native Kanban + effect publisher enforces leases, any claimed lease is informational only. Avoid overlapping path claims; use GitHub file blob SHA preconditions for all writes and independent PR review. Never grant your own claimed epoch authority over another agent's work. Never auto-reassign a silent peer without external side-effect reconciliation.

## 4. Triage recipe for `task stopped`

1. Read canonical task ID, run ID, current code/provider/extension revisions. Unknown IDs => `NOT_OBSERVABLE`.
2. Query authoritative task/run status and *cursor*; reconcile gaps or `replay.truncated` before inferring terminal state.
3. Check most recent confirmed execution stage: admission, queue, model call, tool started, external receipt, result persisted.
4. Distinguish disconnected client (transport), suspended Chrome MV3 service worker (lifecycle), missing plugin capability, stalled provider, real cancellation, budget exhaustion, and unknown external effect.
5. If external write was dispatched but receipt absent, mark `UNKNOWN`, **do not auto retry**.
6. Query independent evidence (provider/request ID, external system read-back, exact CI SHA, browser tab/document generation).
7. Only after independent cause confirmation propose a minimal reversible code change, targeted regression, full relevant CI and rollback check.

## 5. Current blockers requiring owner-only action

- Actual installed extension and Windows runtime are not reachable through available Local Workspace connector. No claim of a local fix can be made.
- Permission to deploy or update the owner's user-facing Chrome profile is **not implicitly granted** by research prompts.
- GitHub Issues disabled on this repo; board and PR comments are fallback only.
- Existing #4/#5/#6 overlap; choose canonical behavior before integration.
- Modern upstream-first migration needs isolated canary, backups, exact version/permission checks and user-approved promotion. Do not silently alter main/host.

## 6. One-agent task contract for future sessions

**This is a high-complexity, safety-critical integration.** An agent must not mark it easy or finished because one mock test passed. Work in bounded, reproducible slices. Prioritize objectively verified root causes over feature volume. Preserve negative evidence. Log all meaningful changes with exact SHA/CI and rollback. Avoid unrequested background promises. Use a single supervisor and leases when a durable controller exists. Every write-causing action requires explicit scope/authorization and a verified outcome. The spec's goal is to make failures understandable at every causal boundary without exposing protected model internals or private user data.
