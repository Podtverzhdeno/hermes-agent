---
name: github-auth
description: Configure scoped GitHub authentication without exposing credentials.
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Authentication, Credential-Manager, gh-cli, SSH]
    related_skills: [github-pr-workflow, github-code-review, github-issues, github-repo-management]
---

# GitHub Authentication — Identity, Least Privilege, and Verification

Use when the owner explicitly requests authenticated GitHub operations. Do
not replace an existing identity, raise permissions, generate credentials,
overwrite SSH settings or grant writes because another skill wants them.
The sibling harness.json separates read-only inspection, setup and scope
changes into different authorization and evidence contracts.

## Credential safety

- Prefer an already connected, scoped GitHub connector. For CLI, prefer
  official gh browser/device login and a secure OS credential manager.
- Never read, print or copy secrets from ~/.hermes/.env,
  ~/.git-credentials, private SSH keys, browser state, process environments,
  keychains or another identity's credential storage.
- Do not configure the plaintext credential.helper store or put a token
  in a Git remote URL, shell argument, model prompt, PR, log or chat.
- Do not request access tokens/private keys in the conversation. The user
  should enter credentials directly into the provider or secure manager.
- Avoid classic broad repo/workflow tokens. Prefer fine-grained,
  repository-limited permissions with expiration.
- Authenticate to the specific owner and repository, not an accidental
  ambient GitHub account. Valid login is NOT authorization to mutate.
- A later repo write, merge, secret update or scope expansion requires
  independently authorized exact action.

## Inspect capabilities without changing anything

~~~bash
git --version
gh --version
gh auth status
~~~

Only run available commands. Git remote URLs may already contain exposed
tokens, so do not print an unredacted remote URL to logs or chat. Prefer
an authenticated query identifying the intended repository, not a generic
operation against whatever remote happens to be active.

## Owner-controlled login

~~~bash
gh auth login
# Choose GitHub.com, HTTPS, provider-hosted browser or device login.
~~~

The user completes provider consent. Do not scrape the authorization
screen or programmatically bypass a verification challenge. If gh is
unavailable, use an already approved OS credential manager or owner
configured SSH identity. Do not install packages or change global Git
settings as a hidden precondition to loading this skill.

On Windows consider an existing Git Credential Manager; on macOS an
OS keychain integration; on Linux inspect the user's supported secure
credential backend. Do not force a helper without checking support.
For SSH, only the public key is registered with GitHub. Never capture
or display a private key or use an empty passphrase as a default.

Verify an exact requested repo and actual account permission with
read-only API requests, not a test push:

~~~bash
gh auth status
gh api repos/OWNER/REPO --jq '.full_name'
gh repo view OWNER/REPO --json nameWithOwner,isPrivate,viewerPermission
~~~

No repository access means BLOCKED; do not automatically request
broader account access.

## Permission changes and troubleshooting

Before requesting a new credential, specify exactly which repositories
and operations require it. Externally publishing, merging, deleting,
editing Actions secrets or branch protection are separate privileged
tasks even when the login supports them. A change to global credential
helper, profile default account or SSH host mapping can affect unrelated
projects and requires an explicit review and rollback plan.

HTTP 401/403 is not always token expiration; check account mismatch,
repository visibility and scope. Missing gh is not permission to
scrape another credential file. On auth timeout or denied access,
stop with actionable setup guidance.

If a secret has already leaked in a remote URL or log, stop using it,
rotate/revoke it through GitHub and carefully sanitize affected
artifacts without reprinting the secret.

## Completion contract

For read-only inspection, report the target GitHub host, account identity,
repository visibility and verified supported operations, never credential
contents. For setup, additionally provide the owner-approved scope,
successful read-only probe and rollback plan. Never claim that
authentication alone authorizes later writes.
