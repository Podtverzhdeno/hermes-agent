# Hermes GPT browser extension — fault-domain and atomic protocol contract v1

**Status:** Design for independent review; *not an implementation and not an assertion of access to the owner's browser*. **Date:** 2026-11-22.
**Related work:** [GPT causal SDD](GPT_CAUSAL_OBSERVER_ADDENDUM_2026-11-22.md); PR #7 high-level SDD; PRs #4/#5/#6 competing API patches; current upstream Hermes Runs/Kanban.
**Hard gate:** actual extension source/version and Windows native host must be discovered and SHA-pinned first. Earlier reports reference a local unpacked extension beneath a Windows Tunnel directory, but that is historical, not observed in this review; Local_WorkSpace returned Session terminated.

## Explicit deployment modes and trust boundaries

- **Primary agent mode:** documented API/SDK with user-authorized credentials and a Hermes durable run/task. It can run without a browser tab.
- **Extension status mode (read-only):** optional user-visible panel showing authenticated task and diagnostic projections. Content scripts never decide success, approve an effect, allocate a worker or change the canonical ledger.
- **Optional explicit UI interaction:** user authorizes one bounded action in one target tab/conversation. Browser UI is fallible, not a machine queue or trustworthy receipt. Use only authorized integrations; never scrape credentials, bypass platform controls, interfere with CAPTCHA, or silently operate someone else's conversation.

Five failure domains must have independent error categories and health:

| Domain | Observable evidence | What is NOT proven |
|---|---|---|
| Canonical Hermes Runs/Kanban | task ID, version, active fence, durable effect state, acceptance checks | user browser connected |
| Local trusted adapter/Native Messaging host | authenticated channel, process incarnation, durable command/ack receipt | external write occurred |
| MV3 background service worker | HELLO/capabilities and last acknowledged cursor | worker always runs; JS globals survive |
| Content script + page document | document epoch, tab association, composer and response markers | provider completed after DOM changed |
| Human/user approval | exact target/action digest/expiry, explicit revocation | approval covers a different action |

A live local status panel is not a durable scheduler and must not run a watchdog whose loss changes task state.

## Message contract, producer ordering and version negotiation

```json
{
  "protocol": "hermes-gpt-bridge/1",
  "message_id": "uuid",
  "reply_to": null,
  "run_id": "opaque-assigned-by-server",
  "task_id": "opaque-assigned-by-server",
  "action_id": "stable-business-operation-key",
  "attempt_id": "unique-physical-attempt",
  "lease_fence": 17,
  "agent_id": "server-assigned-identity",
  "bridge_instance": "new-on-host-restart",
  "extension_instance": "new-on-extension-reinstall",
  "document_epoch": "new-on-navigation",
  "conversation_ref": "opaque-validated-target",
  "producer_id": "new-on-process-restart",
  "source_event_seq": 103,
  "payload_digest": "sha256:64lowerhex",
  "policy_revision": "sha256:64lowerhex",
  "deadline_utc": "UTC ISO8601",
  "kind": "HELLO|CAPABILITIES|COMMAND|ACK|EVENT|RESULT|ERROR"
}
```

The native host authenticates the **extension origin and the owning user separately**; never trust only `Origin`, a trace ID or a page-provided field. Native host allowlisted extension ID; narrow OS ACL; sender identity verified; fixed request schema/maximum size; no arbitrary shell command endpoint; no public-loopback writer. Never send API keys, session cookies, raw prompts, private ChatGPT transcripts, full DOM or unredacted tool arguments in telemetry.

Handshake: `HELLO -> CAPABILITIES -> AUTHENTICATED -> READ_ONLY_SYNC`. Required capability list and protocol major must match; mismatch -> `UNSUPPORTED_VERSION` with read-only failure, never attempt send. Browser permission absent -> `PERMISSION_REQUIRED`, not "model stalled". One documented cursor survives MV3 service worker suspension; reconnect must replay **events only**, never user-submitted actions.

## UI send state machine (optional explicitly user-directed capability)

```text
REQUESTED
  -> LEASE_GRANTED  (server fence valid, one writer per conversation)
  -> TARGET_VERIFIED (user-approved tab and document epoch)
  -> COMPOSER_READY (no human concurrent edit; page capabilities valid)
  -> SEND_INTENT_DURABLY_RESERVED (canonical ledger effect key)
  -> INPUT_PREPARED
  -> SUBMIT_ATTEMPTED
       -> SEND_OBSERVED       (matching action observed in target conversation)
       -> SEND_OUTCOME_UNKNOWN (ack lost, tab navigated, worker suspended)
  SEND_OBSERVED -> RESPONSE_OBSERVED -> RESPONSE_IN_PROGRESS
       -> RESPONSE_COMPLETED_OBSERVED (DOM-level only)
       -> RESPONSE_STALLED / AUTH_REQUIRED / USER_STOPPED / UNKNOWN
  RESPONSE_COMPLETED_OBSERVED -> PROVIDER_RESULT_VERIFIED (if supported)
       -> TASK_CHECKED_BY_CANONICAL_VERIFIER -> FINISHED
```

**Two separations are essential:**
1. UI observation that a response message appeared is not the same as an authoritative Hermes task completed with acceptance evidence.
2. An HTTP 200, a clicked Send button, a sent bubble and a completed model result have distinct acknowledgments. If a command ack is lost **after** submit attempt, status becomes `SEND_OUTCOME_UNKNOWN`; successors may only observe and reconcile, never automatically click Send again.

If using officially documented API mode, use provider request IDs and the durable Hermes run/effect protocol; do not rely on brittle DOM landmarks. UI automation must be capability-gated, opt-in, revocable, and must not be assumed to provide exactly-once delivery.

## Timeout budget and STOP semantics

Never classify a "stuck" run from one universal 30-second timer. Maintain separately configurable policies for bridge connect, auth handshake, tab/document verification, submit acknowledgment, first result, streaming progress idle, tool step deadline, human approval, absolute run deadline and external-effect reconciliation. Values come from measured latency percentiles, not guesses.

An active heartbeat is only availability evidence. The run may be rate-limited, waiting for approval, blocked by a file lock, in a legitimate long tool, disconnected from UI, or stuck repeating tool calls (see upstream issue #100971). Require a new **independent artifact/revision-specific verification** to claim forward progress.

`USER_STOP_REQUESTED` is not `CANCEL_CONFIRMED`; a remote write may still commit after cancellation. Record request, adapter receipt and effect reconciliation separately. A human typing in the target conversation immediately invalidates automatic composition ownership; defer to the user. No "reword denied permission" retry.

## Reason catalog with required evidence

| Reason | Minimum reliable evidence | Safe next step |
|---|---|---|
| `EXTENSION_SUSPENDED` | extension worker lifecycle + missing local ack, native source healthy | restart projection, recover cursor; never resend |
| `BRIDGE_DISCONNECTED` | authenticated channel closure | reconnect with backoff, preserve last known worker state |
| `STALE_DOCUMENT` | changed document epoch after command was prepared | invalidate pending DOM references and re-verify target |
| `WRONG_CONVERSATION` | conversation ref mismatch verified before action | block send, require new explicit target selection |
| `CONCURRENT_SENDER` | existing conversation lease from independent writer/human | pause; do not steal ownership |
| `COMPOSER_CONTRACT_CHANGED` | landmark/schema probe invalid | fail before action, require reviewed selector update |
| `AUTH_REQUIRED` | provider's authenticated failure/redirect | ask user; do not harvest or rotate credentials |
| `SEND_OUTCOME_UNKNOWN` | submit attempted, no independently confirmed receipt | never retry; read-back and operator decision |
| `RESPONSE_STALLED` | progress idle past calibrated window, no pending legitimate wait | suspect only; inspect provider/stream and ledger |
| `PROVIDER_RATE_LIMITED` | 429 / server-provided retry-after | scheduler global cooldown with shared budget |
| `POLICY_DENIED` | authenticated exact capability denial | block; no bypass |
| `AUDIT_PERSIST_FAILED` | journal commit error before mutating action | fail closed at authoritative tool gateway |
| `OBSERVABILITY_GAP` | missing per-producer sequence/cursor | replay observations; never infer missing action |
| `WORKER_LEASE_LOST` | current ledger fence supersedes worker | reject new writes at trusted adapter |
| `CI_REVISION_MISMATCH` | check SHA differs from target head | rerun at exact SHA; no completion |
| `UNKNOWN` | absent trustworthy evidence | preserve uncertainty and gather proof |

Only authenticated adapters can classify provider denials, external write acknowledgments and verification results as trusted. Model interpretation may propose competing explanations but cannot convert them to confirmed causes.

## 50-agent contention and fairness rules

- Scheduler is owned by upstream Hermes; one current fenced writer for a conversation or mutable local resource. Fencing must be checked *immediately before* external mutation, not just in a model prompt.
- 50 agents may investigate concurrently but cannot allocate 50 independent retries for one shared provider rate limit. Use parent-inherited token/cost/time budgets, shared token bucket and randomized jitter; track retry amplification.
- Each role writes in isolated worktree and commits with exact base SHA, uses optimistic hash on Obsidian note, and lets independent verifier validate current head. No automated protected branch merge.
- Task A verifier cannot clear task B's no-progress alert. Old proof cannot clear new repeated-intent events; scope by task, attempt, fence and target revision. This was caught in code review and four new regression tests were added to the observer.
- Windowed log and dashboard retention/compact policies require privacy approval. Under storage pressure, privileged actions must fail closed in trusted gateway; background observer may show a loss counter/gap, never fabricate complete timeline.
- Repair agent cannot silently promote its own result to trusted. Persistent owner worktree must be synchronized by a separately validated operation, not repeated ZIP download.

## Minimum release and fault-injection matrix

| Trigger | Acceptance behavior | Current proof |
|---|---|---|
| 50 producer threads, 1,000 event inserts | no duplicate or false gap | offline candidate test |
| Same event from two SQLite connections | one durable record; identical replay no-op | offline candidate test |
| Task B success while task A loops | still reports task A suspect no progress | added offline regression |
| Same task prior verified batch, then repeats | new loop is not suppressed | added offline regression |
| Revision/attempt mismatch | verifier cannot clear other operation loop | added offline regressions |
| MV3 suspension after click | no second send until independent read-back | not tested, extension unavailable |
| Native host crash after external side effect | `SEND_OUTCOME_UNKNOWN` with durable operation ID | not tested |
| Browser navigates between prepare and submit | stale document rejected before action | not tested |
| User edits composer or presses Stop | automation yields; in-flight effects reconciled | not tested |
| Provider returns 429 to 50 agents | one shared budget/cooldown, no retry stampede | not tested |
| SDD/extension code claims CI success on older SHA | exact-current-revision verifier rejects | not tested |
| Bridge recovers after reboot | cursor replay doesn't repeat sends | not tested |
| Prompt injection in page/tool output | no authorization/budget/approved target change | not tested |
| Sensitive browser data in exception | redacted metrics only, no content logging | not tested |
| Local DB corrupted/full | effects fail closed and restore preserves unknowns | not tested |
| Windows native host/WSL integration | clean startup/stop/upgrade and rollback | not tested |
| 24–72h synthetic churn / 50 agents | measured no silent unsafe effects; SLO baseline | not tested |

**Promotion sequence:** current extension source discovery and hash inventory -> read-only HELLO/capability prototype -> authenticated event adapter with durable cursor -> isolated approval/reconciliation tests -> exact-SHA CI/negative tests -> human-approved canary, with one-step kill switch -> only then reconsider bounded automation.

## Operator-visible incident record (no prompt payloads)

```json
{
  "incident_id": "opaque",
  "observed_utc": "UTC",
  "run_id": "opaque",
  "task_id": "opaque",
  "attempt_id": "opaque",
  "lease_fence": 17,
  "target_revision": "full git commit hash",
  "producer_seq_high_water": 103,
  "missing_source_event_count": 2,
  "last_durable_effect_key_digest": "sha256:...",
  "effect_state": "UNKNOWN|NONE|RECONCILED",
  "transport_status": "CONNECTED|DISCONNECTED|UNKNOWN",
  "progress_status": "UNVERIFIED|SUSPECT|VERIFIED_EXACT_REVISION",
  "reason_code": "SEND_OUTCOME_UNKNOWN",
  "evidence_refs": ["sha256:..."],
  "hypotheses": ["remote commit possible", "ack lost"],
  "next_safe_action": "READ_BACK_DO_NOT_RETRY",
  "owner_approval_required": true,
  "post_fix_sha": null,
  "verification_run_id": null
}
```

This is a **schema illustration**, not a real incident record. The monitoring implementation must never claim access to hidden ChatGPT/model internals or user-private browser state. Before any real deployment, confirm the extension source, Native Messaging manifest allowlist, exact host protocol and operator-approved capabilities.

## References

- Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Hermes durable API: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- Hermes upstream Kanban: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md
- Hermes repeated tool-loop case: https://github.com/NousResearch/hermes-agent/issues/100971
- OpenTelemetry event conventions: https://opentelemetry.io/docs/specs/semconv/general/events/
