# Hermes ↔ GPT: Causal Audit Kernel — executable SDD

**Document revision:** 1.0 / 2026-11-22  
**Status:** implemented as an OFFLINE, read-only auditor; no production bridge/Chrome extension integration  
**Scope:** `hermes_observer/audit.py`, `tests/hermes_observer/test_audit.py`, isolated GitHub Actions workflow  
**Baseline:** `Podtverzhdeno/hermes-agent` main at `7e9100901819ee44c16b4ddcb79a6bcb7909f591`  
**Related unmerged work:** PR #1 Autopilot ledger, #3 ACP approval isolation, #4/#5/#6 gateway idempotency & SSE, #7 GPT Bridge conceptual SDD.

> This document is an extension of the design in PR #7, not a competing task-control design. An offline validator reading an export cannot monitor a stopped host, certify the source of a claimed event, authorize external actions, or change an authoritative task state. "No anomalies in supplied slice" explicitly DOES NOT mean "task succeeded".

## 1. Problem and explicit contract

The need is *atomic, evidence-based understanding* of a workflow with tens of agents: which step attempted which operation, which effect is unknown, whether retries are safe, why an agent stopped, and what independently verified change fixed it. Common transcripts/LLM explanations cannot establish any of this: messages can arrive out of order or disappear; a successful-looking UI response may precede a tool failure; a timeout after an external write may conceal a committed change; and an expired worker can act despite a replacement being assigned.

**Implemented in this PR:** deterministic metadata event validation, per-producer sequence diagnostics, event-ID collision detection, causal DAG checks, fenced effect ambiguity detection, revision-verifier completeness checks, safe stop-reason *observations*, bounded input/output, offline test/CI harness. Does not ingest raw prompts, tools, cookies or auth tokens.

**Not implemented:** exporter, authenticated host, durable inbox/outbox, Chrome MV3 extension, native messaging, live watchdog, effect reconciliation via API, self-repair, CI attestation validation, autonomously activated agent scheduler, seamless Windows extension integration. Such features are separately gated below. This boundary is intentional: coding an observer should not quietly mint a second authority.

### Evidence vocabulary

- `SOURCE_OBSERVED`: verified by GitHub file/PR/commit or exact official documentation.
- `LOCALLY_TESTED`: tests actually executed in an isolated container on the listed files; not full-repo/CI evidence.
- `CI_VERIFIED`: GitHub Actions check actually completed successfully **for this exact head SHA**; never infer this from created workflow files.
- `OPERATOR_VERIFIED`: independently produced receipt/process/log from the owner's operating environment.
- `DESIGN`: future contract with an explicit acceptance gate.
- `BLOCKED`: necessary source is inaccessible; do not substitute a guess.

## 2. Trust and process separation

```text
[Owner + policy / R0..R3]
       |
       v
[ONE task/effect authority: Autopilot ledger / upstream Kanban after parity decision]
       | committed transaction (task + effect reservation + audit outbox)
       +--------------> [durable exporter] -- metadata-only, authenticated --> [immutable raw observation store]
       |                                                                       |
       |                                           independent cursor/watermark |
       |                                                                       v
       |                                           [read-only causal auditor + reason engine]
       |                                                                       |
       v                                                                       v
[scoped effect gateway] --- independent receipts ----------------> [verifier / operator findings]
                                                                                |
                                                                                v
                                                                  [optional MV3 status panel]
```

No read-only observer gets the ability to advance tasks, submit approvals, write a PR, or replay external actions. The extension/panel displays evidence and can present an operator-approved action request to a separately authenticated policy endpoint; it is NOT the work queue. A `trust_level` string in an event is **self-reported** unless the transport and server bind it to a verified producer identity. Event correlation/trace IDs are **not** capability tokens. Never treat ChatGPT page/DOM content as an authoritative worker API.

**MCP/Local Workspace current blocker:** `Local_WorkSpace.list_workspaces` returned `Session terminated`. The real extension source, current host manifest, Windows processes, Obsidian state and runtime logs were not inspected. Do not claim a live extension improvement based on a fork API adapter alone.

## 3. Input contract v1 and parsing limits

Format: UTF-8 newline-delimited JSON from a separately trusted *metadata-only* exporter, never a chat transcript. `schema_version=1`, UUID `event_id`, UUID-or-null `task_id`, `producer_id` (unique per process boot), positive integer `source_event_seq`, `occurred_at_utc` with `Z`, and enumerated `kind` are required. All other fields are a strict allowlist; unknown fields are rejected rather than silently retained.

Optional: `source`, `run_id`, `attempt_id`, `agent_id`, nonnegative `lease_fence`, W3C-shaped `trace_id`/`span_id`/`parent_span_id`, `causation_event_id`, `observed_at_utc`, `state_from`, `state_to`, `reason_code`, `target_revision`, `effect_key`, opaque `evidence_refs`, and a non-authoritative `trust_level` label.

For `tool.effect.{reserved,acknowledged,unknown,reconciled}`, require task ID, effect key and fence. Effect acknowledgement must reference an opaque external receipt; a receipt *reference* alone is still NOT independently verified. `tool.effect.reconciled` is an extension event kind for forward-compatible experiments; the offline auditor intentionally does not clear an outstanding unknown based on that untrusted claim.

Limits enforced by the module:

| Item | Bound | Why |
|---|---:|---|
| Raw NDJSON line | 32,768 bytes | refuse massive/secret-bearing payloads; stream-drain oversized lines |
| Entire input scan | 64 MiB | stop excessive disk/CPU consumption with an incomplete result |
| Accepted/invalid lines per invocation | configurable up to 100,000 | bounded memory/CPU; overrun means incomplete, not green |
| Event findings in output | 250 | prevent alert-response amplification; counters keep total |
| Evidence IDs per event | 16 | stop metadata abuse |
| Identifiers | typed UUID / opaque token constraints | never print raw exception/payload text |
| Duplicate JSON object keys | prohibited | prevent ambiguous parser interpretations |
| JSON `NaN`/`Infinity`, deeply nested JSON, boolean-as-int, null required occurrence time, invalid UTC, zero trace ID | prohibited | strict schema |

The offline audit retains validated event metadata in memory until exit; it does not persist inputs. The source file is opened read-only. This is **not a guarantee** against a malicious, already compromised host, nor a substitute for source-side redaction. File reads, machine logs, and third-party tracing need their own privacy audits.

## 4. Deterministic invariants (executable wherever specified)

| ID | Invariant | Offline response | Authoritative enforcement owner |
|---|---|---|---|
| I-01 | Same `event_id` must replay bitwise-equivalent parsed content | exact duplicate counted; differing payload = collision | producer outbox/ingress unique key |
| I-02 | `(producer_id, source_event_seq)` identifies at most one event | conflicting pair = collision | durable producer sequence allocator |
| I-03 | Sequence is per *producer incarnation*, not per worker name | 30 producers can each emit sequence 1 | producer bootstrap identity service |
| I-04 | Missing interior sequence is an observability gap, not task failure | incomplete; no synthetic missing event | exporter cursor + storage |
| I-05 | Causation links must not cycle or invert same-producer order | cycle/inversion = anomaly | source instrumentation |
| I-06 | An external effect is not safe to replay if reserved but not conclusively accounted for | `EFFECT_OUTCOME_UNKNOWN`; no retry permission ever emitted | fenced tool adapter + reconciliation endpoint |
| I-07 | Receipt-less, earlier-than-reservation or unlinked acknowledgements do not clear unknown effects | anomaly; keep unresolved | authenticated receipt-verifier |
| I-08 | Multiple distinct reservations for one `(task,effect,fence)` need investigation | `MULTIPLE_EFFECT_RESERVATIONS` | durable idempotency/effect table |
| I-09 | Same task + fence must not be claimed by two owners | `FENCE_OWNER_CONFLICT` | ledger compare-and-swap lease |
| I-10 | Success needs exact target revision's independent verification | missing pair = incomplete | independent verifier, not model |
| I-11 | A reported success with unknown effect is inconsistent | `SUCCESS_WHILE_EFFECT_UNRESOLVED` | ledger transition guard |
| I-12 | A stopped task must explain its reason using stable reason codes | reason observation, or missing-code gap | event producer/incident review |
| I-13 | No log or auditor output contains prompt, tool arguments, private messages, tokens | reject fields, output allowlisted identifiers only | exporter/access control/security tests |
| I-14 | Metadata snapshot does not prove who produced a receipt | all findings labelled untrusted/offline | authenticated ingestion/OS trust |
| I-15 | An expired lease cannot authorize future external writes | **NOT enforced here** | scoped tool gateway fence check immediately before effect |
| I-16 | A single authoritative commit includes task transition and audit outbox | **NOT enforced here** | Autopilot ledger or chosen upstream lifecycle owner |
| I-17 | Empty observation is incomplete, never a clean health signal | `EMPTY_SNAPSHOT`, nonzero exit | trusted exporter + snapshot coverage proof |
| I-18 | Contradictory terminal outcomes within one attempt cannot be silently accepted | critical contradiction; no attempt identity = incomplete | task transition CAS and attempt identity |
| I-19 | Two process incarnations with identical display names must not share one fence claim | claimant identity is producer-boot ID + logical agent name | ledger worker incarnation authentication |
| I-20 | Thousands of routine gaps must not hide a late critical effect/integrity finding | deterministic critical-first bounded selection, complete counters | operator triage / incident threshold monitor |
| I-21 | A denial/blocked/expired-lease event without a specific cause is NOT an explained stop | `STOP_WITHOUT_REASON_CODE` or `STOP_REASON_UNKNOWN`, incomplete, no inferred permissions | trusted stop-source taxonomy/reconciliation |
| I-22 | Reordering independent stop-event delivery must not change a bounded operator report | stable sort by validated task/kind/event ID before capped output | diagnostic aggregation and incident-dedup gate |
| I-23 | Every task-scoped denial/lease-expiry must have validated task identity | missing task UUID = invalid event, never a clean snapshot | authoritative task ledger and authenticated incident exporter |


**Causality rules:** wall time may differ or move backward; order by producer sequence and explicit `causation_event_id`. Same-producer `ack` sequence must exceed the related reservation's. Cross-producer acknowledgement must be reachable by an explicit causal chain in the supplied snapshot. An absent cross-producer edge makes the result incomplete or unknown, not success. Partial exports can falsely appear to lack parents/acknowledgements: show *incomplete evidence* rather than asserting a definitive remote state.

**Terminal semantics:** this parser does not invent final task state from an event. It explicitly checks only the consistency of a reported `task.completed/state_to=succeeded` against matching `verifier.completed` events, target revision and outstanding effects. A verifier event is not proof by itself; offline data remains unauthenticated.

## 5. Stop/reason classification and recovery

A `stop_observations` record is a **claim in untrusted metadata**, never a verified diagnosis. Accepted reason codes mirror PR #7: `AUTH_EXPIRED`, `POLICY_DENIED`, `RATE_LIMITED`, `PROVIDER_UNAVAILABLE`, `NETWORK_PARTITION`, `MCP_DISCONNECTED`, `BROWSER_WORKER_SUSPENDED`, `WORKER_LEASE_LOST`, `CONTEXT_EXHAUSTED`, `BUDGET_EXHAUSTED`, `OUTPUT_SCHEMA_INVALID`, `RESOURCE_CONFLICT`, `CI_REVISION_MISMATCH`, `EFFECT_OUTCOME_UNKNOWN`, `OBSERVABILITY_GAP`, `UNKNOWN`.

| Input observation | Plausible cause | Safe next action | Never infer |
|---|---|---|---|
| `tool.effect.reserved`, no valid ack | remote commit may have happened before disconnect | reconcile exact external operation via read-back; human if not possible | safe to retry write |
| adapter 429 + Retry-After with several agents | provider quota, shared rate pressure | one coordinator applies shared cooldown + jitter, obey parent budget | one task alone caused it |
| `bridge.disconnected`, MV3 worker stopped | browser worker idle/suspended, host restart, network split | restore authenticated cursor; no new task dispatch | task failure or task completion |
| expired lease | worker preempted/stale | increment fence in ledger, reject stale external mutations | old worker stopped its OS process |
| unknown ACP permission ID | unsupported/altered response | deny, request exact explicit approval | default permission to proceed |
| CI green on SHA A while head is B | revision drift | verify B, record old result for A only | latest artifact passed |
| payload schema invalid / missing source seq | producer or collector bug, incompatible versions | quarantine slice, add regression test, compare export watermark | missing event's content |
| OTel span present, no ledger record | trace sampling/dropped telemetry, forged trace, lag | compare authenticated ledger/outbox | trace ID gives authority |

**Recovery tiers**: AUTO only for independently safe read-only retries/observer resubscribe; REVIEW for code repair with exact revision and CI; HUMAN for policy denial, credentials, unknown external writes, privilege expansion, irreversible changes, deployments and financial effects. Any external write with ambiguous outcome blocks autonomous replay even after a claimed local ack. The observer cannot grant AUTO permissions; it only suggests hypotheses for a separate trusted decision service.

## 6. Operator CLI contract

```bash
# From repository root, no installation or cloud secrets required:
python -m unittest discover -s tests/hermes_observer -v
python -m hermes_observer.audit /path/to/metadata-only-events.ndjson
```

Return codes: `0` no anomaly in supplied slice; `2` integrity anomaly or unresolved effect; `3` incomplete observation; `4` invalid snapshot/unavailable input. JSON prints only a bounded set of machine-readable findings and aggregate counts; `authority` is always `UNTRUSTED_OFFLINE_DIAGNOSTIC_ONLY`, and both `mutation_allowed` and `external_effect_retry_allowed` are always `false`. A zero exit code is **never** a CI/owner task-completion certificate. Do not pipe chat data, `.env`, session cookies or raw provider traces into this command.

**Example (illustrative, not a real incident):** `tool.effect.reserved(task=T,fence=7,effect=git:commit:X)` without acknowledgement => `requires_effect_reconciliation` + `EFFECT_OUTCOME_UNKNOWN`. If a `task.completed/succeeded` claim is also present, add `SUCCESS_WHILE_EFFECT_UNRESOLVED`. The next human-readable proposal is external receipt reconciliation; never repeat the write blindly.

## 7. Multi-agent contention and snapshot boundaries

Thirty workers are **thirty potentially adversarial clocks and schedulers**, not a single serialized transcript. Every producer has a fresh boot UUID; no global counter is assumed. The authoritative ledger must provide idempotent event ingest keyed by event ID and sequence, not an in-memory lock in each agent. A source event and its outbox entry must commit atomically with the task/effect update, while the exporter can deliver *at least once*. The external write is a separate commit boundary and demands idempotency key, fence, and reconciliation.

To avoid false gaps, future signed export snapshots should include `ledger_revision`, `producer_id`, `low_sequence`, `high_sequence`, `snapshot_completeness`, `exporter_id`, `schema_version`, `creation_time` and a canonical digest; the current v1 auditor does not accept/verify this header and therefore uses the conservative `...IN_SNAPSHOT` nomenclature. For a streaming cursor, acknowledge a contiguous persisted high-watermark, not the highest received out-of-order message; replay from the last contiguous ACK after reconnect. Avoid keeping critical queues inside Chrome MV3 service-worker globals. A browser panel and its local cursor may reconnect but cannot repair gaps by rewriting task history.

For 30+ agents, partition nonconflicting projects and limit global provider quotas; hold short SQLite transactions, monitor `SQLITE_BUSY`, WAL growth and checkpoint starvation, and avoid network-share SQLite. If multi-host operation becomes necessary, choose an actual distributed transactional store/queue rather than pretending SQLite file locks are a consensus protocol.

## 8. Threat model and abuse cases

- **Untrusted source content:** a webpage, repository issue, or model completion may contain instructions to change permissions or stop reporting; treat text as data, use independent policy validation.
- **Forged `trust_level`, span, identity or receipt:** metadata labels are not signatures. Bind producer identity to the authenticated transport/OS identity on future ingest; never trust a declared role from JSON.
- **Telemetry injection / cost explosion:** refuse long lines, unknown keys, too many events and excessive evidence references; enforce authorization and quotas *before* writing collector storage. W3C flags that untrusted inbound trace context can be used to inflate tracing costs.
- **Extension/native host compromise:** `sender.origin` and fixed extension allowlists are necessary but not sufficient; native messaging host may be executable by other local processes. Authorize each privileged operation in the host/tool gateway; do not use a blanket localhost writer.
- **Leaked payloads through tracing:** OpenAI Agents SDK may capture tool/model content; explicitly control sensitive-data tracing and review loggers, exception handlers, crash dumps and downstream exporters. This audit tool cannot sanitize upstream exporters.
- **False success through stale CI:** require exact head SHA, independent verifier result, changed file hashes and accepted requirement revision.
- **Self-improving agent circular evidence:** no agent evaluates its own high-risk fix; use two-role review plus invariant and regression tests. Never accept an LLM assertion of passing tests.
- **Audit collector outage:** read-only observation can degrade; privileged effect execution must fail closed where event persistence is a policy precondition. Neither panel nor LLM should forge a successful receipt.

## 9. Fault-injection evaluation plan (not a pass claim)

**Implemented offline test groups:** exact duplicate vs collision; sequence gaps and 30-producer independence; out-of-order clocks, missing parents and causal cycles; malformed/deeply nested/duplicate-key JSON and null required occurrence timestamp; payload-field rejection and size limits; reserved/acked/unknown/reconciled effects; receipt and causal-link validation; cross-fence replay; misleading success with stale verifier; two claimants on same fence including identical display-name agents in separate processes; stop reason observations; deterministically severity-capped exports, empty snapshots, conflicting terminal states scoped to attempt identity.

**Next release gates:**

1. `G0` Deterministic offline test and code review for this PR on Python 3.11/3.12/3.13; verify GitHub check conclusion on exact SHA. No network/API secrets.
2. `G1` Run exporter and auditor against synthetic one-host Autopilot ledger; force crash at each of four external effect windows; never mark ambiguous write as safe.
3. `G2` Signed/authenticated producer ingest, immutable audit outbox, version negotiation, low/high snapshot watermarks and restore tests.
4. `G3` Source audit of actual owner extension/Native Messaging host, minimal permissions, authentication and replay test. Blocked until local access recovers.
5. `G4` Thirty-worker fork contention, rate-limit stampede, multiple ACP sessions, provider/client cancellation, random clock skew and 24–72-hour synthetic soak, with exact metrics.
6. `G5` Independent verifier on exact Git SHA, privacy review, rollback/kill-switch exercise, operator signoff, then supervised canary. No production integration before `G5`.

Quantitative target *definitions*, not measured claims: `unknown_external_effect_auto_retries = 0`; `incorrect_success_certifications = 0`; `invalid_snapshot_false_greens = 0`; `lost_outbox_events_after_committed_task_transition = 0` under tested durability assumptions; `p99 queue/diagnosis latency` tracked with sample size and confidence interval. Fail if any of the first three occurs, regardless of throughput score. Track exporter gap rate and false-positive rate separately to prevent hiding data loss.

## 10. Strict proposal ranking and tradeoff record

The scores below are **provisional engineering triage**, not benchmark results. Five criteria rated 1–5: impact 30%, safety 25%, auditability 20%, feasibility 15%, operating-cost efficiency 10%. Score `=20×(0.30 I+0.25 S+0.20 A+0.15 F+0.10 C)`. Catastrophic approval/effect-safety violations override the numeric average; highest score does not authorize deployment.

| Candidate | I/S/A/F/C | Score /100 | Decision and falsifying test |
|---|---|---:|---|
| Strict offline causal audit | 5/5/5/5/5 | 100 | IMPLEMENTED isolated; challenge on malicious inputs and partial exports |
| Durable outbox + cursor/high-watermark | 5/5/5/4/4 | 95 | P0 design; crash-after-commit + duplicate relay |
| Authenticated event ingress and producer binding | 5/5/5/3/4 | 92 | P0; forged worker/fence/trace tests |
| Independent exact-revision verifier | 5/5/5/3/4 | 92 | P0; green SHA A vs changed SHA B |
| External effect reconcile-before-retry | 5/5/5/3/3 | 90 | P0; remote commit then lost acknowledgment |
| Global DAG budgets and rate-limit fairness | 5/5/4/3/3 | 86 | P1; 30-agent 429 stampede |
| Read-only MV3 status extension | 4/4/3/3/4 | 73 | P2; worker termination, host rejoin, origin abuse |
| Autonomous self-fix with independent checks | 5/2/3/2/2 | 62 | DEFER; approval circumvention and false successes |
| Immediate multi-host distributed engine | 3/3/4/1/1 | 54 | DEFER until actual one-host limits measured |
| DOM scraping as primary worker/queue API | 2/1/1/2/1 | 29 | REJECT; incomplete/non-authoritative state and brittle auth |

**Sensitivity:** feasibility/operational weights reward the lightweight offline tool; it is only a *phase 0 artifact*. If owner priority shifts to multi-host 24×7 operations, rerate after load/maintenance benchmarks, not by preference alone. The score for an idea is separate from completeness of its implementation; offline tests do not make production system 100/100.

## 11. Decision register / coordination rules for dozens of agents

- `DEC-CA-01 ACCEPT`: this PR owns **only** metadata auditing, its own tests, documentation, and CI workflow. It does not modify gateway `api_server.py`, Autopilot ledger, ACP permission callbacks or other open PRs.
- `DEC-CA-02 ACCEPT`: no trusted advancement from an offline event; `trust_level` is an observed label only.
- `DEC-CA-03 ACCEPT`: no speculative success when source sequence, causal parent or current revision evidence is missing.
- `DEC-CA-04 ACCEPT`: ambiguous external effects remain unresolved even after unverified `reconciled` claims.
- `DEC-CA-05 ACCEPT`: changes from other agents must be merged through PR review; avoid changing a shared SDD branch while independently rewriting its code.
- `DEC-CA-06 OPEN`: reconcile this observation schema with PR #1's ledger once single-source-of-truth architecture is chosen; schema adaptation may be required.
- `DEC-CA-07 OPEN`: discover running extension and host source when Local_WorkSpace recovers; no assertion of currently installed extension capabilities.
- `DEC-CA-08 OPEN`: define authenticated export snapshot boundary, retention, tamper-evident checkpoint, redaction policy and exact ingress authorization before any live data is fed into the auditor.
- `DEC-CA-09 OPEN`: upstream Hermes Kanban parity and fork migration; do not activate a second task scheduler.

Parallel workers must reserve unique file ownership, document expected base/head SHA, and produce one reviewable PR per invariant group. Every agent change log records `reason/observation/hypothesis/evidence/patch/test SHA/CI/rollback/unknowns`. CI/check status must be read fresh immediately before merge. Nobody should claim "monitored continuously" from a completed ChatGPT turn.

## 12. Primary technical sources reviewed

- W3C Trace Context / security and privacy: https://www.w3.org/TR/trace-context/
- OpenTelemetry GenAI spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
- Chrome MV3 service-worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome Native Messaging and sender validation: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chromium native host threat caveat: https://chromium.googlesource.com/chromium/src/+/main/extensions/docs/security_faq.md
- OpenAI Agents SDK sensitive-data tracing: https://openai.github.io/openai-agents-python/tracing/
- GitHub webhook delivery/redelivery: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- SQLite WAL and writer contention: https://www.sqlite.org/wal.html
- RFC 9457 for future machine-readable HTTP problem types: https://www.rfc-editor.org/rfc/rfc9457.html
- OWASP browser extension security: https://cheatsheetseries.owasp.org/cheatsheets/Browser_Extension_Vulnerabilities_Cheat_Sheet.html

The sources establish engineering constraints, not a claim that the owner-specific extension or production system has been inspected. Research quality is prioritized over source count.

## 13. Source-backed convergence decision: 25 parallel GPT PRs (second audit)

**New observation, 2026-11-22:** a fresh owner-connected GitHub query returned **25 open PRs** in this fork. This is a moving snapshot, not a persistent guarantee; all exact heads/check runs must be refreshed at merge time. This is itself a multi-agent failure mode: independently correct components can collectively create incompatible protocol authorities and an intractable merge graph. A GitHub PR's successful source build does not prove that *the combination of 25 PRs* is correct.

### A. Same responsibilities, multiple candidates

| Responsibility | Concurrent candidates confirmed by GitHub file lists | Integrator decision | Failure if all are installed |
|---|---|---|---|
| OpenAI-compatible `/v1/chat/completions` and `/v1/responses` | #4, #5, #6 each edit `gateway/platforms/api_server.py`; #11 is stacked on #4 | **ONE** baseline implementation after upstream parity review; transplant non-overlapping tests/fixes, do not merge all three | conflicting 409/422/503 semantics, inconsistent replay and false SSE success |
| Native `/v1/runs` status/event observation | modern NousResearch upstream, #4 `gateway/gpt_bridge_event_audit.py` (SSE), #5 `scripts/hermes_gpt_run_observer.py` (poller) | Use upstream run lifecycle as truth; choose at most one active status-ingress adapter, treating SSE interpretation as pure diagnostics | two consumers can disagree or lose event segments; no durable proof merely from SSE reconnect |
| Durable task/agent scheduling | upstream Kanban and Runs; #1 Autopilot ledger | upstream lifecycle authority FIRST; integrate only *non-duplicating* effect/evidence invariants from #1 | two task queues claim the same work and independently schedule retries |
| Metadata-only forensic event auditing | #9 `gpt_bridge`, #12 (+ stacked #23) `gpt_companion`, #16 `gateway/gpt_bridge_observer`, #21 `gateway/gpt_causal_observer`, this PR #25 `hermes_observer` | nominate ONE production journal schema and adapter; treat **this PR as an offline test oracle** unless expressly selected as part of the canonical contract | divergent source sequences, duplicate DB writes, contradictory stop diagnoses and hidden unknown outcomes |
| Cross-PR collision/merge guard | #14, #18, #22 and #24 | choose ONE maintained integration guard; **never auto-merge** | competing stale inventories certify incompatible branches |
| ACP approval routing | #3 | separate permission owner; complete end-to-end cross-session tests before enabling unattended effects | wrong-session permission forwarded to another agent |

**Technical incompatibility to block before integration:** the existing `/v1/runs/{id}/events` transport uses native run event names (`run.completed`, `tool.started`, etc.), an opaque `run_id`, and run-local event sequence. This PR's conceptual v1 NDJSON contract requires UUID `event_id`, boot-scoped `producer_id`/sequence, ISO timestamp and tool-effect reservations. They are **not the same protocol**. Never feed native SSE directly into `hermes_observer.audit` or fabricate a provenance claim by renaming fields. A reviewed, separately authenticated translator must preserve native `(run_id, seq, cursor, source_revision)`, replay truncation, and an explicit `derived_from_native_stream` provenance record in a *new versioned* envelope; the current allowlist does not admit that envelope. A transport loss must remain an observation gap.

### B. Native-upstream architecture decision, not another bespoke control plane

The official NousResearch Hermes documentation describes a native Runs API, Kanban task history/worker lanes, and replay/terminal semantics. The April fork's `main` does not represent a safe assumption about the owner's live installation. **Proposed target** for a deployed extension, subject to actual host capability discovery: native Hermes `GET /v1/capabilities` → explicit authorization to connect to the local endpoint → read-only `GET /v1/runs/{id}` / event stream with replay-gap detection → stable run/attempt identity → operator-only UI. Do not poll and subscribe concurrently without a single deduplicating ingest owner. Do not substitute a ChatGPT page/tab's presence for authoritative run status.

Some current docs describe bounded replay and terminal receipts, but exact deployment behavior and expiry rules MUST be measured on the installed version. In particular, `replay.truncated` or equivalent must invalidate continuous-timeline completeness. For long-running workers, progress != heartbeat: preserve `last_progress_at`, `last_heartbeat_at`, last tool boundary, and reason for waiting independently. Before any merge, verify whether endpoint `/v1/runs/{id}/events` is true broadcast or subscriber-specific, whether replay windows hold for the needed downtime, and whether status polling can safely repair a lost event interval. A code comment or 200 HTTP response does not prove coverage.

### C. Ranked choices with veto gates (updated after candidate discovery)

The 100/100 score for the isolated auditor in Section 10 is a **local prototype selection score**, not an argument for shipping a new runtime observer. Ranking for the **integrated system** changes after finding existing upstream capabilities. Updated decision order:

1. **P0 / ACCEPT as target**: native upstream Runs/Kanban + exact capability discovery. Veto deployment if installed version cannot prove supported endpoints or if task authority would split.
2. **P0 / ACCEPT**: one authenticated event ingress + one canonical durable outbox and replay cursor, with explicit source provenance. Veto if replay gaps are silently skipped.
3. **P0 / ACCEPT**: a single versioned incident/effect status contract, unknown-effect quarantine, exact-revision verifier; tool gateway owns enforcement. Veto if external writes can replay after timeout without independent reconciliation.
4. **P0 / ACCEPT**: select one merge-guard implementation and use a continuously refreshed, exact-SHA PR inventory. Veto integration if source branches or stacked parents have moved since evidence capture.
5. **P1 / KEEP OFFLINE**: this PR's zero-dependency causal audit as a negative-test oracle. Promote to production only after a versioned native translator, compatibility matrix, privacy/security review and real installed-host E2E tests.
6. **REJECT**: merging all observers/ledgers for extra redundancy. Multiple non-authoritative observers may aid investigations; multiple authoritative stores/retry engines are a correctness and security regression.

### D. PR integration protocol for dozens of agents

- Freeze a single **integration manifest** with `component_owner`, `base_sha`, `head_sha`, `source_contract_hash`, `api_contract_version`, `dependency_parent_shas`, `CI_run_url`, exact paths, and a permanent issue/decision reference. Agents may write isolated branches but must not claim a component they don't own.
- Refresh the entire PR inventory immediately before integration. A snapshot listing 11 candidates cannot establish safety if the repository has since reached 25. The integrator must recompute path overlap and *semantic* overlap, stacked-branch ancestry, status and exact-head tests.
- Choose one API base and one observer/ingress design; cherry-pick only independently reviewed, non-duplicating patches and tests. Validate cumulative branch on **one** exact head SHA rather than multiplying individual green checks.
- Classify mismatches as `CONTRACT_CONFLICT`, `STALE_DEPENDENCY`, `DUPLICATE_STATE_AUTHORITY`, `UNKNOWN_EFFECT`, `CI_SHA_MISMATCH`, or `RUNTIME_UNAVAILABLE`. Emit the source/claim/evidence/reconciliation action without guessing that the first observed timeout caused everything.
- New GPT extension requirements must have one capability manifest and security review: host identity, permission boundary, session correlation, optional user-approved operator actions, Windows/WSL path ownership and rollback. A different agent's summary is not proof that a browser extension has been installed.
- R0 read-only monitoring can fail open **only as a clearly labelled incomplete observation**; R1–R3 mutations must fail closed on lost required audit persistence, unclear identity/authorization, stale lease, uncertain effect or unknown target revision.

**Release blocker today:** no connected Local_WorkSpace/Windows host or trusted extension source; no authenticated native exporter; no production monitor running from this PR; multiple unresolved competing PR contracts. The right action is not to hide these under a synthetic score or silently merge them, but to preserve the exact blocker until a verifiable integration gate passes.

## 14. Browser/CDP/native-extension integration gate: real attachment ownership

**Source audit 2026-11-22:** draft PR #13 edits `tools/browser_tool.py` to redact CDP discovery/log fields and supplies `gpt_extension/cdp_diagnostics.py`. Draft PR #15 independently edits **the same browser tool** so that cleanup of externally attached CDP does not invoke CLI close/terminate and kill a browser shared by another task. Both cite the unavailable local Windows extension. Their changes must be reviewed together in a **single cumulative branch**; a passing isolated CI for either one cannot certify the combined cleanup/redaction behavior. PR #15 explicitly notes that residual CDP proxy daemon ownership is not resolved. Do not automatically apply either to the owner's active browser.

### 14.1 Three different ownership identities

| Boundary | Identity / lifetime | Correct behavior | Blocked or unsafe behavior |
|---|---|---|---|
| OS browser process | Browser owner PID + source `externally_attached` or `hermes_spawned`, not inferred solely from a websocket URL | Close/kill **only** a process created and exclusively owned by Hermes; external attach relinquishes its handle without killing the owner | Agent A cleanup terminates a shared Edge browser used by agent B |
| CDP target/session | Browser incarnation + target ID + attachment generation + provenance | Detach a specific attachment; invalidate stale handles on navigation/disconnect; preserve unrelated target/session | Browser close for task A tears down all targets or leaves a stale tab actor with write rights |
| Hermes task/action | Immutable task/attempt/fence + approved origin/target + effect digest | One active scoped writer to a given target; read-only observers may fan out | Two role-named workers click/type in the same tab, misattribute content or issue duplicate mutating actions |

Never equate a logical agent display name (`A1`) with a process incarnation. The offline auditor explicitly checks same-name different-producer fence collisions; the **runtime CDP adapter** must enforce target/process fencing at the interaction gateway before each write, not in the browser popup or diagnostic code.

### 14.2 Failure stories to reproduce on real browser only after controlled consent

1. **Shared externally owned Edge:** agents A and B attach to two targets of one manually launched Edge. End A, let its idle cleanup and `atexit` run, observe B and OS process still alive; verify no `close`/SIGTERM was sent to external owner. An independently Hermes-created browser remains safely terminable.
2. **Same tab with two agents:** two workers both acquire a logically identical role label. The second action must not gain write rights without a distinct current target fence. Navigate the tab between check and click; stale action must be rejected.
3. **Stale navigation/permission:** target origin changes after approval, or an interstitial/SSO page appears. Previous approval is bound to the prior exact action+origin+target; automatic retry is prohibited, with reason `TARGET_REVISION_CHANGED` or an explicit schema-mapped equivalent.
4. **MV3 suspend / native-host disconnect:** extension state disappears mid-run while the native Hermes run continues. On reconnect, resume only the read-only cursor and compare authoritative run status; no duplicate job dispatch and no inference that the worker died.
5. **CDP endpoint diagnostics leak:** websocket/debug endpoint includes a token or private URL in an exception. Logs and SDD exports must contain only connection state and opaque identifiers; no endpoint, full URL, cookies, session ticket, or unsanitized stack text.
6. **Observer fan-out overload:** 30 extension panels subscribe to one run. A single bounded, authenticated ingest owner polls/streams once and fans out snapshots with a watermark; temporary 429/backpressure becomes `incomplete_observation`, not 30 synchronized retries.

### 14.3 Recommended extension presentation (design only)

The companion status panel should show `task/run/attempt`, actual connected `gateway_version + capability_digest`, the authoritative state and age of that observation, a *separate* progress/heartbeat indicator, last acknowledged causal event and coverage watermark, external effect state (`none/known/unknown`), bounded competing stop hypotheses with evidence level, current Git SHA + CI SHA, and clearly non-authoritative diagnostic findings. Its default control surface is **read only**. Operator-approved recovery actions must go to separately authenticated host endpoints with target/fence/action digest binding; no arbitrary command relay through a content script.

**Kill-switch hierarchy:** operator stops UI observation → native host cancels the observer subscription only → Hermes run remains untouched unless separately authorized to stop the run. Stopping a task is not permission to terminate a shared browser. A hidden automated CDP control loop is not an acceptable substitute for a stable documented API.

### 14.4 Integration block conditions

- Actual extension source/manifest/host version remains unavailable; `web-chatgpt-high-cdp` named in prior agent evidence is not verified installed or compatible here.
- #13 and #15 overlap on one hot-path file; need common-base review, current branch SHAs, cumulative CI, Windows/Edge E2E, external-attach cleanup, origin/target refencing and redaction tests.
- No privileged browser action may be enabled by a static skill document or a browser-origin claim; transport identity, owner authorization, task lease and action-effect receipt are independent trust checks.
- If actual browser targets cannot be safely and stably addressed, only display operator-visible run status from the native Hermes API. `UNKNOWN` is better than a fabricated success or retry.

## 15. Cross-agent incident deduplication and operator-safe monitoring contracts

A concurrent specialist swarm will generate redundant *observations*, not necessarily independent problems. If 30 observers all see a `429`, a failed PR check or an externally owned CDP disconnect, incident creation must not multiply the issue into 30 independent repair campaigns.

### 15.1 Canonical problem identity versus observation identity

- **Incident fingerprint (DESIGN):** `SHA256(canonical(project_id, component_owner, invariant_id, stable_target_resource, root_cause_family))`. Derive only from authenticated, normalized metadata; keep the **investigation identity** stable when different agents report the same causal defect. This is deduplication, not proof the root cause is known.
- **Observation identity:** include independent reporter incarnation, observed SHA, task/attempt/fence, trace/span, source watermark, provider/version and evidence digest. Store separate observations; never discard conflicting explanations just because they have the same fingerprint.
- **Patch/review identity:** target branch+exact commit SHA; a new code revision starts a new verification epoch, even for the same incident. When a candidate merges, reconcile old and new hashes before marking anything resolved.
- **Escalation:** one accountable integration owner per component. Observer-only agents can attach evidence or propose non-mutating fixes; only the explicitly scoped owner may submit code to its lane; only an independent verifier may certify an acceptance gate.

An event's self-declared `trust_level="independent_verified"` is **untrusted metadata** until independently authenticated through the actual authoritative Hermes ledger and an approved verifier. Never trust a receipt-looking string or model-generated CI link to release unknown effects.

### 15.2 Practical high-density operator diagnosis

An incident view should render exactly these four separate sections: (1) **authoritative known state** with timestamp and source, or `unavailable`; (2) **most recent confirmed progression** and coverage/gap watermark; (3) **ranked hypotheses** with evidence vs counterevidence and `confirmed/probable/insufficient`; (4) **only permitted next actions**, including `reconcile_only`, `manual_required` and an explicit prohibition on replay of unknown external writes. Distinguish a provider's successful response from a verifier's acceptance of a task at a specific repository SHA.

The UX must expose which monitor is reporting, its last successful observation and any backward clock jumps. A terminated MV3 service worker, disconnected MCP or unavailable GitHub workflow is not the same as a failed Hermes agent. The global 'Stop observing' control must not alter the underlying run, close an externally owned browser, or revoke another agent's permissions.

### 15.3 Deterministic paging and retention

For each source, keep a producer-incarnation-aware sequence watermark, bounded replay window and explicit `PREFIX_NOT_CAPTURED` versus `INTERNAL_GAP`. Persist ingestion ACK only after durable write. On ingestion truncation, report `incomplete_observation` and a resumable cursor, never a pristine green status. A huge storm of low-severity gaps cannot suppress the highest-severity unknown-effect findings (this offline oracle now has severity-prioritized bounded output, but a production store must implement independent durability and metrics).

## 16. Exact-head CI evidence and release arbitration — checked 2026-11-22

The following are **GitHub Actions observations at these PR heads** (not evidence the owner's running Windows installation is healthy). A cached badge, review-service "success", old commit check or isolated package test does not certify the entire Hermes runtime. Compare actual workflow **conclusion** at **exact SHA**, not a PR's vague mergeability flag.

| PR / SHA prefix | Evidence checked | Honest outcome / action |
|---|---|---|
| #25 `c4227c7` | `Hermes GPT Causal Audit (offline)`, GitHub Actions run `45014925014`; Python 3.11/3.12/3.13 matrix | **3/3 SUCCESS**, independently executed 49 stdlib tests per matrix. Full `Tests` run `45014925022` **FAILURE**: 28 failed / 7550 passed / 171 skipped, including many missing OpenAI credentials, unrelated Codex and file-read timeout failures. Do not claim overall green. |
| #21 `d45194b` | `GPT Causal Observer Offline Contracts` Python 3.11/3.12 jobs | **FAILURE** import path `tests/gateway/test_gpt_causal_observer → gateway/__init__ → gateway.config → hermes_cli.config → yaml`; missing `yaml` defeats claimed dependency-free CI harness. The absence of the dependency does not prove its observer logic defective. A cross-agent review comment was submitted. |
| #5 `ba535dc` | Full `Tests` workflow | **FAILURE**, including missing OpenAI credentials, legacy error-message assertion and a brittle proxy test; see review. Separate source-level P0 risk remains: failure after a mutating effect may remove in-flight idempotency guard and allow replay, as reported by other reviewers. |
| #4 `f2373ed` | Full `Tests` workflow | **FAILURE**; several failures are credentials/environment/timeout problems. Do not infer the entire feature caused all of them. |
| #1 `7077c96` | `Autopilot Offline Contract`; full `Tests` | **Offline success**, broad suite failure. Ledger not activated. No API/extension integration success claim. |
| #3 `f04bd2c` | `ACP Scoped Approval Regression`; full `Tests` | **Scoped regression success**, broad suite failure. Requires same-session, cross-thread and installed-target E2E. |
| #8 `bc6bae3` | `Hermes GPT bridge offline contracts`; full `Tests` | **Offline success**, broad suite failure. |
| #15 `6aea9f2` | `External CDP Browser Ownership QA`; full `Tests` | **Scoped success**, broad suite failure; real Windows/Edge ownership still unverified. |

### 16.1 CI failure investigation protocol

1. Record exact `head_sha`, workflow run ID, matrix job ID, base SHA, test command, Python/OS versions, dependency lock/install mode, and the first error—not only the red badge.
2. Find the causal import/execution path. E.g. PR #21 is a dependency-isolation failure before its tests execute. Fix either the package import boundary or the CI provisioning claim, then rerun exact-head CI. No blind dependency installation should convert a claimed stdlib-only contract into an unrecorded environment requirement.
3. Distinguish failures reproduced on `main` under the **same** environment from PR-specific regressions. Missing OpenAI keys is not a justification to inject private credentials into unaudited PR CI. Design deterministic fakes; keep secret-using E2E as separate explicitly authorized jobs.
4. Review error-redaction vs old assertions as a **security contract change**. Never reintroduce public raw exceptions merely to make a legacy test green. Update expected behavior with trace correlation and negative privacy tests.
5. A test that verifies internal `urllib` object graph structure (e.g., expecting a retained `ProxyHandler({})` in `opener.handlers`) is not the same as a controlled proof credentials are withheld from hostile proxies. Verify externally observable security behavior.
6. Require that the **integration branch**, after selecting one implementation per lane, runs the full relevant suite and live controlled host fault-injection. Never equate 3 successful isolated CI matrix jobs with a production-ready extension.

### 16.2 Rollout decision following source review

**Keep PR #25 DRAFT and unmerged.** Offline audit is validated for its stated deterministic test contract at SHA `c4227c7`, but live native Hermes event translation, source authentication, trusted verifier, local Windows version discovery, extension manifest, CDP ownership, durable cross-worker ingress and system-level fault/soak testing are not verified. If the native upstream runs API differs in deployed installation, use capability discovery and mark `manual_required`, not silent fallback to an April fork handler. The observed full-suite CI failure is also unresolved for an end-to-end release gate.

Primary research for this release arbitration: Chrome MV3 lifecycle (`https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/`), Temporal activities and idempotency (`https://docs.temporal.io/activities`, `https://docs.temporal.io/activity-definition`), W3C trace propagation (`https://www.w3.org/TR/trace-context-1/`) and native Hermes API/kanban documentation in current upstream. Their existence is **not** evidence the user's installed Hermes contains matching versions or permissions.

## 17. Owner-specific GPT extension discovery contract — historical profile vs current evidence

**This section corrects a blind spot:** prior owner-provided configuration is not the same as the upstream Hermes fork's source tree. It must inform the *discovery path* without being misrepresented as a current tested installation. The current code in PR #25 still has no access to Windows extension files or live session logs.

### 17.1 Historical owner facts with explicit observation dates

| Item | Historical evidence (NOT live verified in this review) | What must be proven afresh |
|---|---|---|
| Windows project root | `C:\Users\Vadim\Tunnel` | Actual installed source/version and trust boundary for the Hermes GPT extension; do not assume the fork's `gateway/` is the browser extension |
| Candidate unpacked extension | `C:\Users\Vadim\Tunnel\chat-launch-smoke-desktop-test\web-extension` (owner's 2026-11-11 configuration) | `manifest.json` identity, installed extension ID, service worker/background scripts, declared origins/permissions, host bridge protocol and *current* file digests |
| Prior version | Extension `0.6.6` noted on 2026-11-11 | Current running extension's version, build provenance and compatibility with installed native host |
| Local browser bridge | Port `18763` expected, **not running in that earlier snapshot** | Whether any loopback bridge currently listens; connection/auth handshake, protocol version and lifecycle under suspension |
| Separate MCP tunnel | Observer endpoint `127.0.0.1:8765/mcp`, editor `8766`; profile `local-workspace` | Port/credential health and **actual allowed workspace roots**; do not conflate observer MCP with GPT browser/CDP transport |
| GPT CDP lane | Model/backend identifier `web-chatgpt-high-cdp` and successful prior canary tokens (2026-11-14) | Current authorization, owner consent, session/target provenance, broker version and whether that lane is used by this Hermes extension at all |

**Current scoped connector observation:** in this review a later `Local_WorkSpace.list_workspaces` returned only the `shelter` Obsidian project root with read/write scope; the separately configured read-only connector returned only `temp-folder`. Earlier calls to the same connector returned `Session terminated`. Thus **connector liveness has partially recovered**, but it does not authorize access to `C:\Users\Vadim\Tunnel` or enable inspection of the real extension. Do not expand scope, escape workspace restrictions or write the unrelated shelter vault as a workaround.

### 17.2 Minimum non-invasive Windows/extension discovery sequence (DESIGNED, not executed here)

1. Discover the **actual configured workspace permission** before reading paths. If `Tunnel` is not in the allowed roots, mark `SOURCE_SCOPE_UNAVAILABLE` and request separately scoped operator-approved read-only access *only when necessary*. Never infer permission from remembered paths.
2. If access is granted, inventory the candidate extension with bounded metadata: SHA-256 of `manifest.json`/package entrypoints, declared `permissions`, `host_permissions`, `background.service_worker`, `externally_connectable`, native host allowlisted extension IDs and `minimum_chrome_version`. **Never copy cookies/tokens or full user chat history into SDD.**
3. Probe loopback listener presence at port `18763`, but **do not** assume a TCP listener proves a valid authenticated bridge. The extension and host must negotiate `protocol_version`, `capability_digest`, installation/host identity and supported read-only actions; keep any existing WebSocket/CDP port owned by its actual process. A protocol mismatch is `INCOMPATIBLE_EXTENSION_CONTRACT`, not an agent timeout.
4. Validate `web-chatgpt-high-cdp` as a **separate, optional** provider lane. Do not merge it with an MV3 Extension Transport simply because both can display ChatGPT. Record observed transport/owner (`documented API`, `CDP`, `MV3/native messaging`, `manual`) for each task; controls must be scoped to the lane that actually executed it.
5. Reconstruct a single canary run using authorized, metadata-only events with exact `task_id / attempt_id / producer incarnation / effect state`; read authoritative native Hermes `/v1/capabilities` and `/v1/runs` where supported. Refuse to fabricate prior events from UI text.
6. Only after code/source parity: controlled non-mutating E2E cases for disconnected browser, suspended MV3 service worker, shared browser ownership, delayed CDP ACK, stale session, 429 backoff, process restart and provider timeout. Store outcome + process/extension/Git SHAs in the evidence log.

### 17.3 Stop reason decision matrix for the actual extension lane

| Symptom | Competing possible causes | Evidence required for causal diagnosis | Safe response |
|---|---|---|---|
| UI panel silent but native run alive | MV3 worker suspended; panel disconnected; native host idle | Native Hermes run status and extension lifecycle events at known versions | Reconnect **view** and cursor, no task restart |
| Browser bridge port absent | Native bridge not launched; crash; port changed; firewall policy | Local process/listener owner + versioned host config | `BRIDGE_UNAVAILABLE`; no blind CDP/DOM fallback |
| CDP session gone | Target navigated/closed; shared browser detached; external owner stopped process | Browser incarnation/target ID/provenance and last confirmed action ACK | Mark uncertain pending external effect if write was reserved; never kill/restart externally owned browser |
| Tool status stalls after click | Unknown click ACK; user interstitial; rate limit; approval gate | Effect reservation, target/origin digest, privileged receipt and approval trace | `EFFECT_OUTCOME_UNKNOWN` until read-back or explicit human resolution |
| 30 agents all fail together | Shared provider quota; shared browser/Gateway death; observer/discovery outage | Gateway-wide independent health and shared `Retry-After`, not only worker timestamps | Global cooldown and bounded fan-out for safe reads; effect-preserving halt for mutations |
| Agent completes text but no verified result | Incomplete CI, stale repository SHA, missing destination sync, model hallucination | Independent GitHub SHA/CI receipt and owner worktree hash | `verifying`/`blocked`, never `succeeded` on conversation text alone |

**Gate ownership:** Hermes authoritative run ledger controls state; verified tool/effect gateway enforces actions; the extension is an operator companion; this PR's parser remains offline. Each of these four components must have one named owner and independently tested interface. A working CDP canary from a week ago is not proof a deployed extension remains available today.

### 17.4 Escalating PR storm — new snapshot

A later owner-connected GitHub query returned **30 open PRs** (#1–#30) during the same review, compared with 25 earlier. Recent #26 and #30 add *further* causal observers, while #27/#28/#29 add further merge/ancestry guards. They are mostly **alternative designs**, not 5 new independent engines needed in one deployment. This is evidence of a coordination failure mode, not a verdict that every draft is defective. Do not race to build a sixth observer. The system integration owner should freeze/refresh the exact inventory at decision time, select one adapter contract, one controlled release gate and preserve all useful negative tests as reusable fixtures.

## 18. SOURCE-VERIFIED WebGPT topology: the companion is in `Podtverzhdeno/Tunnel`

**Correction from first-hand repository inspection (2026-11-22):** We located the public, connected GitHub repository `https://github.com/Podtverzhdeno/Tunnel`. It is the owner-published portable MCP/Web Companion source mirror. The separate `Podtverzhdeno/hermes-agent` fork's generic GPT API is **not** the whole extension. This is a source-level finding; it still does not prove which binary/extension revision is running on Windows right now.

### 18.1 Actual source map and state authorities

| Component | Source path / verified blob on Tunnel main | Authority / evidence limit |
|---|---|---|
| Legacy MV3 extension | `chat-launch-smoke-desktop-test/web-extension/manifest.json` SHA `609c794c17f8f7833de22b509205acbb2b1d9088`; version **0.6.6**; service worker `background.js`; host permissions loopback `127.0.0.1:18763` and `https://chatgpt.com/*` | Browser actuator and operator tab companion only; no authority to certify Hermes result from UI |
| Browser task controller | `.../web-extension/background.js` SHA `e6f2fa517c493759ca86a0557bacd3fa1a4046ae` | Session-scoped task storage; `finish`, watchdog, heartbeat, tab cleanup; must not infer durable effect from a missing content-script ACK |
| Content-script Send path | `.../web-extension/background_content.js` SHA `a611a8cbc771658aa5209d991e647e3dadfb7f29` | DOM observation; `button.click()` occurs **before** the `send_clicked` stage message (lines 110–111), so a crash can hide a possibly sent prompt |
| Local bridge | `.../web-companion/bridge.py` SHA `eaf301ac15ad301464159438d6431cbc91d3e323`; authenticated HTTP, port 18763 | Source of bridge queue/active/done records and limited event acknowledgments; no external independent proof of ChatGPT or Telegram delivery |
| Bridge telemetry | `bridge.py` `_event` lines around 392–454 | For each UUID, writes **last 60** `at/stage/reason` metadata events to `bridge-state/diagnostics/<id>.json` via temporary file + rename under process lock; entries have no guaranteed monotonic producer sequence or immutable globally ordered history |
| Relay observer | `Hermes-WebGPT/monitoring/queue_monitor.py` SHA `c22e457ec2e37f3a6fa9b8c411c7185c9bcddecd` | Read-only SQLite `requests(id,state,reason,created)` with explicit WAL visibility and baseline; cannot prove phase timing, report quality or final Telegram delivery |
| Local stack health | `scripts/status-stack.py` SHA `3ce6bdbe6a0117c924bb1705a91baf14306e7bc6` | Read-only MCP auth/bridge health/extension heartbeat + Chain2/3 preview; a fresh heartbeat only proves one operational signal, not loaded code/worker trust |
| Acceptance requirements | `docs/HERMES_FUNCTIONAL_SPEC_RU.md` SHA `d7dcb16f4dc5065404d43f8b6b83b1e03b3df15b` | Five saved URLs and automatic sessions, explicit per-session stop, no send replay, Telegram delivery, browser ownership, revision-specific E2E gates are **requirements**, not assumed implemented features |

**Version mismatch is architectural, not cosmetic.** The Tunnel README and `docs/PORTABLE_QA_20261111.md` distinguish (a) checked-in MV3 **0.6.6** source, (b) portable ZIP base **0.8.5**, and (c) archived **0.9.7** snapshot not auto-installed. The bridge `completion_client_ready()` at source line ~41 explicitly expects heartbeat version `0.6.6`; using a different packaged extension without its corresponding bridge could block report-gated task admission. This mismatch is a deterministic **compatibility hypothesis**; observe actual installed versions before changing the equality. Do not "fix" by accepting arbitrary client versions or lowering host/extension authentication requirements.

### 18.2 Five concrete, privacy-safe causality points

1. `RELAY_QUEUED/CLAIMED`: authoritative Relay SQLite request state and time, stamped with hashed stable request ID, independent claim/fence identity and bridge task UUID link established at dispatch; no raw prompt or bearer in snapshot.
2. `BROWSER_INTENT_RESERVED`: durable gateway/bridge-owned receipt with `(request, attempt, tab owner, origin, action digest)` and explicit uncertainty. The current content script's `button.click()` → `send_clicked` event ordering is **not** an atomic pre-send reservation and must never be represented as one.
3. `MESSAGE_SAVED_OBSERVED`: the browser confirms matching saved user message and expected conversation binding. DOM evidence is useful but never a trusted external write ACK. Network delay, account conflict, manual editor input and navigation remain distinct hypotheses.
4. `BRIDGE_RECEIPT_ACCEPTED`/`REPORT_ACKED`: exact bound bridge report/ACK and independent reviewer acceptance when applicable. A bridge acknowledgment is not proof of independently correct agent work; the existing `completion_mode=report` gates remain advisory until approved review verifies artifact/role/revision.
5. `HERMES_RECEIVED` / `TELEGRAM_DELIVERED`: distinct native Hermes/Telegram receipts, including destination chat/thread and provider send outcome; a successful web UI `assistant_confirmed` cannot infer either one.

Per-job bridge event arrays retain only 60 events. Therefore without a separately versioned append-only journal and producer sequence source, **do not** declare the first entry `seq=1`, invent parent events or claim full trace coverage from the rolling file. At 60 entries, status is at least `coverage_undetermined`, even if no visible gap exists. The offline oracle introduced by this PR cannot consume these legacy event arrays directly without a reviewed *lossy* translator that labels uncertainty. Avoid lying with fabricated causal UUIDs or timestamps.

### 18.3 Source-confirmed destructive tab action risk — distinct from last-tab guard

In `web-extension/background.js` main, `finish(job, status, url,...)` strictly calls `verifiedOwnedTab()` only for **completionMode** jobs. Its **noncompletion** branch considers a tab eligible for destruction if its current URL merely starts with `https://chatgpt.com/`, not if it is still the job's originally assigned conversation. After ~420 seconds, the watchdog may call `finish(task,"unknown")` with no verified saved URL. The operator can meanwhile navigate the same task-created tab ID to an unrelated personal ChatGPT conversation, and the finish path still sees an eligible origin. This is an **observed source predicate, not a confirmed real data-loss incident**.

Current draft Tunnel PRs #11 and #17 independently change browser lifespan/last-tab cleanup but retain a broad origin predicate for ordinary tasks; the #11 last-tab *park* behavior can still replace a navigated conversation with `about:blank`, and #17 may still remove it if there are siblings. A reviewer was sent a specific acceptance-gap comment on **Tunnel PR #17**, comment ID `7078269962`.

**Release-veto acceptance cases:** same job UUID/tab ID but navigated unrelated conversation → never close or blank; unknown outcome lacking bound URL → preserve tab; terminal report with exact verified URL → close only after owner/target checks; one vs two browser tabs; old content-script message after navigation; concurrent tabs; manually typed text. These must be independently tested on synthetic Chrome and controlled installed Windows browser. Merely checking the host origin and last-window count does not establish task ownership; for destructive actions, default to preserve+typed diagnostic when provenance is incomplete.

### 18.4 Existing agent work: do not fork competing components

Read the **actual** Tunnel concurrent PR graph before introducing another monitor:

- #13 provides a non-mutating Hermes-WebGPT incident triage + optional foreground sampler.
- #16 provides a **7-file MV3 source/mirror integrity gate** (34/34 targeted tests, source-pinned CI success reported at its exact head). It also separately flagged click-before-durable-intent; do not duplicate its scanner.
- #19 adds rollback-alert logic to the *existing* `queue_monitor.py`; do not independently patch that same file without selecting a merge owner.
- #11 and #17 both change extension browser lifecycle with overlapping semantics; select one cumulative reviewed patch.
- #5 changes Web Companion completion/receipt safety. Preserve its consent/report ACK and noReplay assumptions in any integration.

The correct first integration artifact is a **cross-repository contract map and version-pinned negative test matrix** tying existing Tunnel instrumentation to modern Hermes native run state. An extra invasive collector or autonomous UI loop is lower value and raises merge risk. Separate detection from authorized recovery; a brief offline diagnosis is valuable even if it is not the always-on production service requested.

## 19. Executable compatibility oracle for the **actual** Tunnel bridge metadata

Added `hermes_observer/tunnel_legacy.py` as a **pure, stateless, read-only** adapter for one saved `Podtverzhdeno/Tunnel` bridge v0.6.6 `diagnostics/<job>.json` source window. The adapter deliberately refuses to convert an old 60-element rolling array to fully sourced `event_id`/`source_event_seq` or claim successful Telegram delivery. It does not add a second control-plane observer, poll network/SQLite, mutate job state, parse prompts, or read any filesystem path. It is independently importable by a future **selected** authenticated gateway after policy review.

### 19.1 API and the deliberately negative guarantee

`from hermes_observer.tunnel_legacy import summarize_legacy_trace` accepts **bytes** of a single previously exported JSON array, using strict `<=32768`-byte cap, `<=60` records, mandatory exact `at` UTC + allowlisted `stage`, optional safe `reason`, duplicate key rejection, malformed/future-unverifiable shape refusal, time-regression suspicion. A large integer or very deeply nested JSON is a controlled `LegacyTraceError`, not a crash or a trace of the raw payload.

Returned metadata consists only of a declared 
`UNTRUSTED_OFFLINE_DIAGNOSTIC_ONLY` evidence class; opaque stage signals and type-coded hypotheses; `coverage_complete=false` for **all** arrays; `window_at_capacity` if 60 entries; immutable `external_effect_retry_allowed=false`, `mutation_allowed=false`, `final_delivery_verified=false`, `source_provenance_authenticated=false`. The last visible stage never becomes `verified outcome`. Source `button.click()` may occur even if `send_clicked` has not been persisted; an absent stage is not a negative proof.

This component is a **compatibility negative-test oracle**, intentionally NOT a client of the Hermes native `/v1/runs` SSE endpoint. There is no assertion that its input came from a trusted running extension or that a bridge/worker was alive. The adapter itself has no CLI/network access, so an installed runtime or independent monitor must supply and authenticate a *read-only* snapshot after verifying approved source path, exact version and snapshot boundary. Never hand it arbitrary private ChatGPT documents.

### 19.2 Integration interface and acceptance boundaries

- Attach an independent `source_reference={repository, commit, host_build, extension_worker_version, collection_scope, collection_time}` when a selected future ingest service reads bridge diagnostics. That wrapper, not this helper, owns file permissions, OS credentials and privacy retention; source-provided fields are not authenticated provenance.
- Preserve `window_at_capacity` vs event count but never infer missing count, first global sequence or no-replay clearance. Rolling array can omit older stages even when only 59 remain after an external reset/truncate.
- Compare separate Relay `queue_monitor.py` status and bridge `last_observed_stage_claim` only through authenticated exact job/attempt binding, not by timestamp proximity. Do not infer `Telegram-delivered` from `bridge receipt_accepted` or a DOM assistant message.
- If a current client emits a different schema/version, **reject** until an independently reviewed per-version adapter is chosen. Never silently accept arbitrary keys or widen the stage set to make a green dashboard.
- Require a future controlled E2E: pre-click crash, after-click lost stage, report ACK loss, extension crash at 60-event rollover, same `job_id` contested by stale producer, manual tab navigation, failed Telegram delivery and clock rollback. It must establish evidence provenance and observed no-replay under owner-approved host conditions; this branch contains no such live proof.

### 19.3 Tests and remaining trust gap

**Local regression:** 49 pre-existing causal event tests + 24 new legacy adapter negative/positive tests = **73/73 PASS** on Python 3.13.5; a separate fixed-seed 9,000-case malformed/mixed source-window fuzz found no unhandled exception or unsafe privilege output. Source test suite is deterministic with stdlib only. The newly discovered >4300-digit JSON integer `ValueError` was corrected and explicitly regressed, plus nested depth, duplicates, secret fields, invalid stages, non-UTC times, rollovers, clock regression, weak ACKs, and click-without-receipt.

**Exact-head validation (2026-11-22):** the 73-test adapter-and-core revision **`f206d22c770b38bdbf75b4b35b9893cd9e5d2878`** passed [GitHub Actions run `45016532004`](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45016532004), **3/3 success on Python 3.11, 3.12, 3.13**; job IDs 137189935850, 137189935593 and 137189935836. Earlier 49-test run `45014925014` passed only its own older SHA. Subsequent stop-explainability fixes in Section 20 change HEAD and **require their own fresh CI outcome**, do not borrow success from the prior head. None prove a live Windows source or browser behavior.


## 20. Red/green self-review of stop explainability and deterministic multi-agent evidence (2026-11-22)

**Observed bug E-STOP-01 (source and failing test):** originally the `audit_stream` stop classification required `reason_code` only for `task.blocked` and `worker.lease_expired`. `approval.denied` without `reason_code` returned `no_anomalies_in_supplied_slice` with exit 0. In operational terms the user would see a denied action with no explanation while audit reports no problem. A new negative test failed before the correction. **Fix:** every `STOP_KINDS` entry now requires a specific reason for explanation; no reason raises `STOP_WITHOUT_REASON_CODE`, literal `UNKNOWN` raises `STOP_REASON_UNKNOWN`, and the supplied event remains untrusted, never permission to retry. The `POLICY_DENIED` token and verifier receipts are NOT inferred.

**Observed bug E-STOP-02 (source and failing test):** `stop_observations` previously took the first 250 records in raw arrival order. Two 30-agent stream replays containing identical independent stop events but received in different orders generated different report ordering, and when capped could select a different subset. Both nondeterminism and truncation can produce false state changes in a cross-agent dashboard. A negative test comparing reordered events failed before the fix. **Fix:** sort the already-validated stop metadata deterministically by `(task_id, kind, event_id)`, then cap at 250, exposing suppression count independently. Sorting does not assert wall-clock order or external causation.

**Local red/green evidence:** initial two regressions failed in the original 73-test suite, showing both real source defects. Added tests for explicit `UNKNOWN` and 300-record capped/reversed replay; after fixes the current **77/77** standard-library tests pass locally on Python 3.13.5 (`python -m unittest discover -s tests/hermes_observer -q`). This is not a claim of Windows/Telegram/browser E2E or untrusted-event authenticity. On the next GitHub commit, 3.11/3.12/3.13 CI must be rechecked against the new exact HEAD.

**Acceptance for many agents:** diagnostic fingerprints and output examples must be deterministic for a given set of valid events even under out-of-order delivery. Missing reasons stay incomplete, including explicit `UNKNOWN`. Genuine reordering of conflicting duplicate IDs still yields a collision and requires source reconciliation; it is not coerced into an invented canonical event. At release, measure baseline jitter/false alerts from real trusted ingress, not only this synthetic replay.

**Persistent task discipline in SDD:** future agents doing Hermes GPT work must perform source discovery across BOTH `Podtverzhdeno/Tunnel` and `Podtverzhdeno/hermes-agent`, maintain a timestamped evidence log with hypothesis-versus-observation, prove red→green for fixes, collect independent CI at exact HEAD, avoid competing source-of-truth schedulers and fabricated cause codes, and report UNKNOWN where Windows/runtime visibility is missing. Do not conclude with a nominal `100/100` score or an untested 'all done'. This is a stored project rule for collaborators, **not** evidence of a continuously running assistant process.


## 21. Strict identity contract: denied approval/expired lease cannot disappear (2026-11-22)

**Root-cause review E-ID-01:** `parse_event` formerly mandated `task_id` only for kinds beginning with `task.` and `verifier.`. It allowed `approval.denied` and `worker.lease_expired` with absent/null task identity because these namespaces do not match that prefix. A later guard `if kind in STOP_KINDS and task_id` then omitted such events from `stop_observations`. An input containing only one such denied/expired event produced **`no_anomalies_in_supplied_slice` (exit 0)**, falsely implying no detected stop.

**Red/green:** added two regression cases, one denied approval and one expired worker lease with `task=None`, both initially failed with a green status. For this **task-scoped schema v1**, `parse_event` now requires a valid task UUID for every `STOP_KINDS` event. Such malformed events make `invalid_snapshot` (exit 4) and cannot be misclassified as healthy. A future real exporter of an unbound *global* worker failure must use a **separately versioned source event/contract**, not invent a task ID or silently drop the event. `reason_code=UNKNOWN` remains explicitly incomplete under E-STOP-01.

**Local result:** total **79/79** stdlib tests pass on Python 3.13.5 after adding the two identity regressions. The prior 77-test exact-head GitHub CI validates only that previous revision, not these new changes; re-check all three matrix jobs on the final published SHA. This exact source fix neither sends ChatGPT messages nor changes installed browser/gateway/Relay code.
