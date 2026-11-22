# Individual Skill Harness — v2 proposal

> **Status: design and reproducible local prototype, not Hermes runtime enforcement.**
> This branch is stacked on the existing advisory-harness PR #31. It does **not**
> weaken or replace its `harness.json` validation, nor install executable hooks.

This proposal deliberately splits: (1) untrusted instructions and routing,
(2) host-minted authenticated Skill identity and resource grants,
(3) exact semantic action contracts, and (4) independently verified external effects.
A Skill file, retrieved comment or tool result can never grant permission.

The offline reference prototype separately exercises **8 specialist domains,
28 semantic operations and 147 unit/SQLite-fixture checks**, with a proposed
80-scenario authored routing and abuse set. **None** of those tests is a live
Hermes/provider integration test or a measured LLM improvement.

## Integration approach

1. Preserve existing `agent/skill_harness.py` advisory behavior.
2. Add an opt-in, isolated host-side operation broker (not another prompt parser).
3. Derive principal, skill identity, profile and delegation ancestry from the
   trusted runtime; never from the language model's tool arguments.
4. Map each vetted adapter to a typed operation and provider-resolved target;
   validate resource owner and current ETag/HEAD/file identity.
5. Require isolated signed approvals for effectful actions and reserve a durable
   journal record **before** executing effects.
6. Verify provider state independently; unknown outcomes remain blocked pending
   reconciliation, not retry.
7. Cover *every* relevant tool path: direct, batch, MCP, terminal, delegated,
   gateway, resumed and custom/plugin handlers; otherwise do not label it secure.
8. Roll out by read-only instrumentation, then shadow tests, then controlled
   deny mode. No permissions widen through automatic Skill self-improvement.

## Merge and collision notes

PR #31 already edits `agent/skill_harness.py`, `skill_view`, prompt routing and
skill-local `harness.json`. PR #32 changes domain procedures and alternative
manifest/eval surfaces. This branch touches only **new docs**, avoiding concurrent
edits to those files; reconcile naming/schema and exact baseline before merging.
No CI or deployment success is implied by this document.

See [runtime proof specification](RUNTIME_SECURITY_PROOF_SPEC.md),
[evaluation protocol](SPECIALIST_EVAL_PROTOCOL.md), and independent specialist contracts
under `contracts/`.
