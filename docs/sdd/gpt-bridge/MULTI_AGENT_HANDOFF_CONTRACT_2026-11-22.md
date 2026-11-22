# Hermes GPT — multi-agent execution & handoff contract

**Draft SDD v0.2, 2026-11-22.** Shared coordination rules for 10–100+ agent reviewers. This file is **not** an operational scheduler, authorization grant or proof a live monitor is running. Refer to INTEGRATION_GATE_AND_AUDIT_2026-11-22.md for source inventory and research evidence.

## Non-negotiable ownership rules

1. **Single task authority** — modern Hermes Kanban owns canonical task/run lifecycle, worker identity and completion. Experimental PR #1 ledger may supply invariant tests or a subordinate effect journal, not a separate concurrent production scheduler.
2. **Single side-effect authority** — trusted tool gateway reserves external effect before dispatch, binds request to a monotonic attempt/fence, and records an authenticated downstream receipt. Lost ACK is **outcome_unknown**, never permission for blind replay.
3. **Single integration owner** — one agent per shared core file group and exact target SHA. Independent agents submit nonoverlapping branches/tests and evidence. No force-push, overwrite or silent migration of another agent's edits.
4. **One accountable reviewer** — the change author may test but cannot self-certify privileged behavior or approve their own effect.
5. **Separation of evidence** — task intent, visible model answer, HTTP response, gateway ACK, external effect and independent verifier result are different facts.

## Proposed immutable work grant (not currently enforced)

- work_id, parent_work_id, canonical_kanban_task_id, owner_agent_id, attempt_id, fence and expected base HEAD SHA
- role, read-only scope, write/file ownership scope, allowed tools and explicitly denied effects
- acceptance criteria with independent verification owner, cost/tokens/wall-time/max-child budgets and exact handoff artifact path
- source version, installed extension version, transport epoch and source event cursor for observability
- required owner approval for irreversible actions, credential changes, production deployment and security policy edits

This document does not authorize any agent to operate a privileged tool without independently enforced gateway permission checks.

## Canonical causal event model

Metadata only: schema_version, event_id, timestamp, source, source_epoch, source_seq, task_id, run_id, session_id, attempt_id, step_id, worker_id, fence, kind, effect_id, receipt_id, reason_code, verified_sha and parent_event_id. No raw prompt, DOM, token, cookie, image, file path or tool argument is necessary for routine incident logs.

States: created → claimed → dispatched → backend_accepted → executing → verifying → independently_verified → done.

Separate **unknown or blocked** states: approval_wait; cancelled; lease_expired; provider_limited; connector_unavailable; context_checkpoint_required; delivery_outcome_unknown; effect_outcome_unknown; monitor_source_missing; verification_stale; file_ownership_conflict.

The dashboard must show **observed symptom** separately from **suspected cause** and **verified cause with evidence**. A healthy partial scan is NOT global all-clear; declare required sources, event cursor range, confidence, observer lag and truncation.

## Multi-agent write and handoff discipline

1. Reserve narrow work scope and exact base revision in canonical coordinator. Duplicate file ownership becomes blocked, not a silent simultaneous write.
2. Source inspection: record reproducible code paths, dates, normative references and uncertainty; never assert that web GitHub code is locally installed.
3. Scoped write: verify expected HEAD/parent revision before mutation. On mismatch stop, create diff artifact, ask the integrator to reconcile; never force-push.
4. QA: run static, targeted regression, cross-module and fault-injection tests on exact revised HEAD. Store commands/results/CI link and independent reviewer findings.
5. Durable two-step handoff: producing agent emits handoff_pending with artifact, task ID, cursor, exact hash and next owner. Receiving agent emits handoff_ack with the same hash. Unacknowledged handoffs remain visible and not done.
6. Integrator handles final acceptance only after source collision matrix, security/retry contract and verified CI/rollback gate.

## Diagnosing stops without inventing recovery

| Symptom | Confirm using | Permitted automated action | Prohibited |
|---|---|---|---|
| Worker heartbeat missing | worker lease, fence, host process status, last trusted event | read-only incident and safe checkpoint | force restart during unknown external action |
| Browser/WS disconnected after send | dispatch record, upstream conversation readback, transport epoch | mark unknown and attempt safe readback | resend prompt on timeout |
| Provider 429 | authenticated status, budget, Retry-After | bounded safe-read backoff | UI automation to evade limits |
| Awaiting approval | exact action digest, reviewer identity, expiry | request explicit owner action | self-approval |
| Model/context cutoff | provider finish/error code, checkpoint hash | bounded continuation from committed checkpoint | infinite hidden retry |
| File conflict | expected/retrieved HEAD, competing owner | stop with diff and handoff | overwrite other's commit |
| Stream ends without terminal receipt | backend final status and event cursor | partial/unknown with preserved data | claim success from HTTP 200 |
| CI stale | tested SHA vs new target SHA | rerun exact-HEAD checks | cite old green CI |

## Resource and proof gates

Bound aggregate worker count, spawn depth, per-profile concurrency, provider QPS, total cost/tokens/wall time, stream queue depth and incident count; include 1/8/32/64/100 synthetic-worker faults and multi-extension disconnects. Event reads must be bounded with cursor and redact raw content. Terminals/effects need independent receipts and exact revision; status from model prose alone is not evidence.

Evidence grades: A = deployed exact SHA + independent live/CI + failover/readback/rollback; B = real isolated backend integration at exact SHA; C = static source inspection or synthetic tests without live target; D = hypothesis; E = environment unknown. Draft PR #11 has a source-observed C-grade API fix with authored but not-run full repository regression; the offline diagnostics have B-grade *synthetic-local only* validation, never live production validation. Local Hermes/Obsidian state is E because Local_WorkSpace MCP session terminated.

This chat is not a permanently running monitor. Continuous service requires explicit owner-directed setup as a supervised process and authenticated local runtime. GitHub Issues were disabled (HTTP 410) at audit time, so use the PR #11 SDD and review comments for coordination until a real issue/task tracker is available.