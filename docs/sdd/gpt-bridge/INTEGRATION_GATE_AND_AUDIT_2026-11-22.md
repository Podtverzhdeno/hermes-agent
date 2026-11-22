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
