# Hermes ↔ GPT: forensic observer SDD and integration gates

**Revision:** 0.2 · 2026-11-22 · **Status:** design-only in this branch, not deployed.  
**Base:** main at `7e9100901819ee44c16b4ddcb79a6bcb7909f591`.  
**Ownership:** Independent observer/investigator; no edits to `gateway/platforms/api_server.py`, the browser extension, ACLs, ACP callbacks or the Autopilot ledger.  
**Implementation note:** The tested offline inspector and its 60 synthetic tests are available in the separately distributed project ZIP, **not committed to this branch yet**. Do not call the real system monitored.

## 1. Evidence classification and source snapshot

**OBSERVED (GitHub):** This fork contains an OpenAI-compatible adapter in `gateway/platforms/api_server.py`; `AGENTS.md` describes synchronous `run_conversation`; fork main's recursively retrieved tree did not include `web-extension/manifest.json`. PR #1 contains a proposed single-host SQLite ledger; PR #3 adds ACP approval callback isolation; PRs #4–#6 all edit `gateway/platforms/api_server.py` with incompatible retry and cache policies; PR #7 proposes a causal event envelope. All seven PRs are draft and separate from main at the observed revision. None of these facts proves the browser extension does not exist in a different local directory.

**BLOCKED (local):** `Local_WorkSpace.list_workspaces` reported `Session terminated` on repeated attempts. The owner's Windows extension, Obsidian documentation, running Chrome, credentials, native host and live task logs could not be inspected. Treat connector outage as *observer unavailable*, not *Hermes stopped*.

**VERIFIED OFFLINE ONLY:** 60 synthetic unittest cases on a separate Python metadata-only trace inspector succeeded; no browser test, installed-extension test, full Hermes integration test or provider stress test was executed. The inspector does not execute external writes.

**Unknowable:** hidden model reasoning, uninstrumented browser operations, missed prefixes/suffixes of a finite log segment, remote side effects without trusted receipt, whether a tab or worker still runs while disconnected.

## 2. Problem and invariants

A silent client or missing response is not equivalent to task death. A 200 response is not proof a tool write took effect; a timeout is not proof it failed. At 30+ concurrent agents, stale owners, duplicated client retries, overlapping worktrees, uncoordinated 429 backoff and observer gaps become expected contention cases.

I1. Exactly one authoritative task and effect control plane: the durable Autopilot ledger proposed in PR #1, after integration and validation; neither extension nor auditor may assign task success, trust, lease or approval.  
I2. External mutating effect requires atomic reservation, current fence, target revision and scoped authorization checked **at the tool gateway immediately before write**. Timeout after reservation creates `NEEDS_RECONCILIATION`, not automatic replay.  
I3. Each source producer incarnation has its own monotonic sequence; a restart either changes producer ID or resumes a persisted sequence. Global ordering across workers cannot be inferred from wall clocks.  
I4. Ledger transitions and outbox notifications commit in one local transaction. Export is at-least-once; identical event delivery is de-duplicated by event ID; conflicting IDs require quarantine.  
I5. Reused idempotency keys with different normalized request bodies must be rejected deterministically; no silent overwrite, optimistic expiration or in-flight eviction. In-process single-flight is NOT crash-safe or cross-host exactly-once.  
I6. `succeeded` needs a trusted verifier receipt anchored to exact commit SHA/artifact digest, not agent narration or observer metadata; unknown effects prevent certification.  
I7. No private prompts, completions, cookies, bearer tokens, raw tool arguments or user-visible ChatGPT content in basic observability. Consent-governed encrypted debug payloads, if ever added, need separate retention policy.  
I8. Stale lease or permission denial fails closed. Read-only observation failure may be reported as a coverage gap, never converted into permission to retry or mutate.  
I9. Every retry inherits finite parent deadline, money/token ceiling, attempt budget and provider-wide rate control.  
I10. Each distinct agent work item owns scoped resource keys, isolated worktree/branch, exact expected file SHA and an independent reviewer; merge control is centralized, not "last writer wins".

## 3. Authoritative and observational architecture

```
Owner task contract (immutable revision, budget, risk)
  → admission/auth → single durable Autopilot ledger (PR #1; pending)
    → leased owner + fence + scoped approval
    → transactional outbox + external-effect reservation
      → trusted tool adapter → external API / GitHub / scoped MCP
      → independent read-back receipt + revision verifier
        → evidence-gated task projection
        → metadata event export with (producer_id, source_event_seq, event_id)
            → read-only JSONL inspector → issue codes / operator timeline
            → optional Chrome MV3 companion (read-only projection)
```

Browser UX is not an authoritative task queue. Chrome Manifest V3 worker suspension should be handled by durable checkpoints, Native Messaging allowlists and reconnection from trusted cursors, not an unbounded keep-alive loop. Unofficial ChatGPT DOM state or remote-debugging events cannot certify success or replace supported provider APIs.

## 4. Proposed versioned metadata event contract

The offline candidate follows **proposed PR #7** field names as *one competing proposal*, not an already deployed contract:

```json
{
  "schema_version": 1,
  "event_id": "7da862e8-7217-4446-9dbd-9d7ea07c1096",
  "producer_id": "worker-boot-uuid",
  "source_event_seq": 12,
  "run_id": "a3efac3d-66f2-4d11-86f0-697f67c248e3",
  "task_id": "f8ba2f44-941a-4778-89e9-87be4b9e7ca9",
  "attempt_id": "ea46d3b5-0c6f-4892-897e-4b02f2b0e5b9",
  "kind": "tool.effect.reserved",
  "observed_at_utc": "2026-11-22T10:00:01Z",
  "causation_event_id": null,
  "effect_key": "stable-within-scope",
  "lease_fence": 7,
  "evidence_refs": []
}
```

PR #6 uses `schema/seq/phase/event_type` and PR #7 uses `schema_version/source_event_seq/kind`. Do NOT silently treat these as equivalent. Ratify one canonical protocol with version negotiation, a documented signed/allowlisted adapter and backcompat fixtures. Provenance identity must include environment, trusted producer incarnation, exporter version and segment cursor. Untrusted textual `trust_level: independent_verified` is NOT actual independent verification.

JSONL segments need 16-KiB default per-line limit, 100k-event default count limit, bounded error output, UTF-8 parsing, no unbounded log echo, safe rejection of unknown versions/fields and fixed-size ACL-protected storage. Detect internal per-producer sequence gaps and contradicting duplicate IDs. A missing prefix or suffix cannot be observed without a segment manifest. Causal edges are a DAG, possibly partial across segments. Use O(V+E) cycle detection.

## 5. Causal stop/failure diagnosis

| Evidence | Stable classification | Permitted next action |
|---|---|---|
| 429, Retry-After, provider ID | RATE_LIMITED | Global jittered bounded cooldown |
| 401/403 or approval deny | AUTH_EXPIRED / POLICY_DENIED | Stop; explicit human recovery |
| Session terminated on MCP observer | MCP_DISCONNECTED | Flag stale observer; never infer task stopped |
| Missing worker heartbeat | POSSIBLY_STALLED | Probe lease and effect state; no eager restart |
| Approval waiting or intentional blocked | WAITING_APPROVAL / BLOCKED | Suppress false dead-worker alert |
| Lease epoch mismatch | STALE_FENCE | Reject tool mutation at gateway |
| CI pass on wrong SHA | CI_REVISION_MISMATCH | Recheck exact target revision |
| Outbox reserved effect without trusted receipt | EFFECT_OUTCOME_UNKNOWN | Quarantine and independent read-back; NO blind retry |
| Duplicate event ID with inconsistent body | DUPLICATE_ID_CONFLICT | Quarantine producer, inspect exporter |
| Producer seq gap inside captured segment | OBSERVABILITY_GAP | Retrieve missing segment; do not fill with inference |
| Acknowledgment without reservation or receipt | INCOMPLETE_EFFECT_PROOF | Request ledger/outbox evidence |
| Agent says `done` without verifier | SUCCESS_WITHOUT_VERIFICATION | Deny certification |
| No objective fault evidence | UNKNOWN | Keep unresolved, bounded investigation |

Terminal states must include who, action, target, code revision, reason, effect reservation/receipt, independently verified result, and permitted recovery. Root-cause confidence is evidence-relative and should preserve alternate hypotheses.

## 6. Parallel agent collision matrix

| Collision | Required remedy |
|---|---|
| PR #4, #5, #6 all change API adapter | One owner approves canonical HTTP 409/422/inflight contracts; cherry-pick only after behavior+CI equivalence; never merge all three blindly |
| #1 task ledger vs bridge retry cache | Clearly separate request dedup from authoritative side-effect reservations |
| #3 approval callback vs parallel ACP prompts | Test callback isolation, unknown permission IDs fail-closed, same-session serialization and async thread boundaries |
| Multiple agents change same file | Per-file/resource lease + optimistic exact SHA and one merge arbiter |
| 30 workers each seq=1 | Use producer-specific sequence namespaces |
| 30 workers all receive 429 | Provider-wide circuit breaker/token bucket; single cooldown group |
| Model context runs out | Durable checkpoint and replacement attempt under same parent task and fence; no "replay prompt and hope" |
| Browser service-worker killed | UI cursor restore; native host owns durable truth |
| Observer goes down | Unknown visibility; independently monitor observer itself |
| PR appears merged while check is older | Revalidate merged HEAD; no SHA-agnostic green badge |

## 7. Proposed offline diagnostic candidate

A separate, tested ZIP includes `scripts/hermes_gpt_trace_audit.py` and `tests/test_hermes_gpt_trace_audit.py`. It strictly validates metadata-only events and emits JSON anomalies and exit codes `0` clean, `1` warning, `2` critical, `3` input/config invalid. It never logs the raw input line, executes commands, opens network sockets, grants approval, changes ledger state, or retries writes. Synthetic cases include 30 workers, out-of-order events, causation cycles, idempotent duplicate delivery, effect uncertainty, missing evidence, human approval wait and 1500-node event chain.

**Known limitations:** It verifies the consistency of **given** records, not historical completeness or authenticity. Without an authenticated exporter and trusted ledger receipts, never let its output authorize completion. The code is packaged separately; this commit documents design and safe integration gates only.

## 8. Prioritized engineering ideas — transparent non-empirical scores

Weights: correctness 30%, action safety 25%, feasibility 20%, scale 15%, maintenance 10%; each dimension 1–5, displayed score = weighted score / 5 × 100. These are reviewed *judgments*, not observed SLOs.

| Idea | Correct | Safety | Feasible | Scale | Maintain | Score | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Strict offline trace inspector | 5 | 5 | 5 | 4 | 5 | **97** | Proof of concept only |
| Resource leases + one merge arbiter + CAS | 5 | 5 | 4 | 5 | 4 | **94** | Test with PR #1 |
| Durable ledger/outbox/fencing | 5 | 5 | 3 | 5 | 3 | **88** | High priority, gated integration |
| Read-only MV3 status companion | 4 | 4 | 3 | 4 | 4 | **76** | Need real local code inspection |
| OpenTelemetry export and dashboard | 4 | 3 | 4 | 4 | 4 | **75** | Only after real instrumentation |
| Blind self-replay / unofficial browser automation | 2 | 1 | 2 | 2 | 1 | **33** | Reject |

Inspector scoring reflects *low operational risk*, not proof that it provides full observability. Do not optimize pretty logs before authoritative evidence.

## 9. Fault injection gates and release conditions

**Offline tested:** duplicate delivery; conflicting ID/sequence; internal gap; 30 producers starting at sequence 1; out-of-order delivery; missing causal predecessor; cycle; reserved/unknown effect; attempt crossover; unsupported schema; missing success proof; pending approval; bounded malformed input; 1500-event DAG. 60 synthetic tests PASS in isolated container, not full Hermes CI.

**NOT EXECUTED:** Chrome/Native Messaging restarts, installed extension audit, Windows/WSL fault injection, actual live GPT session, 100-way gateway retries, 30/50 concurrent file writers, real provider auth/429 faults, source-to-ledger exporter validation. No experimental result should be fabricated for those.

Gate before deployment: obtain local extension source SHA and owner-approved access; ratify one source event schema; implement authenticated exporter and signed/trusted receipts; verify no sensitive data in logs; pass 100-way duplicate/stop-signaling tests; verify replay safety under crash windows; perform 30/50-agent contention tests and MV3 worker lifecycle tests; get independent CI on exact merged SHA; write rollback/runbook and obtain explicit release approval.

## 10. Decision log and sources

**ADR-OBS-001 ACCEPTED DRAFT:** read-only offline auditor lane, no competing API patch.  
**ADR-OBS-002 PROPOSED:** canonical schema council across PRs #4/#5/#6/#7.  
**ADR-OBS-003 PROPOSED:** durable outbox / fenced effect gateway / exact-SHA review.  
**ADR-OBS-004 REJECTED:** browser DOM/ChatGPT scraping as unattended worker API and blind external action replay.  
**ADR-OBS-005 BLOCKED:** extension integration until local code access and human security gate.  
**ADR-OBS-006 ACCEPTED:** distinguish observed fact, hypothesis, evidence gap and independently verified action.

Primary sources (official/spec):
- Chrome MV3 lifecycle https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome Native Messaging https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chrome messaging security https://developer.chrome.com/docs/extensions/develop/concepts/messaging
- Chrome extension storage https://developer.chrome.com/docs/extensions/reference/api/storage/
- W3C Trace Context https://www.w3.org/TR/trace-context/
- OpenTelemetry events https://opentelemetry.io/docs/specs/semconv/general/events/
- OpenTelemetry GenAI https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- GitHub API best practices https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- Temporal activities https://docs.temporal.io/activities

See parallel drafts #1–#7 and exact baseline at https://github.com/Podtverzhdeno/hermes-agent/pulls.


**Local connector recheck (2026-11-22, later in the same review):** `Local_WorkSpace.list_workspaces` subsequently succeeded and exposed only workspace alias `shelter` (the separately scoped Obsidian project), with read/write permission inside that root. **It did not expose the Windows Hermes/Tunnel extension directory or the projects/tools roots.** Earlier `Session terminated` errors were transient or profile-dependent; they should not be interpreted as persistent total MCP failure. Local Hermes extension code/hash, browser runtime and native host remain **unverified / outside granted scope**. No attempts to traverse outside the allowed root were made.


**Offline test update, 2026-11-22:** The separately distributed stdlib inspector now passes **60/60 synthetic tests**. Stronger invariants: any `task.completed.succeeded` assertion remains *unverified* without a distinct authenticated ledger/verifier lookup, even if `trust_level=independent_verified` is present; enforce reason codes on failed/blocked stops, lease fence on effects, reject multiple reservations of a stable effect, detect same-producer causal inversion, preserve critical severity totals even when report output is truncated, cap CLI-tunable resource limits and reject malformed UTC/unknown states. Synthetic 50,000-event, 30-producer input (~16.8 MB) was processed in 3.48 s at 194,924 KiB peak RSS on an isolated container; live system throughput remains unknown.
