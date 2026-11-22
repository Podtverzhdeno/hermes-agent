# Hermes GPT event observability: source-based convergence matrix

**Date:** 2026-11-22. **Evidence:** GitHub connected fork PR heads; this is a snapshot, not continuous supervision. **Status:** COMPARISON ONLY. No merge/deploy approval. All feature classifications below are from inspected source/module boundaries, not independently measured production performance.

## Why convergence is urgent

During one audit the open PR count grew from 7 to 26, while new agents independently implemented multiple diagnostic event protocols and three separate API gateway patch trains. File-path conflict detection alone cannot catch semantic collisions when implementations live under different Python package names. The upstream Hermes Kanban task/worker lifecycle already exists; it must be the task state authority when upgraded. A second dispatcher or competing source of truth would make even excellent logs ambiguous.

## Seven diagnostic implementations observed (distinct code, not seven independent release candidates)

| PR | Primary module | Memory or SQLite | Source-observed useful capability | Integration limitation |
|---|---|---|---|---|
| #8 | `hermes_gpt_bridge/diagnostics.py` | Offline JSONL, no DB | Reason classification and offline run snapshots | Different event input and no integrated durable source cursor |
| #9 | `gpt_bridge/observability.py` | SQLite WAL | Append-only observation store and hash-linked metadata | Yet another event contract; no authenticated runtime producer adapter |
| #12 | `gpt_companion/journal.py` | SQLite WAL | Durable untrusted event inbox, unique sequence, hash chain | Another source/attempt vocabulary; persisted observation is not authoritative task state |
| #16 | `gateway/gpt_bridge_observer.py` | Bounded memory | Strict v1 event allowlist, per-incarnation causal gaps, replay-collision SHA, no writes | Not persistent, no source authentication, no effect verification |
| #21 | `gateway/gpt_causal_observer.py` | SQLite | Causal diagnostics and bounded event acceptance | Independent observer protocol still needs schema reconciliation |
| #25 | `hermes_observer/audit.py` | Offline stream | Strict JSONL parser and output finding classification | No running collector/producer authorization in this module |
| #26 | `gateway/gpt_bridge_event_audit.py` | Offline stream | Proposed event-envelope auditor and bounded report output | Not a canonical storage/dispatch system; scheme may differ |

Additional branches #17/#23 patch the #12 journal; #14/#18/#22/#24/#26/#27 independently propose merge/integration collision gates. These are separate overlapping capabilities even where changed filenames do not intersect. A purely "changed-files intersection" gate will miss competing observers and scripts.

### Decision: do not simply select the largest module

No fair production score exists yet because benchmark conditions, schemas, auth boundary and acceptance tests differ. A provisional selection process should run **one shared conformance corpus** against all candidates; score with objective requirements before design preferences.

**Mandatory criteria (gate, not weighted away):**
- exactly one canonical task/run owner (upstream Kanban);
- documented producer authentication and per-incarnation sequencing;
- metadata-only allowlisted ingestion; Unicode/duplicate JSON/oversize/invalid schema fail closed;
- event_id + canonical payload integrity collision detection, not id-only duplicate handling;
- explicit evidence gaps and partial causal order; missing signal alone never equals worker death;
- independently reconciled unknown external effects and persistent reservation before tool write;
- durable outbox/cursor for hosted collector; worker/browser restart replay safe;
- no privilege expansion by event payload or LLM explanation;
- cold-start recovery, 30–100 worker contention and exact SHA CI acceptance.

**Weighted post-gate criteria (candidate scoring only once testable):** 30% root-cause fidelity, 25% integration safety, 15% restart/resume behavior, 15% 30-agent throughput, 10% maintenance/complexity, 5% ergonomics. Supply denominators and confidence bounds from the same injected-fault corpus. Penalize code duplication and migration cost, not merely test count.

### Integration topology recommended

- Rebase and test official Kanban lifecycle from a pinned upstream release/commit. Freeze fork compatibility matrix before migration.
- Assign one maintainer to event-schema v1 and adapters from old modules; do not create seven equally valid schemas.
- Select **one** append-only diagnostic store behind that interface, or derive projection directly from Kanban event-outbox if sufficient. It must not govern task outcomes.
- Retain at most one read-only offline diagnostic CLI as an operator aid; convert alternate PRs to regression cases, fault-injection samples or focused component patches.
- Independently retain one consented browser status companion after verifying the actual extension manifest/host. A browser tab is not a worker protocol or a task truth source.
- Gate external actions on authenticated tool gateway and Kanban task epoch; unknown-effect reconciliation precedes retries.
- Preserve logs and migration evidence at exact branch SHA; one integrator signs the final merge train after CI and Windows E2E.

### Failure-source distinction to make atomic stop diagnosis useful

| Reported stop | Authoritative evidence | UI-level misleading symptom | Safe next step |
|---|---|---|---|
| Cannot spawn | `skipped_nonspawnable` Kanban dispatch | Agent did not answer | Fix assignee/policy; don't auto-reassign |
| Clean exit without board completion | `protocol_violation` task event | Text answer appears completed | Existing bounded Kanban retry then block |
| Provider overloaded | Exit 75 plus provider Retry-After | Worker seems silent | Shared quota backoff, not N independent retries |
| Invalid credential/model | Exit 78/terminal_provider | Infinite thinking/reconnecting | Block until authorized fix |
| Lost browser/native transport | Adapter disconnect + cursor | ChatGPT page gone | Reconnect observer and replay; do not retry tool |
| Tool wrote then reply lost | Effect reserved, no receipt | Request timed out | Reconcile receipt before any write repeat |
| Session continuation DB read failed | Explicit session ID + storage exception | Model behaves forgetfully | Fail request closed; maintain context identity |
| Separate agent's commit changed base | Expected SHA CAS conflict | CI was green earlier | Verify exact new SHA and rebase in owner worktree |

## Evidence limitations and next gates

The user's local Windows extension, browser logs, Native Messaging registry and Obsidian are NOT accessible through currently failing workspace connectors. No private GPT deliberation or actual worker stop can be inferred from GitHub PR creation. GitHub code snapshots and an isolated Python test run do not establish live monitoring, stable multi-agent operation, or production readiness.

**Primary grounding:** official Hermes Kanban worker-lanes docs; Github PR file listings #8/#9/#12/#16/#21/#25/#26; Chrome MV3 service worker and Native Messaging docs; OpenTelemetry GenAI default privacy policy; SQLite WAL constraints. This matrix is one more *convergence decision record*, not a competing task scheduler.
