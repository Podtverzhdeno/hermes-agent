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

## Audit continuation — CDP wire validation and 27-agent collision wave

**New code:** pure `autopilot/cdp_contract.py` validator for exactly correlated `request_id/content/tool_calls`, capped UTF-8 payload and nested arguments, strict tool allowlist, duplicate JSON/call rejection and safe error categories. `tests/autopilot/test_cdp_contract.py` includes deterministic adversarial fixtures. No extension/Playwright/CDP socket was contacted, no tool effect was invoked.

**Additional observed regression (H-013):** With one trusted `ci/kind/source/revision` record already present, `record_evidence` previously accepted a contradictory new trusted result at the same key, overwriting the old conclusion. This allowed a later pass to erase a trusted failure before finalize. Current PR adds exact-replay idempotency and **rejects contradictory trusted overwrite**; different CI runs require distinct `source` identifiers. Test names: `test_trusted_failure_cannot_be_overwritten_by_same_source_pass`, `test_trusted_evidence_exact_replay_is_idempotent_and_run_identity_stable`. **Still a prototype trust boundary:** any direct Python caller can set `trusted=True`; only an authenticated verifier gateway can establish provenance in the future integrated runtime.

**Interoperability research:** actual upstream Windows issue #147613 identified telemetry `get_version_info -> git rev-parse HEAD -> subprocess.run(timeout=3) -> unbounded reader-thread join` as a prompt delivery hang on v0.22.5. Open PR #151449 proposes managed-worker guard, not yet merged at this audit. Distinguish bound process, delivered prompt, first model call and external receipt. Related issue #146955 observed absence of a `prompt.request` frame, #148389 observed native extension import stall, #152364 reported event-loop lag under ten active workers. These source reports are NOT proof of active defects on user's Windows host or v0.23.3.

**Competing PR audit (H-014):** live open draft PR count rose from 10 to 27. `MULTI_AGENT_INTEGRATION_MATRIX_2026-11-22.md` now records all 27, actual changed-path overlaps and separate semantic overlaps. Confirmed direct collisions: #4/#5/#6/#11 `gateway/platforms/api_server.py`; #12/#17/#23 `gpt_companion/journal.py`; #13/#15 `tools/browser_tool.py`; #4/#26 event auditor; #1/#10 prototype ledger; multiple `pyproject.toml` authors. Six separate read-only PR collision guards are proposed (#14/#18/#22/#24/#26/#27) and must converge to one implementation, not six independent scheduled monitors.

**CDP browser safety (H-015):** PR #15 proposes to avoid `Browser.close` on user-supplied CDP override; #13 removes CDP endpoints from logs. Must merge conceptually in a single tested `tools/browser_tool.py` patch. At one inspected head of #15, targeted CDP ownership QA passed but broader project test failed; not ready for production.

**GitHub coordination limitation:** creating a tracker Issue failed HTTP **410** because repository Issues are disabled. No Issue was created. Source of truth remains GitHub PRs and SDD notes; Obsidian remains inaccessible until tunnel is restored.

### Exact CI history (not conflated across SHAs)

- Run [45013359159](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013359159) on original code head `55e0ef80...` — **failure**, 72 passed / 2 failed due mismatched unit-test assumptions (second lease duration, invalid enum exception). Both assertions were corrected with contract rationale.
- Run [45013450647](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013450647) on `1bdfd1b22f77ec6691df3722e45eac211999d758` — **success**, Python 3.11, 3.12, 3.13 on Ubuntu and Python 3.12 on Windows; Python3.11 log reported 77 passed.
- Run [45014121910](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45014121910) after CDP tests — **failure**, one test passed a literal backslash-u sequence rather than a true unpaired surrogate. Test was repaired to encode `chr(0xD800)` through JSON wire format; this was a **test fixture defect** and no runtime loophole was proven by the failure.
- Runs between these and the final exact SHA may be **cancelled** by workflow `cancel-in-progress: true` as successive fixes/docs were committed. Cancellation is neither failure nor proof of success. See GitHub check runs on the exact HEAD.
- As of the final audit update, new immutable-trusted-evidence test commit `9c78b6ecce096c6c08c3941dbf69d480ef4db5e6` has a new CI run [45014746754](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45014746754); **do not assert it is green until all jobs complete**. Later documentation commits supersede that CI head; always verify latest HEAD after final edits.

### Structural security caveats not resolved by these prototype fixes

- `AutopilotLedger.record_evidence(trusted=True)` is a direct caller-supplied Boolean. It must never be exposed to GPT/ACP workers. A privileged verifier registry must attest source identity, exact checked revision and workflow run ID before accepting trusted evidence.
- `AutopilotLedger.reconcile_effect(...,proof_ref)` accepts an opaque string without cryptographic/provider verification; its docstring explicitly requires **trusted control plane only**. It must not become a public model tool.
- Worker IDs/action keys/result refs may be privacy-sensitive; avoid putting untrusted raw tokens, CDP endpoints or credentials in keys. Future policy gateway needs strict identifier schemas and redacted audit emissions.
- A local SQLite replica/snapshot is not proof that a remote provider did or did not execute a write. Cross-process and cross-host exactly-once guarantees cannot be asserted without compatible provider idempotency and independent read-back.
- PR #10 targets a **frozen review base** `snapshots/autopilot-ledger-6c0d2e-20261122` after the parent advanced concurrently. It is not approved for direct merge to `main`. Rebase/reconcile with the latest PR #1 and rerun all required tests first.

**Done now:** source inspection, isolated code and specs committed, 27 PR overlaps mapped, confirmed previous CI result and new regressions authored. **Still not done:** current exact-head all-platform CI acceptance until completed, live CDP/ChatGPT extension E2E, authenticated Kanban integration, automatic OS-supervised monitor, local Obsidian sync, multi-agent soak, merge/release.
