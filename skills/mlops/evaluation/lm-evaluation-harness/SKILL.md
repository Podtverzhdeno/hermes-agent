---
name: evaluating-llms-harness
description: Reproducible LM model benchmarking with EleutherAI's current lm-eval CLI, fixed task configurations, uncertainty and resource-cost controls.
version: 2.0.0
author: Hermes Agent (curated from Orchestra Research)
license: MIT
metadata:
  hermes:
    tags: [LLM, Evaluation, Benchmarks, Reproducibility, Statistics, Costs]
    related_skills: [dspy, ml-paper-writing, code-review]
---

# LM Evaluation Harness — benchmark protocols, not leaderboard anecdotes

## When to use

Use for repeatable model comparisons using EleutherAI's
`lm-evaluation-harness`, an appropriately selected academic benchmark,
custom task configuration, or training checkpoint evaluation. For end-to-end
agent tool-use performance, add separate task-completion evals and do not
equate academic QA accuracy with deployed agent reliability. Follow
`harness.yaml` for experiment preflight, approvals, acceptance and recovery.

## First validate the installed CLI version

The EleutherAI CLI **changed in December 2025**. New versions expose
`lm-eval run`, `lm-eval ls` and `lm-eval validate`. Legacy releases
use different command syntax. Do not copy a command from the archived
2026 guide without matching its version.

```bash
lm-eval --help
lm-eval run --help
lm-eval ls tasks
```

If `lm-eval` is missing, obtain approval before installing packages or
downloaded model weights. Use an isolated environment and pin project
dependencies. For current versions, backends are separately installable
(e.g. `lm_eval[hf]`); verify the upstream installation guide and compatibility
with the user's PyTorch/CUDA environment.

Primary docs:
- https://github.com/EleutherAI/lm-evaluation-harness
- https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md
- https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md

## Establish a comparison contract

Record all variables that can change scores:
- Exact `lm-eval` version/commit and task definition versions;
- Model weights, tokenizer, revision and provider/backend;
- Chat template, few-shot count, few-shot selection, prompt format,
  decoding, loglikelihood/generation mode and output normalization;
- Data split, language/domain coverage and dataset access restrictions;
- Batch size, precision, quantization, device and system environment;
- Seeds, sample counts, evaluation budget and expected cost;
- Contamination checks, paired task sampling and uncertainty method.

Do not claim a model is generally "better" from a one-task score. Use
a **pre-registered primary metric** that matches the target application
and display per-task results rather than masking poor cases in a mean.

## Smoke test before a full benchmark

This is illustrative for a recent CLI and **requires downloaded model and
dataset access**. It is a wiring check, not a publishable benchmark:

```bash
lm-eval run \
  --model hf \
  --model_args pretrained=gpt2 \
  --tasks hellaswag \
  --limit 10 \
  --batch_size 1 \
  --output_path ./eval-smoke
```

Run only in an authorized workspace and save the actual command and exit
code. The small `--limit` sample deliberately gives unstable, biased
estimates; **never quote its score as model performance**.

For a real experiment, determine current task names from `lm-eval ls tasks`,
remove the smoke-test limit, configure matched tasks and examples, and
write results to separate immutable run directories. Inspect `run --help`
for compatible seed/logging flags before composing the actual command.
Do not mix CLI versions or silently change prompting between candidates.

## Correctness and evidence checks

1. Validate all custom tasks and dataset splits before benchmarking. Test
   task-document rendering and answer extraction on a few known examples.
2. Verify the model backend loaded the *intended weights and tokenizer*;
   a fallback or wrong revision invalidates comparisons.
3. Check `num_fewshot`, truncation, end-of-sequence handling and chat
   template semantics on a sampled prompt.
4. Separate **evaluation crashes**, skipped samples and metric parsing
   errors from valid results; never average partial runs as complete.
5. For small differences, repeat across seeds or compute an appropriate
   uncertainty interval (e.g. paired bootstrap for paired examples).
6. Check for benchmark contamination, repeated test selection and
   indirect tuning on the holdout set.
7. Log latency, GPU-hours/tokens and API spend. A faster backend is not
   assumed better without measured hardware-matched throughput and accuracy.

Model and task revisions can change; reproducibility requires recording
versions, not just benchmark names. Publishing individual model outputs
or private benchmark data requires authorization and rights review.

## Recovery and report

On OOM, reduce only one memory variable at a time and record the changed
precision/batch settings. On rate-limit or provider failure, verify which
samples actually completed before retrying; avoid duplicate paid calls and
unequal evaluation sets. If a task fails to download or is gated, report it
as unavailable, not as zero accuracy.

Report a table: task, sample count, few-shot, metric, baseline,
candidate, uncertainty, cost, and completion status. Include exact model
and harness versions, task config, executed commands, check failures and
remaining unknowns.

Legacy examples are preserved for historical migration only:
`references/legacy-full-2026.md`.
