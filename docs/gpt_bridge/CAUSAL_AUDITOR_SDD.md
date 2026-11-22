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

**Implemented offline test groups:** exact duplicate vs collision; sequence gaps and 30-producer independence; out-of-order clocks, missing parents and causal cycles; malformed/deeply nested/duplicate-key JSON and null required occurrence timestamp; payload-field rejection and size limits; reserved/acked/unknown/reconciled effects; receipt and causal-link validation; cross-fence replay; misleading success with stale verifier; two claimants on same fence; stop reason observations; capped exports, empty snapshots, conflicting terminal states scoped to attempt identity.

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
