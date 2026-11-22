# Audit log — Hermes GPT extension / Autopilot observability

**Audit date:** 2026-11-22  
**Scope:** fork `Podtverzhdeno/hermes-agent`; isolated feature branch `feat/autopilot-observability-sdd-20261122`.  
**Initial fork main:** `7e9100901819ee44c16b4ddcb79a6bcb7909f591`.  
**Initial parent PR #1:** `bc66ef436253e552d5b206f5b4d757f0214ed92d`.  
**Merge checkpoint:** `59d287f3027556f0d6dea425e874e580d51dd56e`, with two parents: our isolated code `975171ff...` and concurrent parent `6c0d2e064adda9cba05d204f5af5c5bbebdd6f5e`.  
**Owner requirement:** exceptionally high complexity; prioritize durable evidence, accuracy, explicit reasons for halts, very strict self-review and many collaborating agents. This record persists that intent for successors; it is **not** ChatGPT's account Memory setting.

## Evidence classification

- **CONFIRMED**: directly observed through GitHub connector in branch content or remote metadata.
- **FIX PROPOSED / COMMITTED**: file committed on isolated branch; no implied runtime operation.
- **TEST DEFINED**: regression scenario exists in code; not a passing test result.
- **VERIFIED TEST**: must include exact command, execution environment, runner and commit SHA. **No verified execution claim** at this checkpoint.
- **DEPLOYED**: must include host service, active version and health evidence. **Not deployed**.

## Observations and interventions

| ID | Observation (evidence) | Proposed correction, exact file | Regression/acceptance evidence | Outcome |
|---|---|---|---|---|
| H-001 | Prototype effect reservation persisted `not_executed` after reconciliation but reservation uniqueness blocked safe subsequent retry | `autopilot/ledger.py` permits re-reservation only for `not_executed` at identical digest with valid approval; never for `reserved` or `acknowledged` | `test_proven_not_executed_can_be_rereserved_but_acknowledged_cannot` | committed, unverified |
| H-002 | Nonretryable failure with uncertain reserved action could enter `retry_wait` after reconciliation | Persist `retry_allowed` per task and block nonretryable recon restart; schema migration | `test_nonretryable_failure_with_uncertain_effect_never_resumes` | committed, unverified |
| H-003 | Trusted success from one CI source could mask trusted failure from another source for same kind/revision | `finalize` vetoes if **any** trusted failure of required kind exists | `test_other_trusted_source_failure_vetoes_success` | committed, unverified |
| H-004 | Later untrusted evidence could overwrite trusted exact-source evidence | Upsert only on untrusted incumbent or trusted replacement; forbid new evidence for terminal task | `test_untrusted_observation_cannot_downgrade_trusted_evidence` | committed, unverified |
| H-005 | An expired pending approval could remain pending while workers stopped | Deterministic expiration sweep during scheduler tick; parent branch also had this fix and was merged, rather than overwriting it | `test_expired_approval_is_closed_on_scheduler_tick` + parent `test_expired_approval_is_blocked_by_scheduler_sweep` | merged, unverified |
| H-006 | Raw error strings in `failed_attempt` event could carry prompt text or secrets | Record allowlisted failure code only; never raw message; observer decodes allowlist only | `test_unstructured_failure_message_is_not_logged` | committed, unverified |
| H-007 | SQLite `PRAGMA synchronous=FULL` must apply per connection; local DB and JSONL default permissions should be private | Each connection enforces FULL; new DB mode 0600, reject final symlink; monitor log 0600 | `test_distinct_connection_uses_full_synchronous_mode`; `test_observer_once_read_only_success` | committed, unverified |
| H-008 | No live authoritative reason for stuck tasks or missing evidence visible from old fork | Read-only SQLite observer with bounded snapshots, event cursor and typed halt reasons | `tests/autopilot/test_diagnostics.py`; `tests/autopilot/test_watch.py` | committed, **prototype ledger only** |
| H-009 | Parent PR concurrently advanced during our execution, first from `bc66ef...` through `22e34de...`, then `b33760e...`, `90d019...`, `6c0d2e...`, and further | Isolated branch plus two-parent merge commit instead of overwriting parent; parent advances after merge require revalidation | `compare_commits` and exact tree identity; gate any merge into main | partially reconciled; parent active |
| H-010 | Parent audit identified modern upstream v0.23.3 released Nov 20 with existing durable Kanban | Supersede proposed second scheduler; Kanban single lifecycle owner, prototype restricted to safety/effect contracts | Modern upstream canary, task ownership and cancellation tests **not yet run** | SDD corrected |
| H-011 | Current local Workspace MCP returns `Session terminated`; cannot observe Obsidian/Windows runtime | Mark Obsidian/local state unknown; do not infer host monitoring is working | Reconnect observer and inspect actual process/DB, then run smoke | blocked external dependency |
| H-012 | GitHub commit status from Devin Review showed `success` but “Full review skipped: trial expired and no credits remaining.” | Required CI checks cannot be replaced by skipped third-party review; verify test run IDs and exact SHA | GitHub Actions pinned checks | not accepted as verification |

## Reconciliation and multi-agent conflicts

Before merge, independently checked that the parent had changed `autopilot/ledger.py` and `tests/autopilot/test_ledger.py`. Its additions included a retry-budget-safe approval resume, a reject-on-unresolved-effect approval guard, exact lease boundary, status projection methods, default SQLite durability, and approval expiration. The merge reconstruction kept these and our fixes. A two-parent commit was published with an expected-head lease on **our branch only**, leaving the parent PR branch untouched.

**Open coordination warning:** other agents continue updating PR #1. Before eventual stacked merge, recompute latest parent HEAD and CI results, test combined branch, and verify no conflict on `autopilot/ledger.py`. Do not assume a prior green test or review certifies the subsequently changed revision.

## SDD/design decisions

Canonical: `docs/autopilot/SDD_GPT_EXTENSION_AND_OBSERVABILITY.md`, version 0.3. Its ADR-002 corrects the original design: production uses modern upstream Hermes Kanban as task owner; no parallel Autopilot scheduler. Work to be built: authenticated Kanban adapter, GPT worker accepted/prompt delivered handshake, exact-effect gateway, independent verified evidence, cancellation propagation, fairness, budgets and local canary.

The observer reports **persisted prototype task state**, not true browser tab status, not model process liveness and not a modern upstream Kanban board. The monitor script runs only if a host explicitly starts it; this chat did not install a service or perform continuous monitoring.

## Quality gate for successors

1. Re-fetch exact parent/main/our branch heads, list open PRs and active sibling branch file ownership.
2. Restore a local checkout or CI with Python; execute `python -m pytest tests/autopilot -q` including policy tests, and static type/syntax checks. Record command, runner, run ID, result and exact SHA.
3. On failure, preserve failure logs with secret filtering, patch regression and rerun. Do not silently weaken policy or assertions.
4. Confirm merged ledger migrations from old schema with both `resume_without_attempt` and `retry_allowed`, and concurrency effects under SQLite WAL.
5. Run security checks and fault injection: unknown-effect crash, stale fence, duplicate webhook, model disconnect, Windows worker prompt delivery, STOP propagation and context replacement.
6. Only after a version-pinned upstream Kanban canary establishes actual task delivery and root-cause telemetry should an authenticated worker adapter be developed. No direct production upgrade/merge until independently reviewed.

**Not done:** local Obsidian sync, Windows host live monitoring, GPT provider integration, service deployment, verified tests or continuous unattended operation. All remain explicit blocked/next-work items; this audit does not count them as completed.
