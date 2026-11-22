# Concurrent Hermes/GPT PR collision census — 2026-11-22

**Evidence:** read-only GitHub connector snapshot of 25 OPEN draft PRs #1–#25 and their `list_pr_changed_filenames` results, captured on 2026-11-22 after PR #25 appeared. **Not** a transactional snapshot of every GitHub branch, not a durable monitor. **Observed fork main baseline:** `7e9100901819ee44c16b4ddcb79a6bcb7909f591`. Heads may move after capture; re-snapshot and retest before merging. No action is granted solely by this report.

## P0 overlapping tracked code paths (confirmed from changed file lists)

| Path | Competing PRs | Why merge is blocked |
|---|---|---|
| `gateway/platforms/api_server.py` | #4, #5, #6, #11 (stacked on #4) | Different same-key mismatch 422/409 policy, in-flight join vs 409 rejection, SSE fail handling, CORS and request IDs. Requires ONE gateway owner, one contract and exact merged-HEAD tests. |
| `tests/gateway/test_api_server.py` | #4, #6 | API test expectations must match chosen gateway implementation. |
| `tools/browser_tool.py` | #13, #15 | Browser CDP redaction vs external browser ownership/cleanup. Review combined cleanup path; never terminate owner's externally managed browser. |
| `autopilot/ledger.py` | #1, #10 (stacked on an immutable #1-related snapshot) | Lifecycle/event model and recovery must be integrated against pinned parent SHA. |
| `tests/autopilot/test_ledger.py` | #1, #10 | Same test suite changed by parent and child; stale green CI is not a merged test result. |
| `gpt_companion/journal.py` | #12, #17, #23 (both later PRs stacked on #12) | Event causal semantics and trust/reconciliation behavior must be reviewed on a refreshed combined branch. |
| `docs/sdd/GPT_COMPANION_SDD.md` | #12, #17, #23 | Conflicting design decisions, not just file merge hunks. |
| `pyproject.toml` | #1, #9, #12, #13 | Packaging, module discovery and optional dependency changes can break isolation even if Python files differ. |

**Important:** these are *proposal collisions*, not proof of merge conflicts at Git level or deployed defects.

## Semantically overlapping, mostly disjoint code paths

| Functional lane | Existing PRs | Canonical decision needed |
|---|---|---|
| API idempotency / SSE gateway | #4, #5, #6, #11 | Exactly ONE canonical adapter, error status contract and regression suite |
| Observer / diagnostic journal | #8, #9, #12, #13, #16, #21, #25 (+ docs/companion revisions #17/#23) | One event schema, source provenance, authority boundary; one selected collector and one selected offline inspector |
| PR/merge collision guards | #14, #18, #22, #24 | Choose one maintained snapshot verifier; don't create 4 independent merge decision engines |
| Autopilot task authority | #1, #10 | Single ledger and task/effect source-of-truth; separate from observer |
| Security and execution | #2 (skills), #3 (ACP), #13/#15 (browser) | Approvals enforced at dispatcher, not in YAML/LLM text |
| Convergence SDD | #7, #8, #9, #14, #18, #19, #20, #22, #24 | Owner-selected canonical index / ADR registry; others are supporting evidence |

Contributing 25 parallel PRs without a merge arbiter is not equivalent to a scalable runtime. **New feature work on contested API, observer, tool ownership and SDD paths should be frozen for integration review**, or assigned explicit non-overlapping modules. This is a recommendation, not an administrative action performed here.

## Cross-agent source audit findings

**REVIEW-21 / actionable defect hypothesis:** `gateway/gpt_causal_observer.py` in PR #21 computes source gaps using `MAX(source_event_seq)-COUNT(*)`. An observer that began at 50,51,52 thus reports 49 missing events rather than 0 *internal* missing events with unknown prefix. Recommend `MAX-MIN+1-COUNT` plus a separate unknown-prefix coverage flag; add 50..52 and 50,52 regression fixtures. Comment submitted in PR #21.

**REVIEW-25 / contract mismatch:** Offline observer PR #25 requires `occurred_at_utc`, whereas the independent proposed inspector accompanying PR #19 requires `observed_at_utc`; limits, reason codes, exit codes and verification semantics also differ. Choose the canonical schema before attaching either to live producers. Comment submitted in PR #25.

**REVIEW-1 / trust boundary:** `autopilot/ledger.py` exposes `record_evidence(...trusted=True)` and `reconcile_effect(...proof_ref)` as trusted-control-plane methods with explicit docstring warning. **The ledger itself does not authenticate the caller.** Any adapter exposing these directly to untrusted tools/LLM input would allow self-certification. Require trusted gateway authorization and receipt provenance before wiring; this is an integration risk, not a claim that unsafe wiring is currently deployed.

**REVIEW-24 / candidate integrator:** PR #24 introduces `scripts/gpt_bridge_pr_gate.py` that validates snapshot schema, detects independent file collisions and checks stacked dependencies. PR #22 also proposes a live GitHub read-only integration guard. Evaluate their actual snapshot freshness, partial-list failure behavior, token exposure, output determinism and code ownership. Select one; do not add a competing authoritative scheduler.

## Recommended merge discipline

**Phase A — Freeze and authenticate snapshot:** record the exact main SHA, all head/base SHAs and filenames, expected branch ancestry, author/owner, and current CI check runs. A non-transactional GitHub scan should re-read heads and fail closed on drift. No false "all checked" when pagination errors out.

**Phase B — Ratify contracts:** API 409/422/in-flight/SSE; one event schema and allowed fields; approval/lease/result receipts; one local extension deployment version and Native Messaging policy. Capture decisions in one ADR register, then mark dependent PRs as superseded or stacked on pinned selected parents.

**Phase C — Integrate in isolated branch:** one integrator per contested path; rebase selected patches sequentially; review *combined* code rather than each PR alone. Preserve the owner's local worktree and credentials. Do not auto-push to main.

**Phase D — Verify exact merged candidate:** verify 100-way duplicate requests and client cancellation, 30–50 worker file/resource contention, crash after side effect before ACK, stale fence mutation, JSONL loss/duplicate/reorder, independent verifier at exact revision, MV3 service-worker restart, CDP external-browser preservation, Windows OS ACL and rollback. Require signed/authenticated evidence. A green "Devin Review" combined status is not a substitute for full code CI.

**Phase E — Authorized staged activation:** require owner/operator approval; release provenance, monitoring coverage, backout plan and quarantine of unknown external effects. Never use a ChatGPT chat turn as the long-running daemon.

## Snapshot limitations

At capture, `Local_WorkSpace.list_workspaces` still returned `Session terminated`. This is **a monitoring-access problem only**. Installed extension code, native host, browser sessions, Obsidian and real agent traces remain unverified. Open PR counts and paths are transient and must be refreshed before acting. All recommendations above are design/review gates, not proof of a live fault.

See `SDD.md` and `WORK_LOG_2026-11-22.md` for the evidence hierarchy, fault taxonomy and independent offline test results.
