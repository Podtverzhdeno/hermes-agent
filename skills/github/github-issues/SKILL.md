---
name: github-issues
description: Safely search, triage, create and update GitHub issues through the connected GitHub provider or authenticated gh CLI, with evidence and controlled external writes.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Issues, Project-Management, Bug-Tracking, Triage, Security]
    related_skills: [github-auth, github-pr-workflow, github-code-review]
---

# GitHub Issues — auditable triage and controlled mutations

Use this skill only for GitHub **issues**. Use `github-code-review` for review comments on a PR and `github-pr-workflow` for branches and PR lifecycle. Follow the individual `harness.yaml` for routing, evidence and recovery. It is **advisory**, not a grant of write access.

## 1. Preflight: identity, scope and authority

1. Identify the **intended linked GitHub account** and exact `OWNER/REPO`. Do not guess from the current directory if multiple accounts or remotes exist.
2. Verify repository access with the connected GitHub provider, or an existing authorized `gh` session. For CLI inspection, `gh auth status` and `gh repo view OWNER/REPO --json nameWithOwner,url` are read-only.
3. Determine whether the user requested read-only triage, drafts or **actual remote mutations**. Opening, closing, labeling, assigning and commenting are writes visible to collaborators. Especially avoid bulk or destructive actions without explicit task scope.
4. Read the issue's current state, comments, labels, assignees and linked PRs. Search for duplicates before creating anything.

**Never** scrape tokens from `~/.hermes/.env`, `~/.git-credentials`, credential stores or browser files. Never embed API tokens in a URL, shell argument, script, git remote, log or chat output. Prefer provider-managed authenticated actions; if unavailable, report the authentication blocker rather than exposing a secret.

## 2. Read and search before changing anything

Use a connected GitHub search/read operation when available. CLI equivalents:

```bash
gh auth status
gh repo view OWNER/REPO --json nameWithOwner,url
gh issue list --repo OWNER/REPO --state open --limit 100
gh issue list --repo OWNER/REPO --state all --search "authentication" --limit 100
gh issue view 42 --repo OWNER/REPO --json number,url,title,body,state,labels,assignees,comments
```

Choose the smallest relevant query. Paginate when the repository has more matching issues than one page. The GitHub REST `/issues` listing also includes pull requests: filter those out during issue-only triage.

## 3. Draft an evidence-backed triage decision

For each issue: reproduce or link evidence, classify its actual type (bug, request, question, duplicate), and recommend priority based on severity, blast radius and urgency rather than rhetoric. Check labels that actually exist in the repository. Do not claim a bug is reproduced unless a test was executed.

Avoid assigning people speculatively. Record the intended change as a small before/after diff and review it for duplicate work, incorrect repo/issue ID and unrelated changes.

Suggested issue structure:

```markdown
## Summary
Observed behavior with source or reproduction evidence.

## Reproduction / Context
Steps, runtime version, and what was actually checked.

## Expected vs. actual
Explicit, falsifiable expectation.

## Impact / Acceptance
Affected scope, fix acceptance checks, and unknowns.
```

## 4. Apply only authorized writes

Where a linked GitHub action is available, use it rather than extracting raw credentials. CLI examples for **explicitly requested** mutations:

```bash
gh issue create --repo OWNER/REPO --title "Reproducible issue summary" --body-file issue.md
gh issue edit 42 --repo OWNER/REPO --add-label "bug"
gh issue edit 42 --repo OWNER/REPO --add-assignee USERNAME
gh issue comment 42 --repo OWNER/REPO --body-file triage-comment.md
gh issue close 42 --repo OWNER/REPO --reason completed
gh issue reopen 42 --repo OWNER/REPO
```

Use verified IDs and only existing labels. A pull request's `Fixes #42` or `Closes #42` may close an issue after merging; distinguish this automatic behavior from closing it now. Do not batch-close by label without an independently reviewed, explicit allowlist of issue IDs.

## 5. Verify every remote change

After a create/edit/comment/close, **read back** the exact issue and confirm the expected state, issue URL, labels, assignees and comment IDs. Classify operations as verified success, verified failure, unchanged, or **uncertain**; a tool returning HTTP 2xx alone is not proof that all intended effects occurred.

If a write times out or returns an ambiguous error, query issues and comments before retrying. Blind retries of creation/comments can create duplicates. A GitHub CLI authentication or permission failure should not trigger credential scraping.

## 6. Report and recover

Return issue links, the exact `OWNER/REPO`, affected issue IDs, before/after summary, approved side effects, read-back evidence, unresolved uncertainties and operations deliberately not performed. Preserve unrelated labels/comments and user edits. For bulk triage, report individual failures; never mark the batch fully complete when only some issues succeeded.

**Acceptance gates:** correct GitHub identity and target; no credential disclosure; no unrequested external write; every claimed mutation has a provider read-back; uncertain retries are reconciled.
