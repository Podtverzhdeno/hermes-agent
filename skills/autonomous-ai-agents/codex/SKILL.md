---
name: codex
description: Delegate bounded coding tasks to Codex with independent verification.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Coding-Agent, Codex, OpenAI, Code-Review, Refactoring]
    related_skills: [claude-code, hermes-agent]
---

# Codex CLI — Bounded, Permissioned Tasks

Use for an explicit owner-requested coding task when the Codex CLI is
already installed and permitted. Read sibling harness.json: read-only
review and autonomous implementation have very different risk/approval
requirements. Do not launch a coding agent merely to gather a
short factual answer.

## Preflight and authority

1. Verify the installed Codex executable/version, legitimate account,
   provider and cost/quota. Do not auto-install global packages or
   trigger browser login without user action.
2. Pin repository, exact head SHA, branch/worktree and expected output.
3. Require owner permission for autonomous shell/file writes; enumerate
   directory and network scope. Use a dedicated isolated worktree,
   not a shared dirty main checkout.
4. Establish budget: maximum iterations, wall-clock time, API spend,
   allowed commands, child count and explicit stop conditions.
5. Keep external publishing, secrets, production deployment, process
   execution outside the task and critical actions on separate approvals.

**Never use --yolo, --dangerously-bypass-approvals-and-sandbox or other
flags that disable normal approval/sandbox enforcement.** Avoid
--full-auto unless the sandbox genuinely restricts all relevant
capabilities and the owner has explicitly approved that execution mode.
Hermes must not assume its own permission prompts automatically
govern what an external CLI subprocess performs.

## Short read-only review

Use the CLI's documented read-only mode for the installed version and
a task-specific prompt; verify that mode genuinely prevents writes.
Do not assume a natural-language "don't edit" instruction is a
security sandbox. If read-only execution cannot be enforced through
the actual CLI and OS environment, block automated delegation.

Example brief (data, not a shell command):

~~~text
Repository: authorized owner/repo
Pinned head: exact SHA
Scope: review files in src/
Permission: read only
Expected output: findings with line references, no modified files
Budget: one bounded attempt
~~~

Inspect worktree before and after; record agent version, exit code and
actual output. A fluent review response is not proof that the repository
was unchanged or completely reviewed.

## Authorized implementation

1. Give the CLI a narrow acceptance contract, not an entire conversation.
2. Launch with an approved sandbox, isolated working directory and
   limited tools; pass explicit timeout and iteration/token budget.
3. Capture worker PID/session identity, process logs and stderr without
   secrets. Monitor cancellation and terminate owned subprocesses if
   requested.
4. After process completion, inspect git status/diff and enumerate all
   files actually written. Tests must run independently of the agent.
5. Require separate GitHub authorization before any push, PR or merge.
   Never use unreviewed child output as a source of tool permissions.
6. After a crash or timeout, preserve worktree state and reconcile
   possible external operations; do not blindly spawn another worker.

For work spanning multiple sessions, prefer durable Hermes Kanban
on a compatible upstream rather than assuming an in-process delegated
child survives gateway termination. A child review is not equivalent to
a durable task record.

## Completion report

Return pinned SHA, actual worktree path, CLI version, bounded execution
details, changed files, diff hash, test commands/exits and critical
findings. Mark tests, review and deployment separately. If permissions,
account or sandbox cannot be verified, report blocked instead of
turning off protections.
