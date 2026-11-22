# Integration & ownership matrix — 10 concurrent Hermes PRs (2026-11-22)

**Scope:** the open PR inventory and changed-file lists retrieved on 2026-11-22 via the connected GitHub API. **Live snapshot:** branches are moving; re-fetch before any merge. This document coordinates proposals; it does not merge, approve, or grant privileges. Canonical owner requirements: `docs/autopilot/OWNER_ACCEPTANCE_CONTRACT.md`.

## Current dependency graph

```text
 Upstream Hermes v0.23.3 (modern Kanban, in isolated canary only)
                 |
      single canonical lifecycle owner
                 |
     typed worker + gateway + verified effect API
       /       |        |           \
  PR3 ACP    PR2 skills  GPT bridge  typed event observer
                        /   |   \      /    |    \
                     PR4  PR5  PR6   PR8  PR9  PR7 docs
                       MUTUALLY OVERLAPPING IMPLEMENTATIONS
                                |
                      independent test and review gate

 Legacy fork main (April 2026)
          |
   PR1 Autopilot experimental kernel
          |
   PR10 prototype read-only diagnostics & safety corrections
   (NOT a separate production Kanban scheduler)
```

## PR-by-PR routing

| PR | Owner scope/actual files | Collision | Integration direction |
|---|---|---|---|
| [#1](https://github.com/Podtverzhdeno/hermes-agent/pull/1) | `autopilot/ledger.py`, `autopilot/policy.py`, tests, ADR, offline CI | #10 dependent | Keep as isolated kernel test suite, do not deploy second scheduler |
| [#2](https://github.com/Podtverzhdeno/hermes-agent/pull/2) | Skill harness validation, manager/tools, skill docs and tests | mostly independent | Review path isolation, symlinks, manifest trust, owner files; independent compatibility testing |
| [#3](https://github.com/Podtverzhdeno/hermes-agent/pull/3) | ACP terminal permissions, approval and session isolation | adjacent to GPT gateway policies | Security review; ensure effective permissions cannot widen across sessions |
| [#4](https://github.com/Podtverzhdeno/hermes-agent/pull/4) | `gateway/platforms/api_server.py`, `gateway/gpt_bridge_diagnostics.py` | **direct** #5 and #6 | Strong candidate for explicit unknown-outcome tombstone, caller-scoped key, redacted events; process-local only |
| [#5](https://github.com/Podtverzhdeno/hermes-agent/pull/5) | `gateway/platforms/api_server.py`, `gateway/idempotency.py` | **direct** #4 and #6 | Strong single-flight coalescing and bounded concurrency; exception retry is unsafe for unknown external effects without durable gate |
| [#6](https://github.com/Podtverzhdeno/hermes-agent/pull/6) | `gateway/platforms/api_server.py`, API gateway test suite | **direct** #4 and #5 | Strong request-ID, header and auth hardening, SSE failure signaling; process-local failed-task eviction needs guarded reconciliation |
| [#7](https://github.com/Podtverzhdeno/hermes-agent/pull/7) | Documentation-only GPT bridge SDD/log | conceptual #8/#9/#10 | Reconcile definitions and link one canonical entrypoint rather than duplicate incompatible state taxonomies |
| [#8](https://github.com/Podtverzhdeno/hermes-agent/pull/8) | JSONL strict event schema + offline diagnostic analyzer | event schema #9 and #10 | Useful offline trace replay and hypothesis/explanation; make event-schema compatibility contract |
| [#9](https://github.com/Podtverzhdeno/hermes-agent/pull/9) | SQLite append-only hash-chain event store + CLI + SDD | event schema #8 and #10 | Useful ordered ingestion and tamper-evidence for accidental corruption; hash chain without external anchoring is **not attacker-proof** |
| [#10](https://github.com/Podtverzhdeno/hermes-agent/pull/10) | Autopilot SQLite read-only observer + safety fixes, SDD/audit | stacked on #1; different task DB than modern Kanban | Keep prototype observer isolated; adopt Kanban only through a separate approved adapter |

**Conflict summary:** #4/#5/#6 all edit `gateway/platforms/api_server.py`, with overlapping idempotency and SSE control paths. None is currently approved as the sole implementation. #7/#8/#9/#10 define overlapping events and terminology but their actual implementations have separate module paths. “Git can merge these files” is not equivalent to semantic correctness.

## Critical semantic comparisons of GPT bridge proposals

These are source-level judgments only; not measured performance or proven failure rates.

| Case | PR #4 | PR #5 | PR #6 | Required unified behavior |
|---|---|---|---|---|
| Same key concurrently | Reject 409 while active | Join one shielded async task | Join one shielded async task | Choose explicit API policy; never run twice |
| Same key, changed payload | 422 conflict | Rejected via fingerprint conflict | Rejected via fingerprint conflict | One documented status code and stable safe message |
| Same key after success | Cache full session/result | Cache result | Cache full response | Replay same logical response/receipt |
| Exception after unknown external effect | Keep **in-memory** unknown tombstone | Failed task removed (retry possible) | Failed task removed (retry possible) | Durable unknown effect + no blind replay, independently reconcile |
| Gateway process restarts | Tombstone lost | Cache lost | Cache lost | Persist cross-process effect contract and provider receipt |
| Multi-process workers | Not authoritative | Not authoritative | Not authoritative | Kanban claim/fence + authoritative tool-effect service |
| Streaming | Failure SSE events and logging | Must be tested separately | Explicit guard against Idempotency-Key on stream; failure SSE | No fabricated `finish_reason=stop` after backend error; explain stream retry semantics |
| Security/trace | Caller/session key digest; no raw error | Canonical request fingerprint | Request ID, constant-time bearer comparison, CORS guard | Structured redacted metadata, no secrets, origin/auth fixed |

**Important hazard:** A model/agent error may be raised *after* a mutating tool call succeeded. The mere presence of an exception, cancellation or transport disconnect does not prove `not_executed`. Caches that evict such outcomes permit duplicate writes on retry. A process-local tombstone is a useful defense-in-depth but expires and does not provide exactly-once across restarts. We recommend **durable effect reservation+reconciliation at trusted gateway**; model-only requests with no effects may use bounded safe retry. Prefer an intentionally narrow unified implementation over concatenating three cache classes.

## Strict selection rubric

Weighted review for a proposed **unified** gateway design (five-point ordinal score per dimension, evidence required):
- Safety against duplicate/unknown external writes **30%**;
- causal diagnostics and reproducible failure reason **20%**;
- API compatibility including SSE/session/auth **15%**;
- concurrency and durable recovery **20%**;
- change scope, testability, rollback simplicity **15%**.

**Hard disqualifiers, regardless of weighted sum:** blind rerun after unknown external effect, replay on mismatched fingerprint, unredacted credentials/errors, unbound approval, false SSE success, no stop propagation, silent cross-process idempotency claim. Until an acceptance fixture passes, do not declare any candidate a “winner” or rank it 10/10.

Candidate composition strategy (not cherry-pick approval):
1. Shared canonical fingerprint, strict idempotency key validation, endpoint+caller+session scope;
2. One bounded in-process single-flight cache with explicit `IN_PROGRESS`, `RESULT`, `UNKNOWN` states and documented join-versus-409 policy;
3. One durable effect journal tied to canonical Kanban task/run identity with external receipts;
4. One reason-coded event envelope, mapped from each bridge/ACP/worker source;
5. Explicit SSE `error` transport semantics, durable server-side continuation policy and cancellation reconciliation;
6. Independent tests that prove response identity stable, no duplicate gateway action, no false success and no accidental leak, including forced process restart;
7. Migration policy, rollback and error/approval usability check.

## Release/merge order and locks

- **Before any edits:** assign owner per file/path, record expected base SHA and task scope. An active conflicting PR requires coordination, not parallel hidden overwrites.
- **Gate 0:** obtain a full current PR inventory, exact commit heads, check results, and independent source audit; install modern Hermes upstream in isolated canary.
- **Gate 1:** land isolated security invariants and offline tests, including PR #1 + #10 stack, only after exact-head CI green.
- **Gate 2:** select one GPT API-server implementation as integration base; carry compatible benefits from other proposals through reviewed cherry-picks/patches, not three manual merges on blind faith.
- **Gate 3:** unify event envelope and source identities. A collector validates producer identity; offline analyzers are read-only and cannot authorize writes.
- **Gate 4:** connect Kanban worker lanes and scoped GPT adapter to a trusted gateway, then inject failures with 10/25/50 worker profiles.
- **Gate 5:** run Windows/WSL prompt-delivery and cancellation tests, exact-SHA CI, local Obsidian write/read-back, approval expiration and recovery drills; maintain user-local rollback.
- **Gate 6:** consider supervised read-only monitoring only after tested host service lifecycle; no dashboard can claim live state from a static ledger file.

## Multi-agent “atomic understanding” acceptance

Each logical task must have a causal chain with immutable `task_id -> attempt_id -> worker/fence -> dispatch_intent -> prompt_delivered -> model_response -> tool_effect_reserved -> external_receipt -> verification -> terminal`. At each transition persist a specific reason for stop or uncertainty; **absence of heartbeat is a symptom, not a verified cause**. Worker/harness self-assessment is untrusted until independently checked.

For 30 agents, require owner/worker assignment per task, per-project budgets, per-resource write locks, fair scheduling, retries bounded by shared DAG budgets, independent review, exact revision evidence, and an explicit effect-reconciliation queue. A0 can advise but may not blindly self-approve. A standalone browser tab should never become a second untracked task authority.

## Current observed CI

PR #10 initial head `55e0ef8062dbe4ffb1b0595d92de88ad29cc7451` triggered Autopilot Offline Contract workflow `45013359159`. Syntax step succeeded; Python 3.12 produced **72 passed, 2 failed**, at tests `test_attempts_are_bounded_and_eventually_fail` and `test_unknown_effect_must_be_reconciled_before_retry`. Root causes were mismatched fake lease length assumption and wrong expected exception type; corrected on branch commit `1bdfd1b22f77ec6691df3722e45eac211999d758`. This records the observed failure, not a passing rerun. Supply Chain Audit `45013359190` succeeded on original head only.

**Recheck all statements on latest SHA before reporting successful verification.**
