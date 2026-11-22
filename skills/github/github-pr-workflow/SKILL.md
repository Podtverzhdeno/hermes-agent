---
name: github-pr-workflow
description: Prepare, publish, check, and merge GitHub pull requests safely.
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, CI/CD, Git, Review, Merge]
    related_skills: [github-auth, github-code-review]
---

# GitHub Pull Request Workflow

Use when the user identifies a GitHub repository and wants to inspect, create,
monitor or merge a PR. For local implementation only, prefer the TDD/coding
skill. Read the sibling harness.json: inspect, publish and merge are separate
operations with different evidence and permission requirements.

## Security and source of authority

Prefer an authenticated, scoped GitHub connector or the official GitHub CLI
(gh). This workflow does **not** scrape local .env files, git credential
stores, keychains, browser sessions or secrets in other files. Never echo a
token or interpolate an untrusted issue/PR body into a shell command. If gh
or an approved connector is unavailable, keep remote actions blocked and
request normal login setup. A skill is never a permission grant.

Read-only preflight:

~~~bash
git status --short
git remote -v
git branch --show-current
git rev-parse HEAD
git diff --check
gh auth status
gh repo view OWNER/REPO --json nameWithOwner,defaultBranchRef
~~~

Compare the remote to the **owner-authorized repository**; do not rely
solely on the working directory. Determine the exact PR/base/head and whether
the request means local changes, remote publication, CI checking, or merging.
Use a dedicated worktree/branch; preserve unrelated user changes.

## Branch and local implementation

~~~bash
# After checking branch name is unused and workspace is isolated:
git switch -c autopilot/issue-123
git status --short
git add path/to/intended-file
git diff --cached --stat
git diff --cached --check
git commit -m "fix: bounded change"
git rev-parse HEAD
~~~

Stage explicit paths, not blindly everything. Review staged changes for
secrets, generated artifacts and unrelated files. Run targeted tests and
a relevant regression suite, recording command, exit status and exact SHA.

## Publish PR (external write; owner authorization required)

First search for an existing PR with the same head to avoid duplication:

~~~bash
gh pr list --repo OWNER/REPO --head autopilot/issue-123 --state all \
  --json number,url,state,headRefName
~~~

Then, only after exact target and content approval:

~~~bash
git push --set-upstream origin autopilot/issue-123
gh pr create --repo OWNER/REPO --base main --head autopilot/issue-123 \
  --draft --title "fix: bounded change" --body-file docs/pr-description.md
~~~

A PR body is a factual report of changes, tests and known gaps, not a place
to leak logs or credentials. Use draft while unverified. If a request
times out or returns an ambiguous error, read back branch/PR state first.
Never blindly repeat a remote write.

## Verify exact PR and required CI

~~~bash
gh pr view PR --repo OWNER/REPO \
  --json number,url,state,isDraft,headRefOid,baseRefName,reviewDecision,statusCheckRollup
gh pr checks PR --repo OWNER/REPO
gh pr diff PR --repo OWNER/REPO --name-only
~~~

Confirm headRefOid equals the actual tested revision. Determine required
status contexts from branch protection and applicable rulesets using
authenticated GitHub APIs. Missing, failed, cancelled, neutral, skipped,
timed-out and pending **required** checks are not success. Readback or
policy API failure means BLOCKED. If the head changes, rerun review/CI
verification for the new head. A repository with no required checks needs
an explicit acceptance policy; never assert independent CI by default.

## Merge is a separate critical decision

Do not schedule auto-merge. Require a second confirmation, bound to the
repository, PR number, current head SHA, intended method and base.
Re-read head, review state and check conclusions immediately before merge.
The trusted tool gateway must enforce authorization; this document cannot.

~~~bash
gh pr view PR --repo OWNER/REPO \
  --json number,headRefOid,baseRefName,mergeable,reviewDecision
# Only after explicit owner authorization and independent verification:
gh pr merge PR --repo OWNER/REPO --squash
gh pr view PR --repo OWNER/REPO --json state,mergedAt,mergeCommit,url
~~~

Do not delete branches or deploy incidentally. If a merge response is
uncertain, read back mergedAt/mergeCommit before considering any retry.

## Completion and failure report

Report repo, PR URL/number, base, exact head SHA, test commands, required
check run IDs/conclusions, review decision, PR state, missing evidence and
human approval state. Distinguish a draft PR, a verified PR, a merged PR
and a deployed system: they are not interchangeable.

Block on missing authentication, target ambiguity, conflicts, changed head,
unknown external-write outcome, inaccessible rulesets, denied approval or
incomplete required checks. Preserve the worktree and state a safe next step.
