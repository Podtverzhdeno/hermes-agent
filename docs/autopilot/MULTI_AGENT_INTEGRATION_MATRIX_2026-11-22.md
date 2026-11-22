# Integration & ownership matrix — 27 concurrent Hermes PRs (2026-11-22)

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

## Second live inventory — 27 draft PRs and new high-risk overlaps

**Observed through the connected GitHub API:** the open PR count grew from **10 to 27** during this same engineering pass. Counts/heads are a snapshot; not a durable lock. The original #1–#10 table above is retained as the baseline for audit continuity. Exact changed-path lists for #11–#27 were inspected separately, not inferred from PR titles.

| New PRs | Scope by changed paths | Immediate integration disposition |
|---|---|---|
| [#11](https://github.com/Podtverzhdeno/hermes-agent/pull/11) | `gateway/platforms/api_server.py`, request preflight and keyed SSE tests | **Direct collision** with #4/#5/#6; include preflight in one selected API implementation |
| [#12](https://github.com/Podtverzhdeno/hermes-agent/pull/12) | `gpt_companion/journal.py`, observer/watch, docs, tests, `pyproject.toml` | Proposed baseline for Companion journal only after independent tests |
| [#13](https://github.com/Podtverzhdeno/hermes-agent/pull/13) | `tools/browser_tool.py`, CDP/log redaction, standalone diagnostics, `pyproject.toml` | **Direct collision** with #15; preserve both browser process-ownership and redaction |
| [#14](https://github.com/Podtverzhdeno/hermes-agent/pull/14) | integration audit script, CI and docs | Competes semantically with #18/#22/#24/#26/#27; choose **one** canonical collision check |
| [#15](https://github.com/Podtverzhdeno/hermes-agent/pull/15) | `tools/browser_tool.py`, browser ownership lifecycle, CI | **High priority physical resource ownership:** do not kill externally owned Edge/Chrome on CDP cleanup; merge with #13 only after cross-tests |
| [#16](https://github.com/Podtverzhdeno/hermes-agent/pull/16) | `gateway/gpt_bridge_observer.py`, watcher, docs/tests | Read-only observation candidate; verify purpose relative to #9/#12/#21/#25 |
| [#17](https://github.com/Podtverzhdeno/hermes-agent/pull/17) | `gpt_companion/journal.py`, `docs/sdd/GPT_COMPANION_SDD.md`, tests | **Direct collision** with #12 and #23, competing old-attempt reconciliation logic |
| [#18](https://github.com/Podtverzhdeno/hermes-agent/pull/18) | integration guard script, tests and docs | Competing canonical PR collision guard |
| [#19](https://github.com/Podtverzhdeno/hermes-agent/pull/19) | observer forensic SDD and log only | Documentation comparison, no direct source collision |
| [#20](https://github.com/Podtverzhdeno/hermes-agent/pull/20) | SDD convergence entrypoint and upstream parity docs | Candidate for navigation, not execution authority |
| [#21](https://github.com/Podtverzhdeno/hermes-agent/pull/21) | `gateway/gpt_causal_observer.py`, CI and tests | Independent observer candidate, overlaps #9/#12/#16/#25 in **semantics**, not filenames |
| [#22](https://github.com/Podtverzhdeno/hermes-agent/pull/22) | PR integration watcher, CI and docs | Competing canonical PR collision guard |
| [#23](https://github.com/Podtverzhdeno/hermes-agent/pull/23) | `gpt_companion/journal.py`, causal safety tests and SDD | **Direct collision** with #12/#17; source-local acknowledgment causal rule stricter than #17 |
| [#24](https://github.com/Podtverzhdeno/hermes-agent/pull/24) | PR gate script, inventory JSON and docs/tests | Competing canonical PR collision guard; inventory can go stale |
| [#25](https://github.com/Podtverzhdeno/hermes-agent/pull/25) | `hermes_observer/audit.py`, CI and 42 fault tests | Separate offline auditor; compare explicit invariants, no claim of authority |
| [#26](https://github.com/Podtverzhdeno/hermes-agent/pull/26) | `gateway/gpt_bridge_event_audit.py`, collision audit script + tests | **Direct collision** with #4 on event auditor; competing guard script |
| [#27](https://github.com/Podtverzhdeno/hermes-agent/pull/27) | PR guard script, CI and tests | Competing canonical PR collision guard |

### Actual same-file conflicts to prevent silent overwrite

1. **API service:** #4, #5, #6, #11 -> `gateway/platforms/api_server.py`; #4 and #6 also share `tests/gateway/test_api_server.py`. These may encode incompatible semantics for in-flight same-key requests, SSE failure and unknown effects.
2. **External CDP browser lifecycle:** #13 and #15 -> `tools/browser_tool.py`. Both are useful, different fixes. #13 removes CDP URLs from logs; #15 avoids triggering `Browser.close` or killing daemons for externally attached CDP. One integrated patch must test both properties.
3. **Companion event journal:** #12, #17 and #23 -> `gpt_companion/journal.py` and `docs/sdd/GPT_COMPANION_SDD.md`. #17 and #23 use different causal semantics for acknowledgments across producers. Neither should blindly supersede the other.
4. **Gateway event auditor:** #4 and #26 -> `gateway/gpt_bridge_event_audit.py`, plus overlapping tests. Review actual schema versions and reason codes, not only code diffs.
5. **Prototype task kernel:** #1 and #10 -> `autopilot/ledger.py`, `tests/autopilot/test_ledger.py`; PR10's frozen base is for reproducibility only. #1 is still moving.
6. **Package metadata:** #1/#9/#12/#13 -> `pyproject.toml`. Changes may be individually syntactically mergeable yet clash in entry points, dependencies or package discovery.
7. **Many semantic duplicates despite no overlapping paths:** #14/#18/#22/#24/#26/#27 all add a GitHub PR collision checker, several with their own Actions. **Deploy at most one owner-controlled read-only checker** after selecting a contract; six parallel schedulers/alerts create noise, cost, and conflicting conclusions.

**Safety decision:** DO NOT merge any batch solely because GitHub reports `mergeable: true`. A green unit suite for a PR does not validate composition with another modifying the same path. File-level and semantic-level collision checks are both mandatory.

### Companion journal causal ambiguity — explicit design gate

PR #17's first iteration treats a prior-attempt effect as resolved if reservation and acknowledgment come from distinct sources or if the same source has a larger sequence; PR #23 instead requires same-source strictly later resolution in its offline event projection and treats cross-source acknowledgment as **uncertain**. A source-local sequence gives order only within an emitter; neither alone attests that the provider truly executed or rejected the external action. Prefer the **conservative blocked outcome**, with a separately authenticated external receipt/read-back from a privileged gateway. The shared SDD must specify a trusted event signer/identity and effect receipt, rather than relying on comparison of untrusted sequence numbers.

### Browser ownership tests and merge veto

PR #15's browser cleanup conditional checks `session_info.features.cdp_override is True`, and the inspected `_create_cdp_session()` populates that marker. Its default action for such sessions is detach metadata, **not** run CLI `close` or kill local session PID. This is safer than closing another user's browser, but needs negative tests: migrated session without flag, corrupted metadata, externally owned pid/socket collision, browser PID reused, detach during pending tool effect, proxy daemon leak, and log redaction from PR #13. Until such tests and the exact combined-SHA CI pass, keep it a draft. On one inspected head of #15, targeted detached-CDP test check reported success but the broader `test` check reported failure; **targeted green is not global acceptance**.

### Integration target / validation policy

Do not select one of the six guard implementations by code quantity or stars. Require each to detect these exact fixtures: simultaneous PRs on `api_server.py`, two branches changing the same test, stale parent SHA, unrelated docs-only updates, stack dependency PR1->PR10 snapshot, name-alias/symlink collision, false "CI green" due skipped review, and owner-local unreachable warning. Compare true-positive/false-positive rate, API pagination/cost, input-data trust, private token handling, output stability, dry-run safety and rollback.

Choose **one** audited script + one CI job that reads a deterministic normalized inventory and writes evidence pointers, not merge decisions. A GitHub workflow is not an independent arbiter for unknown external effects or the user's local CDP browser.

