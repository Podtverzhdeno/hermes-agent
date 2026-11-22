# Hermes ↔ GPT — on-call & incident operator runbook

**State:** proposed procedure for a future trusted observer; no watchdog is currently enabled. Do not run external effects through the read-only diagnostics module.

## 1. First response (do not destroy evidence)
Identify immutable task_id, project, exact task revision, attempt, current owner/fence, last durable ledger sequence, stage, last trusted heartbeat, required verifier receipts, external-effect reservations and stop reason.

Record current connector/host status **separately** from model/provider status. If telemetry is missing, write 'unknown' rather than 'model crashed'. Do not copy raw prompts, cookies, API keys or private document bodies into issues or shared notes.

At all times prefer read-only inspection and task-level cancellation to force-killing the entire service. If a potentially dangerous external action exists, disable further *new* tool dispatch at a trusted tool gateway and inspect its reservation/receipt before retry.

## 2. Critical decision tree

1. **Any action in reserved state, or task needs_reconciliation?** Stop automatic replay. Read downstream provider state using a trusted independent read-only adapter; reconcile using exact action digest and receipt. If uncertainty remains, hold and escalate a narrow yes/no decision. Never delete the reservation to make the task 'green'.
2. **Terminal succeeded without declared required evidence?** Reject. Restore verification policy and independent check. Old-SHA CI results do not count, even if green.
3. **Cancellation requested?** New external actions prohibited. Confirm fence and handle in-flight reserved effects by reconciliation.
4. **Approval pending?** Show exact action+target+digest+actor+expiry; require an authorized independent reviewer. No self-approval from a model message.
5. **Lease missing/expired?** Verify clock health and task state, reject stale worker; check reservation list. Retry only if the ledger proves work safe and the global budget permits.
6. **Connector down?** Record transport failure with timestamp; do not infer task ended. Put Obsidian/local sync into explicitly pending state until verified.
7. **No progress within SLO?** Inspect separate provider-first-token, provider-terminal, tool-runtime, approval wait and delivery queue spans. Missing progress alone does not establish cause.
8. **Retry budget or parent deadline exceeded?** Mark the task blocked/failed per trusted state machine and report the limit; never reset the parent's budget in a child task.

## 3. P0 / P1 / P2 severity

- **P0:** unconfirmed external effect, unauthorized action, lost permission boundary, corrupted ledger or forged trusted evidence. Block mutating effects, preserve forensic artifacts, involve an authorized operator.
- **P1:** missing lease on active task, stale CI accepted, repeated worker replacement, MCP down blocking critical proof, unbounded queue/OOM symptoms, wrong approval routing. Quarantine affected agent or adapter; do not globally retry.
- **P2:** queue delay/backoff, approved waiting, noncritical UI delivery outage, pending ordinary verification. Measure and surface, batch notifications to avoid alert storm.

Severity represents operational risk, not necessarily confirmed root cause. An observed timeout is not a verified provider outage.

## 4. Observation and replay expectations

A task snapshot must bind: (task_id, revision, attempt, fence, status, lease_until, available_at, last_event_at, parent_budget, connector_status, reserved effects, trusted evidence). The diagnostic module consumes an immutable *already-read* snapshot; it cannot fetch, authenticate or mutate the ledger.

To investigate, read events ordered by ledger sequence, compare producer-local sequence gaps, distinguish occurred time from received time, and confirm the currently fenced owner. Deduplicate webhook events before applying a state change. State and event should be committed transactionally before acknowledging receipt.

Do not use browser UI canaries as system-of-record events. A ChatGPT chat being visible and an agent responding to a prompt are not proofs that an external action was completed, authorized or persisted to the user's machine.

## 5. Local Workspace MCP outage

Observed on 2026-11-22: list_workspaces -> Session terminated. The correct report is 'local environment not observable from this ChatGPT run'. GitHub state remains independently available; no statement about whether Hermes or Obsidian is running locally should be made.

When the owner brings the local connector online, run read-only health and permission check first; verify allowed roots, current local worktree HEAD, safe snapshot path, and prior pending sync ledger. For writes use scoped editor and compare expected SHA before overwriting. Only then record a successful sync with a verified result hash.

## 6. Escalation packet

Each escalation must include: exact task and revision, first observed failing event, evidence for hypotheses, what action is blocked, whether outside effects are uncertain, the safest reversible options, and one short decision request. Do not ask owner to resolve speculative details that an independently authenticated verifier can establish.

## 7. Recovery gates and release discipline

No unguarded resume across an unknown reserved external effect. No successful terminal state without verified evidence contract. No fake passing CI or LLM assertion. No protected-main merge and no local shared file write from this experimental branch. Require independent unit/race/fault-injection tests, a green CI result for the exact PR head SHA, and staged rollback procedures.

The diagnostic tests are synthetic and do **not** run live monitoring; they verify classifier behavior only.


## 8. Owner-authorized CDP failure response

For a user-authorized `web-chatgpt-high-cdp` backend, verify authenticated lane owner, expected vs observed fence, bridge connectivity, extension attachment, target tab and command/ACK sequence. If the fence differs, halt all new browser commands. If a command is unacknowledged, do **not** blindly resend: the action may already have been applied.

A ChatGPT UI answer or token canary is only transport evidence. It must be correlated to a task and verified against independently accessible GitHub/CI/file artifacts before declaring task success. One tab, one active writer; other agents queue rather than sharing clicks or typing.

Use the pure `gpt_extension/cdp_diagnostics.py` module for evidence interpretation only. The current local bridge and actual extension health were not observed because Local Workspace MCP returned `Session terminated`.
