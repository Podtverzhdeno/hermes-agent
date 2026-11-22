---
name: faiss
description: Build reproducible FAISS dense-index retrieval with exact baselines, metric/normalization checks and measured ANN recall-latency-memory tradeoffs.
version: 2.0.0
author: Hermes Agent (curated from Orchestra Research)
license: MIT
metadata:
  hermes:
    tags: [FAISS, ANN, HNSW, IVF, PQ, RAG, Recall, Benchmarks]
    related_skills: [chroma, qdrant-vector-search, codebase-inspection]
---

# FAISS — exact neighbors first, then ANN tradeoffs

## Use and non-use

Use for high-throughput dense vector search, local ANN indexing,
metric-selection or index memory/latency optimization. Do not use FAISS
as a substitute for a production database's access control, per-document
metadata permissions, replication or audit log. For managed document
lifecycle, use Chroma/Qdrant or an existing authorized storage layer.
See `harness.yaml` for experiments, budgets and safety checks.

## Preflight

Record `faiss`, NumPy, CPU/GPU build and Python versions, dataset size,
vector dimension, dtype, embedding model/revision, distance metric,
normalization, ID mapping and available memory. Define the fixed labeled
query set and exact-neighbor ground truth.

- `IndexFlatL2`: exact Euclidean distance.
- `IndexFlatIP`: exact inner product; for cosine ranking normalize
  **database vectors and queries** to unit length.
- `IndexIVFFlat`: approximate inverted lists, requiring training on a
  representative sample; tune `nlist` and `nprobe`.
- `IndexHNSWFlat`: approximate graph search with construction/search
  parameters and extra memory.
- Product quantization: compressed approximate search; evaluate trained
  quantization loss and memory separately.

No index is universally faster or more accurate. The dataset distribution,
vector size, hardware and metric determine tradeoffs.

## Safe, explicit exact-search baseline

Runs locally with synthetic data and no network calls; only run where
`faiss` and NumPy are already available or dependencies are authorized:

```python
import faiss
import numpy as np

rng = np.random.default_rng(7)
vectors = rng.normal(size=(128, 32)).astype("float32")
queries = rng.normal(size=(8, 32)).astype("float32")
faiss.normalize_L2(vectors)
faiss.normalize_L2(queries)

index = faiss.IndexFlatIP(vectors.shape[1])  # cosine ranking if normalized
index.add(vectors)
scores, positions = index.search(queries, k=5)
assert positions.shape == (8, 5)
assert np.all(positions >= 0)
```

Here `positions` are integer row positions, not stable external document
identifiers. Use an explicit IDMap and a sidecar metadata store if the
application needs durable IDs or security filters; never silently assume
row number equals source document ID.

## Controlled ANN selection

1. Use `IndexFlat` as the ground-truth top-k baseline.
2. Partition training data from evaluation queries. If IVF/PQ is used,
   train indices on enough representative vectors and record train settings.
3. Tune one variable at a time: `nlist/nprobe` for IVF, HNSW
   `efConstruction/efSearch`, PQ code size and search knobs.
4. Compare recall@k **at equal query distribution and hardware**, plus
   p50/p95 latency, throughput, build time and peak RAM/VRAM.
5. Measure CPU and GPU separately with synchronized timings. Transfers,
   memory pressure and batch sizes can reverse a headline speedup.
6. For RAG, validate end-to-end relevance and document IDs; high vector
   recall does not guarantee well-grounded generated answers.

Never quote hard-coded "10× faster" or "billions of vectors" as a benchmark
for the user's hardware without actual measurement.

## Index serialization and untrusted bytes

Persist only into authorized locations and pair index bytes with embedding
model version, dtype/dimension, metric, ID map and a content checksum.
Round-trip a **trusted, locally generated** index and verify it returns
identical neighbors and scores within expected numeric tolerance.

Do not call `faiss.read_index` on untrusted uploaded indices. Native
deserialization and allocations can consume excessive resources or be
unsafe on crafted files. Treat an unknown binary index as untrusted input
requiring a sandboxed import plan. Never overwrite the only copy of a
production index while experimenting.

## Recovery and results

On OOM, reduce index size/precision or batch safely and log the exact
failure. On metric mismatch, rebuild a separate candidate, never mutate
the only baseline in place. On insufficient IVF/PQ training examples, do
not invent a trained comparison. Keep a reversible manifest and original
vectors when permitted.

Report: exact index family and parameters, embedding/normalization contract,
sample sizes, hardware versions, exact baseline recall, ANN recall/latency/
memory, serialized size, recovery status and all skipped checks.

Primary sources:
- https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index
- https://github.com/facebookresearch/faiss/wiki/The-index-factory
- https://github.com/facebookresearch/faiss

Historical examples: `references/legacy-full-2026.md`.
