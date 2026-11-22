# Hermes GPT integration — causal work log and upstream Kanban compatibility

**Audit date:** 2026-11-22 UTC. **Scope:** connected GitHub repository and official upstream docs. Local Windows/Chrome runtime and Obsidian remained inaccessible from the present tools. **Do not infer live worker health from connector failure.**

## Evidence timeline (point-in-time, no continuous daemon)

| Observation | Fact and exact evidence | Result / next-safe-action |
|---|---|---|
| Initial baseline | Fork main SHA `7e9100901819ee44c16b4ddcb79a6bcb7909f591`; seven draft PRs (#1–#7) present | Avoid patching main and avoid claims of production integration |
| Connector transport | Local_WorkSpace returned `Session terminated`, secondary read-only MCP returned 429 | Observer unavailable; independently verify host health before claiming worker death |
| Concurrent work | New draft PRs #8–#16 appeared during the same inspection; #4/#5/#6 modify the same API server, while #8/#9/#12/#16 each create distinct observer contracts | One integrator must approve a canonical event schema and map old event vocabularies |
| API issue initially observed | Older PR #6 `_IdempotencyCache` removed failed tasks; potential unintended retry after unknown side effect | Branch owner subsequently fixed by quarantining outcome_unknown; this finding is historical |
| API issue currently open | PR #6 `gateway/platforms/api_server.py` blob `2baea1ec40d381440b4df7d77794b16469bbe5b6`: explicit session history-read exception resets history to [] | Comment posted to PR #6; fail closed and add negative test, do not silently drop context |
| Coordination false negative | PR #14 script `CAPABILITY_PATHS` omitted PR #8 `hermes_gpt_bridge/` | Comment posted to PR #14; validate capability semantics in addition to path overlap |
| Canonical control plane | Official upstream v0.23.3 release (GitHub API) and Hermes Kanban worker-lanes docs: task lifecycle/worker identity belongs to Kanban | Do not create competing task authority via Autopilot PR #1; audit/port upstream first |
| Changes made | PR #16 adds parser, read-only observer, offline JSONL inspector and SDD integration gate | Branch only; no runtime activation |
| Offline verification | 43 pytest cases passed in isolated Python environment, `compileall` passed; includes 30 producers × 50 events; duplicate JSON keys and changed-payload event-ID replays are rejected | Offline validation only; no GitHub CI or extension E2E success implied |
| CI | GitHub workflow statuses must be checked against latest PR #16 head after all writes | If pending, mark pending rather than green |

## Upstream lifecycle: explicit stop semantics to reuse, not reinvent

The current official Hermes Kanban worker-lanes documentation (https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes) describes:
- **Canonical task states** ready → running → review, blocked, done or archived. A worker must report a terminal Kanban tool call; a normal process exit without such a call generates `protocol_violation`.
- **Nonspawnable assignment:** unresolved assignee produces `skipped_nonspawnable` and card stays ready, not a silent fallback to a different profile.
- **Worker exit codes:** 0 is successful process exit but not proof of task completion; 75 (EX_TEMPFAIL) covers retryable provider throttling/transient failures; 78 (EX_CONFIG) covers invalid account/model/certificate configuration. `terminal_provider` can activate a blocked circuit breaker without wasting the same retry budget.
- **Workers and descendants:** environment includes HERMES_KANBAN_TASK, HERMES_KANBAN_DB, HERMES_KANBAN_RUN_ID, HERMES_KANBAN_CLAIM_LOCK. Descendant processes are fenced from owner-only board mutations.
- **Incomplete worker exit:** a bounded synthetic nudge may ask the worker to call the terminal Kanban tool, followed by a bounded retry policy that blocks after repeated violations.
- **Observability surfaces:** board task events, workspace, worker logs, run and handoff; browser observer must not overwrite these.
- **Host pause:** missing live notifications are not proof of no task activity or task completion; the durable board must be queried on restart.

### Reuse map for a future GPT bridge

| Event / symptom | Authoritative source | Observer classification | Automation safety |
|---|---|---|---|
| `skipped_nonspawnable` | Kanban dispatcher/task event | blocked assignment | No substitution of assignee without user/owner policy |
| `protocol_violation` | worker exit + Kanban run/event | task incomplete | Bounded existing Kanban recovery, no second retry loop |
| `rate_limited`, exit 75 | provider outcome + dispatcher event | provider throttled | Shared backoff and budget, not multiple fan-out retries |
| `terminal_provider`, exit 78 | provider result/worker exit | configuration needs attention | Never auto-retry with same invalid credential |
| `block_loop_detected` | canonical board event | blocked loop | Require distinct patch or operator triage |
| Browser MV3 suspend | browser/native adapter only | observer temporarily disconnected | Reconnect read-only with durable cursor; do not alter board state |
| External tool lost ACK | durable tool-effect journal + provider receipt | NEEDS_RECONCILIATION | No blind replay or false success |
| ChatGPT UI idle or disappears | UI only | insufficient evidence | Query canonical board and worker/transport diagnostics |
| Explicit session DB read error | GPT gateway request handling | session_store_unavailable | Fail closed; never initialize a replacement empty context |
| CI green on an older SHA | GitHub checks bound to commit | CI_REVISION_MISMATCH | Revalidate exact candidate SHA |

**Crucial constraint:** these are documented upstream behaviors, not a test report for the owner's older fork main. Verify the actual code and migration path before asserting availability in the local runtime.

## Change ownership and merge gating (30+ agents)

1. **Authority owner:** Kanban migration maintainer, not each individual observer agent.
2. **Event contract owner:** exactly one schema maintainer; decide per-producer sequence semantics, event IDs, causal parent refs, immutable versions, producer authentication and migration adapters before integrating #8/#9/#12/#16.
3. **API integrator:** choose one of #4/#5/#6, incorporate #11's preflight safely and add tests for session-read, error-valued result, keyed SSE, unknown external write, cross-process restart and cancellation.
4. **Browser/host owner:** inspect actual installed extension and Native Messaging host identity, permission set, MV3 lifecycle, correlation propagation, message sizes and no automatic hidden browser actions.
5. **Ledger/effect owner:** implement reservations/reconciliation in/under Kanban, not a competing scheduler.
6. **Independent verifier:** reproduce deterministic offline tests, GitHub workflow checks on exact SHA, plus Windows extension integration and injected crash tests.
7. **Operator:** only one person merges a canonical integration train; all alternative PRs remain independent review material until acceptance is grounded.

## Unknowns, safeguards and honest status

**BLOCKED:** real extension source/manifest/runtime, native host logs, Obsidian updates, persistent background collector, multi-host crash recovery, 24–72 hour soak, live provider effects. This session cannot watch continuously after completion.

**Risk priorities:** (1) competing task control planes and schemas; (2) unknown side effect replay; (3) explicit session continuity loss; (4) stale file writers and permission scope; (5) missing causal event gaps/observer outage; (6) provider retry fan-out. A SDD cannot itself guarantee atomicity or service liveness.

**Strict quality test:** do not promote any implementation from draft until every claimed invariant is connected to executable tests, verified current source SHA, live-environment evidence where required, and an incident path that remains safe when monitoring fails.

## Self-audit correction

In a later strict pass, the observer's first version treated any event with the same (event_id, producer_id, sequence) as a replay without checking that the rest of the event payload was identical. A malicious or buggy emitter could thus alter a previously observed event and have it misclassified as a harmless duplicate. **Fixed** by storing a canonical validated event SHA-256 digest in the bounded replay cache and comparing the entire tuple. An independent regression test now rejects same-ID/same-sequence altered content. This increases isolated test count to **43 passing**. This does not establish source authenticity; authenticated producers and durable ledgers remain required.

## Latest adversarial causal-gap review

**Failure found in my own candidate:** when all bounded recent events referenced missing causal parents, the original `causal_capacity` rejection could permanently stop the observer from ingesting new valid events, even though older children were evictable. This would create a second, observer-generated incident and falsely obscure the actual Hermes task state.

**Repair:** map each retained unresolved child to its missing parent, remove both forward and reverse references whenever a child is evicted or its parent arrives, and never turn ordinary causal incompleteness into an artificial permanent ingestion halt. The observer still marks an absent parent as incomplete evidence, **not worker failure**. This is a local, non-durable telemetry policy.

**Repro and validation:** new `test_many_missing_parents_never_starve_bounded_observer` streams 50 events with unknown parents through a two-event bounded cache and demands accepted events throughout, with at most two unresolved links. Full isolated observer set now **43/43 pytest tests passed** and `compileall` passed. Exact local Git blob SHA matched GitHub after patch: observer `1eca46bb647026c4c9fc43e6ec317c9e3d8cbce2`, tests `f660e0d3846dbf0afd113cb54b81ee5ecddd1f47`. **GitHub full-suite CI and actual browser/Windows run are separate acceptance gates**, not proven by these checks.

## GitHub CI root-cause record: do not conflate isolated and full-suite verdicts

**Evidence:** Tests workflow run [45015318217](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45015318217), exact candidate SHA `d60cca4ef2d279057b86c65ef6c504a9d7dbd09b`, job `137186336707`: **FAILED** after 176.01 s; 7,543 passed, 171 skipped, 28 failed, 119 warnings. All listed failure paths are outside `tests/gateway/test_gpt_bridge_observer.py`; this observation does **not prove** that the failures predate the PR because no clean same-environment main baseline has yet been reproduced.

**Failure classes from raw Actions log:**
- Multiple older `tests/test_streaming.py`, `test_run_agent.py`, `test_context_token_tracking.py`, `test_surrogate_sanitization.py` cases fail because the SDK initialization sees no OpenAI credentials. The test workflow explicitly clears `OPENAI_API_KEY` to avoid real provider calls. This is a **test isolation/fixture contract failure candidate**, not a request to add live API secrets.
- `tests/test_codex_execution_paths.py` expects a mocked 401-refresh recovery but receives a missing-model validation error.
- `tests/agent/test_auxiliary_client.py` vision fallback asserts a nonexistent selected fallback.
- Three `tests/tools/test_file_read_guards.py` cases return a 30-second execution timeout under the full parallel run.

**Safe remediation policy:** Never inject real provider credentials into public PR CI, never delete failures from the release-gating suite or relabel it green, and never claim zero regressions without comparing to a pinned baseline. Test suites should use explicit SDK mocks and limit resource contention. Our PR adds an additional **isolated observer contract** workflow `.github/workflows/gpt-bridge-observer-contract.yml` running the 43 observer cases with the same dependency profile and no network credentials. Its green status, when confirmed, is **component-only**, not production deployment approval. The general Tests workflow remains a separate, currently failed gate pending independent root-cause and upstream compatibility work.

**Supply-chain false positive closed:** earlier risk scanner flagged syntactically co-located `subprocess.run(... input=...encode())` in test-only JSON stdin. We split encoding from the subprocess call, left the scanner unchanged, and observed succeeding `Supply Chain Audit` jobs on later exact SHAs. Future SHA must be checked again.

## Graph-integrity recheck: causal cycles

An observer can have individually valid event IDs, timestamps and per-producer sequences while carrying an **impossible causation graph**: A claims B as its parent and B claims A, or A←B←C←A. The first observer version only detected self-parent references; that would leave cyclic traces looking like ordinary events and mislead root-cause analysis.

Added a bounded parent ancestry index for retained events. Before mutating the replay cursor, a newly arrived event checks its causation parent chain and rejects a proven cycle as `causal_cycle`. If an ancestor was already evicted, absence of proof stays **UNKNOWN**, not a false guarantee of acyclicity. The ancestry index is cleaned when an event is evicted, keeping its size bounded by recent events. Regression tests cover both a two-event cycle with safe correction and a three-event cycle.

**Current isolated verifier result:** **45/45 tests passed**; `compileall` passed. Exact source match after uploading: observer Git blob `f26db21ab4cc0518fe92e5b5dc074dbc24d21788`, tests Git blob `e1920ee8c0270db3181eadf98c6ede5e77709a2f`. This is a local conformance result only. The dedicated GPT Bridge observer GitHub workflow is added, but general Tests workflow remains an independent release gate with 28 previously observed non-observer failures. Never silently skip or conceal them.
