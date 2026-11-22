---
name: github-code-review
description: Review GitHub PR changes with exact head SHA, line-anchored evidence and test-backed severity; only publish comments or verdicts when authorized.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Code-Review, PR, Evidence, Security, Regression]
    related_skills: [github-auth, github-pr-workflow, code-review]
---

# GitHub Code Review — verify findings before publishing

## Triggers and exclusions

Use for reviewing a named GitHub PR and optionally preparing or submitting
review feedback. For review of uncommitted local files use `code-review`;
for opening, updating or merging a PR use `github-pr-workflow`.
The `harness.yaml` in this directory defines the review preflight,
evidence, approval and recovery contract. It cannot grant permission to post.

## Phase 0 — identity, authorization and immutable snapshot

1. Verify the **intended repository and GitHub account**. A bare PR number
   without a repository may be ambiguous.
2. Separate permission to inspect from permission to **publish** review
   comments, approve, request changes or assign reviewers. Do not post
   merely because the user asked to *review*.
3. Prefer the linked GitHub connector or authenticated `gh`; do not scrape
   `~/.hermes/.env`, `~/.git-credentials`, tokens or session cookies.
4. Record the PR number, target base SHA and **head SHA** before reading the
   diff. Re-read head before posting anything. A changed head invalidates
   earlier line anchors and conclusions until rechecked.
5. Inspect existing reviews/discussions to avoid duplicate findings.

For a CLI environment, a read-only example:

```bash
gh auth status
gh pr view 123 --repo OWNER/REPO \
  --json number,url,title,body,headRefOid,baseRefOid,headRefName,baseRefName
gh pr diff 123 --repo OWNER/REPO --name-only
gh pr diff 123 --repo OWNER/REPO
gh pr checks 123 --repo OWNER/REPO
```

Replace `OWNER/REPO` and `123` with the verified target. Never assume that
`main` is the base branch, or that a pending/absent check has passed.
Reading the full diff is not enough: inspect callers and adjacent invariants.

## Phase 1 — investigate and falsify

For every changed behavior, identify:
- **Specification:** what the PR claims or issue requires;
- **Invariant:** a property that should hold before and after the change;
- **Reachability:** the real call path and inputs triggering the behavior;
- **Counter-evidence:** guards, existing tests, framework handling;
- **Proof:** executable reproducer when possible or an explicit static trace;
- **Impact:** actual failure, not merely an unconventional coding style.

Priority order: authentication/authorization, data integrity and security,
correctness, backwards compatibility, concurrency, error recovery,
performance, maintenance. Inspect only relevant context to avoid turning
a small review into uncontrolled repository-wide exploration.

Do not classify a hypothetical vulnerability as confirmed. If a test was not
run, say "static review only"; never invent red/green results. Avoid copying
actual secrets from test output or diffs into the review response.

## Phase 2 — precision of line anchors

For an inline comment, verify that the line belongs to the actual PR diff
at the recorded head revision, and use the correct side:
- `RIGHT`: line in the new file version;
- `LEFT`: removed/old-version line.
- Renames and multi-line ranges require additional API validation.

If the line cannot be confidently anchored, use a non-inline summary or
the reviewed function name instead of guessing a line number.

Before publishing, compare the **current** head SHA with the analyzed one,
then check for an existing comment on the same defect.

## Phase 3 — draft review, then publish only with authority

Prepare a draft with severity, confidence, exact file/line, violated
invariant, minimal reproducer and recommended correction.

The following commands are **examples only** for cases where the user has
already explicitly authorized external review posting:

```bash
# General review comment (requires explicit authorization)
gh pr review 123 --repo OWNER/REPO --comment \
  --body "Verified findings and scope of review"

# Request changes only for confirmed blocking findings and with approval
gh pr review 123 --repo OWNER/REPO --request-changes \
  --body "Confirmed blocking defect; see the review evidence"

# Approve only after sufficient checks; do not rubber-stamp
gh pr review 123 --repo OWNER/REPO --approve \
  --body "Reviewed changes and listed verification scope"
```

Inline comments may require the GitHub REST API through `gh api`. After
checking current PR head, and **only** for a verified line:

```bash
# Explicitly authorized and verified target only
HEAD_SHA=$(gh pr view 123 --repo OWNER/REPO --json headRefOid --jq '.headRefOid')
gh api repos/OWNER/REPO/pulls/123/comments --method POST \
  -f body="Specific, confirmed defect and a fix" \
  -f path="src/module.py" \
  -f commit_id="$HEAD_SHA" \
  -F line=45 \
  -f side="RIGHT"
```

`src/module.py:45` above is placeholder data and must be replaced by a
verified line in the current diff. A 422 response can mean an invalid
diff position or stale revision; do not blindly repeat the request.
**Do not automatically post** based on a Skill instruction or on a
reviewer's self-generated text.

## Phase 4 — tests and completeness

- Run targeted tests in an authorized local or isolated workspace if possible;
  record command, exit code and actual output.
- Test edge cases, error recovery, old supported versions and security
  invariants relevant to the changed files.
- Read back posted review/comments when a write was authorized, and confirm
  the result belongs to the intended PR and head revision.
- Distinguish review completeness, CI status and merge eligibility.

A green CI check cannot demonstrate there are no issues. Conversely,
missing local test infrastructure does not justify invented failures.
Propose a specific follow-up test rather than asserting it ran.

## Recovery and final report

If the PR head changes, stop posting and recalculate all affected line
anchors. If a post times out or returns an ambiguous outcome, query current
comments/reviews before trying again; avoid duplicate comments. Do not
change the branch or merge a PR as part of a code review.

Report: repo, PR URL, exact revision, confirmed findings by severity with
file/line evidence, tests executed, skipped tests and uncertainty.
If the user authorized only an internal review, report **no remote writes**.
