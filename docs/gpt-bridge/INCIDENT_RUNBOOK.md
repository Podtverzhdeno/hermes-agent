# Hermes ↔ GPT: Incident response and root cause runbook

**Scope:** investigation of observed Hermes/GPT incidents with a read-only SQLite observer. This tool is not an executor or proof of completion. External writes are managed by privileged Autopilot only after authenticated adapter integration.

## 1. Safety rules

Never treat model prose, browser DOM, or a mere heartbeat as independently verified task success. Never repeat an ambiguous external mutation. If an action was reserved and its effect is unknown, isolate it and reconcile the provider receipt first. Do not capture prompts, cookies, tokens, private chat, tool arguments or CDP websocket URLs in the incident record. No global tokens, no auto-approval of critical actions, no arbitrary browser attachment. Preserve original evidence and exact Git SHA before editing anything. Avoid overriding changes from other agents.

## 2. First response (read-only)

1. Identify the run_id, task_id, agent_id, producer_id and latest **fence** epoch; distinguish which worker owns the task versus the one producing events.
2. Run diagnostics on a **copy** or safely accessible local observation store: python -m gpt_bridge.cli --db /path/obs.sqlite integrity; then status TASK_ID and timeline TASK_ID.
3. Check the latest event sequence/time, event producer and source; compare reported events with actual worker process, collector health, provider status, Autopilot lease and independently verified receipts. If one of these sources is unavailable, state the uncertainty.
4. Before restarting anything, inspect all pending action_ids, approvals, disconnected channel_ids and detached target_ids **independently**. One reconnected tab does not clear another detached tab.
5. Classify urgency from external-effect risk, task deadline, data-loss possibility and user impact. Preserve the event database using SQLite backup API; never copy a live WAL DB without its consistency requirements.
6. Propose smallest reversible repair and one regression test; only then attempt it under appropriate owner permissions and a dedicated PR.

## 3. Reason-to-action matrix

| Observed status or reason | Verification | Safe first response |
|---|---|---|
| needs_reconciliation / EXTERNAL_EFFECT_UNKNOWN | external provider effect/receipt/idempotency key, no duplicate call | stop automatic retries; reconcile with provider or human |
| waiting_approval / APPROVAL_PENDING | exact action digest, requester, scope, expiry | request owner approval; no model self-approval |
| auth_blocked / AUTH_DENIED | trusted adapter authentication result; do not log secret | owner reauthentication through documented route |
| integration_unavailable / CDP_DETACHED_* | per-tab target identity and Chrome debugger onDetach reason | respect user cancellation; reconnect consented browser only |
| integration_unavailable / TRANSPORT_DISCONNECTED | channel ID, collector and network liveness | reconnect channel; replay stable event IDs from durable outbox |
| rate_limited / RATE_LIMITED | actual 429, Retry-After and provider quota | bound concurrency and retry delay, no unbounded loop |
| suspected_stall / NO_RECENT_OBSERVATIONS | model operation, provider heartbeat, worker and collector independently | investigate, do not automatically declare death |
| reported_completed | exact Git SHA, independent verifier CI run and external receipt | report completion as **unverified** until evidence gate |
| hash chain violation | original artifact, DB storage, backups and history | freeze trust-dependent conclusions; preserve forensic copy |
| producer sequence conflict | event_id, producer_id, fence and source_seq | investigate duplicate process/reused producer identity |

## 4. Crash ambiguity protocol

For an external write, the privileged tool gateway must persist **approval + exact action digest + effect reservation** before invocation. After timeout or crash, outcome is UNKNOWN unless a documented stable idempotency key or independent read-back proves the result. Reconciliation may record ACKNOWLEDGED or VERIFIED_NOT_APPLIED; UNKNOWN must remain blocked. A new worker/epoch does not erase the old receipt or authorize repeating the call.

For an observation append, ACK only after durable SQLite transaction commits. If sender retries with same ID/payload, return same recorded sequence. If ID/payload conflicts, reject and investigate; do not overwrite. The observer itself cannot check authorization or effect reservation.

## 5. Required incident record

- Incident ID / UTC discovery time; impact and severity.
- Run, task, owner, producer, fence, revision and environment.
- Minimal sanitized event IDs and timeline (with provenance).
- Observable symptom; what is confirmed; what remains unknown.
- Hypothesis 1 and plausible alternative hypothesis 2; evidence that would falsify each.
- First affected component; relevant failure taxonomy; why broad restart is inappropriate.
- Proposed isolated fix, code/file owner, rollback and acceptance test.
- Exact test command, exit status, check run and final Git SHA (or "not run").
- External effects pending reconciliation and exact action approvals pending.
- Reviewer, disposition, postmortem action and SDD change link.

## 6. Severity and escalation (proposal)

P0 — potential credential exposure, data loss or irreversible action uncertainty: halt privileged effect dispatch, revoke/rotate only through approved process, obtain owner response. P1 — blocked high-priority task, repeated uncertain effects or verified end-to-end event loss: isolate and request owner intervention if reconciliation cannot be independently resolved. P2 — limited transient transport/CDP interruption with no pending external effects: bounded manual or supervised reconnect. P3 — expected MV3 suspension/retryable rate limit: observe, avoid paging unless user-impacting SLO breached.

No observer event, including verification.passed, is proof of an authenticated independent verifier. Treat the observation status confidence as reported_only until the future trust adapter exists.
