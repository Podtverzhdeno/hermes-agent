# systematic-debugging: independent harness acceptance contract

**Scope:** Explicit repository/project and allowed source/test paths; execution only inside isolated sandbox.

**Operation families:** read_code (read); apply_fix (write).

**Host-side preflight:** Construct minimal reproducer that is red for specific symptom; record baseline/HEAD and scope; vet test/setup scripts.

**Approval boundary:** Approve exact patch and allowed paths, not arbitrary shell commands from logs or stack traces.

**Independent verification:** Same reproducer goes red->green; independent regression tests and unchanged expected behavior; bind to resulting commit/diff.

**Unknown outcomes and safe stop:** No reproducer or root cause evidence -> research-only; flaky failure -> collect confidence and avoid quick symptom edits.

**Adversarial regression families:** green-by-deleting-test; malicious log command; unrelated modules; false root cause; cached test success.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
