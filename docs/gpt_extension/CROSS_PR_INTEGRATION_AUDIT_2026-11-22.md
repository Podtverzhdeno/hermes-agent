# Hermes ↔ GPT — cross-PR integration and atomic inventory audit

**Point-in-time observation:** 2026-11-22 around 10:45 UTC, GitHub REST + connected GitHub file inventories.  
**Base:** fork main `7e9100901819ee44c16b4ddcb79a6bcb7909f591`.  
**Status:** Review proposal / NO MERGE APPROVAL / no runtime monitor enabled.  
**Observer:** PR #13. **Coordination partner:** draft PR #14.

## Snapshot summary

GitHub returned **16 open draft PRs**. Changed-file inventories referenced **144 distinct paths**, **5 exact shared paths**, yielding **14 pairwise exact-path collision relationships**. This count is not an atomic transaction and can change while agents push.

| Shared file / cluster | PRs | Precise risk | Integration constraint |
|---|---|---|---|
| `pyproject.toml` | #1, #9, #12, #13 | All edit setuptools include in same line; dropped packages after sequential merge | One final manifest with selected packages, wheel installation smoke check |
| `gateway/platforms/api_server.py` | #4, #5, #6, #11 | Competing cache, request-idempotency, SSE, error and auth semantics | Select one canonical API implementation; port verified features and tests deliberately |
| `autopilot/ledger.py` and `tests/autopilot/test_ledger.py` | #1, #10 | Derived safety improvements to the same unactivated prototype | Treat #10 as derived/stacked work on a moving/frozen #1 snapshot, not independent production scheduler |
| `tools/browser_tool.py` | #13, #15 | CDP endpoint redaction and externally owned browser cleanup share a file | Distinct hunks today; combined browser ownership, logs, cleanup and canary tests required |

**Semantic overlap despite different paths:** GPT SDD, event observer and diagnostics are separately proposed in #7/#8/#9/#12/#13/#16. Multiple read-only analyzers may coexist, but they **cannot** each declare distinct authoritative status or introduce multiple unsynchronized event schemas. Choose one trusted publisher and one versioned causal envelope; adapters map to it and run independent tests.

## Real dependency/authority graph

```text
Current fork main (April 2026) -> isolated review branches
    |- #1 prototype Autopilot kernel -> #10 derived safety observer
    |- #4 API idempotency candidate -> #11 stacked request preflight
    |- #5 API idempotency candidate [alternative to #4/#6]
    |- #6 API trace/SSE/idempotency candidate [alternative to #4/#5]
    |- #3 ACP approval isolation
    |- #13 CDP secret-log redaction + diagnosis
    |- #15 externally-owned CDP browser cleanup
    |- #14 read-only PR collision gate
    |- #7/#8/#9/#12/#16 observers, schemas, docs (semantic overlap)
    |- #2 skills harness
          |
          v
Independent upstream parity gate: NousResearch/hermes-agent v0.23.3
          |
          v
ONE canonical Kanban task/run lifecycle when upgraded and validated
          |
          + one trusted action-effect journal, approvals, revision verifier
          + one transport-neutral event schema + read-only observers
          + bounded per-tab CDP lane / supported GPT API adapter
```

Verified latest stable upstream via GitHub API: `v0.23.3`, published 2026-11-20 UTC (release date November 19). Official Kanban has `task_runs`, `task_events`, worker lanes/heartbeats/reclaim/review. The old fork and the user's local Windows installation **are not proven upgraded**. Autopilot PR #1 must not become a second top-level dispatcher next to modern Kanban.

## Corrective merge choreography

1. **Gate A — stabilized inventory:** snapshot base SHA and PR ID/ref/head, read changed files, then fetch base and every head again. If any changed, label inventory INCOMPLETE and retry with bounded budget. Snapshot paths alone do not ensure consistency; handle non-main-target stacked PRs and frozen snapshot branches.
2. **Gate B — authority:** choose upstream parity/migration strategy before merging control planes. No new duplicate production scheduler, approval service or mutable status DB.
3. **Gate C — API semantic selection:** common fake-client tests for #4/#5/#6/#11:
   - identical key/payload concurrently → at most one execution;
   - key with changed payload → rejection;
   - completed response replay keeps original response/session ID;
   - remote effect completed but ACK lost → UNKNOWN, no blind retry;
   - stream+idempotency semantics explicit (if unsupported, reject before model);
   - failure SSE is typed error, never fabricated success;
   - authorization/CORS, input validation, rate limit and redacted errors.
4. **Gate D — CDP combined correctness:** integrate #13 logging and #15 browser cleanup after verifying externally owned browser is **not closed** on detach. Verify no raw URL/credentials in logs, no mixed tabs across tasks, exact fence, ACK/readback and cancellation behavior.
5. **Gate E — package union:** if accepted, retain `autopilot` (only if used), `gpt_bridge`, `gpt_companion`, `gpt_extension`, plus subpackages. Check installed wheel contents on Windows and Linux and run package import smoke tests. Don't unconditionally accept every competing package solely because it exists.
6. **Gate F — independent CI:** freeze candidate integration SHA and require tests/security/typing, explicit no-side-effect fault injection and rollback manifest. Recheck after *every* new commit; passing old SHA never verifies new HEAD.
7. **Gate G — owner local rollout:** only after trusted local runner and authorized CDP/Obsidian bridges are observable. Verify actual Windows process/extension version, local working copy, precise file hashes, profile permissions and safe rollback. User-visible canaries are not completion receipts.

## Multi-agent execution contract

Each agent has a unique immutable task/run/attempt/fence, exclusive file ownership, exact expected SHA, limited tools and parent budget. Reporter logs both observed symptom and proven cause status, event sequence and source revision. Independent reviewer confirms before merge or any external-effect retry. STOP/cancel must propagate to new claims and tool issuance, while in-flight uncertain effects remain reserved until reconciled.

One canonical event envelope and versioned reason code registry must be selected. Prefer explicit adapters over rewriting similar diagnosis code in many places. Do not let separate agents self-certify their own work or give the same UI browser lane to several writers.

## Auditor bugs / constraints to verify in draft PR #14

- Its `collect(base="main", prs_only=True)` filters out PRs with non-main bases (#11 is stacked on #4; #10 has tracked a PR #1-derived/snapshot base). `prs_only=False` may include those branches but count inherited ancestor changes as independent collisions.
- GitHub inventories are not transactional: base and PR heads may move between list and file fetches. A second head/base verification pass is essential before a green result.
- A reported `NO_COLLISION_FOUND_NOT_MERGE_APPROVAL` means only no collision in the *validated snapshot*, never CI approval, security proof, or live task health.
- Documentation-only PRs can semantically conflict on policy/event schema even without shared paths. Include a capability-ownership registry reviewed by a single integration owner.

The above PR #14 feedback was posted as a GitHub PR conversation comment. No other agent's branch was rewritten.

## Sources and proof boundaries

- Current fork PR inventory: https://github.com/Podtverzhdeno/hermes-agent/pulls
- Existing #14 coordination gate: https://github.com/Podtverzhdeno/hermes-agent/pull/14
- Upstream release: https://github.com/NousResearch/hermes-agent/releases/tag/v0.23.3
- Official Kanban worker lanes: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban-worker-lanes.md
- Official Kanban: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md
- This run's GitHub PR changed-file listings, branch/bases, controlled source diffs for #1/#4/#5/#6/#9/#10/#11/#12/#13/#15.
- Local Workspace MCP = Session terminated. No direct local browser/extension/Obsidian evidence; no production test.

**Never extrapolate this one-time GitHub source snapshot into an actively running host watchdog.** A new snapshot must be taken whenever an operator asks for current status.
