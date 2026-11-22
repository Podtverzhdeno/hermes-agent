# hermes-agent: independent harness acceptance contract

**Scope:** Exact Hermes profile/home, config path and trusted extension directory; secrets separate.

**Operation families:** read_config (read); edit_config (write).

**Host-side preflight:** Check active profile identity, config schema and pinned bytes; save reversible backup and verify doctor/daemon state.

**Approval boundary:** Signed exact path/config change with host profile binding; never expand grants due to a Skill's own instructions.

**Independent verification:** Re-read applied config, confirm profile and instance health; rollback atomically on invalid config; no token leakage.

**Unknown outcomes and safe stop:** Plugin/hook collision or stale profile -> halt; unknown side effect cannot be waved away by a friendly summary.

**Adversarial regression families:** profile switch; untrusted plugin; .env leak; hook timeout; wrong gateway; broad write request.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
