---
name: 1password
description: Safely use existing 1Password CLI identities and scoped secret references.
version: 1.1.0
author: arceus77-7, enhanced by Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [security, secrets, 1password, op, cli]
    category: security
---

# 1Password CLI — Owner-Controlled Secret Access

Use only when the owner explicitly requests work with an approved
1Password account, vault and item. Read sibling harness.json for
different inspection, secret retrieval and command injection
permission requirements.

A Skill should not require a secret merely to load, so this document
does not automatically collect OP_SERVICE_ACCOUNT_TOKEN. Never place
secret values, recovery codes, service-account tokens, one-time codes,
or private key material into a model prompt, CLI argument, verbose log,
Git commit, issue or chat message.

## Identity and scope

- Prefer official 1Password desktop integration with an existing user
  login and owner-controlled approval, or a separately configured
  restricted service account using the provider's secure storage.
- Bind every secret operation to the specific account/vault/item/field
  and intended consuming process; do not enumerate all vaults by default.
- Treat an op:// reference as a **secret locator** even if it does not
  contain the secret value. Never publish references describing private
  account structure unnecessarily.
- Do not automatically install or enable a provider integration from a
  retrieved webpage. Verify the CLI binary and official documentation.
- A trusted tool or OS broker must enforce access. A natural-language
  instruction to avoid printing secrets is insufficient isolation.

## Safe read-only preflight

~~~bash
op --version
op --help
~~~

Do not run commands that list all items or reveal values simply to
test whether the CLI exists. If sign-in is required, the user completes
the official provider flow without disclosing credentials in chat.
If a vault or field is not authorized, report BLOCKED.

## Authorized secret use

Separate three distinct operations: checking a reference's existence,
retrieving a secret value, and injecting a secret into an approved child
process. Retrieval and injection should require exact owner consent.
If needed, use official op run/op inject mechanisms with a trusted
scoped process and ensure values never enter transcript, debug output
or command arguments. Avoid exporting a raw long-lived service-account
token in shell history.

For a service account, prefer a noninteractive trusted credential
store backed by the host (not a hard-coded config.yaml value). Confirm
the account's vault access is minimal and expires/rotates appropriately.
Do not infer that environment access alone authorizes disclosure.

## Verification and recovery

Check only operation success/failure, intended target identity and
whether the approved process could start. Do **not** emit secret
contents as evidence. If a command times out or auth fails, do not
repeat a mutation or widen scope. Invalid/rotated tokens require
owner-controlled renewal. Suspected exposure requires immediate
revocation/rotation through 1Password and redaction of leaked logs.

The completion report must contain access decision, target identity
(redacted where appropriate), actual operation, independent status
receipt, and unresolved permission gaps. It must never contain
the secret value.
