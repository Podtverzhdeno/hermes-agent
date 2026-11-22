# requesting-code-review: independent harness acceptance contract

**Scope:** Pinned repository diff SHA and independent reviewer context; only approved fixes may write.

**Operation families:** inspect_diff (read); apply_review_fix (write).

**Host-side preflight:** Capture staged/unstaged diff with exact base HEAD and files; require independent review, security scan and baseline tests.

**Approval boundary:** Reviewer cannot approve own changes; any auto-fix edits require scoped approval and fresh independent re-review.

**Independent verification:** Compare reviewed diff SHA to final diff, fresh tests and lint, blocking findings resolved with evidence.

**Unknown outcomes and safe stop:** Diff drift invalidates review; missing reviewer -> unverified; document-only diffs still inspect executable examples.

**Adversarial regression families:** author-reviewer same identity; old CI SHA; skipped config secrets; incomplete diff; changed patch after review.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
