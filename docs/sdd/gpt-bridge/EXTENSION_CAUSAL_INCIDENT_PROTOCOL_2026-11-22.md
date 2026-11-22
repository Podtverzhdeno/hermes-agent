# SDD — Hermes ↔ GPT extension: causal incident and effect-safety protocol

**Date:** 2026-11-22. **Document status:** design contract and source review, NOT a live extension modification or deployment. **Target:** support tens of independent agent workers without fabricating explanations for stalls. **Canonical source repo:** `Podtverzhdeno/hermes-agent`. **Related:** PR #22 read-only PR collision guard, ADR guard convergence, PR #4–6/#11 gateway, PR #13/#15 CDP.

## 1. Scope, epistemic rules and modes

- **Source-backed:** April 2026 fork implements REST `/v1/chat/completions` and `/v1/responses`. Newer official upstream Hermes has separate dashboard/gateway sessions and Kanban task lifecycle; the two cannot be assumed to have protocol parity.
- **Source-backed external candidate, not local proof:** public `abundantbeing/hermes-browser-extension` has versions of `gateway-queue.mjs` (durable-session admission, `unknown` after owner restart), `controller-protocol.mjs` (capability handshake; terminal `unsupported_gateway` vs pending `session_pending`), `session-delivery-state.mjs` (stored session identity rather than unstable WebSocket identity), `context-consent.mjs` (origin/principal/profile/controller-scoped consent), `runtime-events.mjs` (canonical tool/assistant event name conversion), and `support-diagnostics.mjs` (public diagnostic copy). These are *reuse candidates*, not evidence of what is installed on the owner's Windows host.
- **Unknown:** The actual GPT/ChatGPT browser extension's manifest, background/service worker, native host mapping, runtime login/permission constraints, installed version and observable tracing hooks. Local MCP accessible roots do not include Hermes code or the extension. No live GPT session or private model thought has been observed.

**Non-goal:** Extract or monitor a model's hidden internal reasoning, bypass ChatGPT session authentication, use private DOM/network internals as a stable API, auto-edit arbitrary Windows files, install unattended browser control, or claim external effects are exactly-once without authoritative provider coordination.

### Transport choice, ordered by available capabilities

| Lane | When usable | Canonical proof | Safe fallback |
|---|---|---|---|
| A — official supported OpenAI-compatible API | Product supports the current documented endpoint | Request/response ID, supported status, stream terminal event | API error with class and receipt; never infer tool-effect outcome from HTTP disconnect |
| B — modern Hermes gateway/WebSocket | Exact gateway revision advertises session events/resume/queue | Gateway `session.resume` + admission/generation and `events.since` cursor | Unknown admission held for user-assisted reconciliation, never resubmit from panel |
| C — third-party extension companion plugin | User installed verified version and granted exact browser capabilities | Authenticated ticket handshake; selected route, profile, context principal and epoch | `unsupported_gateway` stops; `session_pending` can await creation without retry flood |
| D — user-authorized external CDP session | Explicit tab/browser attachment and lifecycle owner verified | Attached session token/lease, tab observation, origin scoping | Detach metadata only; never terminate externally owned browser |
| E — purely observational GitHub PR metadata | GitHub read permission | Exact head/base SHA, changed file list, timestamp and incomplete indication | `UNKNOWN`; neither browser nor model-runtime proof |

A single source must own each lifecycle state; adapters may report observations but not independently advance task state. A read-only dashboard is a projection of task authority, not another queue.

## 1.1. Recommended ChatGPT integration: controlled MCP plugin over native Hermes telemetry

Official OpenAI documentation as checked 2026-11-22 offers MCP-backed ChatGPT plugins with optional UI and/or instructions/skills. This is a **distinct** transport from a browser extension or the OpenAI API running a model. A custom plugin can expose allowlisted tools to ChatGPT, whereas local Hermes is still the source of run state. A read-only MCP plugin does not, by itself, provide an always-on scheduling facility or allow ChatGPT to poll outside an active workflow.

**Two independent mechanisms are required**:

1. **Hermes-side durable monitor**, acting independently of ChatGPT connection lifetime: reads authenticated Runs status/SSE or shared gateway session event cursor, stores allowlisted metadata, records source gaps and unknown tool outcomes, and maintains an incident projection. Its own scheduler/daemon and observability health must be configured and operated separately; not implemented here.
2. **ChatGPT-facing MCP plugin**: exposes bounded, scope-checked *queries* for the durable projection. Model cannot bypass server-enforced access controls. The plugin must not claim that event availability equals continuous GPT awareness, and must not receive raw prompts, hidden chain of thought, browser cookies or unrestricted local files.

### Proposed tool surface (interface draft; not installed)

| Tool | Mode and return | Authorization | Safety |
|---|---|---|---|
| `hermes_capabilities` | Read-only: supported protocol, version, observer coverage and schema | Profile scoped; no secrets | Fail capability mismatch, not infer stopped work |
| `hermes_list_runs` | Read-only: permitted run IDs, state, stage, evidence freshness, cursor/gap | `runs.read` scope | Bounded rows, no user prompt text |
| `hermes_run_incidents` | Read-only: incident codes, last authoritative event, evidence gap, effect certainty | `incidents.read`, project bound | Separate observed cause from hypothesis |
| `hermes_run_evidence` | Read-only: exact event IDs, artifact SHA, verifier status, partial history flag | `evidence.read`, privacy filter | No raw SSE/event payload or tool arguments |
| `hermes_git_integration_risks` | Read-only: PR numbers, pinned SHA, collision classes | Repository-scoped read | GitHub metadata does not prove runtime |
| `hermes_acknowledge_incident` | Changes only **operator alert acknowledgment**, never task/effect authority | `incidents.ack` + version precondition | Does not resolve unknown tool outcome |
| `hermes_request_stop` | Privileged request with task/run ownership and latest fence generation | `runs.stop`, fresh user confirmation | `stopping` is not `stopped`; verify terminal |
| `hermes_resolve_unknown` | Exceptional owner-signed recovery proposal, **disabled by default** | Separate `runs.recover` grant and external-effect reconciliation | Never silently release queued work after crash |

All tool descriptions/annotations (`readOnlyHint`) are usability hints, **not** security enforcement. The server authenticates on *every* invocation and checks issuer/audience/expiry/scope, source profile and task permissions. Follow OpenAI's per-tool OAuth security scheme declarations and resource metadata. Do not share a broad Windows filesystem editor token with the read-only watcher.

**Private vs published:** A private MCP integration may use a secure tunnel with user-controlled setup and narrow scope. A published plugin needs its own stable public HTTPS MCP server and review; an ephemeral local tunnel is not a public production deployment. Per official docs, streamable HTTP is the expected transport, and OAuth 2.1/mTLS may be needed in the published architecture. Audit log excludes credentials; revocation rotates grant at the privileged gateway, not just in UI.

**UI:** A compact optional MCP Apps timeline may expose per-run `stage`, `last_verified_event`, `evidence_age`, `gap`, `effect_certainty`, `blocker` and suggested safe next step. No spinner that claims “agent thinks” solely from a transport heartbeat. Treat browser/Chrome extension only as an optional *user-authorized browser-control source* for tasks requiring tab interaction; do not make it the system of record for a Hermes run.

**Minimum integration gates:** unauthenticated and wrong-profile reads denied; malicious tool input never widens scope; explicit owner approval for writes; invalid/expired OAuth challenges work; no duplicate effect from retry; monitor unavailable shown as `UNOBSERVED`; 30 simultaneous ChatGPT clients do not cause 30 competing schedulers, sessions or external effects. Load/budget policy and constrained concurrency live on Hermes side.

### Source references

- OpenAI MCP Plugin server: https://developers.openai.com/plugins/build/mcp-server
- OpenAI Plugin auth: https://developers.openai.com/plugins/build/auth
- OpenAI Plugin architecture: https://developers.openai.com/plugins/concepts/plugins
- Hermes Runs API: https://github.com/NousResearch/hermes-agent/blob/da8e7d71abe4ac165760cd813c0c18c53e697b90/website/docs/user-guide/features/api-server.md

## 1a. Preferred supported native Hermes Runs API (verified in modern upstream only)

**Source of truth:** official Hermes revision `da8e7d71abe4ac165760cd813c0c18c53e697b90`, its `website/docs/user-guide/features/api-server.md` and `gateway/platforms/api_server_runs.py`. This is a stronger documented extension surface than a reverse-engineered browser tab. It does **not** prove the owner's April fork or installed GPT extension implements it.

### Capability first; never guess from a URL

- Authenticated `GET /v1/capabilities` advertises `run_submission`, `run_status`, `run_events_sse`, `run_stop` and conditional `run_approval`, `run_unknown_resolution`, `session_key_header`. This should be read before presenting controls; absent support is `CAPABILITY_MISMATCH`, not model failure.
- Use `POST /v1/runs` only for explicitly authorized new Hermes work. The 202 response contains a canonical `run_id`. For pure monitoring existing work, **do not POST**: use `GET /v1/runs/{id}` and `GET /v1/runs/{id}/events` with the correct authenticated owner scope. Polling status and SSE observation have different retention and freshness semantics.
- The Runs API's `Idempotency-Key` is bounded to **24 hours after last status update** and scoped to authenticated profile/credential. Exact replay returns the original `run_id` (202, `Idempotency-Replayed: true`), changed payload returns 409. Unkeyed POST always creates a fresh run. Expired replay evidence is not a lifetime exactly-once guarantee. Legacy OpenAI-compatible Chat Completions may instead use 5-minute in-memory dedupe (no keyed streaming in legacy); **never** transfer guarantees between modes.
- Runs events include tool and subagent lifecycle, error status, output delta and terminal reason. The SSE parser must ignore `: keepalive` comments every 10 seconds. Unconsumed event buffers expire after approximately **five minutes**; `replay.truncated` means a missing historical segment even if status polling still sees live work. A green status poll does not backfill lost tool or effect history.
- During normal shutdown, status may carry `shutdown_requested_at` while still `running` and transitions to `interrupted`; after canonical session-owner restart, status may instead be `unknown` and later session work is held. These are **different** incident causes. `POST /v1/runs/{id}/stop` returns `stopping` while executor work has not exited — NEVER report the stop as complete at this point.
- Canonical `unknown` recovery uses authenticated `POST /v1/runs/{id}/resolve-unknown` with **exact** `admission_id` and `execution_generation`, and returns an idempotent resolution receipt or 409 stale. It acknowledges that the lost worker will not finish and unblocks subsequent work; **it does not prove an external side effect did not occur**. Human/authority confirmation and effect reconciliation precede resolution. No adapter may silently invoke it from a browser reconnect.
- Canonical pending approvals expose `request_id`/`prompt_id` and `execution_generation`; stale/foreign replies return 409. A 200 `/steer` means steer was queued, not consumed; check `pending_steer` in final status if no later tool boundary. Unsupported gateway client request capabilities can fail approvals; `client.capabilities` with `server_requests: true` is mandatory for WebSocket clients that answer server→client requests, not assumed from UI rendering.
- Explicit API session IDs are constrained by their owning surface. API clients cannot write CLI/TUI/Desktop/ACP-owned conversations through Runs; 409 `permission_denied` before admission. To observe or act on such a session, use scoped authenticated shared-gateway WebSocket per advertised permissions. Do not create a shadow session to bypass ownership.
- Endpoints are authenticated with a per-profile bearer credential, optional strict CORS origin allowlist, and namespace/profile-specific permissions. A token is a secret, never an event field. Model-provided reasoning summaries may be exposed when enabled, but those are **not** internal hidden reasoning. Do not persist them in operational trace logs.

**Architecture choice:** The GPT extension should first detect a compatible native Runs API, then subscribe/poll using a read-only observer. If unavailable on the installed version, the UI must show *unsupported/version mismatch*, not manufacture success from DOM snippets. The browser extension can offer consented transport, user UX and source identifiers, while Hermes itself owns run state. A bridge observing Hermes Runs is **not** a bridge that can inspect the ChatGPT application's private hidden work.

### Runs API negative test matrix

| Condition | Expected evidence | Forbidden |
|---|---|---|
| Old server `/v1/capabilities` lacks Runs | Feature unavailable/explicit mismatch | Call guessed private route or report “worker dead” |
| Keyed exact retry across server restart within valid retention | Identical `run_id` and replay flag | New run or duplicate tool |
| Same key changed payload | 409, no new run | Silent substitute key |
| SSE disconnected beyond retention | `replay.truncated`/gap + independent current status poll | Reconstruct invented missing events |
| `: keepalive` comment | Keeps transport alive, **not** proof of run progress | Reset worker-progress watchdog |
| `stop` response `stopping` | Pending cooperative shutdown | Mark work terminal or force-kill external browser |
| Canonical `unknown` + stale admission generation | 409, blocked until exact authorized reconciliation | Resume queued follower or re-run unknown head |
| Tool error and later assistant response | Error remains as tool evidence; verify output separately | Treat all tool effects as completed successfully |
| Child delegation still running after parent turn | Source-backed child ID and session persisted delivery rules | Claim parent SSE always carries all child tool steps |
| Wrong session owner/profile | 403/409 denial and scope evidence | Create parallel writer in another surface |
| Upstream exposes reasoning summary | Only provider-supplied allowed output | Claim private hidden CoT extracted |

### Additional source-level hardening of native SSE observer (PR #30, not our implementation)

Static review of `gateway/gpt_bridge_event_audit.py` in draft #30 identified a **same-sequence replay identity bug**: `CausalRunAuditor.observe` only tracks `_seen: set[int]` and silently drops a later event with the same `seq` even if its `kind`/`tool_call_id`/`reason` differs. Example: `seq=1 tool.started` then `seq=1 run.failed` gets treated like a harmless retransmission, potentially hiding a contradictory terminal observation. The chosen observer must retain an allowlisted digest/tuple per event sequence, accept only identical replays and fail closed on contradictory reuses; never log raw payload to compare. An exact-sequence duplicate from an honest reconnect must remain cheap to accept.

A second PR #30 branch clears the sole pending approval on an identityless `approval.responded` event, even when modern canonical approval requires `request_id` and `execution_generation`. This is an *inference* that cannot close an authoritative waiting state; retain pending/unknown until exact-scoped evidence or authenticated `pending_controls`. Comment with minimal reproductions was posted on the owning PR, not a fourth observer package.

**Priority ordering:** when both event gaps and pending potentially effectful tools exist, the operator should see **both** `OBSERVATION_INCOMPLETE` and `POSSIBLE_EFFECT_UNKNOWN` with the safe action `QUARANTINE_THEN_RECONCILE`. Replaying SSE alone must not be displayed as permission for another effect. The observer remains a read-only diagnostic; it does not stop/retry tool effects on its own.

## 2. Identifiers — keep attempt, operation, and artifact separate

The **client-provided request ID** and response contract (`request_id` echo and `content`, `tool_calls` fields) are the minimum compatibility condition only where that client protocol has been explicitly negotiated. This is NOT an assertion that OpenAI's public API uses the same envelope. Do not silently rename an unsupported `request_id` to `run_id`.

| Identifier | Lifetime | Owner | What is proved |
|---|---|---|---|
| `request_id` | Exactly one client transport attempt | Client-issued, adapter echoed, must validate form | Pairing and deduplication of transport receipt |
| `admission_id` | One gateway prompt admission | Gateway queue authority | Accepted/replayed/unknown prompt |
| `task_id` | Logical user work item | Kanban authority | Scoped task, not a model execution |
| `run_id` | One claimed worker execution | Runtime scheduler | Distinct attempt at task work |
| `operation_id` | One intended potentially effectful operation | Privileged effect gateway | Dedup scope for external side effect |
| `effect_reservation_id` | Durable reservation for operation | Effect journal | Exclusive claim with fencing/version |
| `artifact_sha` | Immutable output revision | Git/content store | Hash of output, not acceptance |
| `verification_id` | Exact revision and named test suite | Independent verifier | Defined acceptance proof |
| `producer_id` + `producer_incarnation` | Process instance | Authenticated emitter | Event provenance across restart |
| `trace_id`/`span_id`/`parent_id` | Causal chain | Correlated producers | Causal join, not authority |

**Critical P0:** a successful idempotent API response replay must preserve the **original operation/run ID**, while each network attempt gets its **own request-attempt ID**. A new HTTP request or tab reconnect is not a new worker run. In PR #4 the cached reply tuple omitted the original run ID and the replay returned a freshly generated ID; the owning agent received an actionable code-review comment. This is a static-code finding.

## 3. Wire schema: versioned, allowlisted, authenticated

Proposed metadata-only envelope (`hermes.gpt.bridge.event.v1`), immutable once written:

```json
{
  "schema": "hermes.gpt.bridge.event.v1",
  "event_id": "uuid-v7-or-random-128-bit-id",
  "producer_id": "trusted-scoped-service-id",
  "producer_incarnation": "per-startup-random-128-bit-id",
  "producer_seq": 42,
  "task_id": "opaque",
  "run_id": "opaque",
  "attempt_id": "opaque",
  "operation_id": null,
  "trace_id": "32-lowercase-hex",
  "span_id": "16-lowercase-hex",
  "parent_event_id": null,
  "event_type": "tool.effect.outcome_unknown",
  "stage": "external_effect",
  "status": "blocked",
  "reason_code": "EFFECT_ACK_MISSING",
  "effect_certainty": "UNKNOWN",
  "lease_epoch": 7,
  "stop_generation": 5,
  "artifact_sha": null,
  "source_observed_at": "2026-11-22T00:00:00Z",
  "collector_received_at": "2026-11-22T00:00:01Z",
  "evidence_digest": "sha256:hex",
  "severity": "error"
}
```

**Meaningful absences:** `null` for unavailable fields, explicit `coverage` and `evidence_gap` at projection time. The collector must reject an unknown event type, field, task scope or untrusted producer; do not pass arbitrary payload through a generic `data` or `details` property. Sequence/id verification happens **before** ACK, ideally in one durable inbox transaction with dedup. Authentication requires a cryptographically authenticated connection and bounded per-producer identity; a bare hash chain does not authenticate source.

**No full prompt, response, DOM, page title, selected text, all-tab history, cookies, private CDP endpoint, OAuth token, URL query string, stack trace or raw tool input/output in shared logs.** A displayed preview may be sanitized for the operator but must not be copied into telemetry raw. Public extension `normalizeBrowserRuntimeEvent` includes raw `data` alongside a redacted `preview`: downstream collector code must allowlist fields rather than persisting the returned object wholesale. This is a precaution from source API shape, **not** a proven live data leak.

## 4. Canonical state machines — absence of evidence is not success

### 4.1 Task and model run

`CREATED → ADMITTED → LEASED → RUNNING → AWAITING_VERIFICATION → VERIFIED_DONE`

Alternatives: `ADMITTED → QUEUED`, `RUNNING → BLOCKED` (policy, budget, auth, integration), `RUNNING → CANCEL_REQUESTED → STOPPED` (authoritative stop receipt), `RUNNING → OUTCOME_UNKNOWN` (worker disappeared), `AWAITING_VERIFICATION → REJECTED / NEEDS_FIX`. Browser `run.completed` or assistant text is evidence of **transport/model turn**, not final artifact acceptance.

### 4.2 External side effect

`PROPOSED → POLICY_CHECKED → RESERVED → DISPATCHED → (CONFIRMED | FAILED_NO_EFFECT | OUTCOME_UNKNOWN)`

`OUTCOME_UNKNOWN → RECONCILING → (CONFIRMED | FAILED_NO_EFFECT | MANUAL_REVIEW)`

There is **no** `OUTCOME_UNKNOWN → DISPATCHED` retry transition without trusted proof of absence or the destination's documented idempotency guarantee binding the same stable key/digest. A tool call result can fail after the remote write succeeded. The supervisor checks lease fencing and STOP generation immediately at the privileged call boundary, not just at task start.

### 4.3 Extension transport

`CONFIG_UNVERIFIED → HANDSHAKING → CAPABILITY_NEGOTIATED → ATTACHED → OBSERVING`

`HANDSHAKING → UNSUPPORTED_GATEWAY` is terminal for unchanged configuration. `HANDSHAKING → SESSION_PENDING` waits for the gateway, bounded by user-owned session creation; no independent prompt. `ATTACHED → TAB_DISCONNECTED` never implies model/worker stopped. `ATTACHED → CREDENTIAL_EXPIRED` requires authorized reauth. `OBSERVING → EVENT_GAP` is read-only degraded coverage. The adapter can reconnect and read missing event cursor, but cannot create new external actions merely to repair telemetry.

### 4.4 Git integration

`PR_OPEN → SOURCE_SNAPSHOT_OBSERVED → CANDIDATE_RECONCILED → REQUIRED_EXACT_SHA_CHECKS → INDEPENDENT_REVIEW → APPROVED_MERGE`

`SOURCE_SNAPSHOT_OBSERVED` does NOT mean `MERGE_SAFE`. A green read-only scanner signifies only `COLLECTION_COMPLETE`, while a failed or unavailable scanner means `EVIDENCE_INCOMPLETE`. GitHub's many REST requests cannot yield an atomic cross-PR snapshot; a second-pass HEAD check narrows, but never eliminates, race windows.

## 5. Incident state: symptom, cause, counter-hypothesis

Every incident projection must include: `incident_id`, `task_id`, `last_authentic_event`, `last_progress_event`, `observed_stage`, `symptom`, `supported_cause` (nullable), `counter_hypothesis`, `evidence_sources`, `evidence_gaps`, `effect_certainty`, `safe_recovery`, `recovery_owner`, `revision`, `detected_at`, `triage_status` and `coverage_as_of`. Health is not a single Boolean.

| Symptom | Evidence needed to assert root cause | Counter-hypothesis | Default action |
|---|---|---|---|
| No answer after GPT submit | Accepted admission ID and server event cursor | Client never sent / request rejected | Probe read-only session admission |
| Accepted but no assistant output | Worker claimed, model request start, stage deadline | Waiting for approval, model budget, network | Distinguish blocked vs no-progress; no blind replay |
| Browser tab disappeared | Tab lease/generation lost | Hermes worker still running | Detach/reattach with consent; check run authority |
| SSE silence after headers | Last upstream event seq + termination | Client disconnected while tool still executing | Outcome unknown; no fake `[DONE]` success |
| Tool timeout | Effect reservation and provider receipt/readback | Write committed but ack lost | Quarantine and reconcile |
| Gateway 401/403 | Auth status from legitimate server | Scope-policy denial vs expired token | Manual reauth or policy approval, not retry storm |
| Gateway 429 | `Retry-After`, shared rate-limit authority | Budget exhaustion, fleet stampede | Global cooldown, budget awareness, bounded jitter |
| Heartbeat but no progress | Last progress timestamp, stage/lease deadline | Legitimate long-running tool | Delay classification until bounded stage SLA and effect assessment |
| STOP button pressed | Privileged revocation generation and gateway receipts | UI only dismissed, task still active | Verify enforcement at all dispatch/effect boundaries |
| CI check green | Check name, SHA, conclusion, required policy | Optional/skipped check only | Independently verify required exact-head suite |
| Duplicate assistant response | Durable stored session/admission and delivery cursor | Model produced distinct content vs UI replay | Dedupe by stable identity and event ID; don't delete user content |
| Unknown event name | Producer version and schema capability | Upstream protocol drift | Record code/count, omit raw payload, review adapter |

Alert only on **changes of authoritative state** or prolonged verified lack of progress. Deduplicate using (`project_id`, `incident_class`, `task_id`, `active_fence`, `state_generation`), bounded TTL and channel budget. Notify an owner at most once for one unchanged incident generation; do not spam on six-hour PR inventory cycles.

## 6. Correctness under crashes and concurrency

A 30-agent deployment can produce misleading logs if every agent has its own SQLite truth. Use **one project task authority**, one selected trusted effect gateway, and a separate observer-only projection. Per-task wall clock and per-producer source sequence are not a global order; reason from parent event, lease/fence and durable acknowledgement.

### Crash matrix (negative tests first)

| Crash point | Durable residue required | Forbidden behavior |
|---|---|---|
| Before ingress receipt | No authenticated admission proof | Claim task started |
| After admission before dispatch | Queued row/ID | Create duplicate task on reconnect |
| After worker claim before first model call | Lease + dispatch status | Claim model error from absence of text |
| After external-effect reservation before call | Reserved intent with policy digest | Reuse effect key with different body |
| Immediately after remote side effect, before receipt | `OUTCOME_UNKNOWN` | Blind retry |
| After response generated, before returned to client | Stable operation result and original run ID | Create new run ID for replay |
| After browser disconnect but worker alive | Runtime still authoritative | Kill external browser or worker silently |
| After collector transaction, before ACK | Event dedupe key in inbox | Append duplicate progress that resets stall timer |
| After STOP generation increment | Revoked capability at gateway | Any new external effect by old fence |
| After git commit before CI | Exact HEAD awaiting checks | Promote from green ancestor |

A successful local `BEGIN IMMEDIATE` ledger transaction plus fsync-safe storage does **not** make the remote provider transaction atomic. A token/authorization stored in a file can be stolen; keep sensitive values in OS-managed or scoped secret store and make logs reference opaque secret IDs only. SQLite WAL with synchronous settings and backups requires deliberate config testing on NTFS; do not assert cross-process guarantees on a network share.

## 7. Verification fixtures and metrics

**Golden replay cases** for every selected implementation:
- Same idempotency key + same canonical fingerprint requested twice concurrently: one run/effect, two independent request-attempt traces, original run ID returned.
- Same key + changed body, session, scope or approver: reject before any model/tool work.
- Loss of ACK after external write: no second call, `OUTCOME_UNKNOWN` until trusted destination reconciliation.
- Pending gateway `unknown` after crash: queued follower must not proceed until policy-authorized resolution.
- Event seq 8, 10 without 9: gap, `OBSERVATION_INCOMPLETE`, never “healthy.”
- Wrong producer signature, stale fence or stop generation: reject and log redacted reason.
- Failure tool event followed by “assistant completed”: must not mark output or tool effect verified.
- Two tabs / 32 agents with shared provider quota: bounded global 429 backoff, no retry stampede; one scoped writer per critical file group.
- 30 PRs all editing one executable file: 435 pairwise collisions in read-only report; 100 disjoint PRs still **review-only**, not merge-certified. Add cross-PR `Foo.py` vs `foo.py` and Unicode NFC/NFD aliases: flag likely Windows checkout conflict even though Git paths differ. Exact NTFS checkout is needed to prove impact.
- Process shutdown on externally attached CDP: detach only; user's browser remains alive.

Measure before choosing thresholds: false-positive/negative stop diagnosis on seeded cases, duplicate-effect count (target **zero in supported idempotency/reconciliation scenarios**), last-evidence staleness distribution, stage-level latency, 429 rate and recovery, event gap rate, queued starvation, exact-SHA coverage, operator minutes to confirmed cause, storage cost per 1k events, and redaction-leak tests. Do not claim a score `10/10` or unsupported throughput from 19 tests.

## 8. Practical integration/release plan

**G0:** retrieve actual Windows extension manifest, semver, service worker/broker/profiles and explicit user consent; read-only only. If unavailable, status `HOST_NOT_OBSERVED`, no local canary.

**G1:** freeze conflicting code ownership: one API integrator for #4/#5/#6/#11, one browser integrator for #13/#15, one observer integrator for #8/#9/#12/#16/#21/#23/etc, one PR guard integrator for #14/#18/#22/#24/etc. A human or separate verifier reviews each.

**G2:** pin runtime; compare old fork to upstream v0.23.3 in a **separate Windows canary**. Modern Kanban and gateway admission may be reused only after protocol negotiation and isolated DB tests. Original executable/DB working copy must not be overwritten.

**G3:** implement single versioned event contract at supported boundaries. Do not instrument private ChatGPT UI or hidden reasoning. Separate request ID from operation/run ID and source/evidence confidence.

**G4:** tool/effect authority: durable reservations, scope/STOP/fence at effect boundary, confirmed provider receipt or quarantine. No autonomous write recovery without verified absence.

**G5:** test security, exact SHA, Windows+Linux+browser compatibility, worst-case 1/8/32/64 workers, 100 PR metadata, crash/restart/rollback; independent reviewer attests exact candidate.

**G6:** only after owner approval promote from canary, keep the previous working build, and enable the single scheduled read-only scanner with explicit `COLLECTION_COMPLETE/HOLD_FOR_REVIEW` distinction.

### Reuse and implementation priorities

| Priority | Change | Why / status |
|---|---|---|
| P0 | Pin a single Kanban/gateway ownership boundary | Upstream has a lifecycle already; adaptation unverified |
| P0 | API replay original run ID + keyed-SSE ingress denial before dispatch | Static issue observed in PR #4; comment posted |
| P0 | Preserve external CDP browser and redact all CDP failure branches | Static gaps observed in fork main; #13/#15 integrator notified |
| P0 | One PR integration scanner and exact-SHA required checks | Three+ redundant scanners already in active draft PRs |
| P0 | Unknown external effect quarantine and STOP fencing | Mandatory design, not yet implemented |
| P1 | Browser durable stored-session ID, consent, `unknown` queue replay guard | Exists in public extension source; actual installed compatibility unknown |
| P1 | Authenticated read-only event inbox with gap detection | Observer drafts conflict, must choose one |
| P1 | Structured operator diagnostic exporter (no prompt/secret data) | External extension support-diagnostics already demonstrates redaction |
| P2 | Deduped incidents, per-stage resource budgets and causal timeline | Only after P0 correctness and real baseline measurement |

## 8a. Broad CI forensic classification — do not certify a merge

GitHub Actions full `Tests` on PR #22 SHA `4f5f3eedf6ca3c43ac9b5ef0eb0435d9e59b574d` reported **28 failed, 7,520 passed, 171 skipped**. Grouped from the exact job log:

| Test family | Fail count | Observed error | Interpretation |
|---|---:|---|---|
| `tests/test_streaming.py` | 20 | OpenAI client initialization: missing credentials | Provider/test-fixture setup failure; **not** proof that a real provider call should be made in CI |
| `tests/test_context_token_tracking.py` | 1 | Same missing-credentials error | Verify fake client construction and explicit dependency injection |
| `tests/test_surrogate_sanitization.py` | 1 | Same missing-credentials error | Ensure sanitization tests do not need live credentials |
| `tests/test_run_agent.py` | 1 | Same missing-credentials error | Mock provider boundary before client construction |
| `tests/agent/test_auxiliary_client.py` | 1 | `assert None is not None` | Investigate vision/custom-endpoint fallback; exact functional cause unresolved |
| `tests/test_codex_execution_paths.py` | 1 | Expected refresh recovery response differs | Review 401 refresh mocked contract and returned error; not necessarily a provider outage |
| `tests/tools/test_file_read_guards.py` | 3 | Bounded 30-second test timeout | Distinguish deadlock, slow filesystem and test scheduling; instrument minimal offline fixture |

Sum: **20+1+1+1+1+1+3=28**. On an older PR #22 commit, the broad suite also failed 28 tests (but with a different pass count). This repetition suggests a stable failure pattern but does **not** constitute a controlled baseline A/B, because the same commit and test environment were not run on default branch. GitHub API currently returned **zero `main` workflow runs**. Thus `CI_BASELINE_UNAVAILABLE` must remain explicit.

**Safe investigation:** pin dependency lockfiles, retain exact failing testcase names and SHA, then run the same suite on a clean `main` worktree and the candidate using identical toolchain, with all outbound requests blocked and test-injected fake provider. Compare failures by testcase ID, not total alone. If a specific test needs a credential, fix its mocking/fixture boundaries; do **not** hide the problem by supplying a production API key or setting a dummy key that can trigger real external calls. For timeouts, isolate the file-read guard suite under controlled load and record OS, process state and per-case timing; do not inflate its 30-second watchdog without proof.

Release gate remains **BLOCKED** while required named tests have failures, no matter how many local observer tests pass. The read-only collision guard's passing cases and the whole product's failing suite are distinct facts.

## 9. Evidence and source log

2026-11-22 **verified sources**: GitHub fork main HEAD and PR file patches; #4 replay header behavior; #13/#15 browser cleanup and raw CDP endpoint logging; 30 open drafts; older broad Tests (28 failures) and 19/19 exact-head offline PR22 tests; official latest Hermes release v0.23.3 (2026-11-20 publication); external `abundantbeing/hermes-browser-extension` modules enumerated above; read-only local MCP root inventory (not Hermes). All technical proposals above labeled as implemented/proposed/unknown. PR22 is draft, no production merge or installed extension edit occurred.

### Public references

- Hermes official API server: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md
- Hermes Kanban worker lanes: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban-worker-lanes.md
- Public browser extension and companion plugin: https://github.com/abundantbeing/hermes-browser-extension
- Browser controller protocol: https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/controller-protocol.mjs
- Durable gateway queue: https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/gateway-queue.mjs
- Consent ledger: https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/context-consent.mjs
- Stored delivery session identity: https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/session-delivery-state.mjs
- Runtime event conversion: https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/runtime-events.mjs
- W3C Trace Context: https://www.w3.org/TR/trace-context-1/
- OpenTelemetry GenAI: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- SQLite WAL: https://www.sqlite.org/wal.html
- Chrome MV3 service worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
