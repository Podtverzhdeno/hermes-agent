# Hermes GPT/CDP — incident diagnosis, safe recovery and handoff runbook

**Revision:** 2026-11-22 / R1  
**Authority:** supporting procedure for `SDD_GPT_EXTENSION_AND_OBSERVABILITY.md`. No new write privileges, no real background service, no production permission. This is a hypothesis-and-evidence workflow for an authenticated Kanban observer and a versioned Web Companion/CDP bridge.

## 1. What “atomic understanding” means

A cross-system workflow spanning the browser, local tunnel, Hermes, model provider, GitHub and Obsidian **cannot generally be made one ACID transaction**. “Atomic understanding” means every irreversible action has an independently persisted intent, causal identity, observed receipt, evidence of its effect, and a precise UNKNOWN state if the result is incomplete. It is an auditable saga, not a promise of exactly-once external execution.

Three separate facts MUST be checked:
1. **Liveness:** Is the owner process/worker/CDP target alive? A heartbeat alone does not prove useful progress.
2. **Forward progress:** Did the worker cross the next phase-specific milestone with durable event offset and expected task/revision?
3. **Effect certainty:** Did an external mutation actually occur? Response timeout, browser detach, worker crash or model text are **not** proof that it did or did not.

Persist the causal invariant `task_id + attempt_id + lease_fence + request_id + operation_id + canonical_resource_id + exact_revision`. A change in any identity requires an explicit transition, not an inference from a similar prompt.

## 2. Evidence tiers and display contract

| Tier | Can establish | Cannot establish |
|---|---|---|
| Local process/OS health probe | PID exists, socket bound, event-loop responsiveness | Prompt delivered, model replied, tool executed |
| Web Companion transport event | Requested target attached, matching request_id received | External mutation verified or tool permission |
| Kanban task state | Claimed/blocked/review status as persisted by current owner | Raw provider side effects beyond registered receipts |
| GitHub commit SHA + required check ID | Exact code revision and actual executed CI check | Host deployment, unseen external effect, absence of other pending PRs |
| Scoped Obsidian SHA/read-back | Note content committed in the permitted editor scope | Whole project consistency across other roots |
| Authenticated API receipt + read-back | External action happened or is independently absent (subject to provider semantics) | Other concurrent actions or ultimate business success |
| Human owner approval | Permission for a specific exact action/digest and expiry | That the authorized action ran |

Every dashboard row should carry `observed_at`, `source`, `confidence_class` = observed/hypothesis, `source_revision`, `last_phase`, `last_event_seq`, `missing_evidence`, `retry_class`, `next_safe_action`. Unknown is a valid and important answer.

## 3. Root-cause diagnostic sequence

```text
START task_id
  ├─ canonical owner found? ─ NO → TASK_NOT_REGISTERED / check intake
  ├─ claim record exists? ─ NO → QUEUED / assess scheduling & resource caps
  ├─ worker process booted? ─ NO → SPAWN_FAILED / inspect OS & profile
  ├─ worker accepted lease/fence? ─ NO → WORKER_NOT_ACKNOWLEDGED
  ├─ exact prompt.receipt delivered? ─ NO → PROMPT_NOT_DELIVERED
  ├─ first model request observed? ─ NO → MODEL_NOT_STARTED
  ├─ model response/transport terminal observed? ─ NO → MODEL_OR_TRANSPORT_STALLED
  ├─ tool proposed? ─ YES → scope & approval checked?
  │                           ├─ NO → POLICY_DENIED / STOP
  │                           └─ YES → effect reservation persisted?
  │                                         ├─ NO → GATEWAY_NOT_ATOMIC / STOP
  │                                         └─ YES → provider receipt + read-back?
  │                                                   ├─ NO → EXTERNAL_EFFECT_UNCERTAIN
  │                                                   └─ YES → verification
  ├─ exact-revision required evidence passed? ─ NO → VERIFY_BLOCKED
  └─ yes → VERIFIED_COMPLETE
```

A timeout can correspond to any branch. Diagnose by the **first unacknowledged transition** and preserve the subsequent uncertainty. If multiple failures are present, prioritize unresolved external effect and policy revocation over automatic retry.

## 4. Stop/recovery playbooks (no dangerous speculative fixes)

| Signature | Likely hypotheses / targeted probe | Safe automated response | Hard stop condition | Proof to resume |
|---|---|---|---|---|
| Task assigned, no worker PID | invalid executable/profile, Windows subprocess setup, CLI not found | Queue diagnostic, one bounded read-only process probe | No owner lease or wrong workspace | exact process spawn receipt + worker accepted |
| Worker PID alive, no prompt delivery | Windows admission sequence stalled, session binding, unexpected input pipe or plugin init | Mark `PROMPT_NOT_DELIVERED`, observe session admission state; quarantine worker lane | Unknown in-flight tool (never start second worker) | matching receipt for same attempt/fence |
| Worker starts but no model call | memory plugin import/holographic numpy deadlock, SDK initialization hang | Capture capped process thread snapshot in trusted host, compare safe canary profile | repeating hidden startup restarts | first model request under bounded deadline |
| Worker heartbeats, no useful progress | callback heartbeat without phase advancement, infinite reasoning loop, queue starvation | emit `NO_MEANINGFUL_PROGRESS` based on progress_seq/deadline, not heartbeat alone | repeated no-progress after retry bound | new durable progress marker verified |
| Gateway event loop blocked under 10+ workers | blocking sync call, CPU contention, thread lock, telemetry backpressure | shed new admissions, preserve queued tasks, report queue latency | gateway unresponsive or unknown effects | loop-lag and worker pressure probes return within bounds |
| Browser extension worker suspended | service-worker lifecycle, tab closure, permissions expiry | mark `EXTENSION_SUSPENDED`, do not read cookies or page text | missing owner session approval | extension version+target owner+CDP ready |
| Target/transport disconnects mid-turn | CDP detach, transient network, browser close | classify `TRANSPORT_DISCONNECTED`, retain request_id and pending effect list | effect outcome unknown | matching transport receipt or independent reconciliation |
| JSON response truncated / wrong request_id | partial stream, stale tab reply, cross-agent channel contamination | reject reply with structured safe code, do not dispatch tools | stale fence, wrong target ownership | valid schema, exact request_id and current fence |
| Tool call valid but unauthorized | missing policy scope, unknown tool, expired approval, prompt injection | reject and log policy code only | never bypass by rephrasing model request | independently authorized exact tool/digest |
| Effect reserved, provider call timed out | provider executed, reply lost; process crashed after write | quarantine action key, emit `EXTERNAL_EFFECT_UNCERTAIN` | any attempt to blindly retry | signed receipt/read-back proves executed or absent |
| Receipt exists but external state differs | stale read-back, eventual consistency, conflicting actor | bounded read-only reconciliation polling with deadline | mismatch still unresolved | provider-specific consistency proof |
| Required CI green but another trusted CI red | distinct source conflict, different SHA, real regression | fail verification, open repair task with source links | attempted success despite required failure | all required trusted checks at same exact revision |
| Stale CI result at old SHA | changed branch after earlier green | mark `STALE_VERIFICATION` | merge/release without new tests | required checks on current SHA |
| Owner STOP but child worker still running | cancellation not propagated, queue start race | revoke dispatch, fence child, signal approved local interruption; monitor ack | any new external write after STOP | no active new effect + child stop/uncertainty record |
| Approval pending past deadline | owner not available, leaked queue item | expire/mark blocked | implicit approval | new exact approval and valid expiry |
| 429/credit exhausted | shared provider quota, retry storm, subscription state | provider-declared backoff with jitter, independent project budget | unlimited retries or session cycling | quota/owner budget confirmed |
| Auth expired / denied | supported login or permissions changed | stop protected actions, request supported reauthorization | token scraping/session impersonation | authorized reconnect check |
| GitHub branch changed during task | another agent concurrent write, failed CAS | stop write, re-fetch head and diff, isolate own worktree | force push or silent overwrite | conflict-free change + CI on merged SHA |
| Obsidian editor unavailable | tunnel/observer stopped, editor scoped path mismatch | mark local sync pending, continue repository-only docs | claiming Obsidian updated | read-back from authenticated permitted editor |
| Observer heartbeat absent | monitor crashed or locked DB | restart observer under configured supervisor without restarting worker | status inferred healthy from last cached row | new event cursor and heartbeat from observer process |
| Ledger permission/lock/corruption | concurrent SQLite writers, disk failure, backup age | bounded read-only health check and alert | rebuilding state without receipts | validated backup + integrity + effect reconciliation |

### Proven upstream Windows signatures, not assumed local defects

**Case A — prompt never delivered, telemetry process spawn deadlock.** In [upstream #147613](https://github.com/NousResearch/hermes-agent/issues/147613), a native Windows 11 Kanban worker reached admission sequence 15, session `message_count=0`, repeatedly received `{"messages":[]}` and never emitted a model call. The reporter captured a live stack in `get_version_info -> _run_git -> subprocess.run(["git","rev-parse","HEAD"], capture_output=True, timeout=3) -> join`, where subprocess cleanup/reader join hung even though the nominal timeout was three seconds. A local reporter patch avoided hanging. **Do not assume** the workaround or PR #151449 completely resolves this in v0.23.3: verify all live callers on the canary. The appropriate probes are exact `admission_sequence`, model request count, session message count, OS process thread stacks, and bounded *read-only* version-info check. The **fix category** is elimination of a blocking subprocess on a turn-critical path and a bounded managed-worker admission protocol, not repeating a GPT prompt.

**Case B — prompt framing absent after valid admission.** In [upstream #146955](https://github.com/NousResearch/hermes-agent/issues/146955), admission and `worker_bound` existed but the `prompt.request` frame was never sent on the worker input channel; worker idle in `read_frame` until timeout, while interactive model calls worked. Look at event order and outbound frame confirmation. Distinguish `WORKER_BOUND` from `PROMPT_DELIVERED`, and keep a finite deadline; do not count a socket connection as delivery.

**Case C — model request absent during module import.** In [upstream #148389](https://github.com/NousResearch/hermes-agent/issues/148389), worker was idle in `numpy._core.multiarray` during extension-module loading, even though the same profile's interactive one-shot call worked. Read-only thread/stack probe differentiates this from missing provider credentials. A deterministic startup canary should test dependency import under the **exact worker spawn context**.

**Case D — overloaded gateway event loop under concurrent lanes.** In [upstream #152364](https://github.com/NousResearch/hermes-agent/issues/152364), the reporter saw event loop stalls, clustered receipt timeouts, misleading worker-loss causes, stale toolchain probe cache and occasionally empty notification tails. Their mitigation was lowering concurrent tasks from 10 to 6; this is a local workaround, **not a global safe threshold**. The future gateway should record loop lag, per-profile inflight count and worker receipt latency, then shed new work when a measured saturation threshold is crossed. Record whether the external effect state is uncertain before restarting any worker.

**Upstream semantics:** The current Kanban documentation identifies exit code `75` for retryable/transient class and `78` for configuration/auth class. These codes are *signals to the scheduler*, not a universal guarantee of safe external action replay. Any model-assisted recovery still consults a persisted effect ledger and exact approval. Use version-pinned source and tests before relying on exit-code mapping.

Upstream public issue investigations (not verified on this local host):
- https://github.com/NousResearch/hermes-agent/issues/147613 (Windows prompt never delivered)
- https://github.com/NousResearch/hermes-agent/issues/146955 (admitted, bound, prompt not delivered)
- https://github.com/NousResearch/hermes-agent/issues/148389 (worker startup hang, no model call)
- https://github.com/NousResearch/hermes-agent/issues/152364 (gateway event-loop stalls with 10 Kanban workers)
- https://github.com/NousResearch/hermes-agent/issues/61923 (Windows zombie worker after complete)
- https://github.com/NousResearch/hermes-agent/issues/147409 (review tasks wrongly reclaimed)

**Do not assert these are current v0.23.3 defects without version-specific reproduction.** Fixes from issues may already have shipped; verify exact pinned source and safe canary.

## 5. Agent self-repair authorization policy

Only repairs of **read-only observation components**, safe deterministic projections, or explicitly authorized idempotent read operations may be scheduled automatically. A language model may suggest hypotheses or patches but does not get escalation authority by citing this document.

Unattended repair is prohibited when a change affects credentials, CDP authentication, real external writes, repo force-push, active production deployment, raw session state, ambiguous effect receipts, global file access, or owner STOP. Require signed actor approval and independent verifier at exact scope.

The atomic repair loop:
1. incident_event with reason code and verified minimal reproduction;
2. independent classification and request for an isolated worktree;
3. scoped patch with test first, run in sandbox;
4. capture test command, runner, SHA, stdout/stderr redacted and negative tests;
5. verifier checks behavior and policy, not the implementer's explanation;
6. approved merge behind flag, supervised canary, rollback checkpoint;
7. close incident only after system observation and external effect audit.

If verification is blocked, keep incident **open/blocked**, not “fixed by AI”.

## 6. Resource ceilings (proposals, not live configuration)

The following are **candidate knobs**, not asserted defaults. Determine measured baselines before setting policy:
- max concurrent tasks / project, browser target and provider;
- request/token/cost budget shared across root DAG and all child agents;
- max unmatched request_id replies, invalid JSON frequency and event queue backlog;
- worker heartbeats versus phase-specific forward-progress deadline;
- max retained JSONL bytes and age; minimum supported snapshot recovery duration;
- max external-effect reservations awaiting reconciliation;
- max tracked GitHub/Obsidian write paths and worktree lifetime.

For load tests simulate 1, 5, 10, 30 and 50 agents on fake providers; record p50/p95/p99 claim wait, phase latency, error classification precision, duplicate side effects (must be zero in bounded faults), orphaned tasks, human-review queue and cost. Do not claim a numeric SLA until empirically validated on the actual host.

## 7. Shared 30-agent handoff record

Each agent writes one structured and bounded checkpoint after any durable work transition:

```yaml
schema_version: 1
task_id: "opaque-task-id"
owner_role: "A0|A1|A2|A3|A4|A5|other"
attempt_id: "opaque-attempt-id"
lease_fence: 1
source_sha: "40-char-git-sha"
branch: "exact-branch"
last_verified_phase: "tests_completed"
execution_status: "blocked|running|review|complete"
reason_code: "EXTERNAL_EFFECT_UNCERTAIN|NONE|..."
evidence:
  - kind: "ci"
    source: "github-actions"
    run_id: "exact-run-id"
    revision: "40-char-sha"
pending_effects: []
changed_paths: []
reviewer: null
next_safe_action: "explicit, narrow step"
```

This example is not a real state record. Never place secrets, user conversations, prompt bodies or approval credentials in a shared checkpoint. In the actual system append to the task's canonical Kanban record, not many independent “current status” notes. Obsidian is human-readable specs/decisions and cross-references, not a second mutable job scheduler.

## 8. Runbook acceptance and regression rules

A regression test must show the preceding state and the expected blocked/final state. Test *counterexamples*: stale fence, wrong request_id, same-key changed payload, verified external-absence retry, unknown effect after restart, failed trusted CI plus passed trusted CI, owner STOP during reservation, worker process alive with zero progress, observer missing while workers still active, live parent GitHub SHA changed mid-commit.

Never hide a failure by changing the test expectation unless it is demonstrably mismatched to the written contract (and the code path is independently checked). Keep a record of that decision. For concurrent agents, the **reviewer of a test change must not be the same worker who asserted success** unless a separate trusted CI and acceptance policy verify it.

Current isolated prototype CI success does **not** verify this runbook's full system behavior; end-to-end CDP and modern Kanban adapters are still unimplemented and the local Workspace is unreachable.
