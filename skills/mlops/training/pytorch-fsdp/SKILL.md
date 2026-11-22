---
name: pytorch-fsdp
description: Diagnose and implement PyTorch FSDP2/FSDP1 distributed training with version-checked APIs, reproducible multi-rank tests, checkpoint safety and memory profiling.
version: 2.0.0
author: Hermes Agent (curated from PyTorch upstream documentation)
license: MIT
metadata:
  hermes:
    tags: [PyTorch, FSDP2, fully_shard, DTensor, distributed-training, checkpoints]
    related_skills: [pytorch-lightning, accelerate]
---

# PyTorch FSDP: verified training, not copied API dumps

## When to use

Use for memory-constrained model training across multiple GPU processes,
selecting FSDP1 versus FSDP2, tuning mixed precision/resharding, analyzing
collective hangs, or validating distributed checkpoints.

Do **not** use for single-GPU inference, generic model choice, or claims
about GPU performance without an actual benchmark. For TPU/XLA, pipeline
parallelism or tensor parallelism, check the appropriate specialized docs.
Follow this directory's harness.yaml for preflight, evidence and recovery.

## First establish the environment

Before suggesting code or numerical settings, capture:

- Exact `torch.__version__`, CUDA/ROCm build and distributed backend;
- GPU type, visible device count, local/global rank, worker count and topology;
- Model size, parameter sharing/tied weights, dtype, optimizer and checkpoint
  format; whether the model uses meta-device initialization;
- Symptom: out-of-memory at initialization, forward, backward, optimizer,
  or checkpoint; or a collective hang with rank-specific traces.

FSDP API and supported features change across PyTorch versions. Confirm
against the documentation for the user's **installed** version, not just
the latest main docs. Prefer reproducible minimal scripts over guesswork.

## FSDP1 versus FSDP2

- **FSDP2**: `torch.distributed.fsdp.fully_shard` uses per-parameter
  `DTensor` sharding. For *new* code, current PyTorch documentation
  recommends evaluating FSDP2 before choosing legacy FSDP1.
- **FSDP1**: `FullyShardedDataParallel` wraps modules using a
  flat-parameter strategy. Existing code may require FSDP1-specific state
  dict and optimizer handling. Do not blindly paste FSDP2 examples into it.
- Mixing the APIs without checking invariants is a migration risk. Validate
  parameter aliasing, optimizer construction timing, checkpoint portability
  and precision semantics with an executable test.

Canonical references:

1. FSDP2 API: https://docs.pytorch.org/docs/stable/distributed.fsdp.fully_shard.html
2. FSDP2 tutorial: https://docs.pytorch.org/tutorials/intermediate/FSDP_tutorial.html
3. FSDP1 legacy API: https://docs.pytorch.org/docs/stable/fsdp.html
4. PyTorch Distributed Checkpoint:
   https://docs.pytorch.org/docs/stable/distributed.checkpoint.html

## Minimal FSDP2 construction pattern

This is **illustrative**, not a runnable standalone program. The process
group/device setup, dataloader and training loop must be supplied and checked
against the installed PyTorch version.

```python
import torch
from torch.distributed.fsdp import fully_shard

# Apply bottom-up so per-layer communication groups can overlap with compute.
for block in model.blocks:
    fully_shard(block)
fully_shard(model)

# Construct the optimizer AFTER sharding is applied.
optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
```

`model.blocks` is a placeholder for actual layer ownership; it is not a
standard PyTorch attribute. Keep tied parameters and module grouping in mind.
Use the API docs for `MixedPrecisionPolicy`, `reshard_after_forward`,
device meshes and CPU offloading; do not assume a default fits every model.

## Investigation workflow

### 1. Reproduce

First reproduce at minimal scale (usually two local GPU processes) with
matching versions. Record exact launch command and per-rank errors. PyTorch
tutorials commonly use `torchrun --nproc_per_node=2 train.py` on a
supported two-GPU host; do not run this on a machine lacking the resources.

### 2. Measure

Separate model, gradient, optimizer and activation memory. Capture the
peak allocated/reserved memory **per rank**, not just system VRAM. Compare
baseline, sharding, precision and checkpoint settings with equal batch,
sequence length and hardware. Account for synchronization timing.

### 3. Change one mechanism at a time

Evaluate wrapping granularity, reshard-after-forward, activation
checkpointing, mixed precision and CPU offloading as independent
tradeoffs. Record throughput, peak GPU memory, communication and
numerical behavior. A memory saving that introduces hangs or incorrect
gradients is not an improvement.

### 4. Verify distributed correctness

- Each rank receives the intended input partition.
- Gradients, parameter updates and loss are finite/consistent for a
  fixed-seed small case.
- No rank deadlocks, collective order mismatch or unhandled uneven inputs.
- Save a checkpoint and **restore** it in a separate controlled run.
- Test world-size portability only if the checkpoint path claims support.
- Explicitly document when the sample is single-node only.

### 5. Recover

On OOM or hang, capture traceback, rank logs, environment and minimal
reproducer. Avoid automatically killing unrelated training jobs. Do not
delete valuable checkpoints. Roll back one change at a time and check
the actual restored state before retry.

## Linked references and provenance

- `references/legacy-generated-2025.md`: **archived**, long 2025
  scraper content preserved for historical context. It includes mixed DDP,
  RPC and distributed primitives that do not by themselves constitute a
  recommended FSDP2 workflow. Load only for a specific legacy API detail.
- `references/other.md`: legacy extracted documentation; very large
  and potentially stale. Prefer upstream PyTorch docs for current APIs.

## Reporting checklist

Report environment and PyTorch version, baseline and candidate launch
commands, measured per-rank memory/throughput, checkpoint round-trip,
correctness test results and all unverified assumptions. Do not claim
a speedup or memory reduction without a comparable measured baseline.
