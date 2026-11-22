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

## Fifth source review: CDP external browser ownership / GPT extension (2026-11-22)

- **SOURCE_OBSERVED:** PR #13 `feat/gpt-observability-sdd-20261122` and PR #15 `fix/preserve-external-cdp-browser-20261122` independently edit `tools/browser_tool.py`. #13 targets credential/CDP endpoint redaction; #15 fixes external browser cleanup so agent A does not kill another task's Edge process.
- **RISK:** these are distinct, valid-looking improvements to one hot-path file, but **isolated success is not combined success**. A naive merge can lose redaction or reinstate destructive teardown. Their own authors state the live Windows extension was not inspected.
- **DESIGN DECISION CA-12:** `browser_process_owner`, `cdp_target_id`, `attachment_epoch`, `agent_incarnation`, and `task_lease_fence` are separate; never infer browser ownership from a model/agent name. Shared CDP targets require one authenticated writer, not 30 concurrent UI actors.
- **ACTION:** Section 14 of SDD now records six precise controlled E2E tests, UI evidence design and non-destructive cleanup guarantees. This PR itself does NOT modify browser control or launch an extension.

## Sixth evidence review: exact GitHub Actions CI, cross-agent noise, and retained blockers

- **EXACT_HEAD_CHECKED** PR #25 at `c4227c78994b1f3debe8c46a9b92dbf460887430`: run `45014925014` (`Hermes GPT Causal Audit (offline)`) concluded **success**. Individual Python 3.11 / 3.12 / 3.13 jobs also all **success**; this validates scoped offline tests, not live Windows or browser integration.
- **EXACT_HEAD_CHECKED** PR #25 full Tests run `45014925022` concluded **failure**; `28 failed, 7550 passed, 171 skipped`. Inspected job log `137185133045`. Failures included missing OpenAI credentials, stale Codex expectation and `Test exceeded 30 second timeout` file read guard cases. No evidence that these failures were introduced by the standalone auditor (it does not touch runtime paths); baseline parity comparison in identical CI environment still required.
- **EXACT_HEAD_CHECKED** PR #21 at `d45194b0e0e12972d4aa99bf480db1adc06afd0b`: Python 3.11/3.12 targeted offline jobs failed `ModuleNotFoundError: No module named 'yaml'` from implicit package import chain before executing observer tests (GitHub job `137184637160` verified). Posted source-specific, non-duplicative GitHub review comment #`7078161429` recommending isolated package import or honest provisioned dependencies.
- **EXACT_HEAD_CHECKED** PR #5 at `ba535dc5a0a48f205165efaccff4319f813587a1` full Tests failed: the newly redacted `Internal server error.` contradicted a legacy raw-exception assertion; authenticated observer's test assumed `ProxyHandler({})` survives in `opener.handlers`, which need not hold. Posted a precise independent comment #`7078167997` recommending behavior-based proxy credential test and preserving redaction. Other agents already repeatedly reported a distinct, much more severe *source-path* risk of repeating mutating external effects after exception; this work did not spam duplicates.
- **SOURCE_OBSERVED** Multiple agents independently edited and documented overlapping components. This evidence log and SDD now include incident fingerprinting by stable invariant/resource, with separate observations per reporter, to prevent duplicate issue storms and accidental last-writer wins.
- **SOURCE_OBSERVED** Browser PR #13 and #15 overlap in a critical file; added six controlled E2E cases to SDD and separated browser process ownership, CDP target and task fence. No local browser connection or external process was opened by this review.
- **BLOCKED** Local_WorkSpace connector still returned `Session terminated` during this work. No actual user Chrome extension binary/manifest or active session/process/log has been inspected; no live monitoring and no E2E completion claim.
- **DECISION** Keep GitHub PR #25 DRAFT. Exact SHA scoped CI **success** coexists with overall Hermes Tests **failure** and an unverified native extension integration. Fixes are tracked in separate lanes; do not merge or deploy without trusted production data and re-validation.

## Seventh evidence correction: historical Windows GPT extension route and connector scope

- **HISTORICAL_OWNER_CONTEXT (2026-11-11, not revalidated now):** candidate unpacked extension path `C:\Users\Vadim\Tunnel\chat-launch-smoke-desktop-test\web-extension`; historical version `0.6.6`; browser bridge expected port `18763` but had no listener in earlier configuration. Separate observer MCP uses `8765`; scoped editor uses `8766`.
- **HISTORICAL_OWNER_CONTEXT (2026-11-14):** model/backend name `web-chatgpt-high-cdp`; two canary markers reportedly succeeded. These are prior connectivity signals, not a current supervised event source or authorized write capability.
- **SOURCE_OBSERVED IN CURRENT REVIEW:** later `Local_WorkSpace.list_workspaces` returned a `shelter` Obsidian-only root; secondary read-only workspace returned `temp-folder`. An earlier call had returned `Session terminated`. No connector exposed `C:\Users\Vadim\Tunnel`; therefore extension source/manifest could NOT be safely opened or modified. Report the actual `SOURCE_SCOPE_UNAVAILABLE` blocker rather than saying the entire local MCP is always down.
- **SOURCE_OBSERVED IN CURRENT REVIEW:** fresh GitHub query had 30 open PRs (#1–#30). #26/#30 add redundant observer candidates and #27/#28/#29 propose more PR gates. One canonical observer and one canonical release gate remain an architectural release requirement.
- **ACTION:** added Section 17 to SDD with a source-pinned discovery path, transport separation, read-only version/capability handshake, explicit failure matrix and allowed scope boundary. No assumptions about a working port, no local file access outside granted roots, no browser navigation or credential handling.

## Eighth evidence: actual Tunnel source, versions, 60-event cap, tab ownership defect

- **SOURCE_CONFIRMED** connected GitHub repository `Podtverzhdeno/Tunnel`: manifest 0.6.6 (`609c794`), `web-extension/background.js` (`e6f2fa5`), `background_content.js` (`a611a8c`), `web-companion/bridge.py` (`eaf301a`), `Hermes-WebGPT/monitoring/queue_monitor.py` (`c22e457`), and stack diagnostics (`3ce6bdb`). Source location verified; no claim running Windows installation equals this GitHub snapshot.
- **SOURCE_CONFIRMED** portable archive version mismatch: Tunnel README/portable QA say checked-in extension 0.6.6, tested ZIP base 0.8.5 and non-installed snapshot 0.9.7. Bridge `completion_client_ready` hardcodes heartbeat `0.6.6`. Operator must discover installed bridge+worker version pair before any deployment; relaxing version gate blindly is unsafe.
- **SOURCE_CONFIRMED** bridge `_event` only retains last 60 per-job metadata event objects, timestamped at second resolution; no durable global producer sequence or immutable full causal history. Legacy exporter must output `coverage_undetermined` rather than artificial complete history. Existing Relay monitor is read-only and does not measure phase durations or final Telegram delivery.
- **SOURCE_CONFIRMED** `background_content.js` calls `button.click()` before `stage("send_clicked")`; a crash window exists. No claim a duplicate prompt has actually happened; design a durable before-send reservation plus reconciliation and noReplay.
- **SOURCE_CONFIRMED** `background.js` noncompletion `finish()` uses `tab.url.startsWith("https://chatgpt.com/")` instead of exact task-conversation ownership; watchdog ~420 s can run with no saved URL. If the operator navigates that tab to a personal ChatGPT conversation, it may be closed or blanked by competing #17/#11 cleanup proposals. This is a **source-level destructive eligibility risk**, not a real-tab incident. Posted focused reviewer comment on Tunnel PR #17 ID `7078269962`, leaving code ownership with its current author.
- **SOURCE_CONFIRMED** the live browser code is mirrored across `web-extension` and `web-companion`; Tunnel PR #16 owns mirror equality enforcement, and #13/#19 own incident/queue monitor lanes. Avoid a second interfering tool implementation.
- **ACTION** SDD Section 18 records exact source paths/blobs, five-phase end-to-end evidence contract, lossy legacy telemetry boundary, non-destructive tab regression acceptance and owner handoff. No extension install/Windows browser edit, hidden Send or Telegram request occurred.

## Ninth change: actual Tunnel rolling-event compatibility oracle (isolation, not a new worker)

- **IMPLEMENTED** `hermes_observer/tunnel_legacy.py` read-only pure function over published Tunnel v0.6.6 bridge's allowlisted `at/stage/reason` JSON, capped at 60 records/32KiB. Never synthesizes a durable event ID/sequence, never grants permissions, never claims all events, effect receipt or final Telegram delivery. No FS/network input, no side effects.
- **IMPLEMENTED** 24 new stdlib unit tests in `tests/hermes_observer/test_tunnel_legacy.py`; prior 49 remain unchanged. **LOCAL_TESTED 73/73 PASS** on Python 3.13.5.
- **LOCALLY_FOUND_AND_FIXED** huge JSON integer (>4300 digits) triggered an unhandled Python `ValueError` instead of a typed invalid-source diagnostic. `json.loads` now returns `LegacyTraceError("invalid_json")` with regression. Deep recursive JSON and duplicate keys also fail safely.
- **LOCAL_FUZZ** fixed-seed 9000 malformed/mixed traces, no unhandled exceptions and no output with `mutation_allowed`, `coverage_complete`, `final_delivery_verified` or `external_effect_retry_allowed` set true.
- **DISTINGUISH SOURCES** Tunnel bridge event-file shape was verified from connected GitHub `bridge.py` blob `eaf301ac15ad301464159438d6431cbc91d3e323`. Input file authenticity and installed browser/host versions were NOT authenticated. No native Hermes SSE adapter or Telegram write confirmation is in this patch.
- **PENDING** New GitHub head's 3.11/3.12/3.13 CI must complete before matrix success is asserted. Older matrix for only 49 tests remains legitimate evidence for its previous exact SHA, not for the new code.
