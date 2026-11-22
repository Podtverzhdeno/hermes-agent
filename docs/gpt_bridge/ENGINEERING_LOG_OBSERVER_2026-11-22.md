# Hermes GPT Bridge — independent observer work log (2026-11-22)

**Immutable base inspected:** `Podtverzhdeno/hermes-agent main@7e9100901819ee44c16b4ddcb79a6bcb7909f591`.  
**Authority:** source inspection and offline tests only. No local Windows runtime claim.

## Evidence records

| ID | Class | Observation / reproduction | Risk and corrective action | Status |
|---|---|---|---|---|
| O-01 | OBSERVED_GITHUB | Seven draft PRs #1–#7; three separate PRs #4/#5/#6 modify `gateway/platforms/api_server.py` | Competing idempotency/SSE behavior; freeze file until a single integration owner reviews patches | OPEN |
| O-02 | OBSERVED_CODE | Base `_IdempotencyCache.get_or_set()` awaits computation before storing a result | Same key concurrent calls can both invoke AIAgent | Separate gateway fix pending; not modified here |
| O-03 | OBSERVED_CODE | Base SSE writer swallows `agent_task` failure before sending normal `stop` chunk | False-positive stream success | Client-specific fault injection required; not modified here |
| O-04 | OBSERVED_GITHUB | `main` GitHub branch reports `protected=false` | No automatic assumption of merge protection; enable/check branch rules | OPERATOR_GATE |
| O-05 | OBSERVED_GITHUB | PR #3 test and Nix jobs cancelled; #1 offline contract 3.11/3.12/3.13 success but general test cancelled; #4/#5/#6/#7 tests were in progress when inspected | CI is not complete proof; review check-runs at exact head later | OPEN |
| O-06 | OBSERVED_UPSTREAM | `NousResearch/hermes-agent` latest release v0.23.3 published 2026-11-20 | Old April fork parity must be resolved before scheduler integration | OPEN |
| O-07 | BLOCKED_CONNECTOR | `Local_WorkSpace.list_workspaces` returned `INVALID_ARGUMENT: Session terminated` | Actual extension/native host and Obsidian not inspected; do not claim live monitoring | BLOCKED |
| O-08 | TESTED_OFFLINE | First 39 observer tests: 37 pass, 2 errors on list-valued `kind` / `trust_level` | Fail-closed type checks implemented | FIXED |
| O-09 | TESTED_OFFLINE | Observer repeat after type hardening: 39/39 pass; additional strict UUID, UTC date, claimed verifier, causal order and stop-hint tests | 46/46 pass | PASS_OFFLINE |
| O-10 | TESTED_OFFLINE | 30 synthetic producers × 500 shuffled events; 15,000 accepted, zero rejected/gaps, ~0.33 s in isolated Python 3.13 | Bounded batch auditor did not assume global clocks | PASS_OFFLINE |
| O-11 | TESTED_OFFLINE | PR overlap script tested with 3 gateway-conflicting PRs, 100 synthetic agents, stale/failed checks | 7/7 pass | PASS_OFFLINE |
| O-12 | UNKNOWN | Cannot validate input producer auth or a claimed `trusted_verifier` from NDJSON alone | The module never grants retry, success or approval; require trusted adapter | DESIGNED_GAP |
| O-13 | UNKNOWN | In-process audit does not guarantee a persisted event journal, current task state, live extension activity or remote side effect | Integrate with ledger outbox and immutable external receipts in separate PR | FUTURE_GATE |

## Operator and review obligations

- Do not merge #4/#5/#6 as independent last-write-wins patches. Review semantics and select a single candidate.
- Do not merge this proposal merely due to 53 offline test passes: require GitHub CI at exact new branch head; assess dependency/lineage and full fork tests.
- Do not send raw prompts, API tokens, cookies, private chats, raw tool arguments or full provider error strings to the audit export.
- Do not treat Local_WorkSpace connector failures as Hermès gateway or extension crashes.
- Do not claim long-running monitoring has started; neither the extension nor the gateway is wired to this read-only CLI yet.
- Any future incident must record exact task+attempt+fence, source event IDs, two competing causes, independent evidence, owner, patch SHA, regression status and rollback decision.

## Validation commands (isolated patch and future fork checkout)

```sh
python -m unittest discover -s tests/gateway -p 'test_gpt_bridge_event_audit.py' -v
python -m unittest discover -s tests/scripts -p 'test_gpt_bridge_pr_collision_audit.py' -v
python -m compileall -q gateway/gpt_bridge_event_audit.py scripts/gpt_bridge_pr_collision_audit.py
```

Production deployment remains **HOLD** until the trusted adapter, actual local extension source, host/Native Messaging security and end-to-end failure injection are verified.


## Follow-up verification (2026-11-22, approximately 10:50 UTC; later same pass)

| ID | Evidence class | Finding | Required action |
|---|---|---|---|
| O-14 | OBSERVED_GITHUB | The open PR count increased to 26 (#1–#26), all draft at inspection. File lists for all 26 were obtained via the GitHub connector. | Refresh snapshots before review; avoid stale seven-PR assumptions |
| O-15 | OBSERVED_GITHUB | Four PRs #4/#5/#6/#11 overlap on `gateway/platforms/api_server.py`; #4 and this PR #26 overlap on `gateway/gpt_bridge_event_audit.py` and the identically named test file. | Do not merge either parser without identifying protocol owner and reconciling types |
| O-16 | OBSERVED_GITHUB | #1 and #10 overlap `autopilot/ledger.py`; #12/#17/#23 overlap `gpt_companion/journal.py`; #13/#15 overlap `tools/browser_tool.py`. | Single owner per mutable state machine; coverage at final combined SHA |
| O-17 | OBSERVED_CODE/RESEARCH | PR #4's candidate parser targets native upstream `/v1/runs` SSE; this PR's offline module targets proposed SDD event-envelope v1, not native event shapes. | Versioned adapter with no hidden content/privilege elevation; see ADR-GPT-016 |
| O-18 | RESEARCH_NOT_CURRENT_RUNTIME | An Oct 2026 upstream issue describes `replay.truncated`, missing run discovery and in-memory approvals at that revision; not validated against current v0.23.3. | Source-specific capability probing and current integration tests |
| O-19 | OBSERVED_GITHUB | Draft PR #26 opened on this audit branch, initial SHA `3990f675d93e80c2526dc758c317c200b507cb8f`; at first check full tests and offline matrix were queued. | Never claim GitHub CI success; query the *latest* head |
| O-20 | TESTED_OFFLINE | Added strict type/cycle/deep nesting and producer-ID hashing tests: 49 observer + 9 PR guard checks passed on local Python 3.13. | Repo workflow must independently run exact committed content |
| O-21 | DESIGN_DECISION | MV3 shutdown must not imply run failure and must never trigger a second POST; observe native seq gaps, then reconcile from trusted status. | Include SSE replay and operator STOP in E2E tests |

**Not done:** no Windows extension implementation; no MCP/Obsidian inspection after `Session terminated`; no live Hermes process monitor, no auto-fix deployment, no merge into main. These are intentional release HOLDs, not hidden achievements.



| O-22 | OBSERVED_RELEASE_TAG | Verified upstream tag v0.23.3 docs and `api_server_runs.py`: canonical durable admissions, scope-bound approvals, replay-truncated SSE and `unknown` recovery with generation fencing exist. | Align migration with current upstream behavior; do not reintroduce April legacy races. |
| O-23 | CHANGE_ISOLATION | Renamed this PR's metadata v1 parser to `gateway/gpt_bridge_metadata_audit.py` and its test to `test_gpt_bridge_metadata_audit.py` in one expected-HEAD Git tree update. | Exact-path overlap with #4 removed; semantic integration/adapter still OPEN. |

**O-22/O-23 verification:** only release-tag source inspection and atomic Git source-change provenance; new PR CI and Windows integration require separate evidence.
