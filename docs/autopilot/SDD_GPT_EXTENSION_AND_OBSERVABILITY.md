# SDD — Hermes GPT integration, observability and multi-agent recovery

**Version:** 0.4 (2026-11-22)  
**Status:** review proposal + isolated read-only monitor and control-plane fixes; not a production activation.  
**Parent:** docs/autopilot/ARCHITECTURE.md, PR #1, base snapshot 7e9100901819ee44c16b4ddcb79a6bcb7909f591.  
**Ownership:** this SDD and observability code are in a stacked feature branch; concurrent skill-harness branch is not modified.  
**Core objective:** answer, with persisted evidence rather than model opinion, *which task was doing what, at which revision, why it stopped, what did/did not happen externally, who may safely recover it, and which evidence closes the work*.


## Architecture correction — modern Hermes Kanban is the single task owner (ADR-002)

**Supersedes any reading below that treats the prototype AutopilotLedger as a second production scheduler.**
A same-day competing-agent audit verified that the fork main at 7e910090 is substantially older than NousResearch/hermes-agent v0.23.3, published **2026-11-20**. Modern upstream has SQLite-backed Kanban boards, worker lanes, persisted tasks, dispatcher, heartbeats, task reviews and worktrees. See `docs/autopilot/UPSTREAM_PARITY_AUDIT_2026-11-22.md` and `docs/autopilot/OWNER_ACCEPTANCE_CONTRACT.md` for source evidence, Windows caveats, and user's persistent quality requirements.

**Decision:** Kanban owns the canonical task lifecycle. This isolated prototype ledger is a research/test **effect + approval + verifier** kernel, with a read-only observer for the prototype database only. It is **not** running inside upstream Kanban, its `claim()` is **not** approved for parallel production task dispatch, and `scripts/autopilot_watch.py` **does not monitor actual Kanban boards**. A separate, version-pinned Kanban projection adapter must be added and validated before the operator may see live task states.

For v0.23.3 deployment, map task identifiers from upstream Kanban into a narrowly scoped extension action journal; defer new orchestration infrastructure unless validated upstream gaps remain. Never allow both the prototype claim loop and upstream Kanban dispatcher to execute the same owner task. The safe migration is a separately isolated canary install and revertible readiness gates; no in-place pull over the local Windows working copy.

Highest-priority real-world failure investigations from current upstream issue tracker:
- Windows workers may be assigned but receive no prompt, making a task appear busy without progress;
- cancellation and global STOP can fail to propagate to child workers/watchers;
- a worker heartbeat may be mistaken for meaningful task progress;
- non-Hermes external/GPT worker lanes need a supported, typed protocol and trust model.

These are **reported upstream issues**, not demonstrated defects on this machine. Acceptance: pin upstream release, reproduce on a canary, trace assignment->prompt receipt->model call->tool action->evidence->terminal state, and verify cancellation propagation. A heartbeat and a green CI badge without executed required checks do not prove work.

**Design updates to sections C/J/L below:** reinterpret 'intake/dispatcher/worker leases' as *Kanban adapters*, never independent production authority; keep the diagnostic proof-of-concept isolated until a Kanban event feed and authenticated policy gateway are implemented. Promote the Kanban adapter and independent worker-prompt-delivery acknowledgment to P0. A native GPT integration must use documented API/SDK worker interfaces and scoped authentication, not automation of ChatGPT UI.

### GPT worker delivery handshake

To prevent 'claimed but not actually started':
1. Kanban dispatcher issues `dispatch_intent` with canonical task_id, attempt_id, lease_fence, workspace_ref and contract_version.
2. Worker replies with `worker_accepted` after validating ownership, permissions and local workspace availability.
3. Worker emits `prompt_delivered` only when the model/API/ACP adapter has accepted the actual task prompt; no dispatcher may infer delivery from process spawn.
4. Worker emits `first_model_response` and `first_effect_proposal` as independent span events, followed by receipt/evidence.
5. Watchdog classifies `DISPATCH_NOT_ACKNOWLEDGED`, `PROMPT_NOT_DELIVERED`, `MODEL_RESPONSE_TIMEOUT`, `NO_MEANINGFUL_PROGRESS`, or `EXTERNAL_EFFECT_UNCERTAIN`. Do not auto-requeue an unknown tool effect.
6. A cancellation/revocation token must be checked at every gateway call and an explicit `stopped` acknowledgment or uncertain-effect reconciliation produced. Escalate missing acknowledgment, never silently report STOP as complete.

Do not implement this handshake inside the prototype observer; wire it to Kanban worker lanes on an isolated upstream canary, with Windows/WSL regression tests.


## A. Confirmed facts versus hypotheses

Confirmed by repository inspection:
1. Fork main is a large Hermes agent project with an AIAgent synchronous execution loop, platform gateway, API-server adapter, ACP support, cron, checkpoint manager, subagents and tests. Individual workflows are not a durable cross-worker control plane.
2. PR #1 adds an **inactive** SQLite Autopilot task ledger, leases/fencing, reserved external effects, approvals and evidence. It is not wired into a live GPT or gateway execution path.
3. A separate skill-harness branch adds advisory YAML skill contracts. It neither enforces security permissions nor replaces the Autopilot ledger.
4. A GitHub commit status may report “success” while the actual status description says a review was skipped due to expired credits. Therefore raw combined-status success is not proof that a named required test suite ran.
5. Local Workspace MCP was unavailable during this audit. Live Windows processes, local Obsidian state and runtime logs cannot be asserted from GitHub alone.

Hypotheses requiring tests: dropped gateway stream can leave an uncertain in-flight tool; provider retry can duplicate an external write; many workers may starve lower-priority tasks; session/context compression may hide a previous failure; unmanaged observer may silently die; a prompt-injected issue could try to forge completion evidence. Treat every hypothesis as a fault-injection case, not an already observed outage.

## B. GPT extension scope: two transports, one trusted execution contract

Earlier project state included a **user-authorized Hermes <-> ChatGPT Web Companion / CDP bridge**, with model marker `web-chatgpt-high-cdp`, plus a separate proposed native GPT API/SDK path. Do not silently replace the CDP project with an API-only implementation. The locally installed Web Companion/extension version previously reported as **0.6.6**, experimental bridge on port **18763**, and chains Chain2/Chain3 are **historical context only**; their state on the current host is unknown because Local Workspace MCP is disconnected. A prior connectivity canary does not prove full agent lifecycle/authoritative recovery.

### B1. Web Companion/CDP transport — current project requirement

The accepted Hermes-to-GPT bridge contract was a JSON-only response envelope containing exactly `request_id`, `content`, and `tool_calls` (with a versioned schema and explicit permitted extension fields only after negotiation). A response is valid only when `request_id` exactly matches the pending request. Hermes itself interprets/executes offered tool calls through its **own** authenticated tool gateway. The model or extension never receives permission to perform external writes merely by describing a tool.

Use a user-authorized, supported browser session or explicit connector. Never bypass authentication, anti-bot checks, rate limits or platform controls; never harvest cookies or session tokens; do not treat hidden DOM scraping as an authorized unattended execution API. The extension may relay prompts/results through a consented channel, but the **cross-agent orchestration must not rely on reading ChatGPT DOM or declaring text as proof of work**. GitHub commit SHA, scoped Obsidian file hash/read-back, CI run, action receipt and explicit owner decision are the authoritative evidence layers.

A CDP transport is inherently ephemeral. If browser target or service worker disappears, mark `TRANSPORT_DISCONNECTED` and the in-flight response `UNKNOWN`. Do **not** fabricate an empty success response, auto-replay an action with unknown effects, steal another tab's lease or silently create a replacement authenticated session.

### B2. Native official GPT API adapter — optional parallel backend

A native API/SDK adapter can provide documented streaming, usage, provider response IDs and tool-call structures; it must expose the same **task/trace/effect** envelope and be evaluated separately. It is not automatically interchangeable with a browser ChatGPT model: model capabilities, billing, tool authorization, rate limits, session persistence and compliance differ. Do not assume an API credential is present or that a product ChatGPT subscription grants API access.

### B3. CDP request and result handshake

1. Hermes allocates `task_id` and immutable `request_id`, `attempt_id`, `bridge_session_id`, per-channel `lease_fence`, schema version, deadline, and accepted tool vocabulary.
2. Trusted local controller checks the preexisting user-authorized session and attaches to one explicit target only. Record target presence, extension version/manifest hash, session ownership and transport readiness; no cookie/token values in logs.
3. Persist `bridge.request_reserved` and send `bridge.prompt_dispatched` with exact request_id; wait for an explicit delivery acknowledgment. Process launch or WebSocket open is **not** prompt delivery.
4. The adapter validates JSON envelope: exact required keys, matching request_id, bounded UTF-8 length, allowed tool schema, safe tool-call identifiers, explicit error type for malformed response. Never infer a missing field.
5. Persist `bridge.response_received`, then classify each `tool_call` as `proposed`; Hermes performs tool policy check and approval. Prior to any external write, reserve a durable effect ID bound to tool name, canonical arguments, resource ID, fence and approval digest.
6. Persist the trusted tool receipt and independent downstream read-back before a retry, finalization or a new model turn. Unknown outcome is quarantined, not treated as denial/success.
7. Emit `bridge.reply_delivered` only for the matching request; end the run with explicit `completed`, `cancelled`, `failed` or `blocked_unknown` and evidence pointers.
8. If the browser disappears after dispatch but before result, never assume request did not execute. Reattach only under owner/session policy, query an explicit trusted completion receipt or require manual decision; do not double-send mutated calls.

**Transport statuses:** `NOT_CONFIGURED`, `AUTH_REQUIRED`, `TARGET_ABSENT`, `EXTENSION_STALE`, `CDP_ATTACH_FAILED`, `SESSION_MISMATCH`, `PROMPT_NOT_ACKNOWLEDGED`, `JSON_SCHEMA_INVALID`, `REQUEST_ID_MISMATCH`, `TOOL_CALL_REJECTED`, `TOOL_EFFECT_UNKNOWN`, `CONNECTION_LOST`, `RATE_LIMITED`, `COMPLETED_WITH_EVIDENCE`. Every status has an observed timestamp, step ID and retry classification; connection readiness cannot override a missing response receipt.

### B4. Browser lifecycle and 30-agent isolation tests

- One browser target/session may carry **one in-flight turn per lane** unless the bridge explicitly supports concurrent correlation. 30 agents must use a bounded dispatch queue, not 30 uncontrolled tabs probing the same ChatGPT DOM.
- Extension worker suspension, tab navigation, stale extension version, target ID reuse, CDP detach/reattach, JSON partial/truncated response, wrong request_id, duplicated tool_call_id, 429, login expiration, active owner STOP, browser crash and host shutdown are **separate** injected failures.
- A response from an old attempt/fence must never complete the new attempt, even if its text looks correct. Verify target ownership and the exact task mapping.
- Per-target semaphore, global request budget, backpressure, stream size cap, explicit user action for required reauthentication, and OS-private transport event logs are mandatory.
- The orchestrator consumes only strictly validated, authenticated structured transport events. It never reads page text to infer agent success, and cannot issue its own approval.
- Test at least 1/5/10/30 active agents using fake CDP sessions (no real accounts required), then a single owner-authorized canary with known safe no-op prompt. Record loss, duplication, false completion, p95 queue wait, task-recovery ratio and real consented prompt receipts.

**Isolated CDP contract implementation (current PR #10):** `autopilot/cdp_contract.py` adds a fail-closed **pure offline validator** for the already agreed `request_id/content/tool_calls` reply. `tests/autopilot/test_cdp_contract.py` defines correlation, duplicate key/call rejection, UTF-8 and payload caps, declared tool names and bounded argument depth tests. It deliberately cannot connect CDP, read browser tabs, grant tool permissions, execute a proposed tool, or establish a live result. The nested tool-call encoding is a **proposed negotiation shape** (normalized or OpenAI-style); test against the real extension before any runtime deployment.

**Implementation boundary now:** this repository's inspected main tree does not contain the owner's Web Companion browser extension sources; local workspace tunnel is unreachable. Therefore **no claim is made that the CDP extension or port 18763 was modified or monitored live**. This SDD documents the accepted contract and a future version-pinned adapter, not a fabricated integration.


## C. Architectural decomposition

1. **Intake plane** accepts owner requests, approved schedules and versioned task specifications. It allocates request_id, immutable task_id, project_id, risk tier and acceptance contract.
2. **Planning plane** compiles bounded DAGs of work items and dependencies; plans are proposals until verified against scope/policy.
3. **Execution plane** leases work to ephemeral GPT/Hermes/CLI/ACP workers, each with exact input revision and narrowly scoped permissions. A lease and fence token bind any action.
4. **Effect plane** reserves mutable external actions before invocation, uses provider idempotency keys when supported, records receipts, and reconciles uncertain outcomes; nothing retries unknown external effects by default.
5. **Verification plane** obtains trusted read-back, tests, CI and file hashes for the exact subject revision. A worker's narrative cannot mark evidence trusted.
6. **Observability plane** reads state and append-only events, computes reason codes and emits bounded private telemetry. It has no write authority over project tasks.
7. **Policy plane** authenticates identities and authorizes action class, reviewer, expiry and exact parameter digest; the ledger is not itself an authentication boundary.
8. **Operator plane** provides block reasons, kill switch, reconciliation queue, exact action approval, audit review and recovery runbooks.

The dependency flow is task -> attempt -> model call -> tool proposal -> policy decision -> effect reservation -> tool invocation -> external receipt -> independent evidence -> finalization. Every step must record start, finish and terminal reason or an explicit **unknown** outcome.

## D. Event and trace contract (proposed schema v2)

Persist event headers in local SQLite before publishing or displaying; publish from a transactional outbox, never directly as an irreplaceable side effect of a DB transaction. Event consumers deduplicate by event_id and advance a durable cursor only after ingest.

Required fields:
- schema_version, event_id, monotone database seq, timestamp_utc, producer_id;
- project_id, task_id, attempt_id, worker_id, lease_fence, parent_task_id;
- trace_id, span_id, parent_span_id, correlation_id (propagated across adapter boundaries);
- operation_kind and phase, state_before, state_after, reason_code, retry_class;
- subject_revision, artifact_refs, approval_ref, effect_key, provider_receipt_ref (when applicable);
- classified error kind, duration_ms, policy version and consumed budget counters;
- redaction_level, schema/contract version; never secret-bearing raw prompts, cookies, credentials, arbitrary tool output or full exception text.

Correlation rules: one top-level trace per owner request; independent child spans per agent turn/tool/action; preserve the parent trace across worker replacement; generate a new attempt_id and fence for every new lease; external idempotency key must remain stable across safe retries of the same *logical* effect. Wall-clock timestamps help operators, but order of local mutations is the SQLite seq and concurrency follows trace parent links. Never infer causality solely from timestamp ordering.

Event classes:
- task.submitted, task.claimed, task.heartbeat, task.retry_scheduled, task.cancel_requested, task.terminal;
- model.request_started, model.response_received, model.response_incomplete, model.usage_recorded;
- tool.proposed, tool.denied, tool.started, tool.finished, tool.outcome_unknown;
- effect.reserved, effect.receipt_recorded, effect.reconciled, approval.requested/expired/decided;
- verification.started, verification.evidence_observed, verification.failed/passed;
- connector.disconnected/reconnected, monitor.heartbeat/error, worker.lost/recovered;
- quota.warning/exceeded, dependency.blocked, workspace.conflict, policy.violation.

**Do not use raw user/model message text as the primary event payload.** Payload sampling must be opt-in, redacted before persistent storage, independently reviewed and bounded in size/retention. Trace links may refer to separately protected artifacts.

## E. Formal “why stopped” classification

Persist a machine-readable reason code and a last known safe step; classify separately whether the worker is alive and whether external effects are known. Priority when multiple conditions exist: uncertain effect > revoked permission/cancellation > expired lease > expired approval > trusted verification failure > retry backoff > ordinary queue state.

| Reason | Detection | Auto-recovery | Operator handling |
|---|---|---|---|
| WORKER_LEASE_EXPIRED_NOT_REAPED | DB lease <= now but task still running | Reaper may retry only if no reserved unknown effects | Inspect worker host and fence |
| EXTERNAL_EFFECT_UNCERTAIN | reservation exists without reliable receipt | **Never** blindly retry | Independent API read-back, receipt or manual reconciliation |
| APPROVAL_EXPIRED_NOT_REAPED | pending approval reached expiry | Mark blocked, do not implicitly approve | New exact request after review |
| WAITING_OWNER_APPROVAL | pending approval still valid | None | Approve or deny exact target/digest |
| PROVIDER_RATE_LIMITED | typed 429/retry-after metadata | bounded retry with jitter | Check provider quota and per-project budget |
| PROVIDER_UNAVAILABLE | classified network/5xx | retry safe model call; tool effects separate | Fail over only when model/protocol policy allows |
| CONNECTOR_UNAVAILABLE | health probe/transport failure | retry read-only probe | Verify local tunnel/agent version; do not claim file sync |
| CONTEXT_LIMIT | model reports context overflow | checkpoint/compact only verified state | Split task if required evidence becomes unreachable |
| TOKEN_OR_COST_BUDGET_EXCEEDED | shared DAG counters | No auto-reset | Reassess budget/priority |
| DEADLINE_EXCEEDED | owner-specified deadline elapsed | Stop new dispatch | Escalate or reschedule |
| TRUSTED_VERIFICATION_FAILURE | exact-SHA check concluded failure | create bounded repair task | Examine failing check, do not relabel success |
| STALE_VERIFICATION | result refers to old SHA | repeat verification for current SHA | Block merge/release |
| WORKSPACE_CONFLICT | compare-and-swap mismatch/overlap | re-read, re-plan | Request owner on irresolvable ownership |
| AUTH_EXPIRED | credential health/401 | no secret reconstruction | Reauthorize from supported flow |
| POLICY_DENIED | policy check refused action | no prompt-rephrase bypass | Explicit permitted alternative or stop |
| CANCELLATION_PENDING | revocation while in flight | no new effects | Reconcile reserved effects then cancel |
| OBSERVER_UNAVAILABLE | no health heartbeat or read error | restart **observer only**, not work | Preserve uncertainty in status dashboard |

Structured errors must include the attempted phase and a safe recovery class (SAFE_RETRY, RETRY_AFTER, RECONCILE, HUMAN_REQUIRED, TERMINAL). Human-readable diagnostic text is **derived** from the code and trusted metadata; do not store raw exceptions. For terminal status the last event kind does not alone establish root cause: retain an explicit terminal reason and a causal chain in the future event schema.

## F. Concurrency model for dozens of workers

Assumptions: 10–100 potentially overlapping GPT/Hermes agents; owner may run multiple projects; a subset share a repository, Obsidian vault or outbound API quotas. All workers should be replaceable, and model context is not a source of truth.

Mandatory isolation:
- Separate task claim, worker lease, attempt id and fence; stable task identifier survives resumption.
- Per-project DAG limits and global token/spend/active-tool ceilings. Child agents inherit and decrement the **same parent budget**; never reset counters when a child or model is replaced.
- Per-resource lock identifiers for git worktree, file path, Obsidian note, external record, deployment environment and provider credential. Stable canonical paths; no lock bypass by spelling/symlinks.
- One source writer per resource; independent verifier cannot share the implementing agent's evidence privileges.
- Git branch/worktree per writable task. Commit with exact expected head; pre-merge verify branch and base versions.
- Durable inbox for webhook notifications with signature validation and delivery dedup; reconciliation polling covers missed webhooks.
- Weighted fair admission by project: priority with aging, protection against starvation and bounded per-owner queue depth.
- A failed or missing worker cannot be treated as idle merely because UI messages stopped. Use worker heartbeat and the durable coordinator state.

**SQLite scope:** one host and local filesystem, WAL with short transactions and busy retries. Do not advertise distributed consensus. A workload with multi-host writers, high write contention or strong cross-region reliability needs a measured migration to PostgreSQL+queue or Temporal. Schema migrations and the DB backup/restore procedure are release gates.

## G. Lifecycle and crash consistency invariants

G1. Persist task/approval/effect reservation before any external mutation.  
G2. Unknown effect outcome is not “failed” or “not executed”; it stays quarantined until an independent receipt/read-back proves it.  
G3. An explicitly proven not-executed effect may be reserved again with the **same** digest and unexpired approval. An acknowledged effect cannot be replayed.  
G4. A non-retryable failure remains non-retryable even when effect reconciliation completes.  
G5. Expired pending approvals must become blocked; a stopped owner/operator must not leave a task indefinitely pending without an observable reason.  
G6. Never finalize if any required trusted evidence at exact revision reports failure; a passed result from a different source cannot override it.  
G7. Untrusted evidence cannot replace trusted evidence for the same source/revision.  
G8. Once succeeded, terminal evidence must be immutable absent an explicit new task/revision.  
G9. Reaping expired leases requires fencing old workers; any **external** call must revalidate lease at the trusted tool gateway immediately before dispatch.  
G10. No raw tool error, source code secret, authentication response or prompt transcript in default events.  
G11. A component cannot authorize and independently certify its own state transition.  
G12. Operator cancellation revokes the issue of new effects and requires explicit reconciliation of ones already in flight.

These are system invariants, not an assertion that the currently unconnected Hermes runtime enforces them.

## H. Observer architecture

Current isolated deliverables:
- autopilot/diagnostics.py: read-only SQLite observer, bounded status snapshots, cursor-only event headers, missing evidence and likely reason codes; zero tool privileges;
- scripts/autopilot_watch.py: optional host-launched observer that emits local JSONL on state changes plus health heartbeat, restricted permissions, typed errors;
- tests/autopilot/test_diagnostics.py: privacy, status, uncertainty, stale lease, approval and cursor regressions.

The observer **does not** schedule, approve, reconcile or restart work. “Snapshot-only” is marked explicitly. The file log may be appended by the host on each change; a supervisor must persistently launch/restart the watcher and alert if its heartbeat disappears. A scheduler service is a distinct future component.

For each incident the desired operator view contains: task ID, project, current owner/fence, task/attempt state, last safe checkpoint, exact SHA, last successful phase, first failing phase, cause code, last trace event, elapsed/wait time, provider health, pending effect receipts, approver needed, retry eligibility, next safe action. The current observer intentionally exposes only a safe subset until trust boundary and authenticated API exist.

Log rotation: daily rotation or 64 MiB segments; retention policy per profile; crash-safe fsync and collector cursor; OS ACLs/private directories; quarantine corrupted lines and report gaps. Do not store this monitor log in the repository or Obsidian by default. Publish only carefully selected, non-secret summary artifacts.

## I. GPT adapter behavior and GPT/ACP distinctions

For official GPT provider calls:
1. Submit a bounded request with provider request/response metadata, model identity and a task trace.
2. Persist model.request_started before network call. On timeout, mark model call outcome unknown; model-only retries may be safe **only** if no corresponding external tool was executed and budgets permit.
3. Map returned tool proposals into Hermes tool registry only through a trusted policy gateway. Tool schemas and permissions stay stable for the current context to avoid breaking Hermes prompt caching.
4. Stream deltas as ephemeral user feedback; completion requires explicit final-response metadata and persisted full output manifest (not just an SSE socket closing).
5. On client disconnect, distinguish presentation disconnect from server-side work termination; request cooperative interrupt and capture cancellation/unknown external actions. Do not discard the ledger.
6. Log token accounting including cached tokens where provider reports them; unknown usage remains unknown, never zero by assumption.
7. At agent handoff, preserve trace/task/attempt correlation, constraints, evidence manifest and unresolved-effects list; do not rely on replaying the entire chat.
8. Classify auth errors, retryable rate limits, policy denials and provider failures independently.

ACP/Copilot shim is not equivalent to a native GPT API: it sends serialized transcript text into a fresh ACP session; capabilities and cancellation semantics are adapter-specific. Treat model or SDK adapters as separate adapters under one task contract, not as interchangeable sources of identical telemetry.

## J. Options ranked by weighted engineering value

Scoring is an explicit **design judgment**, not measured production performance. Criteria: safety 30%, root-cause visibility 25%, implementation simplicity 15%, scale across agents 20%, operational cost 10%. Each criterion 1 (poor) to 5 (excellent). A score ranks what to build next, not unconditional trust.

| Proposal | Safety | Visibility | Simplicity | Scale | Cost | Weighted /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Read-only event/cause observer | 5 | 5 | 5 | 4 | 5 | **4.80** | Implement isolated first |
| Fenced policy-aware tool gateway | 5 | 5 | 3 | 5 | 4 | **4.60** | Next P0 security gate |
| Independent revision-bound verification | 5 | 4 | 3 | 5 | 4 | **4.35** | Core invariant; integrate |
| Native GPT tracing adapter | 4 | 5 | 3 | 4 | 4 | **4.10** | Follow after gateway contract |
| Temporal multi-host backend | 4 | 5 | 1 | 5 | 2 | **3.80** | Defer until multi-host evidence |
| Prompt-only self-repair | 1 | 1 | 5 | 1 | 5 | **2.00** | Optional hint only, never control plane |
| ChatGPT DOM scraping as authority | 1 | 2 | 2 | 1 | 2 | **1.50** | Reject |

Model-assisted anomaly clustering, self-critique and auto-fix proposals may be useful *after* deterministic status/event collection. Their quality must be validated by observed recovery time, false-blocking/false-pass rates and cost, not by persuasive generated prose. They must never grant themselves elevated permissions.

## K. Release gates and verification plan

P0 / offline primitives:
- Python import and syntax checks of every touched file; unit tests for the ledger and observer;
- concurrent claim test under independent DB connections; restart from persisted DB;
- exact approval expiry; denial, cancellation, stale fence, unknown effect, not-executed replay, acknowledged no-replay;
- prevent failed trusted evidence being masked by another source pass;
- prevent untrusted evidence downgrade; disallow terminal evidence edits;
- verify raw exception canary is absent from events and observer JSONL.

P1 / read-only monitored runtime:
- launch observer under local supervised process; kill/restart it; confirm durable cursor and health alert;
- inject missing SQLite DB, locked DB, corrupt DB, permission error, disk-full and log rotation;
- simulate 10/25/50 workers with deterministic fake clocks; measure DB lock contention and queue p95;
- verify that status shows **unknown** when host connectivity is missing rather than showing a fabricated healthy run.

P2 / GPT and gateway integration:
- mock official API streaming completion, partial stream, timeout, 429 and 5xx; track request IDs;
- test cancellation at each window: before model request, after model response, before effect reserve, after reserve, after effect success but before acknowledgment;
- assert one trusted gateway decision per action and no provider call on denied/expired approval;
- preserve durable task state and trace continuity across worker replacement, agent context compression and provider change.

P3 / real connector and CI:
- hermetic GitHub fake + authorized test repo; duplicated webhook event; stale SHA; check marked successful but no executed required suite;
- Obsidian read-only observer and scoped editor tests; compare-and-swap conflict, disconnected adapter, symlink traversal and write rollback;
- 24–72 hour supervised soak with injected shutdowns, clock skew, disk pressure, retry storm and provider outage.

Shipping gate: zero unauthorized writes, zero blind retries of unknown effects, zero false “verified success” against required trusted failure, exact revision matching, recoverable read-only work after hard stop, observable blocked tasks, operator-visible monitor heartbeat and audited human override. No production/unattended activation before these pass and approval policies are configured.

## L. Immediate priorities and ownership

1. **P0:** verify current upstream Kanban worker lanes and pin versioned canary, then land reviewed prototype ledger bug fixes / observer tests as a separate stacked PR (this branch); validate Python tests externally before merging. Do not activate the prototype scheduler alongside upstream Kanban.
2. **P0:** develop typed event/trace schema with schema versioning, explicit terminal reasons and transactionally persisted outbox.
3. **P0:** implement authenticated, fenced tool gateway and denial tests; ledger methods not exposed to GPT workers.
4. **P1:** integrate one native GPT adapter + one read-only GitHub observer on an isolated demo task. Capture model, tool, verifier and resource spans end-to-end.
5. **P1:** add owner dashboard with reason codes, timeline, exact revision, queue state, unresolved effect queue and approval links.
6. **P2:** integrate one scoped local editor and GitHub PR pipeline, then DAG/lock/budget coordination for many agents.
7. **P3:** long soak/failure tests, audited retention, local host supervisor and backup/restore drills.
8. **P4:** evaluate storage migration only after measured throughput or multi-host need.

Parallel ownership rule: new branch/worktree per independent agent, exact initial SHA recorded, file ownership reserved, and PR checks reviewed before integration. The simultaneous skill-harness branch owns skills and skill contract readers; this branch owns autopilot control-plane diagnostics and documentation. Cross-branch interfaces should be versioned; do not cherry-pick concurrent changes without running combined tests.

## M. Real-world research considered

Sources consulted (2026-11-22): 
- OpenTelemetry GenAI semantic conventions: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md and https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md.
- OpenTelemetry Agent Harness instrumentation guide (2026-11-12): https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/.
- OpenAI Agents tracing and integrations: https://developers.openai.com/api/docs/guides/agents/integrations-observability and https://openai.github.io/openai-agents-python/tracing/.
- Temporal durability/idempotent Activities: https://docs.temporal.io/durable-execution and https://docs.temporal.io/activity-definition.
- LangGraph interrupts/persistence and replay cautions: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/interrupts.mdx.

Read the upstream docs with version pinning before implementing a production adapter: event/span semantic convention attributes and SDK capabilities evolve. Research links are technical references, not proof that this fork has implemented those guarantees.

## N. Unresolved questions to resolve from evidence, not guessed answers

N1. Is the local owner machine running an observer/gateway process, and can the authenticated workspace channel be restored? At this audit the connector terminated.  
N2. Which exact supported GPT API account/provider and model policies are enabled? No credentials or browser sessions are inferred.  
N3. Which host and service manager will supervise the ledger, observer, local worker and restart logic?  
N4. What are acceptable maximum token spend, retry count and write scopes per role/project?  
N5. Which CI checks are required for a trusted merge, and who is authorized as verifier/reviewer? A skipped third-party review **must not count**.  
N6. Is continuous multi-host coordination actually required or just many isolated workers on one host? This controls the database choice.

Until these are decided in owner policy or verified configuration, the system must default to read-only/unactivated behavior rather than creating broad permissions.

---
**SDD quality rule:** every new recommendation must link a concrete failure mode to an invariant, a test, a deployment/rollback decision and a measurable outcome. No status of “10/10” or “fully autonomous” is asserted from text alone.
