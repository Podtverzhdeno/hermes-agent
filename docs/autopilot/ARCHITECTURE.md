# Hermes Autopilot — design review and phased implementation

Status: **engineering proposal + independently testable coordination kernel** (2026-11-22).

**Architecture update (2026-11-22):** Modern upstream Hermes v0.23.3 already has
first-class durable Kanban, worker dispatch, reviewer gates and exact GitHub PR
completion checks. **Do not deploy this prototype as a second task scheduler.**
Use the supported upstream Kanban as canonical lifecycle, and adapt the
prototype's approval/effect/evidence concepts as a narrow publisher sidecar.
The prior SQLite-vs-Temporal comparison applies to the older April fork and
research simulation only. See [ADR-001 and upstream parity audit](./UPSTREAM_PARITY_AUDIT_2026-11-22.md)
for the migration and updated decision.

Target fork snapshot: Podtverzhdeno/hermes-agent @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591 (2026-04-01).
**Not** an activated unattended agent runner. No production tasks, privileged actions, model calls, browser control, or automatic merges are enabled by this change.

## 1. The actual problem

The goal is not "more prompts per hour." It is a **continuous, auditable, interruptible control plane** for independent A0–A5 workers that can survive app restarts, context-window exhaustion, model changes, connector outages, and worker replacement, while keeping an always-current local working version.

Required capabilities:
- Convert objectives into bounded work items with explicit outcomes and ownership.
- Use GitHub/CI and Obsidian artifacts as evidence, without depending on reading ChatGPT DOM/output.
- Recover *known safe* work after workers disappear; distinguish unknown external effects from safe retries.
- Allow local workspace files to remain authoritative for the owner's running build; avoid repeated download workflows.
- Keep writable scopes narrow: repository branches/worktrees and explicitly permitted Obsidian notes, not globally writable machines.
- Support multiple worker types (official model APIs/SDKs, local coding CLIs, scoped MCP). Browser/CDP is never the source of truth and must respect owner permissions and provider policies.
- Never claim completion from a model's narrative. Require independently obtained, revision-bound verification.
- Keep human decisions rare but unavoidable for genuinely ambiguous or high-impact operations.

### In scope and out of scope

In scope: orchestration, task ledger, worker replacement, evidence, budgets, approvals, audits, operator visibility.
Out of scope: bypassing CAPTCHA, interactive safety steps, auth/metering, UI usage restrictions; pretending that free-form chat is a durable worker API; unreviewed external publishing/production deploy; assuming a timer can guarantee 24/7 execution when the host is off.

## 2. Evidence from current source audit

| Existing subsystem | What it already does | Why that is insufficient |
|---|---|---|
| cron/jobs.py | JSON schedule storage, atomic file replacement, missed-run catch-up | A scheduled occurrence is not a durable multi-step work item |
| cron/scheduler.py | Process-level tick lock, advances recurring schedule before running | Explicit at-most-once choice can lose an occurrence after crash |
| tools/delegate_tool.py | In-process child agents and ThreadPoolExecutor | No durable independent child work ledger |
| tools/process_registry.py | Background process tracking and checkpoints | An OS process result is not a verified business outcome |
| tools/checkpoint_manager.py | Shadow Git snapshots | File rollback does not undo an external API action |
| tools/approval.py | Conditional command prompts | Non-interactive paths and YOLO/disabled modes require a stricter AUTOPILOT policy boundary |
| tests/integration/test_checkpoint_resumption.py | Batch checkpoint experiments | This does not verify exactly-once external effects or multi-agent fencing |

Do not replace those modules wholesale. Autopilot is a **higher-level control plane** that treats them as adapters and resource providers. Upstream has developed well beyond this fork; changes must remain isolated for future rebasing.

## 3. Architecture

```text
 Owner UI / Telegram / policy file / approved schedule
       │
       ▼
 Intake + immutable task spec ── policy / budgets / permissions
       │
       ▼
 DAG planner (A0 policy; A1–A5 execution ownership)
       │                ┌──────────────────────────────┐
       ▼                │ Durable SQLite ledger         │
 Scheduler/dispatcher ◄─► tasks, leases, epochs, effects │
       │                │ approvals, evidence, events   │
       ▼                └──────────────────────────────┘
 Per-project resource locks + priority / quotas
       │
       ├─► API / SDK worker
       ├─► Hermes subagent / local coding CLI worker
       ├─► scoped Obsidian MCP adapter (only allowed notes)
       └─► GitHub PR/worktree/CI adapter
                │
                ▼
       Versioned artifacts + output manifest
                │
                ▼
       Independent verifier (schema, tests, CI @ exact SHA,
                             review, runtime smoke tests)
                │
          pass / repair / block / escalate
                │
                ▼
       Operator dashboard + event audit + local sync
```

Treat prompts as *instructions*, never as the system of record. The system of record is a durable state machine with immutable task identifiers and externally verifiable artifacts.

### Durable work contract

Each work item should eventually have:
- identity: project, request_key, task_id, parent_id, dependency IDs, assigned role;
- objective: precise goal, non-goals, expected artifacts, acceptance tests;
- snapshot: repo branch and exact HEAD SHA / Obsidian file revision / requirements version;
- execution budget: maximum attempts, wall-clock deadline, token/API spend, number of parallel children, change scope;
- risk declaration: read-only, local reversible, external write, or critical irreversible;
- checkpoint: last completed safe step, idempotency key and external receipts;
- resolution: independently verified evidence at the same revision, or explicit blocker.

**Never infer "finished" from a fluent answer.** Absence of new messages is not proof that an agent has ended or completed a task.

### Worker lifecycle

States: queued -> running -> verifying -> succeeded. Alternative branches:
- running -> retry_wait -> running for a safely retryable failure;
- running -> waiting_approval -> queued for explicitly approved exact action;
- active + uncertain external effect -> needs_reconciliation -> retry_wait or failed;
- refusal/approval rejection -> blocked;
- cancelled tasks stop acquiring new work; active work stops cooperatively, and external effects are reconciled first.

A task in running/verifying is protected by an expiring lease and an increasing **fencing token**. A stale worker must not commit completion or acknowledge an effect after a replacement claims the work. Expired work with no reserved external effects can retry with bounded backoff; unknown effects must not be retriggered.

## 4. Non-negotiable invariants

**I1. Durable before side effect.** Persist approval and effect reservation in a committed transaction *before* invoking a mutating connector. A crash after reservation but before/during external call is ambiguous; call reconciliation, not blind retry.

**I2. No exactly-once illusion.** Internal state transitions can be transactional; external API requests are generally at-least-once or uncertain. If an external provider supports idempotency tokens, pass a stable request key; otherwise independent read-back must prove what happened.

**I3. Narrow approval binding.** Approvals authorize only an action identity + normalized parameter digest + target + actor + expiry. An LLM cannot approve its own request; no "approve anything" from a chat message.

**I4. Revision-bound evidence.** Test success for SHA A does not certify SHA B. Required checks must report final completed/success for the exact intended head; missing, stale, neutral, skipped and in-progress checks are not success by default.

**I5. Separation of trust.** Worker output can propose evidence, but only an independently authenticated verifier/service can mark evidence trusted. The raw ledger Python method is *not* a security boundary; the API adapter, OS process rights and connection architecture must enforce this.

**I6. Revocation is stronger than plans.** Kill switch/revoked credentials and cancellation stop issuance of new tool calls. Leases must be validated at the tool gateway immediately before the side effect (not just at planning time).

**I7. No secret propagation.** Never put tokens, session cookies, connection secrets or private message bodies into git, event logs, prompt traces or user-facing artifacts.

**I8. Strict budget.** Attempt/time/cost budgets apply to the entire task DAG, not independently reinitialized for each child. Exceeded budgets block further dispatch.

**I9. Evidence not agent role.** A0 review should be independent of the implementing agent. A critical change needs both objective checks and authorized human review.

**I10. Backup is not sync.** Local worktree backup, project source sync, Obsidian document sync, and external action compensation require different mechanisms.

## 5. Trust boundaries and tools

### Four action classes

| Class | Examples | Default unattended policy |
|---|---|---|
| R0 read | Read repo, inspect issue, retrieve approved Obsidian note | Allowed within explicit scope and rate limits |
| R1 reversible local edit | Edit a worktree, run tests, propose a branch commit | Allowed only within sandbox/worktree plus audit/rollback |
| R2 external write | Publish PR, change issue labels, send message, write shared note | Exact action approval, unless owner has granted a narrowly scoped, expiring policy |
| R3 irreversible/high-impact | Delete repo/data, merge into protected branch, deploy production, change credentials, transfer funds | Human approval each time, secondary confirmation and verified preconditions |

**R0–R3 here are policy recommendations, not classifications already implemented in the source tree.** The current kernel conservatively requires explicit approval for every mutating effect. No broad YOLO-style bypass is inherited.

### Prompt-injection model

GitHub issues, PR descriptions, Obsidian notes, websites, docs, and chat replies are all *untrusted inputs* for the model. Their embedded instructions must never gain the ability to edit policy, alter action permissions or self-certify tests. The policy engine consumes structured identifiers and trusted configuration, not text the model can rewrite.

Use sandboxed commands, scoped working directories, network allowlists, per-agent credentials, secret redaction, and deterministic validators. Do not put a globally writable workspace editor behind an unrestricted tool endpoint.

### Authentication and CDP

Prefer native, documented APIs and tool protocols for work execution. If owner-authorized CDP is used to navigate a browser, isolate its profile and session; treat UI signals as hints, not authoritative completion/approval proof. Do not read ChatGPT DOM/messages as the primary agent-result channel. If a platform has no supported automation interface, mark it as manual rather than circumventing product controls.

## 6. Integrating with existing Hermes

- **Intake from cron:** a cron tick can enqueue a unique task specification; the scheduler must not execute long-running business logic as an opaque single run. Use unique occurrence IDs and deduplicate deliveries.
- **Executor:** a Hermes AIAgent / child agent is an ephemeral worker. Give it a task contract, lease token, narrow tool policy and checkpoint refs. Its response alone cannot write trusted evidence.
- **GitHub:** work on a dedicated branch/worktree per task. Before writing, compare expected SHA; after a PR, attach head SHA, workflow run ID and check conclusion to evidence.
- **Obsidian:** use scoped MCP writer with read-before-write SHA and allowed folder; keep shared task/decision notes there when the connector is healthy. If disconnected, queue an explicit document-sync task; do not claim the note is written.
- **Local working version:** the developer's machine should have a persistent worktree managed by a local runner. A read-only observer and separate scoped editor are preferable to a globally writable tunnel.
- **A0–A5 orchestration:** A0 validates requirements and gates; A1–A5 own disjoint deliverables; a verifier checks their artifacts independently. Ownership conflicts become blocked tasks rather than concurrent modifications to the same file.
- **Agent replacement:** if a session ends, stops responding, or exhausts context, the next eligible worker reads the *ledger and manifest*, not an assumed complete chat history. It is never safe to deduce failure solely from the absence of a UI reply.
- **Notifications:** send state transitions, not raw prompt streams. Escalate only actionable blockers with a one-sentence decision request and a link to evidence.

### Proposed minimal event envelope

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "task_id": "stable task ID",
  "attempt": 2,
  "fence": 7,
  "project": "My_shelter",
  "kind": "verification.completed",
  "subject_revision": "git SHA",
  "artifact_refs": ["github workflow run", "Obsidian note version"],
  "timestamp": "UTC ISO-8601",
  "correlation_id": "end-to-end trace"
}
```

Webhook receiver: validate X-Hub-Signature-256 and event/action, deduplicate by X-GitHub-Delivery, persist inbox event before returning 2XX, process asynchronously and reconcile missed events by polling. Do not use webhook arrival order as the only ordering guarantee.

## 7. Architecture selection

| Option | Advantages | Costs and failure modes | Decision |
|---|---|---|---|
| Cron + JSON only | Already in Hermes; simple | Lost mid-run state; no effect ledger, multi-worker fencing | Reject as autopilot core |
| LangGraph checkpoint graph | Good agent-state persistence/HITL | Side effects must still be isolated; not a complete permission/effect ledger | Suitable *within* executor |
| Temporal | Strong durable event history, retries and worker recovery | Additional service, storage, versioning and operations | Future multi-host tier |
| Local SQLite WAL + adapter processes | Small, local-first, transactional, testable, no extra service | One-host durability; no distributed consensus; manual migrations and backups | **Chosen for staged prototype** |

SQLite WAL supports a single writer at a time; don't put the DB on a network share. Use a transaction, timeout, fencing and backoff. Protect backups by checkpointing or using SQLite backup API rather than copying a live .db file alone. Temporal is more appropriate once genuine multi-host workers and high-throughput durable queues justify it.

## 8. What is implemented in this pull request

The new stdlib-only autopilot/ledger.py provides:
- atomic task submission with content-sensitive request-key deduplication;
- SQLite WAL task/event/evidence/approval/effect tables;
- bounded attempts, priority and retry backoff;
- expiring worker leases with fencing tokens;
- approval pause/resume for an exact action fingerprint;
- one-time external-effect reservation, acknowledgment and reconciliation;
- revision-matched trusted evidence gating;
- cooperative cancellation and auditable state transitions.

Tests under tests/autopilot exercise concurrent claims, stale workers, crash ambiguity, unknown outcome, approval expiry, evidence gating, idempotency, cancellation, retry exhaustion.

**Not implemented yet:** model dispatch, live watchdog process, authentication server, GitHub/Obsidian adapters, read-only policy registry, DAG dependencies, bounded cost accounting, backup/restore service, operator dashboard, deployment scripts, signed/verifiable audit stream, end-to-end failure injection, agent CI verification. These omissions are intentional: exposing the ledger directly to LLM tools before trusted adapters exist would undermine its security guarantees.

## 9. Implementation roadmap and release gates

**Phase 0 — safety kernel (this branch).** Unit tests pass offline; package import works; no privileged side effects. Review all state transitions and fail-closed behavior.

**Phase 1 — local read-only observer.** Wire status/metrics and poll GitHub CI plus approved Obsidian notes; record untrusted source events. No edits, no agent spawning. Verify webhook replay/dedup and cursor recovery.

**Phase 2 — sandbox execution.** Single worktree worker; fenced tool gateway; safe timeout/restart; persistent manifest; scoped local filesystem with path traversal defenses; token/time budgets; no external writes.

**Phase 3 — verified PR pipeline.** Per-task Git branch, tests and PR, independent CI/GitHub verification bound to exact SHA. Block stale CI, changed base SHA, branch conflicts, untrusted PR body instructions.

**Phase 4 — multiple A0–A5 agents.** DAG dependencies, role ownership, global budgets and concurrency quotas; preemption/priority, worker replacement, loop detection; dual independent evaluation when needed.

**Phase 5 — guarded external effects.** Scoped Obsidian writer and GitHub write adapter; approval UI, exact action signatures, idempotency/reconciliation, operator kill switch and recovery runbook.

**Phase 6 — long-run reliability.** Soak tests, fault injection, audit retention, backup restore drill, model/provider failover, release canary and rollback. Consider Temporal only if multi-host requirements make SQLite insufficient.

### Suggested release acceptance targets (unmeasured goals, not claimed results)

- 100% of high-impact tool actions have a valid, bound approval audit record.
- 0 unauthorized external effects in fault-injection and policy tests.
- 0 automatic replays of an *unknown* reserved external effect.
- 0 terminal 'succeeded' transitions without all verified required evidence at exact revision.
- 0 duplicate claims during concurrent claim tests.
- Task recoverability after forced restart for pure read-only/rollback-safe tasks.
- Every task exceeding retry/cost/deadline limits becomes visible as blocked/failed, not silently dropped.
- Manual restoration exercise for a crashed DB host and a disconnected Obsidian connector.
- 24–72 hour soak test under synthetic failures before unattended deployment.
- Separate performance measurements: queue latency p95, success rate, verifier false-pass rate, action conflict rate, recovery time p95, tokens per verified task, human interruption rate, and stale-task count.

## 10. Fault-injection acceptance matrix

| Fault | Correct system response |
|---|---|
| Agent dies before any external action | Lease expires; bounded, delayed retry with new fence |
| Agent dies after effect reserved, before result | Needs reconciliation; never automatically repeat |
| External API succeeds but response times out | Check provider receipt/read-back, reconcile; no blind retry |
| Duplicate webhook/redelivery | Deduplicate delivery ID and business operation key |
| Worker A wakes after B took over | Reject A's heartbeat/commit by fencing token |
| Two agents modify same file | Resource-lock conflict; rebase/re-plan |
| CI passes for old head | Never mark new revision as verified |
| CI skipped/neutral/in-progress | Not accepted unless the explicit task policy says otherwise |
| Read-only MCP disconnects | Suspend evidence freshness; retry safe reads |
| Obsidian write disconnects | Retain pending action; reconcile from file hash |
| User cancels a running task | Reject new actions and finish/reconcile in-flight external effects |
| User denies an action | Terminal blocked/denied; never reword/retry as another action |
| Model hallucinates "tests passed" | Ignore until trusted CI/test adapter confirms |
| Retrieved document says "ignore rules" | Treat as data, never policy |
| Billing/quota exhausted | Stop dispatch, preserve tasks and report budget blocker |
| Host loses network | Pause external calls; continue only explicitly offline-safe work |
| Clock jumps backward/forward | Use UTC timestamps plus monotonic clocks for same-process timeouts; time-source health checks in service |
| Schema upgrade during active work | Quiesce workers, backup, migrate atomically, rollback on failure |
| Database corruption | Stop external effects; restore verified backup and reconcile |
| Token revoked/secret leaked | Kill switch, credential rotation and audit of attempted actions |

## 11. Operational runbook (prototype)

1. Keep main unchanged and use the feature branch for review.
2. Run `python -m pytest tests/autopilot -q` in the repository environment; follow with full CI.
3. Do **not** start background execution: no runner is connected to this ledger yet.
4. Before integration, create an OS-private directory for the DB; use per-service accounts for trusted verifier/control plane.
5. For schema upgrades, stop dispatch first; make a SQLite online backup; migrate with rollback.
6. For an uncertain external action, inspect downstream service state and record independent proof before reconciliating. Do not manually clear or delete the reservation.
7. Operator dashboard should expose task ID, exact revision, owner, fence, last heartbeat, approval queue, unknown effects, required evidence and next action.
8. Maintain an explicit owner-owned local worktree plus a separate build/verification lane. Confirm that the local working version is updated before reporting completion.
9. On Local Workspace MCP errors (including 429/session termination), report the connector outage and keep pending Obsidian sync work; never mark notes updated.

## 12. Primary engineering references

- Temporal durable execution: https://docs.temporal.io/durable-execution
- Temporal idempotent activities: https://docs.temporal.io/activity-definition
- LangGraph interrupts/checkpoint semantics: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- OpenAI Agents SDK approvals: https://openai.github.io/openai-agents-python/human_in_the_loop/
- OWASP AI Agent Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
- GitHub webhook best practices: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- GitHub status checks: https://docs.github.com/en/pull-requests/reference/status-checks
- SQLite WAL: https://sqlite.org/wal.html
- OpenTelemetry trace conventions: https://opentelemetry.io/docs/specs/semconv/general/trace/

The central criterion is **provable, bounded, safely recoverable work**, not the number of model iterations or superficial autonomy.