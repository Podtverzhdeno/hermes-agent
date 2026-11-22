# SDD: Hermes GPT Read-Only Run Auditor (independent, upstream-first)

**Version:** 0.1, 2026-11-22. **Status:** isolated implementation + tests, NOT production verified, NOT a resident monitor. **Owns:** only offline diagnostic projection and documentation; **does not own:** run scheduler, browser automation, gateway routing, API auth or shared durable state.

## 1. Exact source evidence and objective

The April 2026 fork `Podtverzhdeno/hermes-agent` main `7e9100901819ee44c16b4ddcb79a6bcb7909f591` lacks some newer run control structures. Official `NousResearch/hermes-agent` v0.23.3 (2026-11-20) and source pinned to `da8e7d71abe4ac165760cd813c0c18c53e697b90` have run APIs and Kanban. Verified directly in official `gateway/platforms/api_server_runs.py`, `api_server_run_idempotency.py` and `website/docs/user-guide/features/api-server.md`.

Modern upstream surfaces:
- `POST /v1/runs`, `GET /v1/runs/{run_id}`, `GET /v1/runs/{run_id}/events`, plus authorized stop, approval, steer, unknown outcome resolution.
- Run event JSON contains `event`, `run_id`, `timestamp`; streaming wrapper adds numeric `seq` and `id:` SSE cursor. Reconnect using `Last-Event-ID` or `last_seq`.
- Event replay buffer is **bounded** to 1,000 records per observed run stream; per-subscriber queue cap **256**. The server reports `replay.truncated`. An event subscription is NOT a durable complete operation audit.
- `gateway.api_server.max_concurrent_runs` documented default **10** (HTTP 429 beyond capacity). 30 GPT clients may experience **intentional admission backpressure**, not a Hermes crash. The actual configured value must be read from running instance.
- `RunIdempotencyStore` may fall back to non-durable in-memory storage. Check `GET /v1/capabilities` and the effective authorization/profile; do not assume all installations are durable.

- **CANCELLED does not necessarily mean externally stopped:** pinned upstream `gateway/platforms/api_server_runs.py`, `_execute_run_via_live_owner` (lines 1016–1024), explicitly states that a live Bot Chat owner may continue its claimed task even after gateway `/stop` marks a run `cancelled`. Do not infer the absence of tool effects from a terminal cancellation status; the auditor returns `VERIFY_EXTERNAL_EFFECTS_BEFORE_RETRY`.
- Native events also include `message.interim` and `run.stopping`, not only `message.delta` and terminal run events. The allowlist must stay pinned to the inspected upstream revision; legitimate new event types need a schema change rather than being mislabeled as an agent crash.


**The problem**: When a GPT UI observer disconnects or an agent stalls, determine what is known, unknown, and safe to do next. Do not invent private reasoning, tool effects, or full history from a truncated stream. Tens of agents share one human operator: reports must be short, structured, authenticated, and comparable.

## 2. Ownership and architecture

```text
Authorized local operator / extension (future)
    | GET status and subscribe to events
    v
Native modern Hermes /v1/runs (authoritative state)
    | export or independent local collector with consent
    v
Redacted SSE file + status snapshot
    | offline
    v
gateway/gpt_bridge_event_audit.py (this branch)
    | event order, tool/approval correlation, reason codes
    v
Read-only explanation JSON
    | never auto-resubmit browser prompt
    v
Authorized operator decides reconcile / observe / pause
```

This branch deliberately makes **zero changes** to `gateway/platforms/api_server.py` and `gateway/idempotency.py`, which are concurrently owned/modified by PRs #4/#5/#6. No run status override, new ledger, scheduler, wildcard Chrome permission, CDP bypass or automatic send is in scope.

## 3. Inputs and invariants

CLI:
```powershell
python -m gateway.gpt_bridge_event_audit --run-id run_0123456789abcdef0123456789abcdef --events-file .\redacted-run.sse --status-file .\redacted-run-status.json
```

Expected inputs: **at least one** access-authorized evidence source: exported SSE, separately authenticated run-status JSON, or both, from the **same resolved profile and run**. Status-only mode deliberately sets `STATUS_ONLY_NO_EVENT_HISTORY` and `EVIDENCE_INCOMPLETE` rather than claiming a reconstructed execution. No network clients or tokens are embedded. Tool arguments, full messages, screenshots, cookies, prompt content, response bodies and raw errors are deliberately discarded from the output.

Invariants:
- Every processed SSE event is bound to one `run_id`; mixed runs are rejected.
- Do not report a completed run from an SSE terminal event alone: fetch independent status.
- Missing `seq`, sequence gaps, partial replay, reordering or slow-subscriber overflow imply `EVIDENCE_INCOMPLETE`, not «agent crashed».
- Duplicate SSE sequences are deduplicated. Late events cannot rewind the current projection or mutate an authoritative run.
- The native SSE `id:` cursor and JSON `seq` field must agree; conflicting IDs are malformed evidence and are rejected. Unknown status/event/reason values are redacted, flagged as schema drift, and cannot silently become terminal success.
- Official `turn_exit_reason` values are normalized using pinned `agent/turn_explainers.py` exact and parameterized categories; any unrecognized/free-text suffix is discarded to prevent a token-shaped secret in logs.
- Pending tool call may represent external side effect. **NEVER retry solely from this diagnosis.**
- Pending approval cannot be bypassed. If an unscoped approval response may have cleared the only outstanding approval, report a **weak inference**.
- If `updated_at` of the provided status predates the latest event, flag possibly stale snapshot; re-fetch status before deciding. Clock comparison is conservative, not proof of causality.
- `tool.completed` with error flag remains visible even if later run status says completed, so the operator can inspect recovery evidence.
- All outputs are an allowlist of IDs, booleans, counters, diagnostic codes and safe timestamps, bounded by maximum input/event limits. No user content is echoed on parsing errors.

- **Syntactic validity is not redaction.** A single-token credential can match a permissive “reason code” regex. Audit metadata now uses closed allowlists for event names, run statuses and reason categories. Unknown labels are replaced by `event.unrecognized`, `unknown_status` or `UNCLASSIFIED`; tests check that fake token-shaped inputs do not reach diagnostic JSON.
- A terminal `cancelled`/`interrupted` state is an execution-control report, **not proof that a remote Bot Chat owner or previously launched external tool stopped**. Preserve this distinction in the operator action field.


## 4. Reason codes and deterministic next actions

| Reason | Meaning | Safe operator action |
|---|---|---|
| `NO_EVIDENCE` | No event observed | Check admission/auth and correct run ID |
| `NONTERMINAL_OBSERVATION` | Event stream ended before terminal | Re-query authoritative status; no blind retry |
| `TERMINAL_EVENT_NOT_STATUS_VERIFIED` | SSE claims terminal but no independent status | Query status for this run/profile |
| `EVIDENCE_INCOMPLETE` | Gap/truncated/out-of-order/uncorrelated events | Fetch status + validated replay; mark missing range |
| `STALE_STATUS_SNAPSHOT` | Status timestamp older than latest event | Re-fetch status; check clock/version |
| `POSSIBLE_EXTERNAL_EFFECT_UNKNOWN` | Started tool has no correlated completion | Verify external effect receipt; human approval if needed |
| `WAITING_APPROVAL` | Unresolved approval evidence | Pause, require authorized decision |
| `CONTRADICTORY_STATUS` | Terminal SSE and polled status differ | Repeat two independent reads; check profile/cursor |
| `COMPLETED_WITH_TOOL_ERRORS` | Terminal completed with at least one tool error | Inspect whether agent recovered |
| `COMPLETED/FAILED/CANCELLED/INTERRUPTED` | Independently provided terminal status | Inspect persisted result; don't auto-retry |

The diagnoser is a projection: its hypotheses never have write privileges. Neither SSE EOF nor `: keepalive` constitutes progress. The output is not a substitute for a real durable action/effect ledger.

## 5. Evidence-driven test gates

Source test fixture: `tests/gateway/test_gpt_bridge_event_audit.py`. Includes native SSE comments/seq parsing, duplicate handling, gaps and truncation, out-of-order events, stale and fresh status snapshots, failed tools, correlating approvals, privacy, invalid data, 30 isolated synthetic runs and bounded input sizes.

**Synthetic 30 run IDs != proof of 30 live concurrent browser tabs or model workers.** Further system tests require real profiles, available official API capability, measured admission limits, run status persistence, queue pressure, stream disconnects and browser MV3 lifetime.

Before merging: tests must finish green on exact HEAD, compare to unmodified main baseline, independent reviewer signs off that no new work authority was added. Before deployment: pin modern upstream, migrate profile state with backup, test Windows extension source/bridge with consent, verify actual network callbacks and crash recovery.

## 6. Failure and collision register

| Date | Evidence | Classification | Disposition |
|---|---|---|---|
| 2026-11-22 | Local_WorkSpace MCP initially returned session termination; later re-probe succeeded with only scoped `shelter` workspace | Transport recovered, scope insufficient | Cannot access Windows Tunnel extension |
| 2026-11-22 | Read-only MCP initial HTTP 429; later works for `temp-folder` only | Transient external transport symptom | Not proof of GPT rate-limit |
| 2026-11-22 | PRs #4/#5/#6 simultaneously modify the April-fork `gateway/platforms/api_server.py` | High merge/integration collision | This independent PR does not modify it |
| 2026-11-22 | PR #4 earlier Actions: 7,513 passed, 29 failed; 171 skipped, old compatibility assertion and environment problems | Full-suite release gate failed on earlier SHA | No merge claim; latest CI required |
| 2026-11-22 | Modern official source exposes max 10 direct runs and bounded SSE replay by default | Expected capacity and evidence-loss conditions | Prefer reason-coded 429 and replay gap reporting |
| 2026-11-22 | This branch copies only read-only auditor, synthetic tests and extension-specific contract | Implementation proposed | CI/live verification pending |
| 2026-11-22 | Focused CI on earlier SHA 90fdedbf: syntax compiled, tests failed before collection because shared pytest addopts required xdist | Verified Actions job 137186420057 | Workflow overrides addopts in later commit; rerun on exact HEAD required |
| 2026-11-22 | Upstream _execute_run_via_live_owner explicitly documents local /stop limitation on a claimed Bot Chat turn | Verified source contract | On cancelled/interrupted, independently reconcile remote effects before retry |
| 2026-11-22 | Single-token secrets passed through safe-code regex in initial auditor design | Self-review identified and code fixed using closed allowlists | Regression tests added; CI on exact HEAD is the gate |

## 7. Follow-on implementation (NOT included here)

A separate, explicitly authorized local collector can subscribe to per-run SSE and status and produce daily incident summaries, but needs actual local workspace scope and a process supervisor. It must implement bounded persistent queue, GDPR/security retention policy, authenticated profile boundaries, `Last-Event-ID` cursor, backpressure and read-only mode. A browser extension can then display the same `run_id` and last confirmed stage. The new collector must not silently approve, restart, re-submit, or patch GitHub repositories.

Any automatic fixer is **proposal-only** until: reproducible redacted failing test → isolated feature branch → independent reviewer → exact HEAD CI → rollback proof → permitted scope. Never directly write to `main` or a live ChatGPT conversation on a model's own unverified root-cause hypothesis.

## 8. Source and coordination references

- Official release: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
- Pinned upstream run handler: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/gateway/platforms/api_server_runs.py
- Pinned upstream idempotency: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/gateway/platforms/api_server_run_idempotency.py
- Browser extension contract: [HERMES_GPT_EXTENSION_COMPONENT_CONTRACT.md](HERMES_GPT_EXTENSION_COMPONENT_CONTRACT.md)
- W3C trace context: https://www.w3.org/TR/trace-context-1/
- OpenTelemetry GenAI spans: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
- Chrome MV3 service worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle


## 9. Multi-agent stop taxonomy: reuse native Hermes Kanban, NOT another orchestrator

**Directly source-verified** in official `website/docs/user-guide/features/kanban-tutorial.md`, `kanban-worker-lanes.md`, `hermes_cli/kanban_ops.py`, `agent/kanban_turn_recovery.py` (2026-11-22 upstream pin as above). These describe the modern native task authority, not the old April fork's installed behavior.

| Observed task state / result | Why progress appears stopped | Required read-only evidence and safe action |
|---|---|---|
| `todo`, unsatisfied parent | Task graph intentionally blocks dependent work | `hermes kanban show <task_id>`: parent IDs and states; do NOT bypass by re-submitting child |
| `ready` but no worker yet | Dispatcher runs at a default **60-second interval** (configurable) | Read actual dispatch interval, queue capacity, last tick and current claims before labeling stalled |
| `running`, no recent updates | Could be model wait, tool wait, OS worker dead, or lease expired | `kanban_show` run+event log, claimed PID fingerprint, task + task_run `claim_expires`, latest heartbeat |
| `blocked` after `spawn_failed` | Circuit breaker; default `kanban.failure_limit=2` consecutive failures (task override possible) | `hermes kanban runs <task_id>` and `hermes kanban tail <task_id>`; inspect `gave_up` evidence; only owner unblocks after cause fixed |
| `blocked` with explicit reason | Human escalation, not technical hang | Ask the authorized owner; never auto-unblock |
| `review` | Structured code/test/release approval lane | Match chosen same-card or downstream review model; check reviewer and failing CI; no self-approval |
| `crashed` | Worker process exited without terminal lifecycle tool, or actually died | Inspect pid/exit code/worker log and claim cleanup; reconcile possible external effects before replacement |
| `timed_out` | Worker exceeded `max_runtime` | Confirm watcher outcome, lease state and external action receipt before retry |
| `gave_up` | Failure breaker exhausted, final run outcome | Requires cause repair and explicit unblocking; no perpetual retry |
| `reclaimed` | Stale claim/expired lease reclaimed by native dispatcher | Confirm old worker fenced before successor writes; do not add a competing lease store |
| `run.queued` in API after owner retirement | Native run remains queued for a new owner (not failed) | `GET /v1/runs/{id}` + native run SSE and owner state; do NOT create second run |

**Dangerous topology:** `hermes_cli/kanban_ops.py` explicitly warns that the gateway now embeds the dispatcher by default, and running both the gateway and deprecated standalone `hermes kanban daemon` races for task claims. For a fleet, verify **one intended dispatcher per authoritative board** and active claim fencing. Do not launch the standalone daemon as a generic hang fix.

**Existing built-in audit surfaces:** `kanban_show` exposes task events and run attempts; task events include `claimed`, `heartbeat`, `completed`, `blocked`, `review_requested`, `changes_requested`, `gave_up`, `crashed`, `timed_out`, `reclaimed`, `claim_extended`. `hermes kanban runs <task_id>` and `hermes kanban tail <task_id>` provide an existing trace. The native `worker_claim_is_live` proof checks exact DB/task/run/lease/pid coordinates and fails closed on mismatch, expiry, or missing identity. Do not duplicate these mechanisms in the GPT bridge.

**Review strategy:** choose either native same-card `kanban_request_review` OR a precreated downstream review/QA/release card. Official `kanban-worker-lanes.md` warns that combining both can strand or duplicate the review lane. For dozens of agents, release ownership and review choice must be recorded with each task, not guessed from chat text.

**Potential existing visualization:** the official plugin catalog lists community `hermes-kanban-graph` (repository `Senci/hermes-kanban-graph`, pinned `6dee7313...`) as a read-only dependency/run graph. Its disclosure says it reads worker `state.db` including latest assistant messages and tool-call arguments. **Do not auto-install or expose this dashboard** without source, permissions, provenance, PII, retention and local-only binding review; prefer native Kanban CLI/Desktop status first. Read-only database access can still leak sensitive content through a web UI.

### 9.1. Strict relative evaluation (planning estimates, not measurements)

Weighted risk reduction 30%, verified-source confidence 20%, compatibility/reuse 20%, operational reversibility 20%, cost 10%; scores 1–5 and safety veto independent of score.

| Option | Risk | Evidence | Reuse | Reversible | Cost | Weighted /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Native Kanban task/run events and CLI + GPT run correlation | 5 | 5 | 5 | 5 | 4 | **4.90** | P0 preferred |
| Native claim/lease/failure-limit checks and explicit review rules | 5 | 5 | 5 | 4 | 4 | **4.70** | P0 reuse, do not clone |
| Consent-gated redacted dependency graph built from explicit summaries | 4 | 4 | 4 | 4 | 3 | **3.90** | P1 after schema and privacy review |
| Community graph plugin with full worker state.db read | 4 | 3 | 4 | 3 | 3 | **3.50** | Hold for source/privacy audit |
| Second uncoordinated GPT-run/kanban scheduler | 1 | 5 | 1 | 1 | 1 | **1.80** | REJECT by architecture veto |
| Automatic forced restart/replay of unknown external effects | 1 | 5 | 1 | 1 | 1 | **1.80** | REJECT by safety veto |

A low numerical score does not indicate a performance benchmark. Safety requirements supersede quantitative ranking. Unknown local extension code and absent user authorization remain release blockers.

### 9.2. Source links for operator reference

- Native Kanban tutorial and circuit-breaker example: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/website/docs/user-guide/features/kanban-tutorial.md
- Worker lanes and review patterns: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/website/docs/user-guide/features/kanban-worker-lanes.md
- Embedded dispatcher warning: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/hermes_cli/kanban_ops.py
- Fail-closed claim proof: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/agent/kanban_turn_recovery.py
- Community graph plugin metadata (source/privacy audit required): https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/plugin-catalog/kanban-graph.yaml
