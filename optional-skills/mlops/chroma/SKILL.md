---
name: chroma
description: Build and test local Chroma RAG collections with stable embeddings, document metadata, tenant filters, persistence and measurable retrieval quality.
version: 2.0.0
author: Hermes Agent (curated from Orchestra Research)
license: MIT
metadata:
  hermes:
    tags: [Chroma, RAG, Embeddings, Local-Index, Metadata, Privacy]
    related_skills: [faiss, qdrant-vector-search, dspy]
---

# Chroma — reproducible document retrieval and safe persistence

## Activation

Use when a task needs an embedded/local document collection, semantic
retrieval, metadata filters or prototype RAG using Chroma. Avoid choosing
Chroma automatically for a multi-node cluster or pure approximate vector
benchmark; compare Qdrant, FAISS or existing infrastructure using actual
requirements. Follow `harness.yaml` for ownership, collection lifecycle,
data authorization, tests and recovery.

## Preflight and trust

Confirm the installed `chromadb` version and client mode:
`Client` (ephemeral), `PersistentClient` (local disk), `HttpClient`
(server), or an authorized managed service. Record the target data directory,
collection, model, vector dimensions, similarity/distance choice, tenant
scope and actual user write permissions.

A collection is persisted state, not merely a cache. Do not reset, overwrite,
delete, migrate or silently share it. A remote embedding function may send
private documents off device; get authorization before enabling it. For
sensitive data, prefer explicit local embeddings and independently enforced
storage and retrieval permissions.

## Minimal, isolated smoke test

The following uses **explicit numeric test embeddings**, preventing an
unplanned external embedding-model call. Run only in an authorized local test
workspace; never point `path` at an existing production collection.

```python
import chromadb

client = chromadb.PersistentClient(path="./.chroma-smoke")
collection = client.get_or_create_collection(name="hermes_smoke")
collection.upsert(
    ids=["test-001"],
    embeddings=[[1.0, 0.0]],
    documents=["Document for authorized smoke test."],
    metadatas=[{"tenant": "test", "source": "synthetic"}],
)
result = collection.query(
    query_embeddings=[[1.0, 0.0]],
    n_results=1,
    where={"tenant": "test"},
)
assert result["ids"][0] == ["test-001"]
```

Reopen with a fresh `PersistentClient` and validate count, IDs,
documents and filters after process restart. If a newer Chroma API changes
this example, use the installed documentation; do not blindly downgrade a
populated database.

## Production ingestion workflow

1. Identify source ownership, consent, version and sensitivity.
2. Design chunking with file/section offsets, document hashes, metadata
   fields and stable IDs for incremental **idempotent upserts**.
3. Choose embedding model and dimension; record tokenizer, normalization
   and model revision. Do not mix models in a collection unintentionally.
4. Bound batch size, concurrency, retries and resource consumption.
5. Keep a source-to-chunk manifest so deletions and corrections are
   traceable. A batch failure should not be treated as all records inserted.
6. Apply tenant/ACL filters at the query boundary. **Client-side filtering
   after retrieving unrestricted candidates is not an isolation control.**
7. Keep secrets out of payload metadata and logging.

Do not imply that a metadata filter alone enforces end-user authorization:
host application and storage-level access controls remain required.

## Evaluation: retrieval quality and correctness

Use labeled queries with document/relevance judgments:
- Recall@k, MRR/nDCG where appropriate;
- Answer grounding and citation-to-chunk fidelity separately from retrieval;
- Latency distribution and index/storage footprint;
- Source update/delete propagation and persistence round-trip;
- Empty dataset, wrong dimension, duplicate ID, missing metadata and
  malformed filter inputs;
- Tenant isolation with documents from two distinct authorized tenants.

Compare hybrid/keyword baselines separately when text-heavy queries are
present. Avoid claiming a default embedding/model is universally best.

## Failure handling and reporting

On dimension mismatch, stage a **new collection** rather than mutating
production vectors. On accidental duplicate ingest, reconcile by stable IDs.
On corruption, restore only from a verified snapshot after inspecting current
state; never silently wipe a collection. On remote connection failure, do not
auto-switch to a different account or cloud endpoint.

Report exact client/version, collection path/name, embedding model and
dimension, chunking, filters, actual read/write tests, retrieval metrics,
authorization scope and unresolved risks. Distinguish a synthetic smoke
test from evaluation on real documents.

Primary docs:
- https://cookbook.chromadb.dev/core/
- https://cookbook.chromadb.dev/core/collections/
- https://github.com/chroma-core/chroma

Historical examples: `references/legacy-full-2026.md`.
