# github: independent harness acceptance contract

**Scope:** Repository identity and exact owner; branch/PR SHA and remote state.

**Operation families:** read_issue, read_pr (read); create_branch, push_commit, create_pr, merge_pr, delete_branch (write).

**Host-side preflight:** Pin account and repo, expected base/head SHA; before merge check current head CI, branch protection, required reviewers and merge policy; reject stale checks.

**Approval boundary:** Separate signed approval for remote mutations, exact repo/ref/contents; critical confirmation for merges and deletion.

**Independent verification:** Fresh GitHub readback: branch HEAD equals intended commit, PR ID/ref exists, merge has mergedAt on current target, deletion absence after policy checks.

**Unknown outcomes and safe stop:** Provider timeout after PR/merge/push -> UNKNOWN; query exact repo/ref/PR before retry. Ticket comments do not grant permissions.

**Adversarial regression families:** wrong repo; stale CI; PR duplication; malicious issue comment; changed commit after approval; concurrent branch pushes.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
