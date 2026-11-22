# ADR-001 — Upstream-first Autopilot, not a second scheduler

Date: 2026-11-22. Status: **decision proposal / prototype audit**, not production approval.
Sources were checked against the upstream repository and official docs on this date.
The local fork is \`Podtverzhdeno/hermes-agent\` at main SHA
\`7e9100901819ee44c16b4ddcb79a6bcb7909f591\` (2026-04-01).
Upstream \`NousResearch/hermes-agent\` released **v0.23.3 on 2026-11-19**
(published 2026-11-20): https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3.

## Executive decision

**Do not build a parallel durable task scheduler into modern Hermes.** The current
upstream Hermes already ships SQLite-backed, multi-board, multi-profile **Kanban**,
a dispatcher, persistent named worker profiles, heartbeats, crash reclaim, retries,
comments, worktrees, review gates, and exact-head GitHub PR completion contracts.

Instead:

1. Preserve the prototype \`autopilot/ledger.py\` in this unmerged draft for
   **offline validation of effect/approval/evidence invariants**, never as a
   new concurrent production scheduler next to Kanban.
2. Upgrade/test a **separate canary install** from current stable upstream
   before making the user's main working Hermes installation follow it.
3. Use upstream Kanban as the **single owner of task lifecycle**. Extend
   *missing* elements using a plugin or narrow control-plane service:
   project/mission policy record, exact-effect authorization/reconciliation,
   cross-repository+Obsidian evidence, budget authority and cancellation sweeps.
4. Keep any external action ledger keyed to the canonical Kanban task/run ID.
   Never let two independent databases both claim to own "task succeeded".
5. Keep release blocked until verified Windows/WSL worker dispatch, stop
   propagation and recovery tests pass against the exact stable release.

This supersedes any earlier architecture wording that suggests operating
\`AutopilotLedger.claim()\` as the long-term top-level scheduler for a modern
Hermes deployment. That claim() implementation is a deliberately isolated
experimental reference against the **older fork**; future integration must
avoid duplicating upstream task rows or dispatching the same task twice.

## What actually exists upstream

Primary documentation:
- Kanban: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- Worker-lane contract: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
- Delegation: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- Latest stable release: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
- First-class Project/Mission proposal, **still open**:
  https://github.com/NousResearch/hermes-agent/issues/109278
- Zero-authority worker/publisher/reclaim safety tracker, **still open**:
  https://github.com/NousResearch/hermes-agent/issues/82591
- Reported Windows Kanban prompt-delivery regression (v0.22.5), **still open**:
  https://github.com/NousResearch/hermes-agent/issues/146955
- Reported failure of cancellation propagation and premature completion claims,
  **still open**: https://github.com/NousResearch/hermes-agent/issues/106744

An open issue is a **reported concern**, not proof that every release is affected.
An upstream docs assertion is an **implementation claim**, not a local acceptance test.
Neither should be presented as verified on the user's machine.

| Requirement | User's April fork | Upstream Nov 2026 | Remaining gap/owner |
|---|---|---|---|
| Durable multi-agent queue | Cron JSON; child delegation | **Kanban SQLite tasks + dispatcher** | Use Kanban; do not duplicate |
| Boards per project | Not in inspected fork | Multiple boards, separate DBs | Map project registry/owners |
| Durable named workers | In-process delegate children | Named profiles, OS worker processes | Verify each worker actually receives a prompt |
| Retry and reclaim | At-most-once cron occurrences | Heartbeat, reclaim, failure circuit breaker | Power-loss and stale-process E2E |
| Dependency DAG | Manual prompts | Parent/child Kanban links | Deadlock detection and multi-board references |
| Persistent local checkout | No user-specific runner in fork | Kanban worktree/dir workspaces | Local working-build promotion / rollback |
| Code PR acceptance | No first-class PR gate | Exact PR contract, required checks/ruleset checks | GitHub auth, repo config, post-merge promotion |
| Project canonical decisions | Plain notes | Project concept partially separate; formal mission issue open | Versioned project policy/decision/evidence |
| External side effects | Generic command approval | Evolving publisher/worker boundaries | Bound approval, effect receipt, reconciliation |
| Obsidian notes | Separate scoped MCP gateway | \`dir:<path>\` workspace possible | Restricted writer; SHA preconditions; sync queue |
| Cross-service cost budgets | No inspected global budget | Partial per-worker limits (scope to verify) | Aggregate budget authority / kill switch |
| Global stop | Gateway/cron separate | Several intertwined worker/cron systems | Cancel DAG, scheduled watchers, all dependent workers |
| Proof against chat hallucination | No trusted outcome gate | PR completion contracts exist | Extend to Obsidian, builds, runtime, policy |
| Host security | Generic approvals/YOLO paths | Worker containment evolving | Enforce OS-level scoped credentials |
| Windows operation | Old docs say WSL2 | New desktop/Windows packaging | Test actual Kanban prompt delivery and MCP tunnels |

## Hard migration boundaries

### A. No risky in-place upstream pull

The user's fork main is older by many months and may contain implicit local
state outside Git. \`git pull NousResearch main\` directly onto the working
Windows directory is **not** an acceptable migration method.

Safe sequence:
1. Inventory exact fork HEAD, local uncommitted files, Git worktrees,
   Python versions, virtualenvs, editable installs, gateways, plugins,
   provider profiles, credentials (names only, never secret values).
2. Backup Git worktree + configuration + SQLite files using SQLite backup API
   where applicable. Encrypt/limit access; **do not commit backups**.
3. Clone a clean **stable v0.23.3** canary side-by-side with its own
   isolated \`HERMES_HOME\` / profiles / ports / gateway / Kanban database.
4. Map config migrations and behavior changes by comparing controlled
   test cases. Do not point both old and new dispatchers at the same board DB.
5. Perform read-only smoke checks before granting any write scopes.
6. Run full fault-injection suite, then promote only reviewed config and
   workspace references. Retain explicit rollback instructions.
7. Main fork and user's existing Local Workspace editor remain unchanged
   unless the promotion gate is explicitly approved.

### B. Single lifecycle owner

For modern deployment:

\`\`\`text
Human request / GitHub webhook / scheduled signal
         │
         ▼
Project policy + intake validation ─► Kanban task_id
         │                              │
         │                              ▼
         │                  upstream dispatcher / worker profile
         │                              │
         │                              ▼
         │                 narrow tool gateway + action journal
         │                              │
         │                artifact + immutable evidence refs
         │                              ▼
         └─────────────────► independent verifier
                                       │
                            Kanban review/done/blocked
                                       │
                                   notifications
\`\`\`

Kanban owns \`ready/running/review/done/blocked\`; the effect journal owns
\`prepared/reserved/confirmed/unknown\` for **external writes only**.
The project record owns \`scope, constraints, accepted facts, decisions,
current revision, budget\`. A worker session owns only its transient context.
Never let an LLM fill in a missing source-of-truth field with fluent prose.

### C. Strong stop semantics

A global STOP for project P must atomically transition project policy to
\`paused\`, record a monotonic revocation generation, and fan out to:
- running and queued Kanban cards in **all boards** belonging to P;
- child/delegated processes, still-running terminal commands and gateway jobs;
- recurring cron/webhook-created monitors dedicated to P;
- future dispatcher claims and tool gateway calls;
- pending notifications that should be suppressed or consolidated.

Already-dispatched external actions are not magically undone: mark them
\`unknown\` until reconciled. No new actions may start after revocation.
A stopped project must not be restarted by a lingering schedule. A STOP
acceptance drill requires *actual* absence of new model calls and writes,
not just an informational "stopped" message. The 2026-09 upstream
report #106744 documents exactly why this gate is necessary.

### D. Windows / WSL2 acceptance

The 2026-10 report #146955 describes successful Kanban claim+spawn on
Windows with no actual prompt delivered to the worker. Testing only the
Kanban DB status or a process PID is insufficient.

An E2E test must prove this sequence for each required worker lane:
1. task claimed under exact task+run ID;
2. worker bound with expected profile / cwd;
3. prompt request delivered to worker;
4. model request observed, only within allowed token budgets;
5. expected output artifact produced;
6. verifier produces a success/failure receipt;
7. Kanban task reaches correct final state;
8. restart and STOP drills leave no orphan processes.

Test both the preferred runtime and the actual user-hosted Windows
environment. Do not assume that a fix in another version applies
to v0.23.3 without a local run.

## Acceptance gates before enabling unattended work

G0. **Fork/current baseline audited.** Exact old files and state backed up;
the canary has no shared auth/socket/path collisions.

G1. **Upstream work primitives verified.** Kanban board, task, worker,
parent dependencies, retry and per-worker constraints exercised locally.

G2. **Control-plane ownership.** One canonical ID for each project, task,
worker run and PR; no double-scheduler path.

G3. **Isolated code pipeline.** Task-specific Git worktree and safe branch;
tests at actual HEAD; verification cannot certify a different SHA.

G4. **External action receipt.** Every mutation passes a trusted policy
service; approval is bound to exact normalized params, target, owner and
expiry; unknown remote outcome never silently retriggers.

G5. **Cross-system evidence.** GitHub acceptance and scoped Obsidian revision
agree with task's declared requirements; negative/unknown evidence fails.

G6. **Cancellation.** STOP disables agent tasks, background children,
cron jobs and notifications, with no post-stop model calls or writes.

G7. **Recovery.** Forced process crash in each phase; no duplicate
external side effects, no lost safe work, expired leases fenced.

G8. **Operator quality.** A readable status page shows verified percentage,
last evidence revision, open blockers, oldest stale task and money/time burn.
"Completed" always implies proven criteria, never self-assessed confidence.

G9. **Soak and rollback.** Long synthetic replay, downtime recovery,
real backup/restore drill, cold start and safe revert on the user's host.

Any failing gate means **do not enable autonomy**, rather than silently
softening policy to make the demo look successful.

## Exact status of this feature branch

- \`autopilot/ledger.py\` is an **experimental single-host SQLite coordination
  kernel and future effect-journal reference**, not a complete plugin.
- \`tests/autopilot\` contains offline contract tests; check actual CI before
  claiming pass. GitHub Actions runs on the fork were absent during audit.
- No Hermes runtime worker, provider, CI, browser, Obsidian writer or publisher
  is yet wired to this kernel.
- The local Windows workspace was unavailable through Local Workspace MCP
  during this review; no local Obsidian file has been updated.
- This branch must remain **draft** pending upstream integration design,
  review and passing tests.
- Avoid merging these prototype tables into a fresh upstream Kanban deployment
  as a second task owner. Refactor/migrate to a *narrow effect ledger* first.

## Next implementation slices (order is intentional)

1. **Compatibility spike** on v0.23.3 in a disposable environment:
   Kanban API imports, worker-lane contract, PR contract, event hooks,
   project registry, local worktree preservation, full Windows smoke.
2. **Gate-only plugin**: read-only Kanban observer + project-specific status
   and exact revision evidence cache; zero model calls.
3. **Trusted effect publisher**: typed operations; canonical digest;
   approval by independent reviewer; downstream receipt / reconciliation;
   project STOP generation check at dispatch time.
4. **Artifact verifier**: GitHub CI/check runs + worktree head + expected
   Obsidian SHA + build/nightly runtime checks. Assert one revision.
5. **Operator API and dashboard**: reasons for blocked tasks, budgets,
   confirmation queue, STOP, recovery, multi-board per-project index.
6. **Multi-agent pipeline**: A0 policy/review, A1–A5 bounded execution
   roles, dependency-aware routing, tool-budget quotas and conflict lanes.
7. **Deployment**: real local runner canary, fault injection, soak,
   explicit activation/rollback, documentation in the *authorized*
   Obsidian folder when connector access is restored.

This order specifically avoids producing another "beautiful architecture
with no end-to-end activation" outcome.

## Evidence hierarchy for ongoing research

1. **Executed local tests under pinned SHA** (highest direct confidence).
2. Exact release source code and corresponding official documentation.
3. Reproducible upstream issue reports linked to precise versions.
4. Architectural standards (SQLite WAL, GitHub webhooks/CI, OWASP, Temporal).
5. Community recommendations and plugin marketing (hypotheses only).

A vendor feature page cannot override a failing integration test, and an
open issue for an older version cannot automatically condemn the current
release. Our reports must distinguish **source says**, **our code implements**,
**unit tests run**, and **deployed E2E verified**.
