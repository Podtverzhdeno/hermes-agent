# Hermes ↔ GPT Bridge: System Design Document (SDD)

**Version:** 0.1.0 (2026-11-22)  
**Status:** Design proposal; **not deployed, not verified in a live browser**  
**Baseline:** `Podtverzhdeno/hermes-agent` fork `main` @ `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (stale relative to upstream; rebase audit required)  
**Adjacent design:** `docs/autopilot/ARCHITECTURE.md` in separate draft PR #1, **not yet on main**.  
**Security candidate:** draft PR #3 for ACP callback isolation; its CI and integration status must be checked independently.  
**Owner intent:** make agent processing explainable at the level of individual actions; detect why operations stop, safely recover, improve the system through evidence-driven SDD changes, and support dozens of concurrent specialist agents without destroying local project state.

## 0. Source-of-truth and evidence legend

- **OBSERVED:** confirmed from code or connector metadata at the stated revision.
- **DESIGNED:** reviewed proposal, not implemented.
- **HYPOTHESIS:** plausible failure mode needing targeted test.
- **VERIFIED:** only an independent test/artifact with exact revision and environment can justify this status.
- **BLOCKED:** cannot reach resource, and no verification is claimed.

Existing source audit (OBSERVED): `acp_adapter/server.py` uses a shared four-thread executor and previously assigned `tools.terminal_tool._approval_callback` globally around each ACP prompt; `acp_adapter/permissions.py` previously treated an unknown option as `once`. See draft PR #3 for a scoped fix. The separate Autopilot draft PR #1 proposes a durable SQLite ledger but explicitly does **not** activate dispatch, live watchdogs, browser integration, or tools. Local_WorkSpace connector returned `Session terminated` in this review (BLOCKED); the local Windows files, Obsidian notes, and a running browser extension have not been inspected. The repository paths `extension/manifest.json` and `api_server.py` did not resolve on this fork snapshot; this is **not** proof that the user's independent extension does not exist.

### Historical local extension discovery — requires fresh verification

A prior owner-supervised local smoke test (2026-11-11) referenced:
- Windows workspace: `C:/Users/Vadim/Tunnel`
- unpacked extension: `chat-launch-smoke-desktop-test/web-extension`
- native/local companion candidate: `chat-launch-smoke-desktop-test/web-companion`
- extra extension config: `bridge-config.json`
- reported bridge version: `0.6.6`; browser bridge port: `18763`
- last seen operational status at that time: stale extension heartbeat and bridge process not running.

These are **HISTORICAL USER CONTEXT, NOT LIVE SOURCE EVIDENCE** as of this SDD. The present GitHub fork does not prove presence/absence of these local files. First local audit after connector recovery must inventory all extension files and manifest permissions, bridge transport auth, exact process binding, heartbeat producer, stale event rules, user approval path and update integrity. The stated port is an *old configuration reference*, not a claim that a listener exists today.

**Risk-specific design consequence:** avoid adding a second local observer on another port without identifying which process is authoritative for task state. A disconnected heartbeat means only a visibility problem unless the ledger independently proves a worker lease failure.

**Non-negotiable:** the ChatGPT website is not a machine-readable agent queue, and UI presence/absence is not proof of task completion. The bridge uses documented integration interfaces and owner-authorized action pathways. No bypass of platform policy, user approval, CAPTCHA, billing, authentication or access controls.

## 1. Problem statement, success definition, and failure of naive approaches

A sequence such as `agent requested tool → browser appears quiet → runner retries → the same action happens twice` cannot be debugged from a chat transcript. Browser worker suspension, connector disconnection, provider throttling, exhausted context, stale lease, rejected approval, an unknown external outcome and a genuine software failure require **different** recovery paths.

A successful system makes these questions answerable without asking the model to guess:
1. Which immutable task specification was assigned, to which worker and revision?
2. Which durable steps finished, and what remains unverified?
3. Which event caused this state, with what independently obtained evidence?
4. Did a mutating action occur, fail, or reach an **unknown** outcome?
5. Can the same step safely resume under a new fenced lease?
6. Which competing worker, filesystem resource, provider quota, or approval blocked progress?
7. Which exact patch, test and CI run showed the intervention repaired the failure?

Target properties (DESIGNED):
- Every dispatch, approval, external effect reservation, completion, recovery and stop has a durable, queryable event and causal linkage.
- No automatic repetition of an external action with unknown outcome.
- No `succeeded` state solely because an LLM responded fluently or a browser message appeared.
- No cross-agent permission routing, untracked overlapping file writes, or stale-worker commits.
- Local durable worktree remains the operator's working copy; no repeated archive-download cycle.
- Recovery is bounded by an inherited parent budget (attempts, wall time, token/cost, concurrency).
- Operator receives an actionable root-cause hypothesis **plus confidence and evidence**, not unqualified certainty.

## 2. Architecture — single control plane, multiple non-authoritative views

```text
Owner intent ──► versioned work contract + policy + project revision
                         │
                         ▼
        Hermes Autopilot task ledger (PR #1, upon integration)
         ├─ durable task/effect/approval/evidence states
         ├─ lease + fence + idempotency + DAG constraints
         ├─ event outbox / durable source sequence
         └─ scheduler + budget / resource ownership
                 │                         ▲
                 ▼                         │
           Trusted adapters ─────────► verifier
        ┌────────┼──────────┐          (CI @ SHA,
        ▼        ▼          ▼           file hash,
     Official   GitHub/    Scoped MCP    receipt)
     model/API   CI        + local runner
     workers
        │
        ▼
       Diagnostic observer / reason engine / traces
        │
        ├────► local operator dashboard + alert queue
        │
        └────► optional, read-only Chromium MV3 extension
                  │ user-approved interaction/status only
                  ▼
          pinned Native Messaging host
          (no extension permission to mutate global ledger)
```

**Boundary B1 — control vs display.** Autopilot ledger is authoritative for tasks and effects. Diagnostic streams are append-only *observations*; the UI, extension and trace exporter cannot advance task state. Never create a second competing scheduler or database of authoritative task status.

**B2 — GPT connection.** Prefer documented API/Agents SDK or explicit owner-approved integration to issue work and obtain structured outcomes. Treat a ChatGPT web tab and its CDP/DOM as an optional user interface, not a programmatic worker/result API. If a particular action lacks a supported interface, mark it `manual_required`; do not imitate unrestricted unattended access.

**B3 — browser extension.** Manifest V3 service worker is ephemeral. Persist a checkpointed cursor in `chrome.storage` and keep the source ledger in the native host; do not keep queues, secrets, or leases exclusively in JS globals. Use minimum permissions, fixed native-host allowlist, strict sender checks, schema-validated messages and an OS-protected host. Native messaging is an option after the transport threat model, **not** an authorization bypass.

**B4 — execution.** API/agent workers only receive bounded task contracts and scoped tool capabilities. Web content, prompts, GitHub issue bodies and Obsidian notes are untrusted data. A verifier uses authenticated adapters and exact revisions, never agent attestations.

**B5 — local source.** A persistent owner worktree is distinct from disposable per-task worktrees. Sync is an explicit, verified operation. Snapshot rollback is not compensation for an external action.

## 3. Data and protocol contracts (DESIGNED)

### 3.1 Work contract

```json
{
  "schema_version": 1,
  "task_id": "uuid",
  "request_key": "project:objective:digest",
  "project_id": "immutable project id",
  "parent_task_id": null,
  "requirements_revision": "sha256:...",
  "repo_base_sha": "40-hex SHA",
  "owner_role": "A3",
  "dependencies": [],
  "expected_artifacts": [],
  "acceptance_checks": [],
  "allowlisted_resources": [],
  "risk_class": "R0|R1|R2|R3",
  "budget": {
    "remaining_attempts": 3,
    "deadline_utc": "ISO 8601",
    "max_parallel_children": 4,
    "token_ceiling": 100000,
    "cost_ceiling": "configured amount"
  }
}
```

Any model-supplied value in this contract must be validated by the control plane against owner policy. Authoritative identity, roles, budgets and permissions may not be reassigned via a prompt or event payload. Subtasks inherit the parent's remaining budget, not a new free allotment.

### 3.2 Causal event envelope

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "source": "worker",
  "producer_id": "worker-boot-uuid",
  "source_event_seq": 18462,
  "run_id": "uuid",
  "task_id": "uuid",
  "attempt_id": "uuid",
  "agent_id": "A3/worker-2",
  "lease_fence": 7,
  "trace_id": "32 lowercase hex",
  "span_id": "16 lowercase hex",
  "parent_span_id": "16 lowercase hex or null",
  "causation_event_id": "uuid or null",
  "occurred_at_utc": "2026-11-22T10:00:00Z",
  "observed_at_utc": "2026-11-22T10:00:01Z",
  "kind": "tool.effect.reserved",
  "state_from": "running",
  "state_to": "running",
  "reason_code": null,
  "target_revision": "git SHA or artifact digest",
  "effect_key": "stable operation id",
  "evidence_refs": [],
  "trust_level": "adapter_observed"
}
```

Events must be persisted with an atomic DB transaction before acknowledgment. Enforce unique `event_id` and (`producer_id`, `source_event_seq`) key, bounded payload length and version compatibility. Each `producer_id` identifies one producer incarnation (new ID at process restart); two workers may legitimately both emit sequence 1. **Ordering** comes from per-producer sequence and causal edges, not wall-clock timestamps; different sources have only a partial order. Trace context propagates across process boundaries by documented W3C Trace Context semantics; `trace_id` is for correlation, not authorization. Never log prompts, model completions, private chat, credentials, cookies, or raw tool arguments by default. Persist only allowlisted metadata, redacted status and content hashes; configurable short-retention diagnostics require explicit owner consent.

### 3.3 Event vocabulary

`task.received | task.planned | task.claimed | task.blocked | task.retry_scheduled | task.cancel_requested | task.completed | worker.started | worker.heartbeat | worker.lease_expired | model.requested | model.responded | model.throttled | tool.intent | tool.effect.reserved | tool.effect.acknowledged | tool.effect.unknown | approval.requested | approval.granted | approval.denied | verifier.started | verifier.completed | bridge.connected | bridge.disconnected | observer.gap_detected | diagnostic.classified`.

Each terminal task record must answer `who/what/when/why/proof/next_safe_action`. Store original errors only in a securely access-controlled store with redaction, never in shared SDD or basic trace metadata.

### 3.4 Crash windows and acknowledgment contract

- Before persistence: source may redeliver; replay is idempotent by event ID and operation key.
- After ledger persist, before adapter call: reserved effect is ambiguous from an observer's perspective; reconcile before replay.
- After remote commit, before local acknowledgment: remote may have succeeded; read back provider receipt or exact target revision and reconcile.
- After acknowledgment, before user notification: deliver notification again safely, never repeat the underlying action.
- After a worker lease expires: increment fence; stale worker's updates, approvals and effects are rejected at the **tool gateway** immediately before any external mutation.
- After MV3 service worker shutdown: restore cursor from durable native host; no worker lease is inferred from extension connectivity.
- After DB corruption/restore: block external effects until backup integrity and remote reconciliation complete.

## 4. State model and causal failure taxonomy

**Authoritative task states:** `queued → running → verifying → succeeded`; alternatives `retry_wait`, `waiting_approval`, `needs_reconciliation`, `blocked`, `failed`, `cancelled`. These align conceptually with Autopilot PR #1; do **not** implement a parallel state machine in the extension.

**Diagnostic state** is separate: `healthy | suspect | degraded | confirmed_failure | unresolved`. A missing heartbeat is a *suspect*, not proof of failure; activity may be waiting on a provider, human or network.

| Stable reason code | Evidence needed before classification | Next action |
|---|---|---|
| `AUTH_EXPIRED` | 401 / refreshed credential rejected | Stop secret-dependent steps; owner reconnect |
| `POLICY_DENIED` | Authenticated permission rejection + action fingerprint | Block; never retry by paraphrasing |
| `RATE_LIMITED` | 429 + Retry-After/provider response | Global budgeted cooldown with jitter |
| `PROVIDER_UNAVAILABLE` | 5xx/transport and independent health probe | Retry only idempotent requests |
| `NETWORK_PARTITION` | Connectivity failure corroborated by local probes | Queue safe reads; no effect assumptions |
| `MCP_DISCONNECTED` | Connector transport close/session termination | Mark evidence stale; reconnect with backoff |
| `BROWSER_WORKER_SUSPENDED` | MV3 lifecycle disconnection with durable cursor | Reconnect UI observer; never reissue task |
| `WORKER_LEASE_LOST` | Current ledger fence exceeds worker fence | Reject writes; replacement rereads contract |
| `CROSS_SESSION_INTERRUPT` | Two task identities share process-wide cancellation signal and a cancellation appears in unrelated tool trace | Quarantine concurrent terminal execution; apply task-scoped cancellation; do not assume user cancelled both |
| `CONTEXT_EXHAUSTED` | Model/provider token-limit evidence | Checkpoint + bounded summarize; new worker |
| `BUDGET_EXHAUSTED` | Parent DAG budget account evidence | Stop dispatch; surface cost decision |
| `OUTPUT_SCHEMA_INVALID` | Deterministic validator rejection | Bounded repair only if side-effect-free |
| `RESOURCE_CONFLICT` | File lock/ref SHA mismatch | Rebase or replan; do not overwrite |
| `CI_REVISION_MISMATCH` | CI head SHA differs from target | Re-run validation on exact SHA |
| `EFFECT_OUTCOME_UNKNOWN` | Reserved remote action without reliable receipt | Quarantine action; reconcile, never blind retry |
| `OBSERVABILITY_GAP` | Missing source sequence / dropped collector event | Mark timeline incomplete, do not extrapolate |
| `UNKNOWN` | Insufficient objective evidence | Preserve unknown; bounded investigation |

**Precedence:** `EFFECT_OUTCOME_UNKNOWN` outranks generic timeout/retry classifications for any reserved external write. `POLICY_DENIED` outranks a model's attempt to "fix" the command. `CI_REVISION_MISMATCH` blocks certification even when an old check is green.

Do not attribute a root cause solely from an LLM explanation. Distinguish `confirmed`, `probable`, `insufficient_evidence`; expose competing hypotheses and supporting timestamps/receipts.

## 5. Watchdog, recovery and repair policy

Watchdog is a separately supervised local process, not a ChatGPT turn or a Chrome service worker. Detection loop (DESIGNED):

```text
read ledger snapshot + signed/validated inbox
→ join by task_id, attempt_id, fence, trace_id
→ compute heartbeat freshness and critical missing causal events
→ inspect approval/effect reservation state
→ classify with deterministic rules and evidence
→ emit diagnostic.classified and concise operator view
→ if read-only/idempotent and budget allows: schedule fenced retry
→ if external effect uncertain: suspend + reconcile by independent read-back
→ if policy/credentials/irreversibility: request explicit owner decision
→ independent verification at exact revision
→ close incident only after verified evidence + no outstanding unknown effects
```

Intervals are policy parameters, not hard-coded "agent died" thresholds. Use distinct timeouts: queue SLA, model response idle, tool execution, heartbeat lease, provider request, human approval, reconciliation deadline. Time budgets are nested with top-level deadline dominating all descendants. If the host is off, live observation is **impossible**; record last known state and detect downtime on restart.

Auto-fix eligibility:
- `AUTO`: restart read-only observer, resubscribe with cursor, retry idempotent GET, regenerate an uncommitted local artifact inside isolated worktree.
- `REVIEW`: revert a risky patch, rerun tests, repair invalid schema or resubmit a PR (only with exact scoped approval).
- `HUMAN`: permission denial, unknown remote effect with no proof, irreversible action, privilege expansion, credential change, merge/deploy, billing increase.

Never train a self-fixing agent on its own unverified "success" reports; preserve pre/post revision and independent test evidence.

## 6. Multi-agent scale: dozens of workers are an adversarial scheduling condition

1. **Work ownership:** one write lease per resource key (project/ref/path or Obsidian note ID), with fence and expected revision. Write only to per-task branch/worktree. An expired lease never grants rollback of another worker's new result.
2. **DAG integrity:** each task has immutable requirements revision and parent; reject dependency cycles and contradictory acceptance criteria. Rescope through a new versioned task, not mutation in place.
3. **Concurrency limits:** parent-wide and per-provider token buckets, maximum children, CPU/IO/DB writer constraints, and a queue with priority aging to avoid starvation.
4. **State synchronization:** shared brief task manifest, exact object SHA, checkpoint reference, reason code and evidence; no global mutable prompt state.
5. **Reviews:** implementing worker cannot mark its own evidence trusted. A0/verifier role is separated from R1 edit permissions and R2 action approval.
6. **Loop detection:** fingerprint repeated model/tool attempts; cap repeated failure cycles by task and DAG, not session.
7. **Backpressure:** if audit writes fail, privileged mutation must fail closed; for low-risk read-only telemetry, emit a bounded loss counter and `OBSERVABILITY_GAP` rather than pretending completeness.
8. **Provider fairness:** 429 is coordinated across all workers sharing the quota, with jitter and Retry-After where available; never let 30 agents simultaneously retry.
9. **Upgrade safety:** schema version negotiation; incompatible clients become read-only; quiesce workers and take SQLite online backup before migrations.
10. **Monotonicity:** use monotonic duration within process and durable logical sequence across restarts; wall-clock skew never changes verified causal order.

Local SQLite WAL is appropriate for *one-host* prototype if all writers are on that host, writer contention is measured and migrations are disciplined. It is not a distributed lock service and must not sit on a network filesystem. Consider a managed durable workflow engine only once multi-host scale and operating costs justify it.

### 6.1 P0: global cancellation signal is incompatible with concurrent agents

**OBSERVED in main fork source:** `tools/interrupt.py` defines a module-global `threading.Event`. `run_agent.py` calls `_set_interrupt(True)` on one agent's interrupt and `_set_interrupt(False)` on reset/start. Because ACP uses concurrent workers, a single task's cancellation may stop unrelated terminal tools; a second task's reset may erase the first task's cancellation. This is a source-derived, reproducible risk, not a confirmed production incident.

**REQUIRED DESIGN:** per-task cancellation capabilities, nested cancellation scopes, owner/parent->child propagation only by explicit relationship, OS process and manual-thread propagation, and distinct task/worker/cancellation identity. The Autopilot ledger cancellation state remains authoritative; process-local tokens are cached projections, not a second authority. Tool gateway checks the current `task_id`, `lease_fence` and cancel state before each mutation.

**NEGATIVE GATES:** two parallel sessions cancel one without affecting the other; starting a second worker cannot clear an existing cancellation; cancellation with an unresolved remote effect goes through reconciliation, not replay. Test CLI backward compatibility separately.

The GitHub repository has Issues disabled (HTTP 410). Record this work in the SDD and review log instead of falsely claiming an Issue was created.

## 7. Security and privacy design

- No browser cookie harvesting, private ChatGPT message scraping, credential extraction, hidden remote debugging, CAPTCHA evasion or permission laundering.
- Use official provider APIs/SDKs wherever supported; browser extension is a status/explicit-user-action companion. Each new capability requires separate reviewed permissions.
- Native Messaging: pin allowed extension ID in host manifest; validate origin, protocol version, message type, bounded lengths, a per-install pairing identity and replay nonce; enforce OS ACLs and no open arbitrary localhost writer endpoint.
- DOM/content script, fetched webpages, GitHub PRs and Obsidian notes are untrusted. Reject instruction-like tool result data as authorization.
- Per-workflow R0–R3 action classes; high-impact actions require exact target, parameter digest, actor, expiry, external effect reservation, signed/evidenced acknowledgment.
- Trace metadata is allowlisted. No raw payload logging or broad collection of private user conversations; explicit retention and secure deletion controls.
- Separate transport identity (which extension/process sent a message), user authorization (who permits the action), ledger fence (which active worker owns the task) and verifier trust (who can certify evidence).
- Integrity of hash-chained events alone is not proof against an attacker controlling the host; use independently stored checkpoint digests for meaningful tamper evidence.
- Treat optional OAuth/session artifacts as high sensitivity. No secrets in Git, SDD, logs, PRs or issue descriptions.

## 8. Ranked engineering ideas — reproducible, **unvalidated** selection model

Weights: 30% impact, 25% reliability, 20% security, 15% implementation feasibility, 10% operational-cost efficiency. Each criterion is a **provisional expert rating** 1–5; `score = 20 × Σ(weight × rating)`. Scores are design triage, **not measured performance or a claim of 10/10 quality**.

| Proposal | Weighted score | Gate |
|---|---:|---|
| Scoped approvals + trust boundary | 95/100 | P0 |
| UI-independent task truth | 95/100 | P0 |
| Global DAG budgets + bounded fan-out | 95/100 | P1 |
| Causal event and reason-code protocol | 94/100 | P0 |
| Watchdog + reconciliation before retry | 91/100 | P1 |
| File/resource ownership with fencing | 89/100 | P1 |
| Fault injection + independent verifier | 89/100 | P0 |
| Native messaging extension (read-only) | 86/100 | P2 |
| Bounded safe self-healing | 73/100 | P3 |
| Two-model independent review | 73/100 | P3 |
| Temporal deployment on day one | 68/100 | Defer |
| Continuous ChatGPT DOM scraping | 39/100 | Reject |
 
Prioritize safety controls, a single task truth and causal visibility before adding autonomy. The highest-sounding feature can rank lower when it creates unsupported assumptions, fragility, operational overhead or a policy risk. Reevaluate weights/scores only after benchmarks and incidents; record the decision log.

## 9. Failure-injection suite and acceptance gates

Minimum reproducible scenarios (DESIGNED; not claimed to pass):
- 30 workers receive the same task; exactly one active fence may commit each conflicting resource.
- Two ACP sessions request dangerous-command approval simultaneously; no cross-session request or stale callback.
- Unknown ACP permission response must always deny.
- Worker crashes at each of four effect windows: before reservation, after reservation, after remote commit, after acknowledgment.
- Provider returns 429 with Retry-After while 30 agents share a quota; no retry stampede.
- Native messaging host dies, browser service worker sleeps and restarts; no task duplication.
- UI shows a completed sentence but CI is in progress/failed/stale; task never succeeds.
- webhook replays identical GitHub delivery ID; processed once.
- source events arrive reordered with skewed wall clocks; causal order remains correct or incomplete is displayed.
- audit disk fills / SQLite busy timeout / schema mismatch; no unaudited external effects.
- same Obsidian note edited by two agents; hash mismatch prevents silent overwrite.
- repo head changes after verification; old CI is rejected.
- partial multi-step model output; output schema failure is distinguished from provider refusal.
- prompt injection arrives via repo issue/tool response; no change to approval, budget or task permissions.
- unexpected provider bill or missing usage stats; budget gate blocks uncertain spending.
- agent stops responding while long tool is running; do not cancel/retry the external effect without reconciliation.
- clock jumps one hour; fence and causal sequence remain authoritative.
- forced local host reboot and verified restore; task safe-resume is consistent with ledger plus external receipts.
- 24–72 hour synthetic soak before unattended activation, covering connector flaps and memory/queue growth.
- all above must report precise status and incident reference in operator UI.

Target SLOs to measure (NOT results): zero unauthorized effects in fault tests; zero replay of unknown-effect writes; 100% R2/R3 actions with valid approvals; 100% terminal success with revision-bound evidence; 100% state transitions audit-persisted or fail-closed; p95 diagnosis latency under an agreed threshold; p95 safe recovery time; bounded queue growth; worst-case loss on host crash consistent with configured SQLite durability; operator-visible count of unknowns. Track numerator, denominator and sample size for all metrics.

## 10. Phases, ownership and integration checkpoints

| Phase | Scope | Release criterion |
|---|---|---|
| P0 | SDD, source audit, ACP permission isolation fix, event schema, diagnostic reason taxonomy | peer review; unit tests; zero unsafe fallback |
| P1 | Read-only local observer with cursor and outbox, GitHub/CI/Obsidian evidence adapters | crash/replay tests; exact SHA checks; no writes |
| P2 | Native Messaging read-only MV3 companion, local host identity, pairing and status dashboard | SW suspend/restart, origin/payload negative tests |
| P3 | One sandbox worker and fenced tool gateway; explicit approval/unknown-effect reconciliation | forced-crash matrix, safe rollback, zero unapproved actions |
| P4 | 30-agent DAG budgets, resource locks, fairness, cause timeline and independent verifier | load/soak tests, race tests, p95 metrics |
| P5 | Guarded self-healing, staged canaries, recovery drills, scorecard, optional multi-host migration | evidence-driven go/no-go and operator signoff |

Architecture owners: **Autopilot** owns task state and effect semantics; **GPT Bridge** owns client/transport semantics and non-authoritative telemetry; **Hermes adapters** own scoped execution; **Verifier** owns independent evidence; **operator** retains R3 authority. Never merge unrelated branches or alter PR #1's existing code without coordinating changes via an explicit review.

### P0 working backlog (ordered)
1. Review PR #3 ACP approval isolation and its test/CI result, then audit direct dangerous-command approval paths in nested threads.
2. Capture the actual extension source tree and host manifest from a working Local_WorkSpace MCP session; document extension protocol/version and permissions without guessing.
3. Define JSON Schema for envelope and reason codes; provide a parser that fails closed on invalid, oversized and secret-bearing events.
4. Run 30-agent concurrency model and two-phase external effect fault injection against the ledger branch without enabling production adapters.
5. Implement read-only replaying observer with durable cursor, causal-gap indicator and exact event-dedup.
6. Add redacted run timeline, root-cause evidence panel, reason-confidence and safe-recovery advice.
7. Resolve stale fork vs upstream differences before any real integration.

## 11. Incident operator procedure

Given a stopped task:
1. Capture `task_id`, `attempt_id`, fence, target SHA and observation timestamp without dumping secrets.
2. Query ledger authoritative state and reserved external effects **first**.
3. Examine causal trace and find last **durably acknowledged** event; flag gaps or source outages.
4. Compare at least two hypotheses when failure cause is not confirmed (provider/worker/connector/permission).
5. Never replay unknown remote writes. Reconcile via read-back; mark owner decision if no reliable proof.
6. Choose bounded retry, targeted fix, or human decision; persist action rationale and preconditions.
7. Re-run deterministic tests and independent CI at exact SHA, then verify local worktree update separately.
8. Close incident only when evidence satisfies the contract. Link follow-up issue and amend SDD if the class was previously unknown.

Example report (illustrative, **not real telemetry**):
`task=8c… attempt=2 fence=7; status=needs_reconciliation; last=tool.effect.reserved; hypothesis=transport timeout after possible remote commit; confidence=insufficient_evidence; action=read-back external receipt; retry=PROHIBITED until reconciliation`.

## 12. Decision log

- **D-001 ACCEPT:** one Autopilot state authority, read-only GPT Bridge observer. Avoid double schedulers.
- **D-002 ACCEPT:** causal events with source sequence + trace context; timestamps are supporting metadata.
- **D-003 ACCEPT:** bounded recovery by risk class; unknown effects quarantine.
- **D-004 ACCEPT:** native messaging as candidate for operator-visible extension; no broad site access or automation hidden from owner.
- **D-005 ACCEPT:** strict per-session approval context and fail-closed unknown permission response (code candidate PR #3).
- **D-006 REJECT:** continuous ChatGPT DOM scraping for worker supervision, because UI is fragile, incomplete and not authoritative.
- **D-007 DEFER:** Temporal and multi-host deployment until measured need; SQLite single-host constraints and restore drills first.
- **D-008 DEFER:** autonomous prompt self-optimization; without independent evaluation it can optimize away checks.
- **D-009 OPEN:** independently running user's browser extension path/manifest and Local_WorkSpace connectivity require source verification; no fabricated integration claim.

## 13. Primary sources (selection, not an exhaustive literature claim)

- Chrome MV3 service-worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chrome messaging security: https://developer.chrome.com/docs/extensions/develop/concepts/messaging
- Chrome storage: https://developer.chrome.com/docs/extensions/reference/api/storage
- OpenTelemetry context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- OpenTelemetry traces: https://opentelemetry.io/docs/concepts/signals/traces/
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenAI Agents SDK tracing and sensitive-data controls: https://openai.github.io/openai-agents-python/tracing/
- OpenAI SDK integrations and observability: https://developers.openai.com/api/docs/guides/agents/integrations-observability
- Temporal durable execution and idempotent activities: https://docs.temporal.io/durable-execution and https://docs.temporal.io/activities
- LangGraph checkpointing and interrupts: https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph
- GitHub webhook delivery/replay: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- GitHub check-run SHA and conclusion: https://docs.github.com/en/rest/checks/runs
- SQLite WAL constraints: https://sqlite.org/wal.html
- OWASP agent security / prompt injection: https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

**Document completion is not operational completion.** This SDD is the source of decisions and acceptance gates; only future verified code/CI/running-system evidence can establish delivery.
