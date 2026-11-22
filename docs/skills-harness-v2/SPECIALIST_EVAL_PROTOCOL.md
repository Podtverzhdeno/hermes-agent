# Per-Skill evaluation: independent final-state oracles

## Four controlled trial arms
A: no specialist Skill; B: existing Skill; C: improved instructions without
execution policy; D: improved instructions + fully integrated policy broker.
Freeze provider/model versions, fixtures, accounts, tools, temperature, budgets
and time windows. Run matched tasks multiple times, randomize order and publish
uncertainty intervals (paired bootstrap or McNemar for pass/fail).

## Three metrics that must not be conflated
1. Routing: correct activation, false positives, false negatives and wrong
   specialist combinations. Include genuine adjacent negatives and no-skill cases.
2. Business result: independently observed file revision, PR state, Sent id,
   Calendar id, reproduced test state and correct read coverage — not claimed success.
3. Security/reliability: rejected unauthorized calls, safe handling of stale
   versions, duplicate effects, cross-agent scope, missing receipts and budget cost.

Proposed gates: zero unauthorized mutations and duplicate sends in the tested
matrix; non-regressed task success vs B, aspirational +10 percentage points
with confidence bounds; at most 20% extra tokens at matched task success.
Numbers are *targets*, not measured improvements.

## Authored offline corpus
The independent research package includes 80 candidate prompts (ten each for
GitHub, Obsidian, Email Triage, Google Workspace, Debugging, Code Review,
Codebase Inspection and Hermes Administration). Their labels are researcher
hypotheses, **not a validated held-out set**. Before comparative claims,
create a second independently authored holdout set, preserve it from prompt
optimization and instrument actual model/tool traces.

A structural manifest test is never a live routing evaluation. A passing
signature verifier is never proof that the model will pick the right Skill.
