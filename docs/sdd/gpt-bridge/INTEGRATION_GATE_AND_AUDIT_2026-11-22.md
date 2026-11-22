# SDD ADDENDUM — GPT Bridge integration gate, causal observability and multi-agent ownership

Date: 2026-11-22. State: **DRAFT / evidence-based review, not deployed**.
Fork baseline: Podtverzhdeno/hermes-agent main @ 7e9100901819ee44c16b4ddcb79a6bcb7909f591.
This addendum is intentionally **not a second authoritative SDD or task scheduler**; it resolves integration risks between parallel proposals. Reference docs/autopilot/ARCHITECTURE.md and UPSTREAM_PARITY_AUDIT_2026-11-22.md in PR #1, and the GPT bridge SDD in PR #4.

## 1. Evidence registry (as of this review)

| ID | Confidence | Observation and location | Implication |
|---|---|---|---|
| E01 | CODE OBSERVED | The fork's GPT-compatible gateway is in gateway/platforms/api_server.py; server agents execute behind /v1/chat/completions; optional X-Hermes-Session-Id | Bridge hooks must attach to existing API and not invent a second inference service |
| E02 | CODE OBSERVED | GPT bridge PR #4 branches into SSE execution before its nonstream-only Idempotency-Key cache | A streaming retry with the header can invoke the agent twice; fail closed until durable streaming replay is specified |
| E03 | CODE OBSERVED | The request body was accessed with body.get without checking JSON object type, and message values were treated as mappings | Malformed ingress could become unclassified internal errors |
| E04 | CODE OBSERVED | Branch feat/gpt-bridge-observability-20261122 rejects concurrent duplicate keys with 409, while feat/gpt-bridge-atomic-diagnostics-20261122 coalesces and awaits | Implementations have conflicting wire-level semantics, and both edit the same API server file |
| E05 | CODE OBSERVED | PR #1 prototype has SQLite tasks/actions/approvals/evidence/events with leases; the prototype is not a live worker dispatcher | Useful for formal effect invariants, not proof of uninterrupted production operation |
| E06 | SOURCE VERIFIED | Modern upstream NousResearch/hermes-agent has persistent multi-profile Kanban with dispatcher, worker runs, recovery and completion contracts | Future integration must use one task lifecycle owner, not create two schedulers |
| E07 | SOURCE VERIFIED | Community abundantbeing/hermes-browser-extension has Chromium MV3 side panel, companion plugin, opt-in tab control and context tools; plugin requires Hermes >=0.22 | Evaluate as existing UI/transport, but do not assume it is installed or compatible with April fork |
| E08 | CONNECTOR BLOCKED | Local_WorkSpace MCP returned Session terminated; no live local Hermes, Obsidian, browser manifest or telemetry available | Cannot certify a real GPT extension or local synchronization |
| E09 | TEST NOT VERIFIED | GitHub commit status and check runs for the new stacked candidate were absent at inspection; its isolated ingress tests were created but not run in repository CI | Keep branch/PR draft and block integration |

### Immediate change on this stacked branch

The handler now rejects non-object JSON, non-object messages, non-boolean stream values, blank/oversized idempotency keys, and **all keyed SSE** before invoking an agent. The five new parameterized regression cases assert a 400 with the precise error code and that _run_agent was not awaited. This deliberately does **not** claim durable idempotency for external tool effects. Do not silently turn an unrecognized keyed streaming request into an unguarded operation.

## 2. Architecture decision (supersedes draft second-scheduler designs)

Modern Hermes Kanban must be the canonical task / run / owner / completion authority. Attach a narrow effect journal and independent diagnostic projection, **keyed to the Kanban task/run and revision**, rather than activating autopilot/ledger.py as an independent production queue. Existing fork PR #1 remains an isolated reference design for approval binding, effects and evidence until upstream migration and differential verification.

Example causal chain (DESIGNED, not currently emitted by GPT bridge):

- request_id -> kanban_task_id -> run_id -> attempt_id/fence -> step_id -> tool_call_id -> effect_id -> provider receipt -> verification artifact + exact HEAD.
- Each event has schema_version, event_id, monotonically allocated source_seq, trace_id, parent_event_id, kind, state, reason_code, observed_at, recorded_at and redacted artifact_ref.
- Durable state/effect reservation is committed **before** an external action; a timeout after reservation becomes outcome_unknown and requires read-back, never an automatic blind retry.
- Missing SSE final event, client disconnect, model tool-call proposal and a model's fluent "finished" are not verified completion.
- Export via outbox + cursor; OpenTelemetry GenAI spans are a *derived trace*, not authorization or transactional truth.

No raw prompts, DOM text, cookies, Authorization headers, secret-bearing URLs, tool arguments or private user content in routine event logs. Cross-profile and cross-tenant access requires authenticated partitioning at the control plane.

## 3. Explicit stop/recovery contracts

A stopped/slow execution is not one failure type. Normalize **observed** symptom and **hypothesized** cause separately.

| Reason | Confirmation | Allowed automatic action |
|---|---|---|
| APPROVAL_WAIT | Persisted pending action, exact payload digest, expiry, reviewer scope | None beyond reminding the owner |
| OWNER_CANCELLED | Trusted cancellation + fence revocation | Stop new effects; reconcile in-flight effects |
| LEASE_EXPIRED | Lease deadline + scheduler/worker health; beware clock drift | Reclaim only if no ambiguous external effect |
| EFFECT_OUTCOME_UNKNOWN | Reserved effect, no authenticated downstream receipt | Never retry; reconcile first |
| PROVIDER_429/QUOTA | Authenticated provider code, Retry-After and budget | Bounded backoff only on read/idempotent operations |
| CONNECTOR_UNAVAILABLE | Transport error + freshness watermark | Retry safe reads; record pending sync |
| CONTEXT_LIMIT/ITERATION_CAP | Explicit model/runner cap and last safe checkpoint | New fenced attempt with bounded context, not unbounded looping |
| SSE_EOF_WITHOUT_TERMINAL | Stream closed without verified final status | Mark unknown/interrupted; do not infer success |
| VERIFICATION_STALE | CI SHA/status differs from current target | Re-run checks for current exact revision |
| WORKSPACE_CONFLICT | Two workers claim same file/ref/revision | Block second owner and require ownership/rebase |
| HUMAN_DENIAL | Approval denied | Terminal block; do not rename action to retry it |
| OBSERVER_UNAVAILABLE | Monitor cannot read snapshot or advance cursor | Notify with unknown coverage; never issue an all-clear |

Operator display should contain: task/run/step ID, last trusted sequence, observed symptom, candidate causes and supporting evidence, current fence, effect receipts, allowable recovery, version tested, and a copyable incident ID. If only a bounded subset of tasks is displayed, state this; a partial scan must not claim global health.

## 4. Multi-agent ownership protocol (10–100 agents)

Every agent receives an immutable work contract naming project, owner role, allowed files, base SHA, acceptance criteria, budget, max fanout, independent verifier and state handoff path. Shared core components (gateway/platforms/api_server.py, tools/terminal_tool.py, scheduler, database migrations) have a **single integration owner**. Individual agents submit non-overlapping PRs or tests and must not patch the same handler concurrently.

Current observed collisions:
- PR #4 owns GPT bridge instrumentation/API change and its in-flight cache design.
- feat/gpt-bridge-atomic-diagnostics-20261122 proposes a separate incompatible cache; **do not merge both** without an explicit wire protocol decision.
- PR #3 owns ACP approval callback isolation; intersecting changes in generic terminal authorization must be reviewed together.
- PR #1 owns experimental ledger and upstream migration decision; Kanban production ownership remains upstream.
- PR #2 owns skill manifests, which are **advisory** and not privilege grants.

Use branch/write claims keyed by (repo, path group, base SHA). At every write compare expected HEAD; on conflict, stop, produce an artifacted diff, and hand off to the integration owner. Each accepted change needs a failure hypothesis, discriminating test, exact CI revision, rollout flag, rollback method and independently reviewed evidence.

Resource policy: bound per-project concurrency, provider QPS, aggregate token/cost/wall-clock limits and child-spawn budget. Default to explicit max depth and max repair attempts. A stopped chat/UI message cannot replace worker heartbeat and durable task status.

## 5. GPT/browser interface decision

Preferred unattended integration is a documented, authenticated API and structured tool/result contract. ChatGPT website DOM/sessions are **not** a machine-readable autonomous agent queue. No bypass of platform rules, approval prompts, account access limits or authentication. If a UI action has no supported interface, mark manual_required instead of pretending to automate it.

Consider reusing the public Hermes Browser Extension + companion plugin in a **separate upstream-compatible canary** only after verifying the owner's actual installed extension/revision, origin/capability scopes, secret storage and per-tab revocation. Its MV3 service worker is ephemeral, its manifest permits broad hosts and debugger, and its extension control remains opt-in. That community extension is not evidence of a first-party GPT API or of live local installation.

The old April fork cannot be assumed compatible with a plugin documented for Hermes >=0.22. Migrate side-by-side with isolated HERMES_HOME, DB backups and explicit rollback. Do **not** modify the user's running local workspace through an unverified tunnel.

## 6. Candidate improvement ranking (expert prior, not measured data)

Qualitative priority and risk, subject to measured tests:
| Candidate | Value | Risk/cost | Decision |
|---|---|---|---|
| Fail-closed keyed SSE and input preflight | High | Low | **Implemented in stacked patch; still CI-gated** |
| One canonical Kanban lifecycle owner | Critical | Migration risk | **Architecture gate** |
| Read-only incident observer + sequence cursor | High | Low | Design; avoid duplicate observer packages |
| Durable effect receipt/reconciliation | Critical | High | Stage only with trusted adapters |
| Cross-service causal event identity + OTel | High | Medium | Stage behind privacy schema |
| Single per-principal idempotency authority | Critical | Medium | Resolve conflicting branch semantics |
| File/write ownership and SHA fencing | High | Medium | Gate before broad multi-agent rollout |
| Existing browser extension evaluation | Medium | Compatibility and permission risk | Canary; do not fork speculatively |
| Raw prompt/DOM telemetry | Some debugging value | Critical privacy | **Reject** |
| Independent autopilot scheduler next to Kanban | Low net | Critical split-brain | **Reject** |
| Agent self-approval / blind effect retry | Low net | Critical security | **Reject** |

## 7. Release and fault-injection gates

G0 ownership/branch inventory current, with no overlapping unreviewed implementations.
G1 exact source revision and local target environment confirmed (older fork vs modern upstream).
G2 ingress tests including keyed streaming, malformed bodies and typed stream; no _run_agent dispatch on invalid requests.
G3 idempotency tests: same/different payload, shared bearer across distinct principals, token rotation, session reuse, process restart, abrupt disconnect and multi-process dispatch. The in-memory cache is not a substitute for effect receipts.
G4 streaming tests: model exception, cancelled stream, tool failure, no terminal, and client disconnect. Never report finish_reason=stop on failed run.
G5 1 / 8 / 32 / 64 concurrent workers synthetic test with bounded budgets, lock contention measurements, SLA, no duplicate external effects and no false verified success.
G6 kill/restart at reserve-before-call, post-call/pre-ACK, post-ACK, lease expiry, verifier outage and delayed webhook; unknown outcome must remain quarantined.
G7 CI/check-runs exact commit SHA, independent reviewer, local snapshot backups, schema migration and rollback drill.
G8 explicit owner approval before privileged integration, credential changes, production publication or destructive actions.

**Actual validation at authoring:** five request-preflight regression cases authored and Python test-file syntax checked in a local sandbox, but this repository's complete tests, live Windows install, Chrome extension behavior, GitHub CI and 24–72-hour soak **are not verified**. Another independent read-only SQLite diagnostic module underwent 20 local synthetic tests; it is *not* automatically integrated into this PR or a user's running installation.

## 8. Repro / links

- Fork main: https://github.com/Podtverzhdeno/hermes-agent/tree/main
- Experimental ledger PR: https://github.com/Podtverzhdeno/hermes-agent/pull/1
- Skill contracts PR: https://github.com/Podtverzhdeno/hermes-agent/pull/2
- ACP permissions PR: https://github.com/Podtverzhdeno/hermes-agent/pull/3
- GPT bridge owner PR: https://github.com/Podtverzhdeno/hermes-agent/pull/4
- Modern upstream Kanban: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md
- Browser extension: https://github.com/abundantbeing/hermes-browser-extension
- Extension data flow: https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md
- Extension permissions: https://github.com/abundantbeing/hermes-browser-extension/blob/main/PERMISSIONS.md
- OpenTelemetry GenAI: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- GitHub webhook replay: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- SQLite WAL: https://sqlite.org/wal.html


## 9. NEW SOURCE RECONCILIATION: three different Hermes GPT extension directions

**Correction to earlier source discovery (2026-11-22).** Public repositories with overlapping descriptions implement distinct protocols; **the owner's installed extension remains UNKNOWN** because the local workspace MCP session terminated. Do not infer deployment or version from GitHub search.

| Project / exact source | Direction | Evidence | Suitability |
|---|---|---|---|
| [intellectronica/hermes-chatgpt-extension](https://github.com/intellectronica/hermes-chatgpt-extension) | Codex local MCP app → Hermes desktop JSON-RPC over /api/ws and REST | v0.3.1 published 2026-10-01; main a32ef70c, Extension checks CI success; Node 22+ | **Preferred native UI reference** for showing Hermes jobs inside Codex; not hosted ChatGPT Cloud connector |
| [Dworr21/chatgpt-bridge](https://github.com/Dworr21/chatgpt-bridge) | Hermes → Python HTTP/WS → Chrome MV3 extension → ChatGPT web DOM | main 8288cf49 dated 2026-06-20; browser session used by local bridge | **Experimental adapter only**, pending critical correctness and security gating below |
| [abundantbeing/hermes-browser-extension](https://github.com/abundantbeing/hermes-browser-extension) | Browser sidepanel/context ↔ Hermes companion plugin | distinct browser automation design | Optional; does not replace either above |

### 9.1 Source-observed defects and suspected consequences in browser-mediated bridge

These are findings from the **public source**, not claims of an exploit or installed-runtime incident.

| ID | P | Grounded source location | Finding and release requirement |
|---|---|---|---|
| BW01 | P0 | Dworr21 bridge-host.py:841-843, 965-977 | Connected WS clients have no visible identity check; prompt delivery loops over *all* peers. Authenticate local extension identity and bind one leased destination to a request; no broadcast. Loopback bind reduces external exposure but is not a per-process authorization boundary |
| BW02 | P0 | content.js:454-489, 535-631; background.js:447-544 | Send-button count-based retry and response-container retry can submit another message after the first may have succeeded. Do not equate delayed DOM rendering with failed delivery. Once a send is possible, require backend readback or declare outcome_unknown; no blind resend |
| BW03 | P0 | bridge-host.py:899-910, 1200-1265 | WS error affects nonstream pending; SSE timeout can end without a terminal DONE while counters/logs still claim status=ok and success. Use a typed failure/partial/unknown terminal, final receipt and independent status endpoint; timeout cannot equal success |
| BW04 | P1 | bridge-host.py:951-961 | One WS disconnect discards *all* pending futures and stream queues, including work belonging to other surviving extensions. Partition by extension instance+epoch and invalidate only affected owner |
| BW05 | P1 | content.js:704-826 | Partial text on timeout is returned as response data with warning, but not a separate outcome type. Explicit partial_unverified state; do not mark terminal verified |
| BW06 | P1 | bridge-host.py:1055-1084 | Unknown requested model can silently fall back to selected model. Require explicit fallback decision or fail closed; log actual model evidence |
| BW07 | P1 | bridge-host.py:1194-1266, 1411-1431 | Conversation lock is not consistently applied across /chat vs /v1/chat/completions for one shared tab. One per-session/tab admission authority across all routes |
| BW08 | P1 | content.js:760-789 | Streaming frames contain full current snapshots, not append-only deltas. Define snapshot_replace vs delta_append and test client reconstruction |
| BW09 | P1 | bridge-host.py:1588-1611 and debug/health | Local error and health output may expose operational details. Redact raw exceptions/URLs/file paths; require authenticated local control and do not capture private prompts, DOM or screenshots in normal logs |
| BW10 | P2 | architecture.md vs actual background.js | Old architecture doc says WS lives in content script, current code uses MV3 background worker. Enforce docs/code protocol contract through tests |

**No third-party repo files were changed:** connected account has read-only access to these projects. Review code ownership and rights before external PRs. Do not automate bypasses of login, approval, rate, account or browser safety controls.

### 9.2 Source-observed strengths and gaps in intellectronica Codex MCP extension

Positive mechanisms to preserve:
- src/hermes/rpc.ts treats a disconnected pending operation as **ambiguous**, not retry-safe. No automatic re-submission after unknown delivery.
- src/hermes/service.ts:325-347 uses lazy session resume, replay epoch and sequence cursor rather than automatic task continuation. Incoming messages, tools and approvals are scoped to a profile/session.
- src/bridge/http.ts binds loopback, checks Host and Origin, imposes request body size, and uses a per-process local credential. Provider secrets stay out of the UI.
- Cron view distinguishes schedule, execution and delivery; unknown remains unknown.

Missing for **dozens of supervised agents**:
- The UI displays chats and cron records but not the full authoritative Kanban dependency graph, per-worker heartbeat, leases, external effect receipts, verified CI revision or causal failure history.
- The default hides automated chats from sources cron/kanban/tool/oneshot unless sidebar.showAutomatedChats is explicitly enabled. An invisible worker chat is not proof of an unstarted worker.
- src/hermes/service.ts:487-508 returns streaming optimistically while prompt.submit remains outstanding. Separate local_submitted, backend_accepted, executing, outcome_unknown and verified_terminal.
- MAX_MESSAGES=250, MAX_TOOLS=100 and MAX_CHATS=100 are *UI limits*, not forensic completeness. Preserve a durable cursor and event store beyond restart.
- v0.3.1 CI from October does not establish compatibility against the latest November 2026 Hermes backend. Run a version-specific live contract suite in isolated test deployment.

### 9.3 Causal contract and one-owner architecture

Use **modern Hermes Kanban** as the unique task/run authority. Both extension flavors are **edges**, not alternate schedulers. Proposed metadata-only envelope: schema_version, source, source_epoch, source_seq, event_id, ts_ms, task_id, run_id, session_id, attempt_id, worker_id, fence, kind, effect_id, receipt_id, reason_code and verified_sha. Raw prompts, credentials, browser DOM/screen content, full action arguments, file paths and personal data are forbidden in routine diagnostics.

Execution order is created → dispatched → backend_accepted → generating → response_complete → exact_revision_verified. Distinct exceptional states are delivery_outcome_unknown, effect_outcome_unknown, partial_unverified, approval_wait and owner_cancelled. A transport error after dispatch is never automatically replayed; a source epoch change requires lazy authoritative readback. A model's statement of completion does not establish CI success or external effects. Operator exports use HMAC-pseudonymized IDs, bounded output, independent monitor health and **explicit expected sources**; a clean but incomplete trace is UNKNOWN.

Offline local research bundle includes gpt_extension/trace_guard.py and tests/gpt_extension/test_trace_guard.py, which check causal envelope schema and source sequence, missing-source coverage, duplicate attempt, ambiguous delivery, unsafe retry, effect receipts and stale runs. **This is a candidate read-only validator, not wired into any live browser, Codex, GPT extension or user machine.** It cannot perform repairs or certify all agents are running.

### 9.4 Revised prioritized changes and acceptance criteria

1. **P0** Inventory the exact installed project/commit/config under authenticated local access; never assume the similar-name repo.
2. **P0** Correct browser bridge duplicate-send and false-success SSE paths and require typed signed/validated terminal evidence before allowing unattended execution.
3. **P0** Authenticate local transport, bind worker/extension/tab ownership; preserve user approvals and never broadcast prompt content to arbitrary clients.
4. **P0** Extend Codex Hermes app with read-only canonical Kanban task/run/effect/evidence timeline; report missing data and unknown delivery, not inferred success.
5. **P1** Emit ordered, privacy-safe causal events, source epoch/cursor and operator incident viewer; monitor monitor-health.
6. **P1** Establish per-conversation admission, no concurrent different-agent mutation, bounded queues, budgets and file ownership/fencing.
7. **P1** Prefer supported inference APIs for automated production; browser UI adaptation is a separately controlled canary, not an invariant interface.
8. **P2** Rich UI timeline, dynamic fault explanations and opt-in private debugging recordings.
9. **REJECT** Separate second task scheduler, unbounded raw DOM telemetry, automatic approval, blind external-effect retry, silent model fallback or green completion on SSE timeout.

Fault gate: browser/tab/service-worker restart, WS loss with >1 peer, DOM selector drift, late ack, SSE partial/no terminal, simultaneous requests from 1/8/32/64/100 agents, model mismatch, user cancel/approval, upstream backend epoch rotation, exact-HEAD CI and operator rollback drill. Do not report production pass based on static inspection or offline synthetic tests.

Source links: [MCP extension code](https://github.com/intellectronica/hermes-chatgpt-extension/tree/main/src/hermes), [release v0.3.1](https://github.com/intellectronica/hermes-chatgpt-extension/releases/tag/v0.3.1), [browser bridge host](https://github.com/Dworr21/chatgpt-bridge/blob/main/bridge-host.py), [browser background](https://github.com/Dworr21/chatgpt-bridge/blob/main/background.js), [browser content](https://github.com/Dworr21/chatgpt-bridge/blob/main/content.js).
