# GPT Bridge causal auditor — evidence and fault log (2026-11-22)

**Status:** isolated source change, not running/live. This log captures observations separately from hypotheses and external integration gates.

## Provenance

- Target repository: `Podtverzhdeno/hermes-agent` (owner-connected GitHub).
- Base main observed: `7e9100901819ee44c16b4ddcb79a6bcb7909f591`.
- Other pending PRs at audit: #1 Autopilot durable ledger; #2 skill harness; #3 ACP approval isolation; #4/#5/#6 overlapping GPT API transport/idempotency fixes; #7 existing GPT bridge SDD. None of these branches was merged as part of this change.
- `Local_WorkSpace.list_workspaces` returned `INVALID_ARGUMENT / Session terminated` in this session. No live Windows host, actual extension process, Obsidian files, Chrome logs, or user production credentials were inspected.
- Relevant upstream technical constraints were read from primary sources listed in `CAUSAL_AUDITOR_SDD.md`. This is NOT millions of sources or a production benchmark.

## Real implementation activity

| Seq | Classification | Defect/idea | Intervention | Evidence and limitation |
|---|---|---|---|---|
| 1 | SOURCE_OBSERVED | Draft PRs #4–#7 describe errors, idempotency, causal events but no merged offline parser with safe classifications | Own only a new isolated observer and new docs, avoiding edit collisions | PR metadata/filenames checked; these are unmerged designs |
| 2 | DESIGN | Unknown external write must never be auto-retried just because an ack was *claimed* | Pure read-only `EFFECT_OUTCOME_UNKNOWN` and `external_effect_retry_allowed=false` | Tests for reserved/unknown/ack edge cases; ledger still independent |
| 3 | LOCALLY_TESTED | 30 agents can emit the same sequence 1 without conflict | Scope uniqueness to producer incarnation, not global counter | 30-producer deterministic unittest |
| 4 | LOCALLY_TESTED | UI green while external effect unknown or verifier SHA stale | Check task completion consistency; never certify success from metadata | success-with-unknown and SHA mismatch tests |
| 5 | LOCALLY_TESTED | Malicious JSON `reason_code`/`state` list could raise unhandled TypeError | Added explicit type validation, reject malformed fields | Type-confusion regression test added after self-review |
| 11 | LOCALLY_TESTED | Deeply nested JSON could trigger an unhandled `RecursionError`, and null `occurred_at_utc` could pass a required-field check | Catch decoder recursion failures; require non-null UTC; reject `task.completed` with nonterminal `state_to` | Three new regression tests; 49 total locally passed |
| 10 | LOCALLY_TESTED | File/event volume can exhaust resources with dozens of producers | Added 64 MiB total-byte cap, 50-worker/5000-event replay soak, and capped findings with full counts | Synthetic tests only, not a production load benchmark |
| 6 | LOCALLY_TESTED | Receipt-less ack or cross-producer ack without causal link can falsely clear unknown | Require evidence IDs and causal ordering to related reservation | ack-before-reserve, cross-producer causation tests |
| 7 | LOCALLY_TESTED | Two distinct reservations for one effect key/fence might be treated as an ordinary dedup | Flag multiple reservations; do not infer safe replay | duplicate-reservation test |
| 8 | DESIGN | Native extension service-worker suspension is not a task crash | Keep observer independent, propose cursor/resubscribe and no automatic dispatch from browser | Requires real extension source + live failure test |
| 9 | BLOCKED | Local_WorkSpace observer cannot be reached | No attempt to fabricate runtime/Obsidian logs; record blocker | Connector errors, awaiting controlled reconnect |

## Local isolated test execution

Run from the generated repo-relative directory:

```sh
python -m unittest discover -s tests/hermes_observer -v
python -m py_compile hermes_observer/audit.py
```

As of authoring this log: 49 tests passed locally in the isolated container (`Ran 39 tests ... OK`) after fixes (including adversarial JSON depth, null required timestamps, and false task completion while `running`). This is not full Hermes integration CI, not proof of Windows extension behavior, and not a production run. Recheck this count and attach exact head SHA once GitHub CI executes.

## Potential fault stories and evidence still needed

- `H-01` Remote commit then lost ack: simulated at metadata level; actual provider read-back and crash window NOT tested. Needs verified receipt connector.
- `H-02` Browser sleeping 10–30 minutes: not observed; needs MV3 lifecycle/user consent instrumentation.
- `H-03` Malicious `traceparent` with sampling pressure: standards-based hypothesis; needs authenticated ingress rate limiting and traffic test.
- `H-04` Two local agents editing the same Obsidian note: requires optimistic `SHA256` expected revision; no local write performed.
- `H-05` 100 simultaneous gateway Idempotency-Key calls across processes: other PRs cover process-local improvements; no distributed safety certification without durable coordinator.
- `H-06` Connector outage during an effect: should produce partial evidence and blocked status, never forged completion; no live runtime was available.

## Merge/review gates

- Independent review of observer status/authority wording and false-negative risk.
- Confirm GitHub Actions success on exact PR head SHA and run normal repository tests where possible.
- Inspect that diagnostic output contains only allowlisted identifiers; no prompts/private messages/credentials/exception text.
- Test SDK/integration adapters only after exporter exists; no hidden browser automation or privilege expansion.
- Reconcile overlap with PR #7 SDD when merging; preserve both logs or consolidate with cited revisions, never overwrite another agent's work.

**Operating policy:** never say a task is complete solely because the auditor exits zero. A zero result means only that the supplied, untrusted, bounded slice did not violate these specific offline invariants.

## Addendum: live multi-PR collision observation (2026-11-22 UTC)

- **SOURCE_OBSERVED:** GitHub open PR query now includes **25** active draft/open proposals, #1–#25. Read-only observer candidates #9/#12/#16/#21/#25 and several others overlap conceptually, even if filenames do not collide. **This invalidates any older inventory limited to #1–#11 as a complete integration proof.**
- **SOURCE_OBSERVED:** #4/#5/#6 simultaneously edit `gateway/platforms/api_server.py` with different idempotency and SSE result contracts. #4 also created `gateway/gpt_bridge_event_audit.py`; #5 now has a native `/v1/runs` read-only observer. These appeared in a fresher review than the initial PR descriptions; don't assume a static scope.
- **SOURCE_OBSERVED:** #23 is explicitly stacked on #12; merging #23 alone or testing it against a moving base cannot establish correctness. #24 proposes an independent collision guard, but its recorded snapshot describes only 11 PRs; reindex before any integration.
- **DESIGN DECISION CA-10:** This isolated PR #25 is an **offline diagnostic oracle**. Its generic NDJSON v1 is **not compatible** with native Hermes `/v1/runs` SSE without a reviewed, authenticated, versioned translator. Never claim it is the live run observer.
- **DESIGN DECISION CA-11:** Modern upstream native Runs/Kanban owns lifecycle if verified by the installed target; select a single production observer/ingress and single PR collision gate. Do not launch 25 independent monitor/ledger implementations.
- **BLOCKED:** No Windows extension source or runtime through the disconnected Local_WorkSpace connector; no fact about its current deployment can be inferred from any PR's Python unit tests.
- **ACTION:** Updated this SDD with explicit collision matrix, runtime compatibility blocker, release veto gates and one-owner merge protocol. This review added no privileges, credentials, automated retries or running worker.

## Third self-audit: empty input and terminal contradictions (2026-11-22 UTC)

- **LOCALLY_TESTED DEFECT:** an entirely empty NDJSON file returned exit code 0 (`no_anomalies_in_supplied_slice`). A caller might misread zero evidence as a healthy monitor. Fix: `EMPTY_SNAPSHOT`, status `incomplete_observation`, exit code 3.
- **LOCALLY_TESTED DEFECT:** two `task.completed` events with opposite terminal outcomes on the SAME `attempt_id` could slip through event-ID/sequence checks without an explicit conflict. Fix: `CONFLICTING_ATTEMPT_TERMINAL_STATES` (critical); when attempt identity is absent classify as `TERMINAL_CONFLICT_WITHOUT_ATTEMPT_ID` (incomplete) because historical retries may differ legitimately.
- **REGRESSION:** 46 offline stdlib tests passed on Python 3.13.5; new cases cover empty snapshot, single-attempt terminal conflict, legitimate distinct attempts and absent attempt ambiguity. **No claim** of 3.11/3.12 CI, real host execution or source authenticity.
- **CROSS-AGENT REVIEW:** another worker correctly noted that this input schema requires `occurred_at_utc`, whereas a competing observer expects `observed_at_utc`. This is unresolved until the canonical ingress and native Runs translator are versioned. This PR remains an offline negative-test oracle, not a production logging source.

## Fourth self-audit: fence identity, severity truncation, and bounded load

- **LOCALLY_TESTED DEFECT:** two worker incarnations using the same logical `agent_id="A1"` but distinct `producer_id` could claim the same fence without a conflict because ownership collapsed to agent display name. Fix: ownership key is `(producer_id, agent_id)` for each `(task_id, lease_fence)` pair, never display name alone.
- **LOCALLY_TESTED DEFECT:** first-250-finding truncation could hide a critical late event after hundreds of gaps. Fix: severity-prioritized deterministic bounded selection; all finding counters remain complete within read bounds. Replay-order regression added.
- **ISOLATED BENCHMARK (not system performance):** Python 3.13.5, `BytesIO`, single local process, no disk/network: 50,000 valid event rows (~11.5 MB) audited in ~0.88 s; 50,000 invalid event rows in ~2.74 s; 250 visible findings with 50,000 counted. These are one-off durations and not a throughput SLO, confidence interval, browser or Windows test.
- **REGRESSION:** 49/49 isolated stdlib tests pass after these corrections. This work remains a draft offline oracle.
