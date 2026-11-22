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

---

## Addendum D-06 — 24-agent convergence and causal regression review (2026-11-22)

**Revised evidence scope:** First snapshot file in this branch covers only the 11 PRs collected at 10:44:54 UTC. A subsequent authenticated GitHub repository query found **24 open PRs**. This is a demonstrable **coverage gap**, NOT proof that only 11 agents exist or that an offline 11-PR structural report is current. The bundled snapshot must be labelled HISTORICAL/INCOMPLETE for current release decisions. Every release must use a fresh, complete GitHub listing with per-PR files, HEAD/base SHA and a second pass. Receipt order is not an atomic global snapshot; recheck HEADs before merging.

### D-06A — Consolidate one GitHub PR watcher, not four

Source comparison at time of review:

| Candidate | Distinguishing capability | Critical limitation / gate | Disposition |
|---|---|---|---|
| #14 | Active GitHub REST collection; independent branches; multi-Python CI | Excludes PRs with `base.ref != main`, so a stacked child may be missed | Use only applicable tests/branch comparisons |
| #18 | REST check-run capture, metadata-only SQLite journal | No equivalent two-pass global PR-set consistency check was demonstrated in reviewed code | Contribute check evidence concepts |
| #22 | Two-pass open PR listing, source repository-qualified heads, stacked ancestry, scheduled/manual read-only workflow | Schedule not active on main; CI incomplete at inspection; scheduled scan uses non-strict exit and needs explicit HOLD alert/monitor semantics | **Preferred integration candidate, contingent on CI and review** |
| #24 (this review) | 24 offline structural contract tests, historical exact-head fixture, detailed causal SDD | No live GitHub collector, historical fixture partial, duplicates most watcher behavior | **Reference/test corpus only. Do not merge as another independent watcher** |

**Owner gate:** one integration owner selects #22 or a reviewed alternative, imports genuinely unique tests, runs pinned-head CI and marks redundant scanner drafts superseded. Automated test-job success must not be presented as evidence that the Hermes agent, browser extension or GPT workflow is operating correctly.

### D-06B — Confirmed causal regression and safe merge order

PR #23 `gpt_companion/journal.py` source (reviewed blob `2ea7e36d421f238af31e675921000394b66ddf8f`) chooses the last terminal event by `max(terminal_events, key=lambda e: e["sequence"])` **including** `worker.stopped`. Event sequence `worker.started` → `run.reported_failed(reason_code=AUTH_DENIED)` → `worker.stopped` is therefore labelled `STOPPED_UNCONFIRMED`, masking the actual reported failure and reason. A completion report before stop loses `AWAITING_VERIFICATION`. Different completed/failed outcomes from the same emitter are not expressly flagged, and contradictory events with zero sequence gaps incorrectly select `FETCH_MISSING_EVENTS`.

Sibling child PR #17 contains specific regressions in `tests/gpt_companion/test_terminal_causality.py`; PR #23 contains important prior-attempt unknown-effect isolation and cross-emitter ACK fencing. They must be **combined**, not selected as mutually exclusive last-writer-wins changes. Both children have base SHAs behind the subsequently advancing #12 parent; rebase and test the resulting combined revision. These are source-backed findings, not live incidents. Documented to PR #23 in [comment](https://github.com/Podtverzhdeno/hermes-agent/pull/23#issuecomment-7078068696).

### D-06C — CDP ownership and privacy changes are one release unit

PR #15 prevents `cleanup_browser` from closing externally owned CDP browser processes, including inactivity/atexit cleanup. But its reviewed `_create_cdp_session` logs the raw `cdp_url` at INFO level. A CDP endpoint may contain a token, credential or privileged URL. PR #13 separately changes the same `tools/browser_tool.py` to redact URLs/exceptions. Integrate BOTH invariants: externally owned browser survives closure of one worker session; no CDP URL credentials reach stdout/stderr/files or exception bodies. Test a sentinel URL end to end with two simultaneous external sessions. Review recorded in [PR #15](https://github.com/Podtverzhdeno/hermes-agent/pull/15#issuecomment-7078079701).

### D-06D — Green scanner CI is not green GPT

The current #22 workflow runs the collector without `--strict`; a scan can exit zero while reporting blockers, because strict exit is opt-in. That is acceptable if the job means only **collection succeeded**, but unsafe if the UI interprets it as **integration healthy**. Split into three surfaces:
1. scan coverage/data availability and exact collection revision;
2. integration HOLD/PASS gate (strict, independent CI, canonical ownership);
3. live Hermes/GPT/extension health (unknown until the owner's actual install is connected).

Publish deduplicated HOLD transitions and explicit unknown telemetry coverage. Do not flood alerts at every scheduled run. Do not claim this or any other draft runs periodically until a main-branch workflow is merged and observed. Review recorded in [PR #22](https://github.com/Podtverzhdeno/hermes-agent/pull/22#issuecomment-7078078232).

### D-06E — Measurable acceptance contracts for dozens of agents

- **Identity:** `task_id, run_id, attempt_id, producer_epoch, source_seq, lease_fence, action_id, effect_receipt_id, code_sha` are validated with independent origin and never inferred from human-readable chat messages.
- **Completion:** model/worker reported completion is labelled provisional until an independently authenticated verifier confirms the artifact/effect at exact revision.
- **Diagnostic integrity:** failure followed by worker stop retains the reported failure; conflicting terminal outcomes remain `TRACE_INCOMPLETE` with `RECONCILE_CONFLICTING_EVENTS`, never mere gap replay.
- **Effect uncertainty:** unresolved external write from attempt N persists through attempt N+1 and cannot be cleared by a different emitter's untrusted ACK. No blind duplicate write.
- **Ownership:** one canonical implementation per shared file, one task truth plane, one observer schema. Record outstanding PR ownership before every GitHub write; cannot assume today's owner tomorrow.
- **Operational coverage:** 1, 8, 32, 64 workers; crash at reserve/call/ACK boundaries, callback after lease expiry, rate limits, 2 tabs, MV3 suspension, lost ACK, clock regression and repair-loop cap.
- **Evidence:** every claimed fix includes failing-before/passing-after test output, source blob SHA, exact combined candidate HEAD and independent review. Historical fixture data and pending/cancelled/skipped CI never qualify as completed verification.

**Status of this addendum:** source-reviewed, with concrete regression pointers and cross-agent comments; **not** local extension verification, production monitoring, corrected #23 runtime, or accepted merged fix.
### D-06F — Symmetric P0 defect in the competing child PR #17

Additional exact-source review found that #17's prior-attempt resolution test contains:

```python
(reservations[0][0] != resolutions[0][0] or
 reservations[0][1] < resolutions[0][1])
```

Here a **different-source** ACK is treated as a good causal resolution (`!=`), even though sequences are only ordered within each source. Worker A reserves an effect; gateway B acknowledges with unrelated local sequence; replacement worker C starts. #17 may wrongly clear the prior unknown effect. #23 instead requires same-source ordering for this diagnostic but regresses reported outcome precedence. Thus **neither #17 nor #23 alone is a safe final journal**.

A correct composition must include: (a) prior-attempt effect reconciliation and cross-emitter ACK fencing from #23, (b) outcome-over-stop precedence, contradictory terminals and gap-vs-conflict from #17, (c) tests from both branches and an independent exact-head replay/stress run. Cross-source ACK may be displayed as **reported**, never as independently trusted provider proof. Recorded directly on [PR #17](https://github.com/Podtverzhdeno/hermes-agent/pull/17#issuecomment-7078093421).

### D-07 — Actual extension provenance and exact-version compatibility (source-verified)

As of this review the public **community** [Hermes Browser Extension](https://github.com/abundantbeing/hermes-browser-extension) has declared **v0.4.1**, using [`extension/manifest.json`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/manifest.json), a Chromium Manifest V3 background service worker, `debugger`, tab/storage permissions, broad `http://*/*`, `https://*/*` and `file:///*` host permissions, and optional `webRequest`. The root-level manifest is NOT the build's canonical source: `scripts/build.mjs` copies the `extension/` directory into `dist/`. Use the built `dist/manifest.json` and `build-info.json` with commit/sourceBlob hashes for an installed-byte audit; never report root-manifest permission findings as applied to a Chrome installation without this step. **No installation on the owner's machine was inspected.**

Its [`companion-plugin/plugin.yaml`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/plugin.yaml) declares version `0.4.1`, `requires_hermes: ">=0.22"`, user-approved `tab_*` tool registrations and a default bounded durable receipt mode. This fork's [`pyproject.toml`](https://github.com/Podtverzhdeno/hermes-agent/blob/main/pyproject.toml) declares `version = "0.6.0"`; repository code search found **zero matches** for `browser.controller.register`, `session.events.since` and `webapp-socket-ticket` in the fork at audit time. Therefore **do not claim that the modern plugin can be directly installed or that a browser controller is connected to this old fork**. SemVer floor and absent modern methods are concrete compatibility blockers, not a transient transport diagnosis. Side-by-side migrated Hermes canary, isolated `HERMES_HOME`, pinned plugin/extension commits, rollback and endpoint capability probe are required. Source-based compatibility assessment only; no real installed-version proof.

Critically, the community browser extension is primarily a **Hermes client and context/assist side panel**, not an authoritative ChatGPT web-agent queue. [`extension/lib/site-adapters.mjs`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/site-adapters.mjs) recognizes ChatGPT but excludes `chatgpt` from `SAFE_INLINE_APPLY_SITES` and returns `applyMode: "copy-only"` for that site. [`DATA-FLOW.md`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md) describes Hermes Assist as **review/copy then explicit apply without submitting**. This cannot be represented as an autonomous, guaranteed GPT conversation-dispatch transport. For machine-to-machine GPT work, prefer supported APIs and stable tool-result contracts; keep web composer interactions manual/review-first.

**Trust protocol before permitting any browser action:** `(principal_id, browser_profile_id, controller_id, tab_id, frame_id, document_generation, lease_fence, action_id, action_digest, approval_receipt)` must be bound in a privileged authority; `chrome.storage.local` saved tokens are not proof of process ownership, and a `debugger` session detaching does not prove tool failure. No automatic tab scope expansion, no cross-tab result reconciliation, no command replay after unknown write, no DOM-derived approvals. Limit per-agent active tab scopes and lease fanout.

**Regression suite names found in the community source (not run here):** `tests/browser-control-worker-approval.test.mjs`, `tests/browser-control-approval-binding.test.mjs`, `tests/browser-control-snapshot-toctou.test.mjs`, `tests/continuity-replay-persistence.test.mjs`, `tests/gateway-restart.test.mjs`, `tests/e2e-phase6-browser-control-reconnect.mjs`, `tests/e2e-controller-lifecycle.mjs`, `tests/e2e-gateway-failure-diagnostics.mjs`, plus companion-plugin control and lifecycle tests. Adapt only after validating exact compatible versions; a passing upstream community suite cannot certify this fork.

**Validation matrix** before unblocking deployment: fork 0.6.0 → declared plugin floor mismatch (BLOCKED); upstream compatible runtime + community plugin 0.4.1 → inspect installed manifest, permissions, profile-scoped plugin enablement, controller registration, session/event replay, tool/approval fence, network-loss recovery, logged-redacted errors and release build SHA (UNVERIFIED); custom local GPT extension → exact source absent (UNKNOWN). Keep each category explicit in operational dashboards rather than a single green "extension connected".

---

## D-08 — Failure-model-first architecture: effect reservations, audit evidence and backpressure

**Decision date:** 2026-11-22. **Classification:** design decision, pending compatible upstream/local runtime; no claim of installed implementation.

### D-08A — Confirmed API regressions from source review

1. **PR #5 cache failure re-entry (P0):** `gateway/idempotency.py` blob `bf98f9ff6422dc0a318c0e9ba35a572ae2932690`, `execute()` uses `finally` to clear `_inflight` on exceptions and records only successes in `_completed`. A repeated same-key write after an exception may execute again. Required: durable UNKNOWN tombstone, no blind rerun, independent downstream reconciliation and regression that raises after a simulated write and verifies effect call count remains one. [PR review](https://github.com/Podtverzhdeno/hermes-agent/pull/5#issuecomment-7078151801).
2. **PR #6 session-history fail-open (P0):** `gateway/platforms/api_server.py` blob `6a5335c49e5df0ee06395a447024106675f91751`, lines ~694–706, converts `SessionDB.get_messages_as_conversation()` exception for a supplied session ID into `history=[]` and launches the agent. Must return an explicit transient `session_history_unavailable`, **zero agent invocations**, not run with erased context; apply before streaming starts. [PR review](https://github.com/Podtverzhdeno/hermes-agent/pull/6#issuecomment-7078147362).
3. **PR #6 potentially shared idempotency namespace:** cache key is `chat: + Idempotency-Key` or `responses: + Idempotency-Key`, not principal-scoped. This is a **conditional** security problem if a multi-tenant authentication proxy or multi-profile namespace is added; current one-token gateway cannot be assumed multi-principal. Do not enable such expansion until authenticated principal identity and cross-principal tests are implemented.
4. **PR #6 stream truthiness:** `stream=body.get("stream", False)` accepts non-boolean truthy values; a submitted string `"false"` selects SSE. PR #11's strict-bool preflight is the appropriate invariant, but #11 is stacked on #4; require tested combined endpoint behavior.
5. **Reported failure vs delivery success:** `run_agent.py` in baseline exposes explicit `completed=False`, `failed=True`, `interrupted=True` results; present them as failed/interrupted/incomplete. An SSE `[DONE]` **only closes a transport stream**; it is not independently verified successful work. The APIs must not infer tool outcomes from connection close, worker stop, or a final assistant message.

### D-08B — The distributed atomicity limit

There is **no general distributed transaction spanning a GPT model call, MV3 service worker, SQLite, a GitHub write and an unrelated website**. An atomic SQLite insert is not an atomic external operation. Adopt a durable **intent → dispatch → receipt → verification** protocol and design explicitly for the unknown gap.

| Step | Operation owner | Durable invariant | Loss/crash interpretation |
|---|---|---|---|
| 1. Accept | Authenticated gateway | Task/run/attempt stable, input digest and RBAC checked | No acceptance receipt → inspect authoritative task store |
| 2. Claim | Scheduler/ledger | Compare-and-swap lease epoch and resource-owner fence | Old worker may observe but cannot issue new effects |
| 3. Reserve | Privileged effect dispatcher | Unique action ID + payload digest + scope + approval + idempotency key committed **before** external call | Reservation without authenticated receipt is `OUTCOME_UNKNOWN` |
| 4. Dispatch | Same dispatcher | At most one active issuer under fence for this resource | HTTP timeout does not show that provider rejected call |
| 5. Record receipt | Authenticated adapter | Downstream response ID and origin stored; declared state remains unverified | Missing ACK → no automatic replay of non-idempotent write |
| 6. Read back | Independent verifier | Read-only provider lookup at exact downstream ID/revision, with access scope | Verified / not executed / ambiguous classified separately |
| 7. Settle | Task authority | Terminal CAS binds task, run and exact effect receipt evidence | LLM/worker `completed` report cannot settle without proof |
| 8. Publish | Observer | Redacted trace with subject SHA and authoritative watermark | Gaps/collector failure become UNKNOWN, never green |

Where the downstream provider supports documented idempotency, reuse an **unchanged** key for the same business operation across attempts, not a new key on retry. Where it does not, require read-before-retry/human reconciliation; arbitrary `sleep` and retry loops are forbidden. If no trusted independent read-back exists, remain quarantined and surface the uncertainty. Handle clock rollback with source-local increasing sequence and lease epoch rather than client wall clock alone.

### D-08C — Agent fan-out and ownership when 32–64 agents operate

- One coordinator owns **task truth**, one issuer owns an **external side effect**, one canonical observer schema, and one integration owner owns each shared file / PR domain. These are different roles; do not let every observer run a scheduler.
- Each task has **one active execution fence** even if many agents review it; fan-out occurs into read-only subtasks or separately scoped effect keys. Each agent writes to its own PR branch; shared files are integrated only by an assigned owner using exact-parent SHA, not "last commit wins".
- Queue bounded by both `max_workers` and `max_effects_in_flight` per provider/tenant. Excess work yields `QUEUED_BACKPRESSURE` with evidence; no silent drop, unlimited task creation or unbounded retries.
- Expiring heartbeat detects *suspected* liveness loss, not completion or safe side-effect replay. On expiry, increment the fence and **reconcile outstanding effects before another actor can write**.
- Worker crash, MV3 suspension and network disconnect are separate failure classes. The browser side panel can observe/report; durable admission, retries, terminal proof and authoritative workflow identity must remain outside a volatile content script or service worker.
- Use canary isolation for extension origin/profile, tab lease, frame/document generation and activity ownership. A newly loaded tab, document generation, role or origin is a **different authority context**; old approval never carries over.

### D-08D — Evidence-based priority decision, not unsupported precision

Priority is lexicographic: **(a) ability to cause a duplicate or unauthorized effect or false completion**, then (b) recoverability/correct root cause, then (c) throughput/UX, then (d) implementation cost. These are engineering judgments, not measured probabilities or a fabricated statistical ranking.

| Candidate | Critical failure it prevents | Value | Evidence grade | Decision |
|---|---|---|---|---|
| Durable unknown-effect tombstone, principal-scoped idempotency, verified read-back | Duplicate external writes on timeout / restart | **P0 safety** | Source defect #5; official Temporal Activity retry/idempotency guidance | Implement before autonomous writes |
| Fail closed on missing session history and incompatible gateway methods | Agent executes with erased context or wrong API contract | **P0 safety** | Source defect #6; plugin >=0.22 vs fork 0.6.0 | Implement before extension canary |
| Merge causality tests of #17 and #23 | Failure masked by stop / cross-source ACK falsely closes unknown effect | **P0 safety** | Reproduced logically from reviewed conditions in both branches | Combined HEAD + all tests |
| One complete SHA-pinned PR scanner and integration HOLD notifier | Dozens of agents silently overwrite same code | **P0 release integrity** | 24 PRs and four scanner proposals; source review #22 | Choose #22, migrate unique checks, no duplicate watcher |
| Trace propagation and redacted outcome metrics | Can't tell rate-limit, browser sleep, API failure or lost receipt apart | **P1 diagnosis** | OpenTelemetry GenAI execute-tool + agent conventions | Add privacy-reviewed end-to-end telemetry |
| Native/managed durable workflows (Temporal-like if warranted) | Recovery complexity on many workers and restarts | **P1 scaling** | Temporal durable execution docs | Prototype only; do **not** run alongside another scheduler |
| Browser UI polish / fast auto-retry | Cosmetic latency | **P3** | No evidence that it solves causal failures | Defer until P0 gates pass |

Do not introduce Temporal, Kafka, Redis, Postgres or OpenTelemetry collectors merely to satisfy architecture enthusiasm. Start with a single transactionally correct ledger and explicit trace/event schema; choose external services only when measured capacity, multi-host ownership, operational support and rollback plans justify them.

### D-08E — Standards / source constraints guiding the design

- [Chrome MV3 worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/) requires survival of unexpected worker termination. Background script globals are not a task ledger; `storage.session` is not an atomic multi-writer database.
- [OpenTelemetry GenAI tool execution](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) defines model/agent/tool spans and trace linkage. Do not put prompts, API keys, CDP URLs, raw DOM or user text into trace attributes by default. A `gen_ai.tool.call.id` sent by the model is not an authenticated effect receipt.
- [Temporal Activity/idempotency](https://docs.temporal.io/activities) and [durable execution](https://docs.temporal.io/durable-execution) explicitly treat activities as retriable; the business effect needs idempotency and reconciliation. Durable scheduling **alone** cannot guarantee unique writes.
- [SQLite WAL semantics](https://www.sqlite.org/wal.html) permit readers during a writer transaction, but do not grant unlimited concurrent writers or guarantee absence of `SQLITE_BUSY`; test contention and checkpoint space exhaustion for 32–64 workers.
- [OpenAI Responses background mode](https://developers.openai.com/api/docs/guides/background) supports response IDs with polling/webhooks for independently verified model lifecycle. It is an **API workflow, not web ChatGPT account orchestration**, and has distinct privacy/retention properties ([data controls](https://developers.openai.com/api/docs/guides/your-data)). Preserve the provider response ID for reconciliation. Do not treat model `completed` as an externally executed GitHub/browser business effect.

### D-08F — Failure-injection harness, pass/fail specification

Use a deterministic fake provider and isolated temporary journal. No live GitHub write, GPT subscription, external CDP or credentials.

| Injection point | Expected durable outcome | Must not occur |
|---|---|---|
| Kill worker before reservation commits | Not dispatched; requeue under new fence possible | False external-effect success |
| Kill after reservation, before provider call | UNKNOWN until trusted determination of not-issued | Blind same-key write without reconciliation |
| Provider applies write then drops ACK | Quarantined UNKNOWN and read-back required | Duplicate write on same-key API retry |
| Two workers claim one resource concurrently | Exactly one fence winner | Two dispatchers making effects |
| ACK arrives from another telemetry source | Unverified external outcome | Cross-source ACK clears prior reservation |
| Agent reports FAILED then worker.stop arrives | Retain FAILED reason and source | STOPPED_UNCONFIRMED masks failure |
| New attempt begins while old write unresolved | Prior unknown effect visible in diagnosis | Reset to RECENT_TELEMETRY |
| Database history load raises `SQLITE_BUSY` | 503, error code + no agent call | Empty-history agent invocation |
| Browser MV3 service worker suspended | Replay continuity / pending status unknown | Implicit task cancellation or success |
| Two panels share a watermark storage record | No missing/high-water mark loss under concurrent save | Stale storage overwrites and dropped replay cursor |
| 429, quota, model context exhausted | Distinct reason + scoped retry policy | Retry despite explicit non-retryable/quota stop |
| CI cancelled/queued/skipped on exact SHA | HOLD/UNKNOWN | Green release indicator |
| 64 read-only agents, 1 integrator | Bounded queue, single integration owner | PR collision auto-merged |

**SLO gates** (safety invariants, not fabricated performance metrics): in all deterministic failure injections **zero confirmed duplicate external writes**, **zero unauthorized effects**, **zero false `VERIFIED_SUCCESS`**, **zero unscoped approval replays**. Record observation coverage and queue latency histograms; set p95/p99 operational thresholds only after a measured baseline on the owner's infrastructure. A green isolated unittest is not a valid load-test result.

### D-08G — Co-existence and ownership contract for other agents

Every agent's new PR description must include `exact_parent_sha`, changed-file owners, an explicit dependency graph, causal invariants preserved, test commands and outputs, fixture provenance, resolved review comments and unresolved risks. Request rebase when parent HEAD advances. If two PRs edit a same authority file, stop autonomous merging and nominate **one** integration owner. Do not duplicate the observer, task scheduler, effect store or browser-owner process. If Local_WorkSpace access is terminated, continue **source-only** reviews and label runtime visibility UNKNOWN; never infer live health from GitHub PR checks.

**Scope limitation:** these are design gates and source-reviewed defects. They do **not** constitute working patch for #5/#6, live patch of the installed GPT extension, scheduled monitor activated on main, authenticated downstream receipt, verified upstream migration or production rollout.

---

## D-09 — Runtime-surface selection, wrong-socket failures and evolving multi-agent evidence (2026-11-22)

**Observed scope:** source reviews of third-party public repositories and moving draft PRs. **Unverified:** which GPT/Hermes extension, bridge, profile, browser and runtime the owner actually installed. There is no local diagnostic session; Local_WorkSpace MCP returned `Session terminated`. No claim of a deployed monitor, restored localhost connection or corrected installed behavior.

### D-09A — Select the right product and message direction *before* writing any transport code

| Repository / artifact | Initiator → target | Latest observed release / constraint | What it is not |
|---|---|---|---|
| [asimons81/hermes-gpt](https://github.com/asimons81/hermes-gpt) | ChatGPT or other MCP client → Hermes | v0.18.0, published 2026-11-06; local-first MCP sidecar; rich owner-approved mission and Autopilot surfaces | Not a ChatGPT browser-DOM provider |
| [intellectronica/hermes-chatgpt-extension](https://github.com/intellectronica/hermes-chatgpt-extension) | Codex desktop embedded MCP app → Hermes | v0.3.1, published 2026-10-01; Node >=22, local stdio, compatible desktop backend WS JSON-RPC and REST | Not hosted MCP for ChatGPT cloud; old fork `/v1` alone is insufficient |
| [madpower2000/chatgpt_mcp_bridge](https://github.com/madpower2000/chatgpt_mcp_bridge) | ChatGPT Web MCP → Hermes subprocess job | FastMCP 4 tools; SQLite-backed job identity and cancel; authenticated private endpoint needed | Not a general distributed effect ledger |
| [Dworr21/chatgpt-bridge](https://github.com/Dworr21/chatgpt-bridge) | Hermes → ChatGPT website tab, via Python localhost + Chrome MV3 | GitHub README/source; no tagged latest release found; HTTP :11557 / WS :11558, CDP :9222 | Not a stable authenticated provider API / exact-once backend |
| [abundantbeing/hermes-browser-extension](https://github.com/abundantbeing/hermes-browser-extension) | Chromium/Firefox side panel → Hermes gateway | v0.4.1, published 2026-11-12; companion plugin requires Hermes >=0.22 | Not ChatGPT cloud → local Hermes MCP, not an autonomous ChatGPT tab dispatcher |

**Selection gate:** record installed package's *origin, exact build SHA, signature/digest where available, actual local process command, browser profile, enabled host permissions, protocol direction, runtime version and capability handshake*. Select the `asimons81` track for ChatGPT→Hermes MCP, `intellectronica` for Codex host, and `Dworr21` track only for explicitly permitted Hermes→ChatGPT web UI interactions; do not silently redirect from one track to another on connection failure. The detailed independent comparison in [PR #29's surface-selection ADR](https://github.com/Podtverzhdeno/hermes-agent/blob/feat/gpt-stacked-pr-proof-audit-20261122/docs/sdd/gpt-bridge/HERMES_CHATGPT_EXTENSION_SURFACE_SELECTION.md) supports this decision. The user's original extension identity remains UNKNOWN.

### D-09B — Concrete multi-socket causal defects in a potential ChatGPT DOM bridge

Inspected [Dworr21/chatgpt-bridge `bridge-host.py`](https://github.com/Dworr21/chatgpt-bridge/blob/main/bridge-host.py), Git blob `0f9d9464b8a3f7578bfa4a1dce80ffaa05cf25d9` (source audit, **not** deployment evidence):

- **P0 conditional duplicate-send:** `_send_to_extension` loops through **every** socket in the mutable `connected_extensions` set and sends the same `msg_data`. With two connected extension sessions, the single prompt can be delivered twice and to two distinct ChatGPT tabs/profiles. Each response uses the same volatile `rid`; the server does not bind inbound response to an intended socket or profile. This is **broadcast fanout**, not per-agent isolated exactly-once dispatch.
- **P0 conditional false-stop:** `ws_handler(ws)` finally closes/raises **all** `pending` futures and drops **all** `stream_queues` on **any** single socket disconnect, not just operations owned by that socket. A healthy parallel extension loses its reply because an unrelated extension disconnects.
- **P0 conditional authority issue:** WS server is on loopback `127.0.0.1:11558`, but `ws_handler(ws)` in reviewed code unconditionally adds sockets without an authenticated per-session pairing or bounded owner challenge. Loopback reduces remote network exposure, but other local processes and unauthorized web contexts must not gain bridge authority. No session-scoped sender check before `pending[rid].set_result` was found; verify Origin and authentication boundaries rather than assuming localhost is trusted.
- **P0/P1 unknown-outcome handling:** `pending` and `stream_queues` are process memory; a sent prompt followed by WS loss, restart or timeout has no authoritative durable receipt or visible provider reconciliation. The `/chat` endpoint catches timeout and responds `{"success":false,...}` with default HTTP status 200. SSE generator ends on deadline without a typed terminal failure, and its broad `except Exception: pass` hides stream errors. UI client may treat stream close or HTTP 200 as success when no model result was confirmed.
- **P1 diagnosis truth:** `/health` reports bridge/CDP connectivity, conversation metadata and aggregate counts, **not** task completion. A ChatGPT DOM "done" event is not external effect verification. Treat probe reachability, browser tab readiness, model response report and verified downstream write as distinct states.

**Required redesign for any approved adoption of this codebase:** allocate an immutable `(request_id, session_id, profile_id, tab_id, document_generation, connection_id, lease_fence)`; select exactly one authenticated socket owner per request and record that mapping **before** send. Reject unsolicited/mismatched `rid` replies and never publish a transient WS ACK as an independently verified external effect. On socket detach, degrade or reconcile **only the in-flight requests owned by that socket**, never the global pending table. If delivery may have happened, status is `OUTCOME_UNKNOWN` with no blind resend. Bind HTTP caller principal and WS handshake to scoped authorization; expose error/diagnostic summaries without leaking prompts, tokens, tab URLs or arbitrary exception text. A single browser tab cannot be driven concurrently by multiple mutating agents. Respect user consent and platform-supported automation boundaries.

**Deterministic acceptance tests:** 2 WS sockets, 1 request ⇒ exactly 1 send to assigned socket; wrong socket's response for same `rid` ⇒ ignored and alarm; one socket closes ⇒ other socket's pending request stays intact; assigned socket closes after send ⇒ exact UNKNOWN; 2 workers share one tab ⇒ only one fence winner; HTTP timeout ⇒ explicit 504/typed unknown without false 200; SSE timeout/exception ⇒ unambiguous failure terminal (not success or silent EOF); process restart at pre/post-send ⇒ no blind duplicate send. These tests have **not been executed on Dworr21's branch here**; they are a source-backed remediation specification.

### D-09C — Separate multi-panel replay concurrency hazard in community side panel

In [`extension/lib/replay-watermarks.mjs`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/replay-watermarks.mjs), blob `74fe7d3e0a64e87f442379a5d9c995c8933ab3cd`, multiple panels persist the same `storage.session` key by `get()` → merge → `set()`; this is **not atomic cross-panel compare-and-swap**. The tests [`continuity-replay-persistence.test.mjs`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/tests/continuity-replay-persistence.test.mjs), blob `9307c854960d688b898890ddfc9e32ef1bdce103`, cover sequential `await one.flush(); await two.flush()`, but not a forced concurrent read/write interleaving. A simultaneous last-writer-wins update could erase a newer session watermark or another panel's endpoint. This is a **source-grounded potential race, not a reproduced incident**. Add a synchronized two-reader barrier, one delayed `set`, and reload assertions; then move writes through one service-worker serialized coordinator/transactional authority, not competing `chrome.storage.session` readers. Only use a proven writer/merge and durable replay lease after crash tests.

In [`extension/lib/connection-readiness-orchestrator.mjs`](https://github.com/abundantbeing/hermes-browser-extension/blob/main/extension/lib/connection-readiness-orchestrator.mjs), each `ReadinessStageError` sets `retryable=true` (even for potentially permanent auth/capability errors). `Promise.race(operation, timeout)` does not cancel a losing in-flight operation; guard mutations with per-connection generation and abort if supported. A completion after timeout should be ignored, not turn a previously blocked session ready. This is a suggested negative-path test, not proof of occurrence.

### D-09D — Changes after previous reviews and 30-PR reality

An authenticated GitHub listing during this pass found **30 open draft PRs**, up from 11 and 24. The `PR_INVENTORY_2026-11-22.json` bundled with this branch represents **only the first eleven**, intentionally historical. The offline checker now supports `reported_open_pr_count`, returns `PR_INVENTORY_COUNT_UNKNOWN` or `PR_INVENTORY_COUNT_MISMATCH` and `inventory_coverage_attested=false` always. **32/32** local isolated regression tests passed on the updated checker. No offline count is a cryptographic guarantee that the live API listing is complete. The canonical full GitHub collector should be selected rather than merged beside another watcher.

- #23 updated `gpt_companion/journal.py` to blob `f94aed529518b796214f960e31b546e5726348ae`. Earlier reported worker-stop overwrite and two conflicting outcome omissions **have been fixed in current source**, with added tests. Remaining diagnosis issue: `TRACE_INCOMPLETE` on contradictory but gap-free events still directs `FETCH_MISSING_EVENTS`, not `RECONCILE_CONFLICTING_EVENTS` ([follow-up review](https://github.com/Podtverzhdeno/hermes-agent/pull/23#issuecomment-7078210696)).
- #17 updated to blob `eed019f0f3d3a6178c7ca3e87e2aa358409a3612`, removing the previously reviewed literal cross-emitter `!= or` condition. Do **not** cite that removed expression as a present bug. Current journal **still lacks prior-attempt unresolved-effect tracking**; ensure the action from attempt N remains unknown when N+1 starts ([follow-up review](https://github.com/Podtverzhdeno/hermes-agent/pull/17#issuecomment-7078212827)).
- #22's current scanner provides separate `collection_status`, `integration_verdict`, `runtime_verdict` and `ci_verdict`, which mitigates ambiguity in its workflow summary. However, the scheduled collector job without `--strict` can be green while `HOLD_FOR_REVIEW`; only scanner operation has succeeded. Its schedule runs **only after main merge**, not while draft; new unrelated GPT PRs also do not trigger it via current PR path filter ([updated review](https://github.com/Podtverzhdeno/hermes-agent/pull/22#issuecomment-7078214689)).
- #25–#30 introduce additional independent causal auditors, GitHub collision/ancestry guards and extension SDDs, all **draft**. Do not integrate six more independent schedulers/observers. Diff unique invariants against #22 for scanner and #25's offline causal oracle; select one implementation owner, migrate only independent tests; archive/supersede redundant candidates when their tested work is preserved.

### D-09E — Non-negotiable ongoing reviewer contract

Future Hermes/GPT reviewers (including dozens of concurrently active agents) must treat this as a **high-complexity, evidence-first, iterative integration problem**, not a one-response "fixed" claim. An agent's completion statement is only a claim. Each observation needs `observed_at`, upstream source/revision, authenticated vs untrusted classification, last trusted state, negative tests, exact artifact SHA, expected next observation, unknown effects and blocking reason. Record changed bug status as parent branches move; correct outdated comments explicitly as in #17/#23. Never allow an observer to authorize an action; never infer permission or "all green" from a log sentence or successful collector CI. Maintain one canonical SDD decision log, one effect authority, single merged-tree test proof, and reserve human owner intervention for truly irreversible/restricted decisions. The work does not continue autonomously between chat turns unless an actual user-enabled scheduled service/monitor is deployed and observed; this repository document persists the instruction **for future work**, not model memory.
