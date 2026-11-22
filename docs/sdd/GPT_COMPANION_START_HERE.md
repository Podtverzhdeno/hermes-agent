# Hermes GPT Companion — START HERE (integration / audit)

**Purpose:** lightweight onboarding for 10–100 concurrent reviewers and worker agents. This file is an **advisory index**, not a scheduler, trusted ledger, production configuration, or proof of live monitoring.

**Date of checkpoint:** 2026-11-22. **Reference:** [full GPT Companion SDD](GPT_COMPANION_SDD.md), [source findings & audit log](GPT_COMPANION_AUDIT_LOG_2026-11-22.md), [offline observer README](../../gpt_companion/README.md). **Heads move:** everything below must be checked against GitHub immediately before a decision.

## 1. Hard truth at this checkpoint

- In connected GitHub, the project exists as `Podtverzhdeno/hermes-agent`. 30 open PRs were observed; this count will change.
- This change lives in stacked **draft PR #17** on **draft PR #12**; neither should be treated as deployed.
- A GitHub Actions isolated Python 3.11/3.13 test matrix exists. A green job is meaningful **only for its exact commit SHA**, and not for real Chrome/Windows/Obsidian/ChatGPT installation.
- The local workspace connector returned `Session terminated`, and alternative MCP returned HTTP 429 in this conversation. No local observer or always-on service was verified.
- No one may claim a report is final or an external write did **not** happen solely from `worker.stopped`, a model message, UI disappearance, SSE end, timeout, or absent hook event.

## 2. Decision tree: what did the agent really do?

1. **Identity & revision:** determine canonical task/run ID, attempt, owner/fence and immutable source SHA. If unknown, classify `IDENTITY_UNVERIFIED`.
2. **Trusted lifecycle:** query the exact installed Hermes Kanban/task_runs source and version. If unavailable, classify `CONTROL_PLANE_UNAVAILABLE`.
3. **Telemetry:** find producer source-local sequence, source boot epoch and event receipt. If source prefix uncertain or chain invalid, mark `TRACE_INCOMPLETE`; distinguish internal sequence holes from an unverified prefix.
4. **Side effects:** any reservation with an unverified outcome in the current **or previous** attempt blocks replay. Even an event called `tool.effect_acknowledged` remains a claim until a trusted effect receipt/readback is matched.
5. **Progress:** distinguish heartbeat, call start, stage completion, provider response, approval wait, queue admission and browser transport. Fresh heartbeat can coexist with `ALIVE_NO_PROGRESS`.
6. **Verification:** `run.reported_completed` → `AWAITING_VERIFICATION`, never `SUCCEEDED`; check artifacts and CI tied to exact revision, signed/authorized evidence and independent reviewer.
7. **Safe action:** proposal `inspect → reproduce → guarded fix PR → exact-head tests → independent review → rollout/rollback`. Never auto-merge/deploy/retry an unknown external action.

## 3. Proposed ownership map (not approved merge order)

| Function / write lock | Candidate owner | Competing work | Non-negotiable gate |
| --- | --- | --- | --- |
| Canonical Hermes task lifecycle | Installed upstream Kanban after version-probe | Legacy fork Autopilot #1/#10 | One task dispatcher, one lease authority |
| Offline event journal | PR #12 | PR #9/#16/#21/#25/#30 | Choose one schema/adapter, prove migration |
| Terminal outcome / prefix / liveness diagnostics | PR #17 (stacked on #12) | #23 overlaps some terminal cases | No stale parent merge; prove exact-head test |
| Unknown effects, causal ACK, watcher dedup | PR #23 | Duplicate candidate in #17 **removed** | Sticky across attempts, trusted gateway proof |
| Gateway API idempotency/SSE | **UNASSIGNED** | #4/#5/#6/#11 | Keyed SSE preflight, principal scope, error after write |
| ACP permission safety | PR #3 | Later ACP-related work | Session isolation, typed failure, prompt redaction |
| Browser CDP external owner cleanup | PR #15 | #13 also modifies browser_tool.py | Opt-in attach, never kill externally owned browser |
| GPT diagnostics/Native Host SDD | PR #13 / #19 | Other GPT observer docs | Validate strict input types, boot cursor, consent |
| GitHub PR collision/CI evidence | PR #27 primary; #29 ancestry adapter | #14/#18/#20/#22/#24/#26/#28 | One pinned, read-only complete snapshot |
| SDD / release arbitration | **A0 integration steward required** | all teams | Human approval, exact revision, rollback |

**No competing owner may independently force-push or merge a shared file.** If the parent SHA changed, stop; review semantic differences; preserve both sets of unique tests and invariants. An independent reviewer is a different source of evidence, not merely another assistant's confidence statement.

## 4. Current code/test artifacts

- `gpt_companion/journal.py`: local untrusted metadata-only append-only SQLite WAL; immutable event IDs and hash chain; no trusted ingress, external effect authorization or live browser control.
- `tests/gpt_companion/test_terminal_causality.py`: failure/completion vs worker stop, contradictory run reporters, reported reason origin, gap vs source prefix, clock rollback, single-snapshot latest-attempt query, stage-progress vs heartbeat, synthetic 30-source and real 30-thread WAL ingestion.
- `.github/workflows/gpt-companion-contracts.yml`: isolated tests on Python 3.11 & 3.13 and installed-wheel command check, triggered on stacked branch push.
- `gpt_companion/watch.py`: **parent PR #12 owned**. Owner must finish integrity verification, stable fingerprint coverage, durable notification delivery before production.
- `gpt_extension/diagnostics.py`: **PR #13 owned**, read-only pure function, not live extension. Strict bool/NaN/evidence provenance tests are outstanding.
- `gateway/platforms/api_server.py`: **no canonical integrating owner yet**. Four draft PRs have conflicting behavior.

## 5. Required readiness checks before any release

- [ ] Freeze and capture parent + child exact HEAD SHA and complete PR file list.
- [ ] Consolidate competing `api_server.py`, `watch.py`, `browser_tool.py` and event schemas by owner-led semantic review.
- [ ] Verify full repo CI **on the final merge commit**, across supported Linux and Windows host/runtime variants, not only isolated branch tests.
- [ ] Verify provider response ID, signed webhook delivery, duplicate callbacks and unknown external write handling with deterministic fault injection.
- [ ] Verify actual installed Hermes version, observer hook allowlist, permissions, Chrome profile/extension ID and native-host binary path.
- [ ] Prove prompt/secret redaction, strict input types, tenant isolation, approval roles, resource ownership/fencing and safe cancellation.
- [ ] Stress 10/30/100 workers with source replay, outbox loss, clock skew, two-process restart, SQLite busy/WAL crash, stale CI and browser detach; publish **measured** latencies/false positive rates.
- [ ] Define explicit operator approval and rollback; no automated production mutation until those gates pass.

## 6. Evidence grades

`CONFIRMED_SOURCE` = code/test/PR content inspected at a stated SHA; `CI_EXACT_HEAD_PASS` = GitHub workflow run and job metadata on that exact SHA; `REFERENCE_CONTRACT` = official public API/framework docs, not an installed runtime; `HYPOTHESIS` = plausible failure with no reproduction; `LIVE_VERIFIED` = authenticated running host evidence, **currently absent**.

**No amount of repeated agent agreement upgrades HYPOTHESIS to LIVE_VERIFIED.** When unable to gather evidence, record UNKNOWN and a reproducible next check. Update the append-only audit log, not a fake heartbeat.

## 7. Key trusted references

- Hermes observer hooks: https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks
- Hermes Kanban/worker lanes: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
- SQLite snapshot isolation: https://www.sqlite.org/isolation.html
- OpenTelemetry GenAI and Weaver harness: https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/
- OpenAI API Background & webhooks: https://developers.openai.com/api/docs/guides/background and https://developers.openai.com/api/docs/guides/webhooks

This page is intentionally **shorter than the full SDD**. For detailed test/risk/ADR descriptions see sections 14–37 there and the audit log. Do not copy its snapshot tables as live authoritative state.
