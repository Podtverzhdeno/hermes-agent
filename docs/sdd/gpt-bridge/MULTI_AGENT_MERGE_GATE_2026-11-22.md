# SDD Addendum: Hermes ↔ GPT cross-agent integration and evidence gate

**Recorded:** 2026-11-22. **State:** DRAFT; structural controls verified offline, live extension NOT verified.  
**Code baseline:** [`Podtverzhdeno/hermes-agent` main `7e9100901819ee44c16b4ddcb79a6bcb7909f591`](https://github.com/Podtverzhdeno/hermes-agent/commit/7e9100901819ee44c16b4ddcb79a6bcb7909f591).  
**Owner of this addendum:** independent integration reviewer; does not take over GPT gateway, browser extension, task ledger or existing parallel PR branches.

## Decision D-01 — What the owner actually needs

The objective is **causal, evidence-backed process visibility and recoverability**, not more status messages. Every agent must be distinguishable by task, run, attempt, lease fence, action, external receipt, branch and code revision. A stopped chat response, closed Chrome tab, disconnected telemetry socket, max-iteration termination, provider 429 or a worker crash do not imply the same failure. Never reinterpret an *absence of observations* as an authoritative *absence of an external side effect*.

The user may employ tens of independent agents at once. Thus, the first immediate scaling risk is *uncoordinated edits and incompatible designs*, even before runtime agent scheduling. A decision for one proposed implementation must not authorize the merging of every competing PR.

This addendum adds an **offline, read-only preflight tool** `scripts/gpt_bridge_pr_gate.py`, a bounded snapshot `docs/sdd/gpt-bridge/PR_INVENTORY_2026-11-22.json`, and isolated tests. The tool does not call GitHub/ChatGPT, apply patches, spawn agents, mutate a database or authorize merging. Its output is a structural conflict report only.

## Evidence ledger (fact vs interpretation)

| ID | Classification | Evidence | What is and is not known |
|---|---|---|---|
| E-01 | Repo observed | Main `AGENTS.md`, `gateway/platforms/api_server.py` | Hermes has a GPT/OpenAI-compatible API. This does **not** prove there is a running ChatGPT extension. |
| E-02 | Source observed | PRs [#4](https://github.com/Podtverzhdeno/hermes-agent/pull/4), [#5](https://github.com/Podtverzhdeno/hermes-agent/pull/5), [#6](https://github.com/Podtverzhdeno/hermes-agent/pull/6) | All edit `gateway/platforms/api_server.py`. Their duplicate request semantics cannot be safely merged by summing patches. |
| E-03 | Source observed | PR [#11](https://github.com/Podtverzhdeno/hermes-agent/pull/11) stacked on #4 | It adds fail-closed ingress checks for keyed SSE. Parent #4 HEAD must be revalidated at integration time. |
| E-04 | Source observed | PR [#10](https://github.com/Podtverzhdeno/hermes-agent/pull/10) stacked on [#1](https://github.com/Podtverzhdeno/hermes-agent/pull/1) | At inventory, #10 base SHA `59adecd6…` differs from #1 head `c315a8da…`. The child requires replay/rebase/reverification. |
| E-05 | Source observed | PR [#9](https://github.com/Podtverzhdeno/hermes-agent/pull/9) and PR #1 | Both edit `pyproject.toml`; #8, #9 and #10 offer separate diagnostic/observer approaches. Select one canonical observer contract. |
| E-06 | Connector failure | `Local_WorkSpace__list_workspaces` | `Session terminated`; no local extension files, live logs, Obsidian sync, Windows installation or Chrome session was verified. |
| E-07 | Offline tested | 24 dedicated `pytest` cases against the structural gate | Verifies input rejection, collision rules and default non-approval; not a Hermes integration test. |
| E-08 | External upstream documentation | NousResearch Hermes Kanban; Chrome MV3; OpenTelemetry; W3C; SQLite | Supports a design hypothesis; **not** evidence that a specific local runtime meets it. |

## Decision D-02 — One canonical task authority and one effect boundary

**Candidate:** migrate/align with the actual modern upstream Hermes Kanban lifecycle and use a narrow add-on effect/approval/verification journal when needed. The experimental `autopilot/ledger.py` of PR #1 is an offline design/reference; do **not** activate it alongside upstream Kanban as a second live task scheduler. A single stable `(task_id, run_id, attempt_id, fence)` identifies the active claim; stale workers cannot execute side effects.

Every external action has `action_id`, `payload_digest`, `approval_receipt`, `reservation_id`, `provider_idempotency_key` (where supported), downstream confirmation or independent read-back, and reconciliation status. The **privileged dispatcher/gateway** owns effect authority. Observer events, LLM text and the Chrome DOM may not grant a permission or mark an external action verified.

For **side effects after transport loss**: reservation-before-call, then if no trusted receipt -> `EFFECT_OUTCOME_UNKNOWN`; first reconcile with the provider or an independent read-only check. Do not blindly rerun, even if a replacement agent claims the previous one failed. Cancellation revokes new effects; already issued effects remain to be reconciled.

## Decision D-03 — One canonical API behavior before implementing more code

Exactly one GPT-compatible API implementation must own `gateway/platforms/api_server.py`. Draft #4 and #5 differ on concurrent duplicate request behavior (409 vs joined computation); #6 adds its own variant. The integration owner must write an explicit wire contract **before picking**:

1. Principal and credential scope for idempotency, session scope, exact body fingerprint, TTL, durability and restart behavior.
2. `Idempotency-Key` behavior for nonstream requests, in-flight duplicates, payload mismatch, client cancellation, worker crash, process restart and shared credentials.
3. SSE: keyed stream must reject **before dispatch** until replay semantics exist; no false success sentinel after exception, tool failure, disconnect or missing terminal event. A closed SSE stream means unknown unless a trusted terminal record is read back.
4. Stable response/session IDs and separate `request_id`, `run_id`, `trace_id`; never use the model's answer as completion evidence.
5. Tests for 1, 8, 32 and 64 concurrent requests, including two separate processes, and crash windows before/after an external effect. Process-local dedup is not exactly-once execution.
6. Refuse unsafe server exposure without authorization and explicit security review; keep secrets, prompts and raw tool args out of telemetry.

**Decision state:** API implementation unselected. The existence of passing tests on any one branch does not resolve the semantic collision.

## Decision D-04 — Choose observer by its guarantees, not by its directory name

Current competing concepts: `hermes_gpt_bridge/diagnostics.py` (#8), `gpt_bridge/observability.py` (#9), `autopilot/diagnostics.py` (#10), plus #4/#5 API diagnostics. The final interface shall be an **independent append-only observation plane** with one versioned event contract and one source-of-truth for action outcomes. Recorder labels are claims until producer identity is authenticated.

Minimum event envelope: `schema_version`, stable `event_id`, `task_id`, `run_id`, `attempt_id`, `agent_id`, `producer_id`, producer epoch, monotonic `source_seq`, `trace_id`, `parent_event_id`, `action_id` if applicable, `kind`, reason enum, `observed_at`, **collector receipt sequence**, privileged fence and privacy-safe metadata. Outbox commit and ACK must be atomic from the producer's perspective; replay should preserve ID and payload hash. Different producer epochs are not ordered by wall clock. One tab detach cannot clear the status of another tab or action. Hash chains alone do not authenticate event authors.

Expose **observability gaps**: last delivered source sequence, gaps, queue age, observer health, authoritative ledger watermark, uncertain effect count and partial scan indicator. The UI must distinguish `reported_success` from `verified_success`, and `suspected_stall` from `failed`.

## Decision D-05 — Extension path is gated by provenance, consent and platform semantics

Do not assert the custom ChatGPT/GPT extension was inspected or repaired: local workspace did not connect. Community [Hermes Browser Extension](https://github.com/abundantbeing/hermes-browser-extension) is a **candidate** for a separate compatibility canary, not proof of the user's installed extension. Its typed `hermes.browser.turn.v2`, per-tab control and companion plugin warrant evaluation against the exact installed version and runtime. Browser permissions, host origins, session binding and user approval must be rechecked from actual manifest and source.

Chrome MV3 service workers can be suspended; durable pending work therefore must live outside volatile JS globals. Chrome `debugger.onDetach` distinguishes `target_closed` from `canceled_by_user`; either can disconnect an observer without proving the business task failed. A native transport is not necessarily installed or permitted. Prefer official authenticated APIs and documented extension hooks over using the ChatGPT website DOM as a task authority. Do not automate authentication bypasses or concealed website behavior.

## Failure causality and safe reaction

| Observed symptom | Plausible causes | Discriminating evidence | Response permitted without new user approval |
|---|---|---|---|
| No model output / quiet tab | Provider latency, sleeping service worker, broken event pipe, agent cap | Provider receipt, worker log, outbox cursor, explicit terminal state | Read-only diagnostics; no mutating replay |
| HTTP 429 or Retry-After | Rate limit, account quota, burst contention | Actual response headers and scoped principal | Backoff only for provably safe/idempotent operations within budget |
| Worker lease expired | Crash, sleep, clock drift, stalled process | Lease epoch, heartbeat source, pending reservations | Reassign only after effect reconciliation and new fence |
| GPT SSE ended abruptly | Client close, transport drop, parser failure, backend exception | Server-side terminal event and durable result lookup | Unknown result; no success assertion |
| Chrome debugger detached | Tab closed, owner DevTools takeover | `onDetach` reason, tab/target/document generation | Respect owner cancellation; no automatic forced reconnect |
| Multiple agents edited same file | Concurrent branches, outdated ownership, merge conflict | Exact base/head SHAs and intersecting paths | Freeze common file, assign integration owner, cherry-pick reviewed tests |
| Success message but no verified artifact | Model self-report, stale CI, wrong commit | Independent CI/result tied to exact HEAD and trusted verifier | Status remains `reported_only` |
| External timeout after write | Lost ACK, write executed, duplicate webhook | Idempotency receipt and independently observed provider state | Quarantine action and reconcile |
| Collector DB locked/full/corrupt | SQLite contention, disk full, WAL growth | OS/SQLite error, checkpoint/lock metrics, hash/integrity check | Alert observer unavailable; never claim all-green |

## Machine-checkable invariants implemented here

- Validate an explicitly versioned, size-bounded **snapshot** of PR heads, bases, path sets and scope decisions. Malformed input yields no untrusted content in error diagnostics.
- Detect incompatible edits to a common file by independent PRs, distinguishing **stacked** ancestry from independent parallel ownership.
- Detect parent HEAD drift in stacked PRs, main baseline drift, unknown parents and cycles; do not infer mergeability from GitHub's `mergeable` flag alone.
- Detect duplicate API, observer, control-plane and extension proposals; force explicit canonical choice even when they avoid file-level conflicts.
- Detect missing local extension verification, local observer disconnection and stale inventory; prioritize truthful `BLOCKED` over false health.
- **Never** output `release_authorized=true`. Even a collision-free structural snapshot is labelled `STRUCTURAL_ONLY_NOT_APPROVED`. CLI default exit is **3** for this state, **1** for blocked, **2** for invalid. Exit **0** is opt-in `--structural-only-ok`, suitable only for non-release staging checks.
- No network, host tool invocation, background agent spawn, authenticated browser use, token capture, or state mutation occurs in this gate.

### Example preflight

```bash
python scripts/gpt_bridge_pr_gate.py docs/sdd/gpt-bridge/PR_INVENTORY_2026-11-22.json
# Expected for this historical snapshot: exit 1, status=BLOCKED.
python -m pytest tests/test_gpt_bridge_pr_gate.py -q
```

Snapshot is historical and **must be re-collected** from GitHub, including all open PRs and exact ref SHAs, immediately before any review. A stale snapshot blocks automatically; it does not mean current PR status is known. CI status, security review, live runtime and owner approval are independent gates not supplied by this script.

## Release gate: never interpret tests in isolation

- **G0 identity:** authenticated owner, exact local extension source/revision and enabled permissions, active Hermes version and integration URL confirmed; otherwise blocked.
- **G1 ownership:** all PR branches inventoried at a recent timestamp, conflicting API implementations resolved, single canonical observer contract chosen, parent/child rebased, expected HEAD protected against concurrent writes.
- **G2 runtime:** verified input preflight, error SSE semantics, multi-process idempotency and external-effect reconciliation with fault injection. All results tied to exact candidate SHA.
- **G3 evidence:** trusted CI and independent reviewer, credential boundary, structured logs/PII audit, no false terminal success, explicit uncertainty propagation and backpressure telemetry.
- **G4 stress:** workload 1/8/32/64 plus failure bursts, check actual queue lock waits, duplicate effect rate (must be zero), false verified success (must be zero), data loss and 99th-percentile queue delay; do not invent latency budgets before baseline.
- **G5 rollout:** read-only shadow mode, scoped canary, kill switch, snapshots and rollback drill. No unattended writes/merge in this draft. Prefer production schema evolution compatible with rollback; a downgraded reader should fail safely.

## Ranked improvement decisions (engineering judgment, **not** benchmark)

| Rank | Improvement | Impact | Confidence | Decision |
|---|---|---|---|---|
| P0 | Canonical single task owner and exact external-effect fence/receipt | Critical: prevents duplicate writes | High conceptual, integration unverified | Required design gate |
| P0 | Resolve incompatible API request/idempotency/SSE contracts | Critical: same handler modified 3 ways | High, source-backed | Select one owner before merge |
| P0 | Ownership + exact SHA PR collision gate | High: stops unsafe concurrent integration | Verified offline, no production claims | Implemented in this PR |
| P1 | Durable, authenticated per-producer outbox and causal event chain | High: diagnosis after restarts | Medium, pending adapter | Prototype and fault injection |
| P1 | Single incident timeline with reason *and uncertainty* | High: actionable repair | Medium, pending source | Integrate after event schema decision |
| P1 | MV3 real tab/document generation tests for extension | Medium/high if browser actually used | Unknown until source identified | Separate canary |
| P2 | OpenTelemetry traces/GenAI semantic conventions | Useful diagnosis | Medium | Metadata-only, content opt-in, derived view |
| P2 | Distributed workflow engine migration | High cost, not justified by agent count alone | Low current need | Defer until measured multi-host bottleneck |
| Reject | Silent DOM scraping as task truth, self-approved writes, blind retries | Dangerous | High confidence | Never implement |

## Sources (verified design references, not deployment evidence)

- Chrome [service worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle), [debugger API](https://developer.chrome.com/docs/extensions/reference/api/debugger/).
- [Hermes Browser Extension DATA-FLOW](https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md), [permissions](https://github.com/abundantbeing/hermes-browser-extension/blob/main/PERMISSIONS.md).
- [NousResearch Hermes Kanban](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md).
- [W3C Trace Context](https://www.w3.org/TR/trace-context/), [OpenTelemetry GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
- [SQLite WAL](https://www.sqlite.org/wal.html), [GitHub webhook replay guidance](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks).

## Open blockers and handoff

**Not performed:** no local ChatGPT extension inspection, no running Windows/WSL integration, no live monitoring, no Obsidian sync, no production patch, no database migration, no full Hermes suite or GitHub CI signoff. `Local_WorkSpace` returned `Session terminated`. All integration candidates stay draft pending source verification. This review should be handed to a single integration owner who resolves #4/#5/#6, chooses an observer, checks upstream Kanban migration, and records the exact tested merge commit before attempting any canary.