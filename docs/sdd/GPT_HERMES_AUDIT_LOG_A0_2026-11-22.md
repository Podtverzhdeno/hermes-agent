# Audit ledger — Hermes GPT × A0 integration, 2026-11-22

Source provenance: connected GitHub repository, specific PR metadata / check-runs / job logs; tests in isolated Python; Local_WorkSpace MCP unavailable. All timestamps refer to observed evidence and are not guarantees of future status.

## Verified facts
- Repo Podtverzhdeno/hermes-agent main 7e9100901819ee44c16b4ddcb79a6bcb7909f591 from 2026-04-01.
- 12 open draft PRs (#1..#12); #4/#5/#6 same handler; #11 stacked on #4; #10 stacked on #1; #9/#12 competing collectors; #1/#9/#12 packaging pyproject edits.
- PR #4 HEAD 5b8497b510b0a8543e8a2e30aaac5861bf30f264: test failed, 29 failed / 7513 passed / 171 skipped, run 45013330331; actionable mismatch in test_agent_error_returns_500 (old message leaks Provider failed; now safe error). Other failed tests cannot be attributed to this change without baseline comparison.
- PR #9 HEAD 8fb2d37e5df6344ecb96ce5a56fa08e0f4ebdfe6: test failed, 28 failed / 7540 passed / 171 skipped, run 45013244320; missing CI provider credentials and other issues.
- PR #6 HEAD 781a31feaf2b7061d3540449924e13b465d3b24d: targeted-api-tests = success; full test still in progress at observed snapshot. PR #12 full test in progress at observed snapshot. Do not project these observations into the future.
- Legacy Devin Review success says skipped because no credits; not a successful code review.
- Local_WorkSpace MCP list_workspaces: Session terminated; installed browser extension, local runtime, Obsidian could not be inspected. No 24h runtime monitoring was performed.
- GitHub create_issue API returned HTTP 410, Issues disabled. No issue created.
- Existing PR #1/#10 explore ledger and diagnostics but do not prove native Hermes Kanban runtime parity.

## Actions in this branch
1. Avoid modifying shared gateway handler or producing third observer storage.
2. Add standalone read-only PR evidence snapshot collector, strict exact-head check classification, collision/stacked dependency and semantic candidate identification.
3. Add offline no-network tests and read-only CI workflow.
4. Add consolidated SDD with ownership, end-to-end event contract, effect ambiguity, typed incident taxonomy, release gates and weighted decision record.
5. Keep merge_ready=false, no writes, no automatic PR merge or task retry. GitHub PR itself is the review/cooperation venue.

## Known limitations / next verification
- Local Windows/WSL, Chrome MV3, Obsidian, MCP tunnel cannot be verified until authorized connection returns.
- Confidence in full integration or production readiness: NOT VERIFIED. Offline success does not imply E2E success.
- GitHub PR heads may change at any moment. Recollect exact SHA before considering merge. GitHub Actions cannot make REST retrieval atomic across independent endpoints.
- Existing failures from environment/credentials require a controlled comparison with unchanged main, with dummy/mocked credentials for no-secret CI.
- Repo-level integration diff + combined SHA CI, security review, source extension inspection and 30–100-agent fault injection still pending.


## Follow-up, exact A0 GitHub CI and API source control-flow audit
- PR #28 initial commit 02d63cfdddb4001836ca78678517f81aa9dca282: Github Actions offline contract code reported 13 tests OK, then live stage failed at 2026-11-22T10:53:46Z because PRs changed during snapshot. This is a live consistency race under many agents, not an offline unit test failure. Workflow run https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45014514401
- Remediation on A0 branch: independent CI jobs for unit contracts vs live evidence, maximum three bounded snapshot-race retries, explicit incident report with merge_ready=false and code SNAPSHOT_RACE / EVIDENCE_INCOMPLETE.
- PR #5 code-level: failed compute removes inflight entry without retaining unknown-outcome tombstone; later same-key retry may repeat effect. Not observed as a production incident. A0 review comment 7078088372.
- PR #6 code-level: unsupported JSON message type / stream type / blank keyed SSE can bypass intended request validation. A0 review comment 7078088737; stacked #11 contains a preflight pattern.
- PR #4 CI: 29 failed including changed safe 500-response vs old leaked error test; old test should be revised without raw backend error disclosure. A0 comment 7078089025.


## 30-PR inventory + CDP overlap, dated snapshot
- At GET 2026-11-22T10:55Z, 30 open PR #1..#30 were observed. New independent PR audit implementations include #14/#18/#22/#24/#26/#27/#28/#29; this is an integration coordination duplication issue.
- PR #13 and #15 both modify tools/browser_tool.py. #13 redacts CDP credentials but retains destructive cleanup for external CDP; #15 protects externally owned browser lifecycle but requires redaction from #13. A0 review comments 7078125611 and 7078125942.
- PR #17/#23 stacked observer modifications must not be treated as independently mergeable siblings. #10 base moved to snapshots/autopilot-ledger-6c0d2e-20261122 as of observed snapshot; exact ancestry and branch SHA must be rechecked.
- Hardened own A0 report against Markdown injection via PR path with pipe/CR/LF. Added negative test and proper multiline incident report.

## Exact-SHA regression, locally authored code
- PR #28 SHA `f85b736b4b8519d6b93b9a1f75ccf4af8f2a40ff`: both offline-contract and live-evidence failed **before functional execution** with Python SyntaxError in `_safe_markdown` (`return (` lacked closing parenthesis). Source typo was introduced in A0's own redaction/escaping hardening. Confirmed from GitHub Action job 137185428300 and 137185428459. Fix is one additional closing parenthesis and a fresh exact-head CI. No passing claim until new jobs complete. This demonstrates why independent syntax compilation/CI must precede source claims.

## Source-pinned arbitration and 100-PR metadata fixtures
- Added the A0 selection dossier: 8 competing PR audit tools (#14, #18, #22, #24, #26, #27, #28, #29), native upstream Kanban, Chrome native host and GitHub API rate limits. No implementation choice or merge has been authorized.
- Added two metadata-only unit cases for 100 independent PRs (zero collisions) and 100 PRs writing one same path (4,950 expected independent pairs). This does not simulate real worker orchestration or establish 24-hour reliability; await exact-SHA offline CI.

## Hardening A0's own evidence boundary
- Observed source audit discovered a false-stack risk: git branch names are not globally unique across forks. A0 now identifies branch owner by origin repository + head branch, and refuses ambiguous identical origins. Missing fork identity becomes conservative unknown rather than a fabricated causal dependency. Adds regression fixtures.
- GitHub legacy status-context strings, file paths and offline snapshot observed_at are untrusted data; Markdown escaping now covers the complete presentation, not only file paths. Adds injection fixture.
- These are source-level fixes; review exact new commit CI before claiming tested.

## Upstream API compatibility pivot — native Runs API before new observer storage
- Read primary current Hermes API docs and developer Programmatic Integration: POST /v1/runs, GET /v1/runs/{id}, SSE /events, /stop, /steer, /resolve-unknown and GET /v1/capabilities are already built into native session authority; legacy mode does NOT have the same dedup guarantees. They distinguish unknown, interrupted, cancelled, failed, partial and completed, and warn a 200 streamed response can still be an error.
- Previous premise that Hermes GPT must own another run journal is superseded. Additional journal only for external tool-effect confirmations, extension transport metadata and independent verifier. Separate ADR records source-specific migration/fault gates. Not verified in stale installed fork.
- PR #30 contains an offline native run SSE parser (not a live extension); candidate to reuse normalized event contract after migration. No auto-merge or production integration claimed.

## Root-cause enrichment for moving PR snapshots
- A0 live-evidence job at PR #28 older head 2f5f261652df1f8925b4a16b275c75c72cc5bec3 returned EVIDENCE_UNAVAILABLE after three attempts because PR heads changed during the 30-PR collection. GitHub Action job 137187226132 wrote durable JSON/Markdown incident to artifact ID 14751193836 despite exit 3. This is an expected fail-closed race, not a passing merge assessment.
- Follow-up source changes record unstable PR numbers and differentiate SNAPSHOT_RACE, UPSTREAM_RATE_LIMIT, UPSTREAM_PERMISSION_OR_RATE_LIMIT, TRANSPORT_UNAVAILABLE and EVIDENCE_INCOMPLETE. Added two no-network tests. Still no continuous daemon, just CI on change.

## Multi-producer liveness source schema audit
- Source-level conditional correctness finding on PR #12: event schema/SQLite uniqueness uses (source,run_id,attempt,sequence), not producer_id; source may be category worker rather than unique worker incarnation. Multiple agents same source category can falsely conflict or merge liveness. A0 comment 7078274443 requests trusted per-producer ID/fence and negative tests. This is a design risk, not a live reproduced production incident.

## Monitor self-interference / API pressure correction
- Repeated A0 draft PR pushes launched a live-evidence scan with ~3 GETs for every open PR in parallel with other agents' scanners. This contributed controllable API pressure and increased chance of SNAPSHOT_RACE (not proof of API rate limiting, which was not observed). Immediate fix: separate cheap offline-contract on PR from manually dispatched live-evidence, restrict concurrent live collectors to one and provide a future default-branch-only 6-hour safety snapshot. Schedule does NOT run while draft PR #28 is unmerged. Production proposal is webhook+incremental reconciliation instead of expensive polling.

## Owner project context refinement
- Retrieved prior authorized CDP canary context for model route web-chatgpt-high-cdp (Nov 14–15) and newer preference for a separate Agent Control Center without mandatory browser extension and without interfering with normal browser. Historical context is not a current health check.
- Local_WorkSpace access recovered partially: list_workspaces exposed only the unrelated shelter Obsidian vault. No authorized Hermes project/root/runtime/log path was available, so Hermes Windows/CDP E2E remains BLOCKED. Did not write Hermes docs into the shelter game vault.
- New ADR-A0-03 separates Hermes native run authority from an isolated opt-in CDP browser lane, consolidates typed failure cases and 30–100-worker acceptance, and keeps all execution/approval gates explicit.

## Bounded collision fan-out, overflow test
- Discovered A0 bug: 150 PRs each editing up to 1000 common files could emit 11,175,000 collision dict entries (150 choose 2 × 1000), risking memory exhaustion and self-inflicted auditor failure. Source fix limits detailed independent pairs to 5000, reports collisions_truncated true and collision_pairs_at_least (lower bound), never greenlights. Added 150-PR and 100-PR explicit regressions. This is a metadata stress test, not simultaneous real workers.

## Rename-vs-edit collision negative tests
- Audit discovered its own false-negative: GitHub /pulls/{n}/files reports a renamed file with status=renamed, filename=new path and previous_filename=old path. Earlier collector only inspected filename, so a rename A->B and another PR editing A appeared disjoint. Fix: record BOTH names for every rename and fail closed if previous_filename absent, with two adversarial contract tests. This is source/metadata test, not a real merge integration test.

## Additional audit robustness: full rename cap / malformed fields
- Live file endpoint allows up to 1000 changed files, yet each of 1000 renamed files produces two touched paths. Earlier max_files 1000 check would fail closed on valid 1000 renames; now MAX_TOUCHED_PATHS=2000, with offline test.
- Main audit error handler now includes KeyError/TypeError from malformed API/fixture payloads and persists typed EVIDENCE_UNAVAILABLE instead of losing incident artifact to an unhandled parser exception. Failure is not success, and merge_ready stays false.

## Source-pin verified upstream parity, separate from documentation assertions
- Repo trees compared by connected GitHub GET at fork SHA 7e9100901819ee44c16b4ddcb79a6bcb7909f591 (1261 blobs) and upstream SHA 0f602c5f6f18615632535251d62a2db74ce93b69 (27462 blobs): 667 common exact paths, 26795 upstream-only, 594 fork-only. Structural sample gateway 33 vs 421, hermes_cli 36 vs 909, agent 20 vs 478. Counts include tests/plugins/resources, not effort estimate.
- Read actual upstream gateway/platforms/api_server_runs.py route table (~285), API durable reservation (~768), run idempotency store, authority runs and kanban_db. Key native modules are structurally absent in fork baseline. Detailed migration gate in GPT_UPSTREAM_PARITY_SNAPSHOT_A0_2026-11-22.md. Not a claim to have tested/installed upstream or identified a stable released tag.
