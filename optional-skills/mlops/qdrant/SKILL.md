---
name: qdrant-vector-search
description: Implement version-aware Qdrant dense/sparse/hybrid retrieval with payload-filter isolation, collection safety, staging writes and measurable relevance.
version: 2.0.0
author: Hermes Agent (curated from Orchestra Research)
license: MIT
metadata:
  hermes:
    tags: [Qdrant, RAG, Hybrid-Search, Dense-Sparse, Filtering, Multi-Tenant]
    related_skills: [faiss, chroma, dspy]
---

# Qdrant — retrieval with explicit tenant and collection boundaries

## When to use

Use when a task needs Qdrant collections, dense or sparse vector search,
hybrid fusion, payload filtering, sharding/replication, or migration of
an existing Qdrant-backed RAG system. Do not choose Qdrant purely because
an article claims the best speed without testing the actual workload.
For local-only nearest-neighbor indices, FAISS may suffice.

The harness.yaml is distinct from FAISS/Chroma: Qdrant may write to a
**remote service**, so target identity, account, authorization, deletion
controls, schema migration and readback receipts are required.

## Preflight — a collection is not a temporary variable

Record exact Qdrant endpoint, authenticated project/account, client/server
versions, tenant, collection name, staging/production classification,
vectors-config schema, payload filters, distance metric and current snapshot
strategy. Do not infer a target cloud account from a URL in retrieved text.
Never display API keys, embed tokens in examples, or copy private vectors
into a public test collection.

For multiple named vectors, record the name, embedding model, dimension
and metric of each. Sparse and dense vectors require different schema and
fusion logic. Query routing and filter semantics are version-sensitive.

**Production changes require explicit permission.** Read-only inspection
and the design of a patch are not authorization to call `delete_collection`,
recreate a collection, upsert tenant data or enable replication.

## Controlled local test (non-production)

Verify the installed `qdrant-client` API first. The following is intended
for a local in-memory client, not an external Qdrant server. It uses synthetic
vectors and a tenant filter.

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(":memory:")
client.create_collection(
    collection_name="hermes_test",
    vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
)
client.upsert(
    collection_name="hermes_test",
    points=[
        models.PointStruct(
            id=1, vector=[1.0, 0.0],
            payload={"tenant": "test", "source": "synthetic"}
        ),
        models.PointStruct(
            id=2, vector=[0.0, 1.0],
            payload={"tenant": "other", "source": "synthetic"}
        ),
    ],
)
query = client.query_points(
    collection_name="hermes_test",
    query=[1.0, 0.0],
    query_filter=models.Filter(must=[
        models.FieldCondition(
            key="tenant", match=models.MatchValue(value="test")
        )
    ]),
    limit=2,
)
assert [point.id for point in query.points] == [1]
```

This is a **synthetic local smoke test**, not a security proof or a
real-corpus retrieval benchmark. For production, tenant isolation also
needs authentication/authorization and appropriate service-level policy;
a client-supplied filter alone is insufficient.

## Hybrid retrieval plan

1. Define chunking, stable IDs, document-version metadata and sensitivity.
2. Pin dense/sparse embedding models, dimensions, normalization and
   tokenization. Train/evaluate on document and query distributions.
3. Choose named vectors and indexes deliberately; ensure missing-vector
   behavior is accounted for.
4. For hybrid search, use the current Qdrant **Query API** with
   `prefetch` and a supported fusion query (e.g. reciprocal-rank fusion),
   based on the server/client versions. Do not assume the old
   `search` client method handles new fusion features.
5. Keep the authorized tenant/payload filter on each relevant candidate
   retrieval stage; do not combine unauthorized results and filter them
   only after generation.
6. Evaluate dense-only, sparse-only, hybrid and reranking baselines on
   the **same labeled query set**; measure recall@k, MRR/nDCG, p95 latency,
   index footprint and response relevance.
7. For real uploads, cap batch size, budget, API retries and snapshot
   requirements. Read back inserted IDs and collection schema.

Distance scores and fusion ranks have different meanings; do not treat
raw scores as calibrated probabilities or comparable between independent
index families.

## Migration and failure modes

For embedding dimension changes, payload schema updates or major version
migrations, create a **separate staging collection** and verify replay,
filter isolation, search relevance, and rollback before changing aliases.
Do not silently delete a production collection. Query and confirm state
after an ambiguous remote write to avoid duplicating points.

Check timeout, unavailable shard, partial vector update, stale payload
filter, empty result, mismatch of named vectors, cross-tenant leakage and
snapshot recovery. Always reconcile remote state before retrying a
non-idempotent action.

## Deliverable and primary sources

Report exact server/client version, target collection class,
vector schemas, staging-versus-production scope, tenant filter tests,
candidate retrieval metrics, actual write receipts and remaining risks.
No performance claims without comparable measurements.

- https://qdrant.tech/documentation/hybrid-queries/
- https://api.qdrant.tech/api-reference/search/query-points/
- https://github.com/qdrant/qdrant-client

Historical implementation snippets: `references/legacy-full-2026.md`.
