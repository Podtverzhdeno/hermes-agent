# Hermes GPT extension — engineering evidence log

## GPT-OBS-001 — 2026-11-22

### Objective
Produce an isolated, source-grounded SDD and *read-only* diagnostic module for an eventual GPT adapter. Preserve the existing draft Autopilot ledger and main branch. Require honest failure classification, revision-bound verification and safe external-action reconciliation, considering dozens of parallel agents.

### Sources and access
- Repository: Podtverzhdeno/hermes-agent; baseline main 7e9100901819ee44c16b4ddcb79a6bcb7909f591.
- Parallel branch draft PR #1: feat/autopilot-durable-ledger-20261122, head bc66ef436253e552d5b206f5b4d757f0214ed92d.
- GitHub file, branch and PR reads succeeded. Local Workspace MCP list_workspaces returned Session terminated; local machine / Obsidian not observable.
- Container GitHub network resolution unavailable; source files examined through GitHub connector. No real GPT credentials or browser sessions accessed.

### Audit findings: source-backed risks, *not* reproduced field incidents

| ID | Evidence | Risk | Status |
|---|---|---|---|
| OBS-01 | acp_adapter/events.py:27-40, future.result(timeout=5) per update, DEBUG on errors | ACP display delivery can hold up model worker and silently lose useful progress | Source confirmed / reproduction pending |
| OBS-02 | acp_adapter/server.py:57-59, max_workers=4 | Queue capacity saturation for many requests | Source confirmed / queue tracing pending |
| OBS-03 | acp_adapter/server.py:~263-315 shared terminal approval callback | Concurrency/permission routing race | Hypothesis / independent race test pending |
| OBS-04 | acp_adapter/events.py:~59-85,126-149 same-name FIFO pairing | Out-of-order tool completions could mismatch IDs | Conditional hypothesis |
| OBS-05 | gateway/stream_consumer.py:~57-93 unbounded queue.Queue | Slow delivery can exhaust memory | Source confirmed / stress test pending |
| OBS-06 | acp_adapter/server.py:~287-344 exceptions converted to Error: text | Error may appear as normal end_turn | Source confirmed / transport test pending |

### Changes made and verified
- Added gpt_extension/diagnostics.py as pure readonly classifier. No filesystem, network or tool dispatcher.
- Added gpt_extension/__init__.py and tests/gpt_extension/test_diagnostics.py.
- Added docs/gpt_extension/SDD.md, this evidence log, and operator runbook.
- Ran python -m unittest discover -s tests/gpt_extension -q in isolated container: **22/22 PASS**.
- Ran Python bytecode compileall and Python unittest in isolated container; not equivalent to full repo CI.
- Committed on feature branch only; fetched remote files and compared exact UTF-8 content and Git blob SHAs after write.

### Control-review correction
An initial classifier allowed status=succeeded with zero required evidence kinds to produce VERIFIED_SUCCESS (vacuous truth). Fixed by adding explicit EVIDENCE_POLICY_MISSING and regression. Also ensured reserved external effects take precedence over apparently terminal success and unknown runtime root causes stay unknown.

### What is not complete
- No active end-to-end monitor daemon, OpenAI Responses API adapter, model call, local host probe, GitHub CI verified on this branch, or synced Obsidian note.
- Existing Autopilot PR #1 is still independent and draft; integration cannot be claimed.
- ACP shared callback concurrency failures are hypotheses, not observed exploit/race.
- Feature branch changes need independent code review and CI at exact head SHA before merge.
- No guarantee of memory persistence or future background work from a single chat run.

### Next work, with ownership boundaries
1. ACP owner: per-session approval callback, stable tool-call ID correlation, typed error propagation and deterministic race tests.
2. Transport owner: bounded async update queue, signal/metric for failed ACP delivery, slow-consumer stress tests.
3. GPT API owner: typed response stream lifecycle and idempotency/recovery semantics, mocked protocol tests.
4. Autopilot owner: trusted, authenticated ledger snapshot API; do not expose raw mutable methods to model.
5. SRE owner: span correlation, event dedup, heartbeat/lease incidents, ingress/outbox, proactive but bounded alerting.
6. Verifier owner: exact-SHA CI check, independent receipts and stale-evidence adversarial fixtures.
7. Local runner owner: scoped worktrees, optimistic file hashes, Obsidian sync only when MCP is healthy.

A task is not complete because a model says so. Mark unobserved causes as unknown; do not repeat externally uncertain side effects.


### Addendum: owner-authorized CDP and wheel package audit
- Historical Hermes backend: `web-chatgpt-high-cdp` with a direct CDP canary and single-lane behavior. Historical extension/bridge status is **not** a current 2026-11-22 health check.
- SDD section 15 now specifies browser lane fencing, command/ACK sequences, no blind replay, tab exclusivity, and independent task receipts.
- Added `gpt_extension/cdp_diagnostics.py` and 16 synthetic tests; isolated test suite **38/38 PASS**, Python compileall PASS. Not a real CDP execution test.
- Packaging audit detected `pyproject.toml` explicit setuptools package include list omitted the new `gpt_extension`. Added `gpt_extension` and `gpt_extension.*` on this feature branch, verified exact file contents and blob SHA. Autopilot PR #1 modifies the same include list for `autopilot`; eventual merge must retain both.
- Read original Hermes browser source `tools/browser_tool.py` and `tests/tools/test_browser_cdp_override.py`; this is a generic CDP override interface, **not** proof that the separate user-specific extension binary/source is present in the fork.
- Hot-path ACP behavior is **not** modified: suspected global callback isolation and queue backpressure require separate reproducer and integration tests before changing production code.


### Control gate review, source correction and expanded offline checks (same date)
- Audited 16 concurrently open draft PRs through connected GitHub: 144 distinct changed paths, 5 exact shared paths, 14 pairwise overlaps at the observed snapshot. The inventory is **not atomic** and branch heads move during audits. Recorded reproducible dependency/ownership matrix at `CROSS_PR_INTEGRATION_AUDIT_2026-11-22.md`.
- Corrections from upstream verification: verified the latest official NousResearch/hermes-agent release `v0.23.3` (published November 20 UTC). Its Kanban has durable run/task events and worker lanes. The SDD's prior endorsement of PR #1 as an eventual *production* scheduler was **withdrawn**; use canonical upstream Kanban after audited migration, and treat prototype Autopilot as an isolated source of safety invariants. See SDD ADR-GPT-008.
- Commented on draft PR #14 integration gate after reviewing source: non-main stacked PRs are excluded from PR-only scanning; moving heads/base can invalidate a nominally green inventory. No other agent's branch was edited.
- Fixed two additional class-of-risk gaps in our own evidence classifier after reading Autopilot PR #1 source: `passed` vs `success` labels, unknown effect state, missing external receipt, and simultaneous trusted pass/fail for one required CI kind. Each case now fails closed and has tests.
- Re-ran local isolated tests: **46/46 PASS**, Python compileall PASS and setuptools `find_packages` includes `gpt_extension`. Three added synthetic multi-agent tests exercised 3,200 separate classifications on 32 parallel read-only threads and 20 state/effect combinations. These are **NOT** 32 live GPT/ChatGPT workers.
- Four browser integration regression tests reside in `tests/tools/test_browser_cdp_redacted_logs.py`; they need GitHub full-repo CI / real installed dependencies, not counted among 46 isolated tests.
- Main remains untouched; PR #13 is draft and may not be merged until **exact current HEAD** CI and independent review. Local Workspace MCP still `Session terminated`; no live extension, local host or Obsidian sync verified.


### Browser subprocess privacy audit — high-risk residual boundary
- Reviewed `tools/browser_tool.py:_run_browser_command` and found additional raw CDP exposure in subprocess stderr, non-JSON stdout, command-prefix logs, exception text and structured failed responses.
- Hardened CDP-specific subprocess error logging and failure returns without changing successful JSON or normal non-CDP diagnostics. Source paths and code reviewed after commit; **eight** browser-log regression tests now exist, but complete full-repo CI is still required.
- Found residual leak surface: the CLI still receives the **full CDP bearer URL in OS argv**. Logging redaction is partial mitigation, not credential isolation. Documented in SDD section 18 and added version-gated validation of `AGENT_BROWSER_CDP` / `AGENT_BROWSER_PIN_TAB` for a later secure invocation.
- Version compatibility nuance: Hermes source explicitly avoids `--session` + `--cdp` for observed agent-browser ≥0.13 semantics, while newer vendor documentation supports session tab pinning. Do not switch CLI flags without a per-version E2E test matrix.
- No live browser process was started or affected by these changes; user-local state remains unobservable.
