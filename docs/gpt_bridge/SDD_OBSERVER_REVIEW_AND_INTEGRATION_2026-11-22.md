# Hermes ↔ GPT Bridge — SDD integration addendum: causal observer, PR contention and failure gates

**Status:** REVIEW CANDIDATE; not deployed, not a live ChatGPT extension or authoritative Hermes state machine.  
**Date:** 2026-11-22 (UTC).  
**Repository:** `Podtverzhdeno/hermes-agent`  
**Audited fork baseline:** `main@7e9100901819ee44c16b4ddcb79a6bcb7909f591` (2026-04-01).  
**Canonical SDD dependency:** draft PR #7, `docs/gpt_bridge/SDD.md`; this addendum does not replace #7.  
**Autopilot dependency:** draft PR #1 is the only proposed owner of durable task/effect/approval state.  
**Relevant peer PRs:** #3 (ACP permissions), #4/#5/#6 (overlapping gateway API fixes), #2 (skill harness).  
**New implementation in this PR:** `gateway/gpt_bridge_event_audit.py` (pure-stdlib, read-only offline event validator/reducer); `scripts/gpt_bridge_pr_collision_audit.py` (offline PR file/CI SHA collision gate); tests and minimal CI.

## 1. Explicit epistemic boundary

Evidence statements below use these terms:

- **OBSERVED** — current GitHub API/source at the exact stated revision.
- **TESTED_OFFLINE** — executable deterministic tests in an isolated container, *not* live production validation.
- **DESIGNED** — policy/interface proposal; no feature-completeness claim.
- **UNKNOWN** — needs local/production evidence.
- **BLOCKED** — connector unavailable; cannot infer a user device failure.

**OBSERVED:** the linked GitHub repository had seven open draft PRs on 2026-11-22, with #4/#5/#6 all modifying `gateway/platforms/api_server.py`. All originate from the old fork baseline. `main` GitHub branch metadata reported `protected: false`, which means repository-wide merge safeguards must not be assumed. GitHub check-runs for inspected PRs included in-progress or cancelled runs. A passing supply-chain scan or an isolated unittest **cannot** establish global CI success.

**OBSERVED:** upstream `NousResearch/hermes-agent` published **v0.23.3 on 2026-11-20**, and its current Kanban documentation specifies one task lifecycle authority with worker lanes. Therefore migrating the April fork to current upstream is a **separate parity project**; merging parallel April-era patches into upstream without revalidation is unsafe.

**BLOCKED:** `Local_WorkSpace.list_workspaces` returned `INVALID_ARGUMENT / Session terminated` at inspection. The actual Windows ChatGPT/GPT extension code, native host identity, installed manifest, network bridge and runtime logs **were not inspected**. Historical mention of `C:\Users\Vadim\Tunnel\chat-launch-smoke-desktop-test\web-extension` is not fresh deployment evidence. A confirmed GitHub fork API server is not proof the extension exists inside that fork.

## 2. Stop-to-explanation contract: three different things

| Layer | Can say | Cannot say | Evidence origin |
|---|---|---|---|
| Authoritative ledger (future Autopilot integration) | Task lifecycle, lease/fence, mutation reservation, approval state, committed completion | Remote action definitely succeeded with only a local timeout | Signed/verified records and transactions |
| Read-only event observer (this patch) | Received event counts, malformed events, replay collisions, sequence holes, causal cycles, **candidate** stop reasons | 'Task finished', 'retry allowed', 'approval granted' or even 'heartbeat gap = crash' | Unauthenticated redacted NDJSON metadata |
| Browser MV3 companion (future separate extension) | Display and reconnect a cursor; signal UI transport health | Own task queue, mutate ledger based on DOM, infer worker success from pixels | User-authorized authenticated host |

An event may claim `trust_level=trusted_verifier`; in the **offline** parser this is not authenticated evidence. The diagnostic output deliberately never sets `automatic_retry_allowed=true`, and it always says `ledger_state=not_read_in_this_tool`.

### 2.1 Machine-readable stop reason workflow

1. Observe a lost request/SSE/heartbeat; label **SUSPECT**, not `failed`.
2. Fetch the current authoritative state from the ledger, recording `task_id`, `attempt_id`, `lease_fence` and exact `target_revision`.
3. Fetch only authenticated, redacted event envelopes by a durable cursor. Audit gaps, collisions and causation; never invent missing events.
4. Reconcile any reserved-but-unacknowledged external effect **before** touching retries. A remote commit followed by a network drop is `needs_reconciliation` until an independently confirmed receipt or read-back exists.
5. Rank candidate causes from transport, model, approval, worker/lease, tool, verifier and local persistence; attach evidence and explicit confidence. If the source is unreachable, use `UNKNOWN`.
6. Choose `resume_safe_read`, `budgeted_retry`, `await_approval`, `reconnect_observer`, `reconcile_effect`, `fix_and_reverify`, `manual_required` or `stop`. **Only the trusted control plane may authorize this action.**
7. Run a dedicated regression, full integration tests, and CI check at the exact candidate SHA; log the effect on error rate and false-success rate.

### 2.2 Failure atlas (diagnostic evidence, not automatic action)

| Trigger | Plausible root causes | Disambiguating evidence | Safe decision |
|---|---|---|---|
| SSE ends after 200 OK but no final answer | task exception swallowed, client disconnect, proxy close | adapter exception, terminal stream event, ledger state, trace | No synthetic `stop` success; verify output contract |
| Duplicate GPT request | client retry after timeout, two concurrent tabs, changed body | trusted principal, full canonical body digest, idempotency key, current operation state | Same active key = 409 pending; changed payload = 422; no replay |
| Browser worker disappears | MV3 lifecycle sleep, extension reload, host crash, browser close | native host cursor, extension version, connection transition | Reconnect status view; task continues independently |
| Hermes not responding | rate limiting, long tool, context budget, dead worker, stale lease | adapter 429/Retry-After, tool intent/effect, trusted heartbeat, fence | Budgeted branch, never blind retry of mutating step |
| Approval prompt delivered to wrong agent | global callback, `ContextVar` propagation, shared session | ACP session ID, action digest, fence, authenticated principal | Fail closed and isolate callback route |
| Two agents overwrite same file | shared checkout, no compare-and-swap, stale base | working-tree lock, file SHA, PR overlap graph | Reject stale write and ask owner to reconcile |
| Successful CI applied to new HEAD | check result at older SHA, untrusted status narrative | GitHub check run `head_sha` and exact branch SHA | Do not mark verified |
| Missing event #N | reorder, collector lag, producer restart, permanent loss | per-producer watermark, replay checkpoint, stable producer boot ID | `POSSIBLE_SOURCE_GAP` until durable watermark |
| DB write delayed | SQLite writer contention, full disk, checkpoint starvation | WAL/busy metrics, checkpoint duration, disk/backup inspection | Fail closed on high-risk effects; do not ignore audit failure |
| Tool call may have committed | response lost after external mutation | durable effect reservation, remote receipt/read-back | Block repeats; reconciliation |
| Many agents hit 429 | shared quota, synchronized retry, budget mis-scope | provider `Retry-After`, per-principal budget, queue depth | Global coordinated cooldown + jitter |
| Prompt injection changes 'permission' | untrusted issue/README/browser content | provenance, tool gateway policy decision, signed approval | Treat as data; never let an LLM self-grant capability |

## 3. Agreement required before merging overlapping GPT API PRs

**OBSERVED file conflict:** #4, #5, #6 all touch `gateway/platforms/api_server.py`, with different in-process idempotency semantics and separate tests. #7 is design-only and does not override the endpoint behavior. Blindly merging all three would reintroduce or hide regressions.

| Contract dimension | Required integration decision | Why it is a gate |
|---|---|---|
| Active request with matching key | **Proposed:** `409 Conflict` with an unambiguous retryable pending code, *never dispatch twice* | IETF HTTPAPI Idempotency-Key internet-draft (not yet an RFC) describes 409 for concurrent duplicates |
| Existing key, changed canonical request | **Proposed:** `422 Unprocessable Content`; fingerprint includes all relevant JSON and effective session | Draft semantics, prevents silent payload substitution |
| Replay of completed request | Preserve **same** completion `id`, session identity, `created` and result; no second side effect | New wrapper ID on cache replay is not semantically identical |
| Principal scope | Trusted resolved caller identity/tenant + endpoint + key; **not** raw bearer token printed to log | Prevent cross-tenant collision and credential leakage |
| Cancellation of waiter | Never assume cancellation of transport cancels a tool already sent | `asyncio.shield` protects in-process task, not durable external effect |
| Restart/multi-host | **UNKNOWN** until backed by durable ledger, transactional outbox and tool-gateway fencing | Process-local single-flight is not exactly-once execution |
| Streaming failures | No normal `finish_reason=stop` after backend failure; explicit terminal error semantics **must be tested in actual client SDKs** | Custom `event: hermes.error` alone may not be recognized by all OpenAI-compatible clients |
| SSE terminal acknowledgment | If stream headers are already sent, HTTP 500 is impossible; client contract needs terminal error and no false-green | Avoid silently converting exception to successful end-of-stream |
| `X-Hermes-Session-Id` | Versioned opt-in and CORS allow/expose review for configured origins | Session continuity is not a permission to call arbitrary agent tools |
| Error logs | Structured error type + run ID + full private stack only in protected sink | No prompt, cookie, bearer token or internal exception in HTTP 500 response |

**Decision ADR-GPT-010 (PROPOSED):** nominate one gateway maintainer/PR as the single integration branch; cherry-pick tested behaviors and tests from #4/#5/#6 after full diff review. Do **not** merge their whole `api_server.py` changes sequentially. Test cases should include 30 same-key callers, 30 different-key callers, mixed principal/session, mismatched body, client cancellation, process restart, stream exceptions and remote-commit/timeout ambiguity.

**Decision ADR-GPT-011 (ACCEPT for this patch):** ship pure read-only diagnostics separately from API/Autopilot changes, so tests are useful even while the source integration is blocked. Do not import it into a live gateway request handler yet.

**Decision ADR-GPT-012 (PROPOSED):** do upstream-parity analysis before enabling any scheduler in the fork. Modern upstream Kanban is lifecycle authority; PR #1's experimental ledger invariants may be adapted as a sidecar, not started as competing queues.

## 4. Observer interface implemented here

`gateway/gpt_bridge_event_audit.py` consumes newline-delimited **redacted metadata** conforming to SDD PR #7 envelope v1. It validates a closed field allowlist, valid UUID/trace IDs, bounded input, known event kinds, UTC timestamps, per-producer sequence, effect keys, and target revision digest. Sensitive extra fields are rejected without echo. Each event ID and `(producer_id, source_event_seq)` is unique within an audit snapshot. Duplicate identical replays count once; conflicts are reported.

The observer detects:

- Input malformed/oversized, unknown versions and forbidden payload-like fields.
- Event ID collisions and producer sequence collisions.
- Noncontiguous sequences **within** an observed producer range, treated as *unconfirmed gaps*, not failures.
- Missing causal parents (possible truncated export); directed causal cycles and same-producer causal sequence contradictions.
- Cross-task causation requiring explicit parent-task context.
- Unacknowledged/unknown external effects, acknowledgments without observed reservation, acknowledgments without authenticated proof, and conflicting lease fences.
- Unverified completion claims, verifier *claims* without trusted attestation, provider throttle / approval denial / bridge disconnect / lease expiry indicators.

The output contains no prompts/tool inputs, no original error stacks, no full effect keys; suspected effect keys are SHA-256 prefix correlation IDs. Note that even metadata can reveal sensitive project structure; keep local reports access-controlled. The module **does not persist events**, does not subscribe to runtime, does not invoke the model, does not change task state or grant capabilities.

**Bounds:** at most 50,000 distinct events in one audit; 4 KiB per event/line; no recursive traversal of deep causal chains. The CLI atomically writes a summary file (same-directory temporary file, flush/fsync, `os.replace`) and doesn't claim physical power-loss durability on every platform. A production adapter must separately establish authenticated producer identity, durable cursor, transactional outbox, backpressure, retention policy and data loss SLO.

### Local use (metadata exports only)

```sh
python -m gateway.gpt_bridge_event_audit event-metadata.ndjson --output diagnostics.json
python scripts/gpt_bridge_pr_collision_audit.py pr-snapshot.json
```

`pr-snapshot.json` uses `{ "base_sha": "<40-hex>", "pull_requests": [ { "number": 4, "head_sha": "<40-hex>", "base_sha": "<40-hex>", "draft": true, "files": ["gateway/platforms/api_server.py"], "checks": [ { "name": "test", "head_sha": "<40-hex>", "status": "completed", "conclusion": "success" } ] } ] }`. The overlap checker treats stale/empty/skipped/cancelled/not-at-HEAD checks as **not proven passing** and never authorizes auto-merge, even if all presented checks are successful. The trusted GitHub adapter must generate a fresh snapshot: user-supplied JSON is only a planning input.

## 5. Multi-agent coordination contract (30+ simultaneous specialists)

1. **Task contracts:** immutable scope, owner role, allowed paths, base SHA, exact acceptance tests, deadline/budget, dependency IDs, effect risk class. Copying a prompt does not create new rights.
2. **One authoritative owner per mutable resource:** `gateway/platforms/api_server.py` and per-file writers use compare-and-swap with expected SHA. If the ownership lease/fence changes, no stale agent writes even when it has a cached approval.
3. **Worktrees/branches:** each agent uses an isolated branch and worktree; the persistent Windows working copy remains separate and is updated only after tested integration. No competing workers writing one shared Obsidian note without expected hash.
4. **Atomic event transaction:** control-plane ledger stores task transition, associated event and outbox entry together before acknowledging the mutation. Cross-host/remote tool effects still require reservation + remote receipt + reconciliation.
5. **Budget and fairness:** derive child budgets from parents, enforce project/provider rate limits and bounded queues. 30 agents must not imply 30 independent model retry storms or unlimited token spend.
6. **Observability:** per-producer boot UUID and sequence, UUID event ID, trace context for correlation (never identity), causation edges, outcome reason and evidence, independent verifier at exact SHA.
7. **PR integration:** read-only overlap graph before review; identical paths require one designated integrating maintainer, not last-write-wins. Check conclusions must match exact HEAD. Docs-only checks are not code integration evidence.
8. **Approval:** dangerous actions require independently authenticated, action-digest-bound decisions; a model/DOM event cannot alter the security gate. Unknown approval option = deny.
9. **Incident learning:** each confirmed incident creates a minimal reproducer, scored hypothesis, unique root-cause class, target test, fix PR and regression record. Do not auto-edit SDD to justify an unverified patch.
10. **Operator authority:** retain global stop and rollback; no unattended production mutation until canary and explicitly passed gates.

### Resource classes / reviewers (DESIGNED)

| Resource | Primary owning workstream | Review dependencies |
|---|---|---|
| `gateway/platforms/api_server.py` | Single GPT gateway integrator | security, client contract, idempotency, SSE client regression |
| `autopilot/` | Autopilot ledger owner (#1) | storage, tool gateway, risk policy, upstream parity |
| `acp_adapter/` + permission callbacks | ACP security owner (#3) | sandbox, concurrent approval tests |
| `docs/gpt_bridge/SDD.md` | GPT SDD coordinator (#7) | integration and QA leads |
| `gateway/gpt_bridge_event_audit.py` | Observer diagnostics (this patch) | protocol owner, privacy/security reviewer |
| Chrome extension/native host | Real local extension owner (UNKNOWN) | user-authenticated runtime, browser threat model |
| `docs/` Obsidian mirror | Documentation sync owner | local Workspace availability, optimistic hash lock |

## 6. Evidence-driven option evaluation — NOT a claim of measured quality

Criteria, all 1–5: failure safety (0.30), integration friction (0.20), observability (0.20), security (0.20), operational simplicity (0.10). Rating rubric: 5 strong, 3 partial, 1 inadequate. The scores are expert planning assumptions to be revised after evidence; they are not benchmark scores.

| Option | Safety | Integration | Observability | Security | Simplicity | Weighted / 5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| A. ChatGPT DOM-only watcher with hidden agent control | 1 | 2 | 2 | 1 | 2 | **1.50** | Reject |
| B. Second standalone task database in MV3 extension | 1 | 2 | 3 | 2 | 2 | **1.90** | Reject |
| C. Read-only, metadata-only offline causal observer | 5 | 5 | 3 | 5 | 5 | **4.60** | Implement now (this patch) |
| D. Read-only authenticated live observer + durable cursor | 5 | 4 | 5 | 5 | 3 | **4.60** | Next after trusted adapter |
| E. One modern Kanban authority + fenced tool gateway + receipts | 5 | 3 | 5 | 5 | 2 | **4.30** | Target architecture, needs upstream parity |
| F. Automatic self-healing without effect reconciliation | 1 | 3 | 2 | 1 | 3 | **1.80** | Reject |

The offline observer's high score describes its low risk and bounded scope, **not** product completeness: it cannot fulfill the live-monitoring use case until a trustworthy event producer and operator-facing integration exist.

## 7. Verification matrix and rollout gates

**TESTED_OFFLINE (local isolated Python 3.13 harness):** 46 observer unit tests passed after hardening; 7 PR collision tests passed; 30 simulated producers × 500 metadata events = 15,000 events, randomized arrival, `accepted=15,000`, `rejected=0`, `diagnostic_issues=0` on that synthetic stream. The ~0.33-second run was a local measurement, **not** an SLO or live Hermes benchmark. Additional supported versions must be checked in GitHub CI after committing.

**Not verified:** full fork pytest, authenticated producer ingestion, real SSE clients, true DB/outbox behavior, persistent host reboot/restart, origin/pairing rules, live extension and Obsidian mirror, soak and Windows tests.

Release gates, with **explicit nonwaivable STOP**:

| Gate | Evidence needed | If missing |
|---|---|---|
| G0 — repository source | current HEAD SHA, full PR diff, collision resolution, `main` protection review | HOLD |
| G1 — protocol | schema + trust boundary, replay/invalid/overflow tests, privacy review | HOLD |
| G2 — CI | complete required checks `success` on **exact HEAD**, suite coverage without hidden skipped critical checks | HOLD |
| G3 — host | inspect actual extension manifest/version/native host, authenticated pairing, allowed origin, break glass | HOLD |
| G4 — durable ledger | transaction/outbox, fencing at tool boundary, receipt-based reconcile on crash windows | HOLD |
| G5 — 30 agents | fair quota, bounded retries, resource contention and crash fault injection, 24–72 h *synthetic* soak | HOLD |
| G6 — canary | user-authorized sandbox, independent verifier, rollback and local snapshot restore | HOLD |

A `Cancelled` CI run, a skipped check, a GitHub PR body saying 'tests passed', or a green screenshot without SHA is not G2 evidence. The user’s machine may work even when Local_WorkSpace is unavailable; record this as connector health, not Hermes health.

## 8. Adversarial acceptance cases (for next integration PR)

- **Replay:** duplicate identical event 100× then collision with the same UUID but changed metadata; accept one, detect collision, no execution.
- **Cross-producer ordering:** 30 producers all start at seq=1; randomized receive order, missing seq, reappearing seq, restarted producer boot; no false global ordering.
- **Causal tampering:** cycle, backward parent sequence, unobserved parent and cross-task parent; report separately.
- **Privacy:** reject forbidden `prompt`, `token`, `tool_arguments`; never echo values; conservative metadata identifier policy; fuzz invalid JSON and oversized lines.
- **Non-verified completion:** report cannot mark succeeded even for a `trusted_verifier` label without independent verifier attestation and exact SHA.
- **Unknown effect:** reservation then network loss, unknown marker after ack, fence divergence; never mark auto-retry safe.
- **Client cancellation:** REST/SSE cancellation before, during and after external commit; no repeated side effect on retry.
- **SSE error:** injected agent exception after headers; no finish `stop` or success `[DONE]`; test real OpenAI-compatible SDK handling.
- **Webhook replay:** same GitHub delivery ID redelivered and signature verified; no duplicate dispatch.
- **PR race:** three workers all change `api_server.py`; overlap checker reports all three edges; all checks matching old head are stale.
- **SQLite stress:** 30 writers under WAL/checkpoint pressure, disk-full crash, backup restore and anti-stale fencing; measure loss and fail-closed behavior.
- **Windows host:** disable/re-enable extension, sleep/restart Chrome, disconnect/reconnect MCP tunnel and native process; local UI stays a view only.

## 9. Decision journal and sources

- **2026-11-22 / ADR-GPT-010 / PROPOSED:** align parallel API fixes to one idempotency/SSE contract; no silent conflict merge.
- **2026-11-22 / ADR-GPT-011 / IMPLEMENTED OFFLINE:** separate read-only reducer with strict metadata field whitelist and no authority over effects.
- **2026-11-22 / ADR-GPT-012 / PROPOSED:** audit upstream v0.23.3 Kanban parity and avoid a second task lifecycle.
- **2026-11-22 / ADR-GPT-013 / IMPLEMENTED OFFLINE:** read-only file overlap and CI SHA collision reporter; cannot itself authorize merges.
- **2026-11-22 / ADR-GPT-014 / OPEN:** authenticate producer identity and verifier receipts *outside* the reader before allowing stronger confidence or operational decisions.
- **2026-11-22 / ADR-GPT-015 / OPEN:** determine actual extension transport and host permissions from fresh local source, not prior notes.

Primary review sources:

1. IETF HTTPAPI **Internet-Draft**, Idempotency-Key header (draft-09, Nov 2026, **not** a published RFC): https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09
2. Chrome MV3 worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
3. Chrome native messaging manifest and host origins: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
4. W3C Trace Context: https://www.w3.org/TR/trace-context/
5. OpenTelemetry events: https://opentelemetry.io/docs/specs/semconv/general/events/
6. SQLite WAL caveats and checkpoint behavior: https://www.sqlite.org/wal.html
7. Python `asyncio.shield` and cancellation: https://docs.python.org/3/library/asyncio-task.html
8. GitHub webhook replay and signatures: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
9. OWASP Top 10 for Agentic Applications 2026: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
10. Upstream Hermes v0.23.3: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
11. Upstream Kanban worker lanes: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban-worker-lanes.md
12. Current fork competing GPT drafts: https://github.com/Podtverzhdeno/hermes-agent/pulls

**The module, tests and this design are a bounded first implementation step. They do not constitute an always-on agent, production extension deployment or Hermes runtime repair.**


## 11. November 22 convergence audit — 26 concurrent draft PRs (observed later in this pass)

**OBSERVED_GITHUB at approximately 10:50 UTC:** 26 open draft PRs (#1–#26). Earlier "seven PRs" counts in this document and the work log are point-in-time observations, not current totals. The conflict set expanded while independent agents were still pushing. File paths below were fetched from each PR's own GitHub `/pulls/{n}/files` endpoint; authors can push new HEADs at any time, so consumers MUST refresh and bind these statements to head SHAs.

| Exact file | Concurrent PR owners | Integration risk |
|---|---|---|
| `gateway/platforms/api_server.py` | #4, #5, #6, #11 | Four distinct request-idempotency / streaming approaches; P0 conflict |
| `gateway/gpt_bridge_event_audit.py` | #4, #26 | Native SSE parser and metadata v1 validator share path but **not contract** |
| `tests/gateway/test_gpt_bridge_event_audit.py` | #4, #26 | Conflicting test assumptions; requires explicit source/API version separation |
| `autopilot/ledger.py` | #1, #10 | One ledger owner only; no accidental overwrite of safety invariants |
| `tests/autopilot/test_ledger.py` | #1, #10 | Tests may validate different state machines |
| `tools/browser_tool.py` | #13, #15 | Browser lifecycle changes can silently affect CDP cleanup |
| `gpt_companion/journal.py` | #12, #17, #23 | Three journal variants risk breaking event replay compatibility |
| `docs/sdd/GPT_COMPANION_SDD.md` | #12, #17, #23 | Shared SDD concurrently overwritten |
| `pyproject.toml` | #1, #9, #12 | Packaging and test entrypoint conflicts |

**Additional semantic duplication beyond exact path collisions:** #8, #9, #16, #21, #25, #26 implement causal/offline observer variants; #14, #18, #22, #24, #26 implement different PR-merge/ownership gates. File-path isolation does not remove duplicate scheduling or misleading "all green" assertions. Do **not** merge all of them merely because each branch has distinct filenames.

### ADR-GPT-016 — prefer native Hermes Runs API as an input, not a replacement task ledger (PROPOSED)

Modern Hermes gateway exposes `POST /v1/runs`, `GET /v1/runs/{id}` and SSE `GET /v1/runs/{id}/events` with event sequence IDs. The stream supports `Last-Event-ID` / `last_seq` and a `replay.truncated` signal when retained events are no longer available. A gateway-specific parser proposed in PR #4 reads **native** SSE frames. By contrast the v1 event envelope handled in PR #26 is a **proposed normalized cross-agent schema** and cannot ingest native SSE frames directly.

Choose an explicit, separately tested adapter:

```text
current Hermes gateway /v1/runs SSE -> native parser, cursor, replay.truncated
  -> schema-checked redaction/translation (never implicit trust elevation)
  -> normalized v1 metadata events + observation gap markers
  -> non-authoritative causal observer
  -> current Kanban/ledger state and authenticated receipts consulted separately
```

The April fork `main@7e910090` predates modern Runs API; route discovery and version/feature negotiation are mandatory. An API response, SSE frame or callback cannot authorize execution, approvals or tool permissions by itself. The observer must not receive `reasoning.available` raw reasoning text, `message.delta` content, tool preview/arguments, secret-bearing exception text, or raw `run.completed.output`; only allowlisted statuses and hashed correlation IDs may be promoted.

Current research status: An October 2026 upstream Hermes issue reported asymmetric registration for streaming vs non-streaming session-chat, in-memory run statuses and pending approvals, and unowned-run authorization concerns. These are **historical issue observations, not proven defects in v0.23.3**. Recheck current source and owner-scoped integration tests before claiming a fix is required. Official issue: https://github.com/NousResearch/hermes-agent/issues/141364. The modern API source reference is `gateway/platforms/api_server_runs.py` in upstream; do not infer compatibility from filenames alone.

**Protocol acceptance tests to add before integration:**
1. Native `run.failed` or `run.interrupted` must never be translated to `task.completed` with proof.
2. `replay.truncated` creates `OBSERVABILITY_GAP` and blocks causal-completeness assertions until independently reconciled.
3. Same `id:` SSE value replayed with identical data is deduplicated; same ID with changed data is a collision, not an overwrite.
4. Missing events on service-worker reboot must not trigger another `POST /v1/runs`.
5. Request authenticated to profile A cannot observe/approve/stop profile B's run.
6. Run whose admission response is lost is retried only with exactly the same admission idempotency key **if** the actual gateway contract proves dedup; unknown mutations still need reconciliation.
7. Legacy gateway without Runs API must explicitly report `CAPABILITY_UNAVAILABLE`, not silently assume SSE route exists.

### ADR-GPT-017 — unique integration owner / collision-first review (PROPOSED)

Set one integrating maintainer for each path group above. PR #4 may own modern native SSE parsing; PR #26 may contribute metadata v1 causal invariants only after renaming/namespacing and protocol translation review. PR #1's ledger must be reconciled with upstream Kanban before integration. No automation may merge on a draft, stale base, conflicting path, missing required checks, or merely a self-reported test count. Any current snapshot is stale as soon as a PR HEAD changes: refresh per-PR changed files, compare exact SHA and check scopes, record the integration decision and test result.

Scored candidate `G. Modern native Runs SSE -> validated internal metadata adapter -> read-only observer`: safety 5, integration 4, observability 5, security 4, simplicity 3 = **4.40 / 5** on the rubric in §6; high promise but BLOCKED until gateway-version parity and authenticated pairing tests. This is a *hypothesis*, not a measured score.

### Fresh observation does not equal continuous monitoring

This audit is a bounded snapshot through authenticated GitHub connector calls. Neither this ChatGPT session nor a draft CI job is a guaranteed continuous monitor. A future source-owned watcher needs durable last-seen IDs, ETag/rate-limit backoff, a supervisor and a user-visible pause/stop control on the Windows host; deployment cannot be claimed while Local_WorkSpace MCP is disconnected.



## 12. Release-tag correction: what Hermes v0.23.3 already solves (SOURCE VERIFIED)

**OBSERVED_CODE / OBSERVED_DOCS:** inspected `NousResearch/hermes-agent` **tag `v0.23.3`**, exact `website/docs/user-guide/features/api-server.md` blob `82c591d3afadd1060d870652f7c350b0a53a6253` and `gateway/platforms/api_server_runs.py` blob `868ed43adf99e0024c9bd31e655a2a1e201cf4d9`. This disambiguates earlier historical October issue reports from present-release capabilities. Sources: https://github.com/NousResearch/hermes-agent/blob/v0.23.3/website/docs/user-guide/features/api-server.md ; https://github.com/NousResearch/hermes-agent/blob/v0.23.3/gateway/platforms/api_server_runs.py .

**Built in already (do not reimplement blindly):**
- Canonical gateway session authority with durable admission identity and per-session serialized ownership, including **Chat Completions/Responses** keyed admission; legacy execution still has five-minute process cache and *no streaming dedup*. Idempotency behavior is mode- and endpoint-dependent, not a single global cache.
- `POST /v1/runs` 24-hour keyed replay ledger, same-key/same-payload 202 replay and changed-payload 409; *unkeyed* submissions deliberately remain non-idempotent.
- `GET /v1/runs/{id}` status, `GET /v1/runs/{id}/events` replay with `Last-Event-ID` / `last_seq`, redaction requirements and `replay.truncated` when truncated.
- Terminal `interrupted` on graceful gateway shutdown; canonical session authority additionally reports **nonterminal `unknown`** after owner restart, holding follower tasks rather than pretending success.
- `POST /v1/runs/{id}/resolve-unknown` uses exact `admission_id` and `execution_generation` with owner checks; successful repeat yields the same receipt, stale generation rejects 409. **Important:** this operator acknowledgement unblocks the FIFO; it does *not* prove that an earlier external tool side effect never occurred.
- Authenticated profile-scoped run status/control and exact `request_id` + `execution_generation` for live approval/clarification; a foreign-surface session is not adopted through ordinary API routes.

**Critical implications:**
1. The old fork `main` is April 2026. Patch sets #4/#5/#6/#11 built on that version must be **compared against v0.23.3 semantics before any merge**, or their new cache/SSE logic can regress durable admission, session ownership, typed failure and recovery.
2. Canonical streaming Chat Completions can emit `finish_reason:"error"` within HTTP 200 with `[DONE]`; a client must inspect the final chunk/error code, not infer success from DONE. Legacy mode and canonical mode must be tested separately.
3. The GPT Companion / Chrome MV3 view is an **optional read-only observer**, not the canonical session authority. Each browser restart reattaches by run ID and replay sequence; if `replay.truncated`, query authenticated run status and show an evidence gap.
4. Never log `message.delta`, `reasoning.available`, tool previews, raw errors or `run.completed.output`. Trust elevation requires a separately authenticated source adapter, not a self-claimed `trust_level` field.
5. Modern official docs specify `API_SERVER_KEY` required even on loopback for deployments with terminal-capable tools; do not deploy a browser bridge with wildcard CORS or a shared unscoped token.
6. Do not present `resolve-unknown` as a fully automatic safe fix; require evidence about remote effects before intentionally unblocking and reissuing follow-up work.

### ADR-GPT-018 (decision)
**ACCEPT for integration planning:** upstream v0.23.3 parity + native Runs API observer + trust-boundary adapter. **REJECT:** building a new authoritative queue or independent recovery engine first. This is higher priority than growing the offline parser, but deployment remains blocked until the real Windows extension and user-approved credentials are inspected.

**Conflict-resolution executed in this draft:** this PR's metadata schema parser moved from `gateway/gpt_bridge_event_audit.py` to `gpt_bridge_metadata_audit.py`, with matching test move. This is NOT a claim that native SSE parser PR #4 and our metadata parser are integrated; it simply removes an unnecessary same-path write collision while preserving the review boundary. Both still require an explicit adapter and unified regression review.


### CI isolation correction — O-24

**OBSERVED_CODE:** `main` includes a non-empty `gateway/__init__.py` which imports `hermes_cli.config`, importing `yaml` at module load time. This makes a supposedly pure-stdlib check under `gateway/` dependent on the full application environment, even if the audit code itself only imports Python standard library. The audit module was moved out to root `gpt_bridge_metadata_audit.py` with a matching isolated import in tests. The real gateway remains unchanged. This is deliberately an **offline** tool and cannot be mistaken for a runtime-installed gateway adapter.

**CI scope correction:** the isolated GitHub workflow now checks documentation changes on exact HEAD and uses per-PR `concurrency.cancel-in-progress` to avoid leaving obsolete checks queued as dozens of agents push. Cancelled checks are not success evidence. A future production observer should be added only through an explicit authenticated adapter and separate integration PR.


## 13. Additional adversarial hardening — current draft revision

**TESTED_OFFLINE:** 53 normalized-metadata tests plus 12 merge-collision tests passed under isolated `python -S` on Python 3.13 (65/65). Python 3.11/3.12 and the full Hermes repository remain gated by GitHub Actions. Local branch coverage: 94% for the event metadata auditor, 77% for the collision guard; these are **statement/branch composite reports**, not guarantees of completeness.

**New bounded-input invariants:** raw metadata input is capped at 64 MiB total, 100,000 records, 50,000 distinct accepted events and 4 KiB/event. JSON nested recursion, ambiguous duplicate keys and URL-shaped evidence references fail closed; the report never echoes rejected payloads. Even with these caps, a caller-provided iterable is not an authenticated event source.

**Windows agent worktree collisions:** GitHub filenames are case-sensitive, but many Windows workspaces are not. The PR guard now separately flags `POSSIBLE_WINDOWS_CASE_ALIAS` for cross-PR names differing by case, and `FILE_DIRECTORY_PREFIX_CONFLICT` when one branch writes a file at another branch's directory prefix. These are review flags, not proof that a particular NTFS volume rejects the path. No merge is automatically authorized.

**O-25 connector state:** the Local_WorkSpace session subsequently answered `list_workspaces` with only the `shelter` workspace. Therefore the connector was no longer universally down, but its allowed scope still did **not** include the Hermes browser extension, its installation log, or its native host. Do not claim direct runtime monitoring or Obsidian edits to Hermes.

**Risk ranking update:** modern upstream-version parity and authenticated native Runs adapter remain above expanding this offline observer. Any 'self-heal' without an independent effect receipt is rejected. After every PR HEAD change, all check-run conclusions from the previous SHA become stale and must be re-read.


## 14. Cross-agent review: native SSE parser PR #4, latest observed head `f2373ed5551fe47168b014b08d63560a6bb0d68a`

**OBSERVED_SOURCE, not production reproduction.** Source-level review of `gateway/gpt_bridge_event_audit.py` at the named PR head found that `CausalRunAuditor.observe()` stores sequence IDs in a set and returns immediately when a previously seen ID reappears. An identical replay is legitimate. A *changed* event (`run.started` versus `run.failed`) with the same seq would be ignored rather than reported as a collision. The native SSE `id:` value and payload `seq` also need explicit reconciliation; on disagreement, do not prefer one without flagging evidence tampering.

**OBSERVED_SOURCE + VERIFIED_RELEASE_CONTRACT.** In upstream v0.23.3 the canonical run status can be nonterminal `unknown` after an owner restart. Native PR #4 `explain()` does not have a dedicated `unknown` branch and therefore classifies it as a generic nonterminal/no-evidence observation. This risks an operator overlooking uncertain external effects. Add `UNKNOWN_EXECUTION_RECONCILIATION_REQUIRED`, block automatic retry and distinguish an *operator acknowledgement that unblocks a queue* from proof the prior effect never happened.

Concrete synthetic tests to require on the native SSE adapter:
```python
# Sketch; use actual PR #4 SafeEvent constructor for the current HEAD.
a.observe(event(run_id="run_a", seq=1, kind="run.started"))
a.observe(event(run_id="run_a", seq=1, kind="run.failed"))
assert "DUPLICATE_SEQUENCE_CONFLICT" in a.explain().evidence

a.observe_status({"run_id": "run_a", "status": "unknown"})
assert a.explain().stop_reason == "UNKNOWN_EXECUTION_RECONCILIATION_REQUIRED"
```
These are **new test requirements**, not test results. Cross-PR review comment was posted in PR #4; no changes made to its branch.

**New acceptance invariant:** No run may be marked reliably completed merely because a transport SSE terminal event appears; require matching status at an authenticated profile-owned run plus independent evidence for externally mutating actions. Every `unknown` outcome must remain distinguishable from user-requested cancellation, tool exception, a network failure, or an unresponsive browser.

**Validation update for PR #26:** At HEAD `8cec46d296e38b156b851dda0fda1b1508048e88`, all three offline GitHub Python matrix checks (3.11, 3.12, 3.13) were independently observed **success**; broad repository `test` was still `in_progress`. This version of the SDD may create a later commit; never extrapolate the old check result to the next HEAD. Do not merge with only an offline green matrix.

### ADR-GPT-019: partial GitHub check export must never be green (implemented in PR #26)

**Source-level failure mode:** A GitHub snapshot containing only a successful supply-chain scan previously produced `checks_ok:true`; the required full test workflow could be absent entirely. Fix: the read-only PR gate now allows an explicit snapshot field `required_checks`. Without a nonempty required list, `checks_ok` is **always false**. Missing mandatory names, contradictory duplicate jobs, stale per-job head SHAs, any reported failure and unfinished checks also prevent a green result. `observed_checks_all_success` is reported separately from the stricter `checks_ok` so users can identify this incomplete-evidence case. Every result still has `automerge_allowed:false`.

**Trust boundary:** `required_checks` is *operator-supplied unverified policy*, not a fetched signed protection-rules contract. Even `checks_ok:true` never means all actual required GitHub workflows or branch protections were checked. A future authenticated policy adapter must compare against repository rulesets and PR merge base; absent that adapter, human review remains mandatory. The four new negative tests raised offline coverage from 65 to **69** total: 53 metadata auditor and 16 PR gate. New GitHub CI at the resulting exact commit is pending separate verification.
