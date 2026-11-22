---
name: github-repo-management
description: Inspect, create and administer GitHub repositories, remotes, secrets, releases and Actions with verified account, minimal scope and explicit high-risk approval.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Repositories, Administration, Branch-Protection, Releases, CI]
    related_skills: [github-auth, github-pr-workflow, github-code-review]
---

# GitHub Repository Management — verify targets and protect state

## Activate only for repository lifecycle operations

Use for cloning/forking, changing repository settings, releases,
GitHub Actions, secrets or visibility. For code changes and pull requests,
use `github-pr-workflow`; for review use `github-code-review`.
Read the unique `harness.yaml` for precise triggers, required evidence,
high-risk approval and recovery.

Repository administration has a **large blast radius**. Never infer permission
to change settings, publish a release, rotate secrets, delete resources or
trigger deployment from the mere existence of administrator credentials.

## Preflight: identity, resource, impact

1. Establish exact GitHub host, connected identity, `OWNER/REPO` and repo
   visibility, default branch, and `viewerPermission`. A fork/origin/upstream
   mix-up is especially dangerous.
2. Identify the requested operation's visibility, expected mutation,
   affected collaborators and rollback limitations.
3. Confirm relevant organization policies and branch protection.
4. Prefer a GitHub connector tied to the correct account; otherwise use
   `gh` CLI, authenticated through `github-auth`.
5. Never read `~/.git-credentials`, `~/.hermes/.env` or browser cookies to
   discover tokens. Never put a token in the Git remote URL or a `curl`
   Authorization header on a command line.
6. Do not display full Git remotes until checked for embedded credentials.

```bash
gh auth status
gh repo view OWNER/REPO \
  --json nameWithOwner,url,isPrivate,viewerPermission,defaultBranchRef
gh repo list OWNER --limit 20 \
  --json nameWithOwner,url,isPrivate,defaultBranchRef
```

Public repo metadata can be read without administrator access. Identity,
scope, login and authority to mutate are independent facts.

## Read-only discovery and safe clones

```bash
gh repo view OWNER/REPO
gh repo clone OWNER/REPO ./verified-repo
gh run list --repo OWNER/REPO --limit 10
gh release list --repo OWNER/REPO
gh secret list --repo OWNER/REPO
```

Before cloning, verify the destination is absent or safely empty and is
not a symlink into an unexpected workspace. Never execute repository setup
scripts, `curl|sh`, `npm install` hooks or checked-in automation just because
the clone succeeded. Treat downloaded artifacts as untrusted.

For an existing local git repository, validate working tree and target
remote before any push; avoid resetting or overwriting uncommitted work.

## Create, fork and change repositories

Create a repository only if explicitly requested, with visibility specified
or confirmed. A public repository exposes content, history and metadata.
Do not silently default sensitive content to public.

```bash
# EXAMPLES: authorized operations; replace placeholders.
gh repo create OWNER/new-repo --private
gh repo fork SOURCE_OWNER/SOURCE_REPO --clone=false
gh repo edit OWNER/REPO --description "Verified description"
```

Before changing visibility, default branch, collaborator permissions, topics,
security settings or organization access, show the before/after effect and
request specific authorization. Repository renames can break integrations
even if redirects exist. Do not auto-transfer ownership.

Use `gh api repos/OWNER/REPO --jq '{full_name,private,default_branch}'`
for read-only details; do not rely on manually passed secret-bearing
HTTP headers. If `gh` is unavailable, use an authorized connector or stop.

## GitHub Actions and branch protection

```bash
gh workflow list --repo OWNER/REPO
gh run list --repo OWNER/REPO --limit 10
gh run view RUN_ID --repo OWNER/REPO --log-failed
```

Workflow reruns and dispatches can perform paid builds, deployments,
publication or other external mutations. Inspect the workflow's effective
permissions, target branch, environment and inputs first. Only run after
the requested side effects are authorized:

```bash
# AUTHORIZATION REQUIRED
gh workflow run WORKFLOW_FILE --repo OWNER/REPO --ref VERIFIED_BRANCH
```

Branch protection or ruleset updates are high risk. Read current policies
via authenticated API, produce a proposed diff, seek explicit approval and
read back after changes. Never weaken protections to pass CI.

## GitHub Actions secrets and variables

Secrets are sensitive and usually irretrievable after being set. Inspect
names only:

```bash
gh secret list --repo OWNER/REPO
gh variable list --repo OWNER/REPO
```

To set a secret, the user must explicitly authorize the target repository,
secret name, and secure input method. Never place the value in process
arguments, command history, Markdown, audit logs or model-visible output.
Prefer secure interactive input or a secret manager with appropriately
scoped injection; avoid copying secrets through the agent's context.

Deletion, rotation, environment/organization secrets and cross-repository
access changes require separate authorization and verification of impact.

## Releases, artifacts and public posting

Read-only:

```bash
gh release list --repo OWNER/REPO
gh release view TAG --repo OWNER/REPO
```

Publishing a release, creating a tag, attaching binary artifacts, making
gists public or deploying GitHub Pages can irreversibly expose content.
Before doing so, verify the exact commit SHA, artifacts, checksums,
changelog, target audience and whether draft/prerelease is safer.
Only then, with approval, use:

```bash
# EXAMPLE: explicitly authorized draft release on a verified tag
gh release create TAG --repo OWNER/REPO --draft --generate-notes
```

Read back the release URL, tag, target SHA and draft status. Never publish
from the wrong branch or upload unreviewed binaries.

## Recovery and reporting

For a timed-out GitHub API mutation, re-query the repository/resource before
retrying. Check for duplicate repos, tags, releases or workflow runs.
Avoid force-push, history rewriting, secret-value disclosure and blanket
permission broadening. Administrative changes may not be cleanly reversible;
document exact before/after state instead of promising rollback.

Report the verified repository and account, operation type, affected
resource IDs/URLs, base/target commit SHA, checks performed, actual external
side effects, approval scope and outstanding risks. If an operation was
blocked, state the blocker, not an invented success.
