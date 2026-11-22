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
