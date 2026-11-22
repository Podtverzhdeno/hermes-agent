---
name: code-review
description: Evidence-anchored review of code changes for correctness, security, regression and compatibility; avoid speculative or stylistic findings.
version: 2.0.0
metadata:
  hermes:
    tags: [code-review, security, regression, correctness, verification]
    related_skills: [systematic-debugging, test-driven-development, github-code-review]
---

# Code Review: evidence before severity

## Scope and triggers

Use for an explicit source review, patch audit, release-readiness check, or
change-risk assessment. For *posting* comments to a remote GitHub PR, use
`github-code-review` with its separate external-write approval rules.
For fixing a confirmed bug, hand off to `systematic-debugging`. If no
code or relevant diff is available, do not pretend to have reviewed it.
Follow this skill's `harness.yaml` for evidence, stages, time budget and
limitations. The harness is guidance, not permission to call tools.

## Preflight: establish a baseline

- Identify repository, base/head revision, language/runtime, deployment
  surface and intended behavior. Do not mix a working-tree review with a
  remote PR without recording which revision was inspected.
- Inventory changed files and caller/callee boundaries. For a PR, review the
  patch **and** the minimal surrounding context required to reason about it.
- Consult project instructions, relevant tests, lint conventions and known
  compatibility constraints; do not import an unrelated style guide.
- Inspect security-sensitive entry points: authentication, authorization,
  filesystem, network, deserialization, SQL, concurrency, secrets and
  remote tool descriptions. Do not scan or expose secrets gratuitously.
- Identify uncommitted user changes; never reset them as part of a review.

## Analysis workflow

1. **State the invariant.** What behavior should remain true across this
   change? For example, a rejected caller cannot mutate protected state.
2. **Trace the affected path.** Follow input, validation, transformation,
   use and any failure/cleanup path. Inspect helpers only when needed.
3. **Form a falsifiable scenario.** Give a concrete valid/invalid input or
   state transition that would trigger the defect.
4. **Look for counter-evidence.** Check nearby guards, tests, framework
   behavior and deployment constraints. If the supposed failure is already
   prevented, discard the finding.
5. **Check regressions.** Consider empty/missing values, Unicode, path
   containment, error retries, partial writes, timeouts, cancellation,
   platform differences and API backwards compatibility.
6. **Validate when possible.** Run a targeted test in an authorized
   environment; distinguish static reasoning from executed evidence.

Never invent line numbers, APIs, test results, CVEs, version requirements,
or sample output. If line anchors cannot be confirmed, cite a function and
a bounded code excerpt with a note about the missing line map.

## Severity and confidence

- **Critical:** directly exploitable security or irreversible data integrity
  failure with an established reachable path.
- **High:** major correctness/security issue likely to affect normal use.
- **Medium:** a confirmed edge-case regression with meaningful impact.
- **Low:** a concrete minor defect; do not escalate speculative concerns.
- **Suggestion:** non-blocking maintainability or style ideas, clearly
  separated from bugs.

Every defect should specify severity **and** confidence. A high-impact
hypothesis with insufficient evidence should be labeled as an investigation,
not silently promoted to a confirmed blocker.

## Required finding template

Use this structure for each actionable finding:

- **Severity / confidence:** e.g. High / confirmed by test.
- **Location:** exact revision and relative path:line range, if available.
- **Invariant violated:** expected versus actual behavior.
- **Reproducer:** the smallest credible scenario or a real test command.
- **Impact:** whose data/flow fails and under what conditions.
- **Correction:** minimal fix and a regression test recommendation.
- **Evidence:** executed test result or clearly labeled static trace.

If no blocking findings remain, say **"No confirmed blocking issues found
in the inspected scope"**, not "the code is perfect".

## Review completeness gates

- [ ] The inspected revision and scope are clear.
- [ ] Every blocking finding has a specific reachable failure path.
- [ ] Findings were checked against available existing tests and guards.
- [ ] Error paths, concurrency and input boundaries were considered.
- [ ] Unrun tests and inaccessible components are disclosed.
- [ ] No secrets or private user data are included in the report.
- [ ] Pure style opinions are not mixed with correctness defects.

## Output

Start with the highest-severity verified findings, then concise non-blocking
suggestions and remaining risks. Provide a short testing ledger: **performed,
not performed, and why**. For an external PR, do not publish comments or
approvals unless that side effect was explicitly authorized.
