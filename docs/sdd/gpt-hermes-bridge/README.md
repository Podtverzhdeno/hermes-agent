# SDD: GPT ↔ Hermes Bridge (version 0.1, design under review)

> **Architecture gate / update 2026-11-22:** Official upstream `v0.23.3` already implements native durable `/v1/runs`, idempotency, task Kanban, delivery, leases and recovery. **Use these as owners; do not implement the proposed duplicate ledger/queue on this outdated April fork.** Read the [source-verified upstream parity and PR coordination audit](upstream-parity-and-pr-coordination-2026-11-22.md) before implementing any item below. The SQL and other contracts below are compatibility/reference designs, **not approved instructions to replace upstream components**.


**Snapshot**: 2026-11-22; source branch: `main` at `7e9100901819ee44c16b4ddcb79a6bcb7909f591`.
**Scope**: Hermes interoperability with GPT/ChatGPT clients, including optional browser extension transport, end-to-end visibility, stop-reason explanation, safe recovery and dozens of independent engineering agents.
**Status**: Proposed architecture; only the separately listed idempotency patch is implemented. Do not confuse SDD acceptance targets with achieved results.

## 1. Verified current state versus unknowns

Verified from repository source:
- `gateway/platforms/api_server.py`: OpenAI-compatible chat/completions and responses endpoints; server-side execution of `AIAgent`; SSE; X-Hermes-Session-Id opt-in continuation; ResponseStore (SQLite).
- `hermes_state.py`: SessionDB with WAL/SQLite contention handling.
- `tools/process_registry.py`: background process tracking and persisted process state.
- `tools/checkpoint_manager.py`: filesystem checkpoints, independent of business-operation recovery.
- `tools/delegate_tool.py`: isolated parallel subagents sharing a parent.
- `tools/browser_tool.py`: browser automation with task-specific sessions.
- `AGENTS.md`: profile-specific state via `get_hermes_home()`; prompt caching invariants.
- Historical local interaction canaries validate *a message exchange*, not persistent execution, CDP safety, task completion, or end-to-end monitoring.

Not verified:
- No browser/ChatGPT extension source or deployed host identified in this repository snapshot.
- No proof of an always-on GPT/ChatGPT browser channel, session recovery after a workstation reboot, distributed exactly-once effects, or real multi-agent load test.
- The local-workspace MCP failed with a terminated session during this audit. Therefore local Hermes installations, browser state, extension manifest, real runtime telemetry and local SDD could not be inspected. Do not assert that they are healthy.

**Gate 0**: identify the exact extension repository and install/build/runtime targets before modifying any browser/ChatGPT UI. Until then, the API integration is the only verified executable substrate.

## 2. Mission and non-goals

The operator should be able to answer, within one timeline:
1. Which user instruction spawned this operation, with which policy and code version?
2. Which actor claimed each step, what tool/provider ran, and what evidence confirms its side effects?
3. Where precisely did forward progress stop, and was it a deliberate approval wait, a service failure, an interrupted browser, or simply work still ongoing?
4. What recovery is safe, who is authorized to apply it, and what has already been retried?
5. Which change, test and evidence substantiate that a defect is fixed?

Non-goals:
- Claiming exactly-once external effects where the destination lacks an idempotency contract.
- Bypassing authentication, permission prompts or anti-abuse controls in GPT/ChatGPT or third-party tools.
- Treating AI-generated conclusions, screenshots or prompt statements as authoritative execution proof.
- Recording raw prompts, cookies, auth headers, full DOM, private files or access tokens in routine telemetry.
- Silently editing other agents' owned work; auto-merging to main; unbounded self-modification.

## 3. Trust boundaries and recommended transport

**Preferred**: explicit OpenAI-compatible API client → local authenticated Hermes API adapter → durable orchestrator → worker/tool adapters.

**Optional, only with separately approved product goals**: a Manifest V3 browser extension consisting of UI/content script + service worker + authenticated native-messaging host or loopback broker. The host is an untrusted input boundary and must authenticate requests, validate sender origin, enforce allowed capabilities and never accept arbitrary shell commands from page messages. Do not embed API keys in content scripts or send them to the page. Keep ChatGPT UI automation behind an explicit capability gate and user consent. Treat it as brittle and best-effort; do not simulate privileged ChatGPT runtime access.

**Fallback**: a local browser/CDP adapter for user-authorized interaction, explicitly labeled unsupported for durable/exact execution semantics. Require session identity and DOM freshness checks after each navigation; do not retry irreversible actions based on UI timeout alone.

Use one transport-agnostic envelope:
```json
{
  "schema_version": "1.0",
  "operation_id": "op_uuid",
  "request_id": "req_uuid",
  "trace_id": "32_hex",
  "session_id": "opaque",
  "tenant_id": "opaque",
  "agent_id": "agent_17",
  "step_id": "step_uuid",
  "parent_step_id": null,
  "attempt": 1,
  "lease_epoch": 4,
  "idempotency_key": "stable-per-business-effect",
  "payload_sha256": "64_hex",
  "deadline_at": "RFC3339",
  "capability": "read_document",
  "capability_version": "1",
  "policy_version": "sha256",
  "context_ref": "encrypted-or-redacted-ref"
}
```
The envelope records *identity* and *authority*, not prompt content. Actor and operation IDs must survive retries; attempt IDs must change per retry. Every side effect must have a unique, stable business key.

## 4. Required execution principles

**I1. Every operation has a final explainable status**: SUCCEEDED, FAILED, CANCELLED or NEEDS_RECONCILIATION. Never translate absence of a response into success.

**I2. Invariants are enforced by storage transactions**: state change, owner epoch and outbox event are committed together; client delivery is allowed to be at least once and consumers deduplicate. No external tool call inside DB transaction.

**I3. A paused operation is not a failed operation**: WAITING_APPROVAL, WAITING_EXTERNAL, BLOCKED_DEPENDENCY, RETRY_SCHEDULED and STALLED are distinct with explicit reason codes.

**I4. First failure preserves evidence**: freeze a redacted last-known-good snapshot, exit reason and version hashes before mutating state. Report confidence level and competing hypotheses.

**I5. Only the current lease epoch may mutate an operation**: old workers that awaken after expiry are fenced. For external tools without epoch validation, execution is restricted through a broker or classified as reconciliation-required.

**I6. Changes are reversible**: source changes in dedicated branch/PR; feature flag; unit and fault tests; rollout canary; operator-controlled rollback.

**I7. No silent failure**: all exceptions, interrupt signals, timeouts, abandoned approvals, lease expirations and auto-remediations produce a reasoned event. Logging failures must also be counted.

**I8. Prompt injection cannot grant capabilities**: permission scope derives from policy engine, not generated text. Never feed untrusted web content directly into a privileged tool router.

**I9. Profile isolation**: `get_hermes_home()` for local state; telemetry partitions by profile/tenant and may not join data just because session names match.

**I10. Deterministic evidence**: immutable event IDs, monotonic per-operation sequence, UTC timestamps plus local monotonic elapsed time, source commit, tool version, result digest and reproducible test IDs.

## 5. Acceptance gates

| Gate | Proof required | Acceptance criterion |
|---|---|---|
| G0 Repo discovery | extension manifest, paths, architecture diagram | Actual GPT bridge located; unknowns resolved or documented |
| G1 Idempotency | same-key concurrent test, conflict test, restart test | No duplicate work under tested in-process cases; cross-process separately marked unsupported |
| G2 Durable ledger | crash-injection + storage verification | No terminal success without persisted evidence; replay resolves interrupted steps |
| G3 Observability | replayable trace from input to tool and final delivery | Every injected stop has a reason code + owning component + artifact link |
| G4 Safety | credentials, origin, approval, prompt injection and authorization tests | Unauthorized effects blocked; redacted logs verified |
| G5 Scale | 10, 30, 100 concurrent actors on representative hardware | Measured p95 queue wait, contention, duplicate effects, event loss |
| G6 Release | CI green, CODEOWNERS review, canary, rollback drill | Operator can disable bridge without losing trace or corrupting state |

Each gate's evidence is versioned in `runs/`; acceptance cannot be self-attested by an AI agent.

## 6. SDD index

- [architecture-and-runtime.md](architecture-and-runtime.md): state machine, schema, transactional outbox, leases/fencing, browser transport, agent isolation.
- [failure-injection-and-observability.md](failure-injection-and-observability.md): reason taxonomy, instrumentation, forensic logs, chaos test matrix, remediation policy.
- [decision-record-and-rollout.md](decision-record-and-rollout.md): weighted decision analysis, architecture decisions, ranked proposals, milestones, agent ownership.
- [implementation-log-2026-11-22.md](implementation-log-2026-11-22.md): exact code changes, verification ledger, outstanding defects.

External authoritative references:
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenTelemetry GenAI conventions: https://github.com/open-telemetry/semantic-conventions-genai
- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- SQLite isolation: https://sqlite.org/isolation.html
- Temporal idempotency/retries (patterns; not a dependency commitment): https://docs.temporal.io/encyclopedia/retry-policies
