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
