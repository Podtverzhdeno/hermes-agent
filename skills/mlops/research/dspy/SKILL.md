---
name: dspy
description: Design, evaluate and optimize version-pinned DSPy LM programs with leakage-free datasets, concrete metrics and controlled provider costs.
version: 2.0.0
author: Hermes Agent (curated from Orchestra Research)
license: MIT
metadata:
  hermes:
    tags: [DSPy, GEPA, MIPROv2, LLM, Prompt-Optimization, Evaluation, RAG]
    related_skills: [evaluating-llms-harness, chroma, code-review]
---

# DSPy — optimize measured program behavior, not prompts in isolation

## Activate when appropriate

Use when a project needs declarative LM modules (`Predict`,
`ChainOfThought`, retrieval/classification pipelines), systematic prompt
optimization, optimizer selection, or program evaluation. Do **not** introduce
DSPy merely to decorate a small static prompt with extra abstractions, or
claim an optimizer improved quality without independent results.

The individual `harness.yaml` defines activation exclusions, preflight,
model-provider cost authorization, evidence and recovery requirements.
The large historic example collection is archived in
`references/legacy-full-2026.md`, which contains version-sensitive API
examples and **unverified** improvement claims.

## Preflight: version, data and provider

Record:
- Installed Python and DSPy versions and optional model backend;
- Actual LM model ID, version, response adapter, temperature and token cap;
- Input/output contract, validation rules and tool side effects;
- Training, development and **held-out** test examples, with deduplication;
- Evaluation metric, aggregation, known failure modes and allowed API spend;
- Personal/sensitive data and whether examples may be sent to a provider.

Use an isolated dependency environment; do not pull the latest development
branch by default. Review the exact installed API before using a tutorial
written for another version:

```bash
python -c "import dspy; print(dspy.__version__)"
```

Primary docs: https://dspy.ai/getting-started/installation/
https://dspy.ai/current/tutorials/rag/
https://dspy.ai/current/diving-deeper/choosing-an-optimizer/

## Minimal, version-aware DSPy pattern

The following example requires **authorized external LM access** and a
properly configured credential provider. Do not paste or log API keys:

```python
import dspy

lm = dspy.LM("openai/gpt-4o-mini")
dspy.configure(lm=lm)

qa = dspy.Predict("question: str -> answer: str")
result = qa(question="What is the capital of France?")
print(result.answer)
```

A hard-coded illustrative question does not test task quality. Replace the
model and schema with the actual project's validated environment. For
retrieval workflows, wrap a deterministic retrieval function with explicit
top-k, tenant filtering and source IDs. LM-generated content must never
override source authorizations or execute tools simply because it came
from a trusted model provider.

## Optimization workflow

### 1. Define success before seeing results

Write an **executable metric** (exact match, weighted F1, semantic
faithfulness with an evidence check, task success etc.). A single opaque
LLM-judge score is inadequate for safety-sensitive workflows; use separate
deterministic checks and assess judge agreement where possible.

Construct immutable, non-overlapping train/dev/test partitions with a
stable split strategy. Group near-duplicates and source documents so
the same answer does not leak between splits.

### 2. Benchmark the unoptimized baseline

Evaluate a `dspy.Predict` or `dspy.ChainOfThought` program under the
chosen model/adapter, using fixed examples and seeds where supported.
Record cost, number of calls, per-item outputs and latency. Inspect
the failures rather than selecting an optimizer from branding alone.

### 3. Choose an optimizer by failure mode and budget

- **BootstrapFewShot / BootstrapRS:** suitable for improving examples and
  demonstrations with limited search; ensure bootstrapped labels are valid.
- **MIPROv2:** optimizes instructions and demonstrations; may require
  many LM calls and a reasonable development set.
- **GEPA:** reflection-guided prompt evolution with metric feedback; validate
  metric assumptions and reflection-model cost.
- **BootstrapFinetune:** modifies model weights; requires additional
  training approvals, data governance and checkpoint handling.

Optimizer options and names change across DSPy versions. Consult the
installed library and current official docs before composing executable
code. Run a small approved pilot before a large budget.

### 4. Validate on held-out data

Compare against the baseline using the **same** model, test set, decoding
setup and scoring implementation. Track uncertainty, examples improved
versus regressed, latency and actual API costs. If the optimizer used the
held-out data for selection, the comparison is contaminated and must be
repeated on a fresh holdout.

Check structural outputs, schema validation, error handling, refusals,
prompt injection resistance, data privacy and untrusted tool results.
When using retrieval, evaluate both retrieval recall/precision and
final-answer grounding separately.

### 5. Version and deploy reproducibly

Save the compiled DSPy program using the version-appropriate official
save/load API. Record hashes of program, training/dev data, dependencies
and model ID. Smoke-test a reloaded artifact on fresh input. If deployed
behind an API, ensure access policy, rate limits, timeouts, retries and
logging redaction. Never deploy or publish by default.

## Failure cases and safe recovery

- **Parser/adapter errors:** inspect one sanitized request/response and
  schema; avoid automatic unbounded retries.
- **High optimization cost:** enforce a provider-side and experiment-side
  call/cost limit; do not rely solely on `harness.yaml` budgets.
- **Near-zero improvement:** report statistical uncertainty; optimizer
  outputs are hypotheses, not guaranteed gains.
- **Leaked examples:** halt external calls and follow data-handling policy.
- **Task metric too weak:** improve and freeze the metric **before** the
  final holdout assessment; otherwise explain adaptive testing bias.
- **Saved program incompatibility:** preserve baseline artifact and roll
  back only owned changes.

## Evidence-backed completion

Return the task metric definition, split sizes and checks, exact model and
DSPy versions, optimizer configuration, baseline versus candidate scores,
per-failure analysis, latency/cost, reproducible artifact ID and limitations.
If no model evaluation ran, explicitly say **"optimization not empirically
verified"** and do not assert quality gains.

Historical API examples: `references/legacy-full-2026.md`.
