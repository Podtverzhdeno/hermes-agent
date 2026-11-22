# Hermes GPT — SDD integration index (proposed)

> **Read before modifying GPT, Chrome extension, API ingress, Autopilot, ACP or event journals.** This index is a proposal on a docs-only branch, **not an adopted runtime contract**. Upstream/owner approval and CI remain mandatory. Peer SDDs are not merged into `main` and must not be presented as operational instructions.

## Canonical integration decision candidate

- [2026-11-22 GPT/Hermes convergence and action-level diagnosis](integration-control/2026-11-22-hermes-gpt-convergence.md) — observed fork defects, branch-collision evidence, proposal for authoritative ledger and observer separation, event states/ACK ladder, safety gates, candidate-level review of PRs #5 and #6, failure-injection matrix, engineering log, measured-vs-proposed legend.
- **Decision status:** PROPOSED. This document is the review entrypoint for cross-branch decisions, **not** a command to merge everything or the source of truth for live task state.

## Reviewable parallel drafts — explicitly not yet canonical

| Candidate | Topic | Rule |
|---|---|---|
| PR #1 + stacked PR #10 | Autopilot authority, effect ledger and read-only diagnostics | Only one authoritative task/effect state machine; verify crash-fence invariants |
| PR #2 | skill harness advisory contracts | No model-supplied privilege escalation |
| PR #3 | ACP per-session approval isolation | Independent security review before enabling unattended concurrency |
| PR #4 + stacked PR #11 | API observability, keyed-stream preflight | Compare with PR #5/#6, never merge entire handlers by concatenation |
| PR #5 | single-flight cache and HTTP API | **Block uncertain-effect re-execution after exception** (see §2.2 convergence SDD) |
| PR #6 | alternate API cache and streaming | **Bind identity to authenticated principal + session** and cap streaming queue |
| PR #7 / PR #8 | causal SDD and trace doctor proposals | Reconcile schemas and historical extension caveats |
| PR #9 / PR #12 | alternative read-only GPT event inboxes | Must not emit authoritative task success or approvals |
| PR #13 | CDP failure diagnostics | No live deployment claim; extension is separately hosted and currently unreachable |
| `feat/gpt-integration-collision-gate-20261122` | GitHub changed-path pre-merge audit | Pre-merge warning gate only, not CI/merge approval |

### Reporting convention

Every change proposal must include `observed_fact`, `source_SHA`, `uncertain_effects`, `root_cause_hypothesis`, `disproving_test`, `safe_fix`, `verification_run`, `rollback`, `owner`, and `next_review`. Never print private prompts, passwords, cookies, raw DOM or full tokens to work logs. Record `LOCAL_MCP_UNAVAILABLE` rather than fabricated browser health if the local connector is down.

### Integration acceptance

A reviewer must independently check at an **exact merged commit**: HTTP multi-principal idempotency, streaming error/backpressure, stale leases, event/outbox atomicity, approval isolation, source-compatible build/wheel, integrity of the owner's local worktree, explicit consent for Chrome/CDP, and synthetic fault injection.

**Current blocker (2026-11-22):** Local_WorkSpace MCP returned `Session terminated`. Deployed Windows companion, Chrome extension and persistent Obsidian logs have not been inspected in this review. GitHub Issues are disabled; use draft PR reviews and committed SDD changelogs.
