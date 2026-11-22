# Runtime authorization proof obligations (unimplemented in fork)

## Counterexample to policy-by-prompt
An instruction telling the model "do not send email" is not a verified
authorization boundary. Even a `pre_tool_call` policy hook cannot protect a
tool call it never sees, and a direct `terminal` execution can perform many
unclassified effects. Hermes upstream has fail-closed timeout behavior for
some `pre_tool_call` callbacks; do not misstate this as absent.

## Host-bound authorization record
```text
session_id, principal_id, profile_id, skill_invocation_id,
pinned_skill_digest, pinned_policy_digest, adapter_id, semantic_action,
provider_resource_id, provider_owner, expected_revision,
canonical_arguments_digest, effects, expiry, parent_delegation_id
```
All fields except the user's requested payload are host-derived or
provider-resolved. The agent cannot self-issue approval or construct HostScope.

**Approval:** separate trusted UI signs an exact canonical intent with Ed25519;
only a pinned public verification key may be in agent runtime. Reject ambiguous
base64url representations, replayed/expired signatures, wrong principal,
changed scope, changed policy, changed resource revision and altered payload.
The unsigned fixture-grant API is never reachable from a model-callable tool.

**State:** SQLite `BEGIN IMMEDIATE` reserves (principal, operation ID),
(principal, canonical intent) and consumes one-use approval in one transaction.
Transition `reserved -> dispatched -> verified|unknown` atomically and record
the transition *before* provider execution. On timeout after an irreversible
side effect, report `UNKNOWN`; reconcile with a trusted readback before
any operator-approved new operation. Native provider idempotency/CAS must
also enforce expected revision at write time.

**Scope:** deny unknown action, wrong account/repo, path traversal, symlink
or junction escape. Path.resolve() alone does not solve TOCTOU; use native
descriptor/handle-based enforcement and a restricted OS sandbox, especially
on native Windows. Never treat an MCP tool's self-declared readOnly annotation
as a trusted grant.

**Evidence:** result text and the model's own recap are not receipts. Require
an independent provider readback linked to the exact resource and version,
or leave the result unverified. Do not log credentials, message bodies or
approval tokens in telemetry.

## Go/no-go checks
- 0 wrong-principal/resource mutations across replay, restart and concurrent callers
- 0 duplicate email/Calendar/PR effects after ambiguous network failure
- Unwrapped terminal/MCP/delegation/browser/batch paths provably unable to bypass
- Linux and native Windows path attack and rollback tests
- Human approval UI and key custody verified out of process
- Provider sandbox integration and matched LLM eval vs unmodified Skill baseline
- Documented rollback + immutable/hashed audit; maintainers sign off

**Not demonstrated:** these proofs have not been run against this fork's
runtime. The separate prototype's 147 local tests cover only its own modeled
paths, with approximately 87% combined branch/statement coverage.
