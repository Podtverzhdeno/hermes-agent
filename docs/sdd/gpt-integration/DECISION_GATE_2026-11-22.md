# ADR-GPT-016 — Evidence-first integration and GPT/Hermes multi-agent safety

**State:** DRAFT / requires independent review. **Date:** 2026-11-22. **Fork baseline:** Podtverzhdeno/hermes-agent main at 7e9100901819ee44c16b4ddcb79a6bcb7909f591.

This is an SDD integration addendum, not a second worker scheduler, browser extension, production telemetry service or grant of permission to merge. The user's top-level goal—atomically explaining all stops for dozens of GPT agents—is difficult. Atomicity here means a reliable evidence ledger for committed transitions, **not** atomic hidden model reasoning or exactly-once execution of arbitrary third-party effects.

## 1. Verified evidence and risk inventory

- The live GitHub repo contains **12 concurrent DRAFT PRs** (#1–#12) as observed 2026-11-22. The exact baseline was 7e9100901819ee44c16b4ddcb79a6bcb7909f591. Base branch metadata returned protected=false and rulesets=[]; the detailed branch-protection endpoint returned 403 through the GitHub integration. Neither a stale snapshot nor an API status badge is permission to merge.
- The local Local_WorkSpace MCP returned `Session terminated`; no actual installed browser extension, local event stream, Windows service or Obsidian writes could be verified or fixed. The existing fork has the OpenAI-compatible `gateway/platforms/api_server.py` but not a confirmed deployed GPT/ChatGPT extension.
- The fork declares version 0.6.0 in `pyproject.toml`. Modern upstream NousResearch Hermes provides Kanban worker lanes. The public community MV3 browser companion targets much newer Hermes; verify its exact installed version and permission manifest before attempting compatibility. A ChatGPT subscription does not imply API access.
- **Critical API collision:** PRs #4, #5 and #6 all alter `gateway/platforms/api_server.py` with competing idempotency/cache semantics; #11 is stacked on #4 and also modifies the handler. PR #4 rejects an in-flight duplicate with 409; other candidates coalesce by awaiting a shielded task. Some have short-lived unknown-outcome tombstones; in-process state evaporates on restart.
- **Competing observers:** PR #8 adds `hermes_gpt_bridge/`; #9 adds `gpt_bridge/`; #12 adds `gpt_companion/`. They must **not** become three independent authoritative state machines. Select one authenticated event contract and accept other implementations only as non-authoritative adapters.
- **Packaging collision:** PR #1, #9, #12 modify the setuptools package include list in `pyproject.toml`. A blind merge risks silently losing importable modules.
- **Stacked ledger:** #10 modifies #1's `autopilot/ledger.py` and is based on #1. This is a useful experimental safety contract but must **not** run as a second production lifecycle owner alongside modern Hermes Kanban.
- **Authorization adjacent change:** #3 scopes ACP approval to sessions and terminal permissions. Cross-session escalation and stale approval replay must be independently tested.

**CI evidence at inspected exact heads:** #3 full Tests: 38 failed / 7500 passed / 171 skipped; #4: 29 / 7513 / 171; #9: 28 / 7540 / 171. Logs show repeated missing OpenAI credentials and file-read timeouts, plus an unrelated Codex response-path failure on #9. Do **not** assign these failures to a PR without comparing the baseline. #6's narrow GPT Gateway Regression passed but its general Tests was cancelled. #1 and #10 passed a narrower Autopilot Offline Contract; this does not prove overall compatibility. Recheck GitHub CI at the **current exact head SHA** before any promotion.

## 2. Architecture decision: no fifth observer

Contribute a **read-only integration evidence gate** in `scripts/gpt_pr_guard.py` and its independent tests. Do not touch the busy API handler, ledger, package configuration or authorization code.

The gate obtains open PR inventories, changed paths and exact-head GitHub Actions results via read-only REST GET; double-reads the PR set and main commit to catch common mid-scan head moves; rejects incomplete or malformed evidence; emits deterministic JSON plus a SHA-256 evidence digest (neither signature nor attestation). It identifies:

- draft PRs, unverified branch protection, stacked branches, and missing or non-green **required** Tests runs;
- critical concurrent edits of shared files (especially `gateway/platforms/api_server.py` and `pyproject.toml`);
- concurrent incompatible observer package families;
- workflow runs whose reported head SHA does not match the inspected PR head.

The gate never writes to GitHub, starts a model, approves a request, authorizes a browser action or performs a merge. A positive report is a **necessary review aid but not sufficient release approval**: it doesn't inspect hidden live effects, merged history, tool permissions, reviewer approvals, test quality, provider policy or deploy runtime health. No green status from an empty/incomplete API response.

Run offline: `python -m unittest discover -s tests/coordination -p 'test_gpt_pr_guard.py' -v`. Analyze current repo read-only: `python scripts/gpt_pr_guard.py --live Podtverzhdeno/hermes-agent --output gate.json --snapshot-output snapshot.json --strict` (requires read-only GitHub API access; optional `GITHUB_TOKEN` must never be logged). Offline reanalysis: `python scripts/gpt_pr_guard.py --snapshot snapshot.json --strict`. Exit code 2 means blockers, 3 means evidence unknown/unavailable. Scheduled CI is advisory: it cannot create PR comments, automatically merge or mutate tasks. It only becomes scheduled after this draft is reviewed and merged.

## 3. Required causal contract for the actual GPT bridge

**Proposed future events, not confirmed live telemetry:**

`intake.accepted → task.claimed(fence) → prompt.dispatch_intent → prompt.transport_ack → model.response_id → effect.reserved → effect.provider_receipt → independent_verification(exact_sha) → task.completed_verified`

Persist `schema_version`, `event_id`, `producer_id`, `source_seq`, `task_id`, `run_id`, `attempt_id`, `parent_event_id`, `fence`, `action_id`, `provider_receipt_id`, `source_ts`, `received_at`, `reason_code`, `evidence_ref`, `component_version` and trust level. Causal ordering requires a source-local sequence or explicit parent relationships: timestamps alone are not enough. Client-supplied events can be delayed, forged, reordered or duplicated; collector validates producer identity and quotas and commits ACKs after durable insert. A fresh replayed heartbeat is not progress.

**Authority separation:** supported upstream Kanban owns task, lease, worker and completion state; trusted tool-effect gateway owns write reservations, approvals and provider receipts; independent verifier owns exact-SHA result proof; event inbox is untrusted diagnostics. An offline observer is NEVER permitted to promote `succeeded` or emit writes. Canonical operation identity and fencing must be shared by all layers.

For an external write use: bound approval → durable reservation with action fingerprint → trusted tool invocation → authoritative provider receipt or read-back → verification. If a process dies after send but before ACK, state is **EFFECT_OUTCOME_UNKNOWN**. Never automatically replay a non-idempotent write until an independent reconciliation establishes whether the effect happened. Cancel stops future invocations and revokes stale fences but cannot undo unknown in-flight effects. Exactly-once guarantees are impossible for arbitrary services without cooperation/read-back.

Do not include prompts, raw DOM, cookies, auth headers, personal files, tool arguments or secret-bearing URL parameters in operational events. Browser companion can report opt-in connection and client lifecycle but must never be an authorization oracle; no clandestine UI scraping or bypass of controls. Use provider APIs and supported extension hooks.

## 4. Stop taxonomy — observable evidence versus hypothesis

| Observed reason | Discriminating evidence | Safe response |
| --- | --- | --- |
| UNOBSERVED | No authenticated intake receipt | Inspect transport; no fabricated task |
| HEARTBEAT_ONLY | Current heartbeat but unchanged progress sequence | Inspect run stage and elapsed budget |
| TRACE_GAP | Missing source seq or delayed replay frontier | Request outbox replay; withhold terminal verdict |
| AUTH_DENIED | Authenticated 401/403 and scope | Reconfigure with user approval; no privilege escalation |
| RATE_LIMITED | Provider 429 / Retry-After / quota | Bounded backoff for read/idempotent actions |
| APPROVAL_WAIT | Unexpired approval bound to action digest and reviewer | Wait/notify; denial is terminal for that action |
| STREAM_EOF_WITHOUT_TERMINAL | SSE/socket loss, no trusted run status | Mark uncertain and reconcile task ID |
| EFFECT_OUTCOME_UNKNOWN | Durable reservation without provider receipt | Read-back first, no blind duplicate |
| LEASE_STALE | Authoritative fence/expiry | Revoke old worker; reconcile prior effects |
| CI_STALE | Check SHA differs from target HEAD | Rerun against exact target revision |
| WORKSPACE_CONFLICT | Two write claims to same path/ref | Freeze second worker; designate owner |
| CLIENT_DISCONNECTED | MV3 background worker slept or browser tab closed | Probe server state; UI loss isn't task failure |
| BUDGET_EXCEEDED | Parent DAG limits or provider allowance | Pause new work, retain checkpoints |

Every incident must distinguish `observed_symptom`, `hypothesized_root_cause`, `discriminating_test`, `confidence`, `last_trusted_transition`, `unresolved_effect`, `current_owner`, `safe_next_action` and `source_sha`. A probabilistic score may prioritize investigation but cannot authorize fixes.

## 5. Dozens of autonomous collaborators

Define immutable work item: project, task, owner/role, base SHA, permitted directories, dependency DAG, expected evidence, budget, maximum child fanout and depth, timeout, approval scope, fencing lease, independent reviewer. One explicit integration owner for shared handler, DB migrations, Python packaging and canonical schema. Others contribute tests, adapters or evidence in separate branches. Use worktrees and revision-aware compare-and-swap; on stale SHA, stop, snapshot diff and reconcile rather than overwrite. Token, provider QPS, GitHub write and local MCP budgets must apply to whole DAG, not separately to every child.

On agent/session loss, restart from persisted objective + artifact manifests + exact revision + remaining budget + unresolved approvals/effects + current fence; **never** reconstruct hidden model thought or silently inherit expired grants. Two agents reporting “done” is not two independently verified proofs.

## 6. Ranked ideas and acceptance criteria

Provisional *architectural judgement* (not measured benchmark): safety 35%, causal transparency 25%, concurrent isolation 20%, migration cost 10%, rollback 10%, each subscore 1–5.

| Candidate | Safety | Causal | Multi | Migration | Rollback | Weighted /100 | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Upstream Kanban + durable trusted effect gateway + authenticated observer | 5 | 5 | 5 | 3 | 4 | 94 | Target after canary/parity |
| This isolated read-only PR evidence gate | 5 | 4 | 4 | 5 | 5 | 89 | Implement and review now |
| Multiple independent process-local caches | 2 | 3 | 2 | 3 | 4 | 52 | Temporary only |
| Browser DOM as task authority | 1 | 1 | 1 | 2 | 2 | 24 | Reject |

Hard veto: unknown irreversible-effect blind retry, stale fencing acceptance, cross-session approval reuse, fake SSE terminal success, token/secret leakage, hidden privilege bypass, multiple active task schedulers. Test controlled crash after effect before receipt; duplicate request across restart; out-of-order producers; 429; stream disconnect; stale lease; delayed heartbeat; multi-worker conflicting writes; exact SHA CI after rebase; MV3 suspend/resume; privacy/redaction and Windows/WSL host integration. Measure on 10/30/50 simulated workers: duplicate writes (target zero in controlled fixture), missed stops, queue latency, p95 recovery, owner conflicts, stale CI and data-loss incidence. Do not assert production SLO without measurements.

## 7. Action plan and audit

- **Completed in this draft:** independent source-level PR review, collision evidence, CI root-cause hypotheses, strict read-only gate + offline tests and SDD. No live browser/ChatGPT monitoring, production deploy, remote effects or existing PR merge.
- **Next gate:** keep PR as draft; run exact-HEAD GitHub Actions (new workflow + baseline) and independent review of script's pagination/race assumptions. Reviewer chooses canonical observer schema and one API cache policy, reconciles #4/#5/#6/#11 and stacked #1/#10, then tests combined candidate—not concatenated branches.
- **After authorization:** migrate current fork toward tested modern Kanban, authenticate emitter, durable outbox/inbox, provider receipt reconciler, Windows/WSL integration and real installed extension version handshake. Only then consider supervised automatic safe read retries. Always maintain user-owned rollback.
- **Evidence record, 2026-11-22:** 12 draft PRs; overlap in API/observer/packaging; CI negatives and narrow successes; Local_WorkSpace MCP disconnected; no live GPT monitor verified. All subsequent agents must append dated source SHA, hypothesis, test, owner, evidence and disposition instead of announcing unsupported “100% complete.”

References: https://github.com/Podtverzhdeno/hermes-agent ; https://github.com/NousResearch/hermes-agent ; https://github.com/abundantbeing/hermes-browser-extension ; https://www.w3.org/TR/trace-context/ ; https://opentelemetry.io/docs/specs/semconv/gen-ai/ ; https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle ; https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
