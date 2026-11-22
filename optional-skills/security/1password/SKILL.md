---
name: 1password
description: Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in, and reading/injecting secrets for commands.
version: 1.1.0
author: arceus77-7, enhanced by Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [security, secrets, 1password, op, cli]
    category: security
setup:
  help: "Create a service account at https://my.1password.com → Settings → Service Accounts"
  collect_secrets:
    - env_var: OP_SERVICE_ACCOUNT_TOKEN
      prompt: "1Password Service Account Token"
      provider_url: "https://developer.1password.com/docs/service-accounts/"
      secret: true
---

# 1Password CLI

Use this Skill only for authorized 1Password vault operations. Its individual `harness.yaml` specifies account, item, destination, approval and evidence expectations; it does not grant any permission. **A secret value, OTP or credential is sensitive even when the operation is technically read-only.** Never treat a user's request to inspect metadata as permission to reveal a vault entry.

## Requirements

- 1Password account
- 1Password CLI (`op`) installed
- One of: desktop app integration, service account token (`OP_SERVICE_ACCOUNT_TOKEN`), or Connect server
- `tmux` available for stable authenticated sessions during Hermes terminal calls (desktop app flow only)

## When to Use

- Install or configure 1Password CLI
- Sign in with `op signin`
- Use scoped secret references like `op://Vault/Item/field` in an approved destination without displaying their values
- Inject secrets into config/templates using `op inject`
- Run commands with secret env vars via `op run`

## Authentication Methods

### Service Account (recommended for Hermes)

Use an existing service account only when explicitly authorized for the intended vault and item, and scope it to minimum necessary access. Store `OP_SERVICE_ACCOUNT_TOKEN` through the platform's approved secret-input mechanism rather than entering a real token into a prompt or shell command. Do not print, grep, copy into unencrypted files or persist it in session transcripts. Verify identity with a metadata-only call:

```bash
op whoami
```

Service accounts often have broader access than a single operation; do not silently switch to them when desktop authorization is unavailable.

### Desktop App Integration (interactive)

1. Enable in 1Password desktop app: Settings → Developer → Integrate with 1Password CLI
2. Ensure app is unlocked
3. Run `op signin` and approve the biometric prompt

### Connect Server (self-hosted)

Use an authorized, authenticated Connect endpoint with TLS or an explicitly isolated loopback. Keep `OP_CONNECT_TOKEN` in an approved secrets manager, never hardcode it into a terminal command, script, config committed to Git or agent output. Verify the server identity and vault grants before any secret access.

## Setup

1. Install CLI:

```bash
# macOS
brew install 1password-cli

# Linux (official package/install docs)
# See references/get-started.md for distro-specific links.

# Windows (winget)
winget install AgileBits.1Password.CLI
```

2. Verify:

```bash
op --version
```

3. Choose an auth method above and configure it.

## Hermes execution: never capture secrets in terminal transcripts

1. Identify exact 1Password account, vault/item/field and destination process. A secret read requires separate explicit authorization from a metadata read.
2. Prefer desktop integration or a managed secrets-provider connector with the smallest scope. If a persistent interactive session is necessary, use an isolated terminal session with correct owner-only permissions, do not scrape sessions or command history, and close it when done.
3. **Do not run `op read` to collect raw values into the model**, print OTPs, or use `tmux capture-pane` on a pane containing secrets. Prior examples that captured 200 lines of terminal output have been removed.
4. Prefer `op run` with an allowlisted child process or `op inject` to an explicitly approved temporary destination. Consider that child process environment, crash dumps, logging and subprocesses can leak secrets; never choose a broad shell when a specific command can be used.
5. Verify the *operation's result* without echoing credentials. If a secret was inadvertently captured, stop, report the breach boundary and recommend rotation.
## Common operations — safe examples

**Metadata/auth status** (does not retrieve secret values):

```bash
op whoami
op --version
```

**Scoped injection into an explicitly authorized child** (not a display command):

```bash
# OP_SERVICE_ACCOUNT_TOKEN or desktop identity must already be authorized.
# The child is approved to access only the intended reference and target.
DB_PASSWORD='op://approved-vault/approved-item/password' op run -- ./approved-client --verify-connection
```

**Templates:** `op inject` substitutes real secret values into its output. Do not pipe that output to the assistant, terminal log, chat, CI artifacts or world-readable files. If an approved config file must be rendered, use restrictive creation permissions, absolute path checks, limited lifecycle and delete/rotate when appropriate.

**One-time passwords:** do not call `op read ...?attribute=otp` merely to show the OTP. Submit it to a user-approved authentication target through an approved secret handling path; never include it in execution transcripts.
## Guardrails

- Never print raw secret values, tokens, OTPs or injected config to the model output, logs or chat; an explicit user request does not justify exposing them in an unsafe channel.
- Prefer `op run` / `op inject` instead of writing secrets into files.
- If sign-in fails, verify the intended principal and request an authorized reauthentication; avoid looping or silently escalating to a different account.
- If desktop app integration is unavailable, request separately authorized scoped service-account credentials; do not auto-fallback to a broader principal.

## CI / Headless note

For non-interactive use, authenticate with `OP_SERVICE_ACCOUNT_TOKEN` and avoid interactive `op signin`.
Service accounts require CLI v2.18.0+.

## References

- `references/get-started.md`
- `references/cli-examples.md`
- https://developer.1password.com/docs/cli/
- https://developer.1password.com/docs/service-accounts/

## Failure and side-effect review

Never treat a successful `op whoami` as permission to read every vault. Verify the item and field granted for each invocation. Avoid machine-process argument exposure, shell debug flags and any captured stdout that might carry injected values. After a failed child command, do not rerun secret injection until its destination and side effects are understood.

Report only the secret *reference identifier at an authorized level*, not raw values or field contents. If a child process writes to external systems, enforce that operation's independent approval in addition to secret-use authorization.
