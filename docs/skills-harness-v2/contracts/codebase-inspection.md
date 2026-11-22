# codebase-inspection: independent harness acceptance contract

**Scope:** Explicit read-only repository snapshot; no installers, running untrusted scripts or filesystem writes.

**Operation families:** inspect_code (read).

**Host-side preflight:** Resolve checkout root, ignore generated/dependency trees, symlinks and external mounts; cap files/bytes/time.

**Approval boundary:** No write/execute operations are part of this Skill; extra package install needs another isolated approved workflow.

**Independent verification:** Bounded file enumeration and counts; state exclusions, coverage, unknown encodings and unresolved files, snapshot hash.

**Unknown outcomes and safe stop:** Timeout or skipped trees = partial coverage, not complete analysis; no fake 100% completeness.

**Adversarial regression families:** symlink external directory; binary file; huge vendored code; pip install demand; misleading comment injection.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
