# Skill Harness and current upstream Hermes — compatibility audit

**Status: design note; upstream migration NOT implemented.**

This PR targets the user's older Podtverzhdeno/hermes-agent fork, not the
current NousResearch/hermes-agent main. Do not cherry-pick blindly.

## Exact observed revision

- Fork baseline: 7e9100901819ee44c16b4ddcb79a6bcb7909f591 (2026-04-01).
- Upstream main: da8e7d71abe4ac165760cd813c0c18c53e697b90
  (observed 2026-11-22).
- Fork pilot PR: https://github.com/Podtverzhdeno/hermes-agent/pull/2

## Divergence at module boundaries

| Component | Fork | Modern upstream | Migration consequence |
|---|---|---|---|
| Skill reader | tools/skills_tool.py monolith | skills_tool.py with skills_tool_setup, skills_tool_plugin, skills_tool_dedup | Hook per-skill metadata at actual serving/validation paths |
| Skill manager | tools/skill_manager_tool.py | Separate skill_manager_scan, skill_manager_guards, skill_manager_batch | Adapt write_harness without bypassing existing read-before-write or background-review rules |
| Startup index | agent/prompt_builder.py snapshot v1, pilot v2 | Snapshot v5 with more caches and filters | Preserve upstream v5 schema, cache invalidation and context limits |
| Metadata | Basic agent/skill_utils.py | Expanded roots, exclusions, environments and platform matching | Reuse upstream utilities, do not overwrite them |
| Security scanner | Older regex scanner | skills_guard.py v16 with additional credential helpers | Retain upstream guard and stronger policy |
| YAML | PyYAML safe-load plus strict pilot parser | hermes_yaml adapter | Reconcile duplicate-key, alias, size and parser rules |
| Provenance | Basic trusted root test | skill_provenance and background-review gate | Version-pin and authorize by actual source identity, not prose |
| Session behavior | Direct skill_view responses | Deduplicated skill views and contextvars | Avoid stale manifests across sessions and dedup scope |

## Migration sequence (not executed)

1. Freeze exact baseline SHAs and evaluate real workloads on fork and
   upstream separately; do not assume skills catalog sizes are identical.
2. Port strict schema validation as a portable, opt-in sidecar.
3. Run source provenance and existing upstream guard before skill activation.
4. Make a true host-side admission controller: permitted tools are the
   intersection of user grant, provider scope, platform policy and declared
   requirements. A YAML manifest never grants authority.
5. Bind approvals to operation, user, target, skill version and expiry.
   Check each tool call at dispatch, not only the initial skill load.
6. Connect write_harness with upstream batch, conflict and provenance checks.
7. Extend the current v5 prompt snapshot after measuring context impact;
   retain existing platform and tool-availability conditions.
8. Evaluate no-skill, hand-selected skill and auto-selected skill modes, with
   memory off/on, more than one model and supported OSes.
9. Gate release on zero unauthorized writes, no secret leakage, and no
   regressions against earlier skill selection and domain tasks.

## Evidence and limitations

The fork's focused CI verified 308 tests, and the corpus auditor found
117 skills, 22 individual harnesses, 0 issues and 0 warnings
(run: https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45015470535).

This proves code-level compatibility with the tested fork snapshot, NOT
runtime isolation, Windows behavior, actual agent routing lift, production
readiness or compatibility with new upstream main.

## Primary references

- https://agentskills.io/specification
- https://developers.openai.com/blog/eval-skills
- https://developers.googleblog.com/en/the-anatomy-of-harness-engineering-how-to-evaluate-iterate-and-guard-ai-coding-agents/
- https://arxiv.org/abs/2611.22017
- https://arxiv.org/abs/2602.12670
- https://arxiv.org/abs/2608.08453
- https://owasp.github.io/www-project-agentic-skills-top-10/
