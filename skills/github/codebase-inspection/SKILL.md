---
name: codebase-inspection
description: Reproducibly measure codebase LOC, languages and comment/code ratios with declared scope, generated-file exclusions and no modification of system Python.
version: 2.0.0
author: Hermes Agent
license: MIT
prerequisites:
  commands: [pygount]
metadata:
  hermes:
    tags: [LOC, Codebase, Reproducibility, pygount, Metrics]
    related_skills: [github-repo-management, code-review]
---

# Codebase Inspection — reproducible, non-invasive metrics

## When to use

Use for requests about repository size, language breakdown, comment-to-code
ratios, source-file counts or size changes. Do **not** infer complexity,
quality, developer productivity, defects or maintainability solely from LOC.
For software defect review use `code-review`. Read `harness.yaml` for scope,
evidence, time budget and exact acceptance conditions.

## Preflight

1. Resolve the requested repository and absolute project root; inspect current
   revision and working-tree status without changing anything.
2. Confirm **measurement scope**: tracked files, all files, test code,
   vendored/generated sources, notebooks, embedded languages and submodules.
3. Check for tool availability: `pygount --version`. Do not install software
   automatically or change a system Python environment just to count lines.
4. If tool installation is authorized, use `python -m venv .venv` inside an
   isolated writable workspace or a user-approved environment, then install
   a pinned version. Never use `pip --break-system-packages`.

## Measure

Run in the selected project root, with a reviewed exclusion set:

```bash
pygount --format=summary \
  --folders-to-skip=".git,.venv,venv,node_modules,__pycache__,dist,build,.next" \
  .
```

For programmatic comparison:

```bash
pygount --format=json \
  --folders-to-skip=".git,.venv,venv,node_modules,__pycache__,dist,build,.next" \
  . > code-metrics.json
```

The second command **writes a report** and therefore requires authorization
for the output destination; prefer a temporary/report directory rather than
placing generated metrics in a protected repo. Verify current CLI syntax
against `pygount --help` before running it in a version-sensitive setup.

If the user asks for tracked files only, build a tracked-file manifest via
`git ls-files -z` and use an appropriate per-file parser; do not imply the
default `pygount .` output excludes ignored/untracked files automatically.
Record exclusions explicitly. Avoid scanning unrelated home directories,
credential stores, private repos, build artifacts or mounted volumes.

## Interpret carefully

Report **code / comments / blank lines**, language totals, files included,
exclusions, revision and tool version. Ratios and file counts can shift with
parser heuristics, generated artifacts, notebooks and language classifications.
Do not compare two repositories without matching scope, exclusion rules and
tool versions. Source-line counts are not equal to runtime instructions or
function points.

Common issues:
- Hidden generated or vendored directories inflate totals;
- Multiple languages in one file can be categorized unexpectedly;
- Binary/minified files are not normal code-line units;
- Submodules may be omitted or counted differently;
- Extremely large trees require bounded enumeration and resource controls;
- Dirty working trees make SHA-only reports incomplete.

## Verification and recovery

Re-run a small known-file sample to validate language and comment detection.
Check that the reported sum matches the per-language totals using the
reported parser semantics. If some files failed decoding, state the number
and path class without leaking their contents. Do not delete reports or
modify user source code as part of measurement.

**Output:** exact project/revision, scope, excluded paths, tool version,
per-language code/comment/blank counts, caveats and a reproducible command.
If the tool was unavailable, give a bounded alternative rather than fake
counts.

Reference: https://pygount.readthedocs.io/en/latest/usage/
