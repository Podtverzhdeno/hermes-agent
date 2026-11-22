# Hermes ↔ GPT Chrome MV3 companion + Windows native-host contract

**SDD extension 0.1 · 2026-11-22 · DESIGN ONLY.** Not installed in Chrome. Existing local extension version/hash, source code and actual Windows host are UNKNOWN because Local_WorkSpace returned `Session terminated`. This document does not grant permission to automate ChatGPT web UI or access private user conversations.

## 1. Design boundary: observer vs executor

A browser tab is not the authoritative source for a Hermes task, a side effect, or its acceptance. A native host/ledger can receive **trusted metadata from approved providers**, but may not derive task success from page text, DOM heuristics, a silent ChatGPT conversation or an LLM saying "done".

```
Hermes trusted runner and official model integrations
    → durable Autopilot task/effect ledger + outbox (PR #1, future gate)
    → authenticated metadata export with source cursor
    → Windows owner-controlled local host [authoritative read-only export endpoint]
         ├── read-only status projection + incident classification
         ├── bounded cursor/audit retention + OS ACL
         └── Chrome Native Messaging per authorized extension instance
               ↓
        MV3 service worker (ephemeral; no scheduler, no effect authority)
               ↓
        popup/options status + explicit human-authorized requests
```

No implicit write capability follows from the Chrome extension being connected. A future user-authorized action must be represented by a separately reviewed, typed capability with exact target, expiry, action digest, owner identity, idempotency key, lease and fence; native host must enforce it.

## 2. Required repository and ownership decisions

- **Extension owner:** isolated `web-extension` or other *verified existing path*, scoped by exact file hashes; do not build a replacement until it is inspected.
- **Native host owner:** Windows installation, process supervision, OS ACL, origin pairing, update/rollback, no unrestricted TCP listener.
- **Ledger owner:** PR #1's durable task/event authority and reconciliation. A separate SQLite trace DB may store observations, not a conflicting task state machine.
- **API owner:** must select ONE among PR #4/#5/#6/#11; agree on 409/422, in-flight replay, SSE exception, cancellation and request id contracts before connecting browser clients.
- **Observer owner:** select ONE event envelope, collector and inspector. Current proposed observers #8/#9/#12/#13/#16/#21/#25 have incompatible schemas, storage models and status codes. This SDD is not another runner.
- **Integration arbiter:** exactly one selected PR guard (#14/#18/#22/#24), one canonical ADR register, reviewed combined diff, exact-HEAD CI and human rollout authorization.

## 3. Native Messaging protocol — *proposal*, not platform default

Use documented `chrome.runtime.connectNative(hostName)` for a long-lived UI status port; host binary speaks Chrome's length-prefixed JSON frames over stdin/stdout. Chrome's documented host→extension single-message maximum is 1 MB; our **application cap is 32 KiB** to reduce untrusted memory exposure. Host manifest `allowed_origins` pins the expected `chrome-extension://<id>/` and Windows registration uses the documented registry path. Verify the origin argument supplied by Chrome against pinned allowlist and OS ACL. Do not treat an arbitrary JSON `sender` or caller-declared `install_id` as authorization.

The following is an *illustrative* wire envelope, not a deployed schema:

```json
{
  "protocol": "hermes.gpt.observer.v1",
  "message_id": "uuid",
  "message_type": "observer.resume",
  "ui_client_boot_id": "ephemeral-uuid",
  "source_cursor": {
    "producer_id": "source-boot-id",
    "source_event_seq": 370
  },
  "requested_limit": 100,
  "capability": "read_only_status"
}
```

Host response is **projection-only** and embeds provenance, coverage and a bounded list of summaries:

```json
{
  "protocol": "hermes.gpt.observer.v1",
  "message_id": "response-uuid",
  "causation_message_id": "request-uuid",
  "message_type": "observer.batch",
  "host_incarnation_id": "host-boot-uuid",
  "snapshot_revision": "sha256:64hex",
  "coverage": "bounded_slice_not_complete_history",
  "last_trusted_observation_utc": "2026-11-22T10:00:00Z",
  "events": [{
    "task_id": "uuid",
    "attempt_id": "uuid",
    "kind": "worker.lease_expired",
    "reason_code": "WORKER_LEASE_LOST",
    "authority": "observed_not_authoritative",
    "safe_next_action": "inspect_ledger_fence"
  }],
  "next_cursor": {
    "producer_id": "source-boot-id",
    "source_event_seq": 371
  },
  "requires_resync": false
}
```

**Important:** source-producer sequences are not globally ordered, so a single `next_cursor` only covers one source incarnation. For N producer streams use a bounded **cursor map** or a trusted exporter-wide sequence with independent per-producer checks. The illustrative single-producer envelope above must NOT be used in multi-producer deployments unchanged.

Reject messages with unknown protocol version, unapproved fields, oversized frames, excessive batches, invalid source cursor, stale pairing, unexpected origin, unauthorized capability, attempt to set task state, and arbitrary URL/filepath/command values. Use stable reason codes and a narrow read-only schema; no raw prompts, cookies, API keys, page URLs or chat text.

## 4. Cursor commit/ACK semantics

The extension must not advance its locally displayed cursor merely because a native message arrived. A safe at-least-once display loop uses:

```
1. Service worker starts (possibly after an arbitrary shutdown).
2. Read last APPLIED UI cursor from chrome.storage.local.
3. ConnectNative to allowlisted host; request bounded next events.
4. Validate response protocol, event ID, source boot ID, source sequence,
   revision, allowed codes and size. Reject mutation instructions.
5. Atomically or recoverably store applied event summary + updated cursor
   in one extension-local storage operation; UI dedupes by stable event_id.
6. Send observer.ack_applied to host, without granting task completion.
7. If worker dies before step 5, events may be redelivered; dedupe UI.
8. If worker dies after step 5 before ACK, events may be redelivered;
   UI continues to dedupe, and host cursor remains authoritative for export.
9. If host sees retention gap or changed source incarnation, reply
   requires_resync; render "coverage incomplete" and request checkpoint.
```

chrome.storage is UI projection only; no secrets, task approval, leases, effect ledger or authoritative status. A single browser session event must not be conflated with an agent attempt. The extension can shut down normally when the popup closes.

## 5. Native host process lifecycle and Windows security

A Chrome Native Messaging host process launched by `connectNative` is not, by itself, a reliable 24/7 supervisor. If ongoing local observation is required, an **independently supervised owner-approved Windows process/service** must own the durable exporter and may communicate with a narrowly scoped native-message shim. Do not rely on a persistent popup, active tab or undocumented MV3 keepalive as the watchdog.

- Install only after verifying host binary path, manifest and expected extension ID; Windows registry entry under the documented `NativeMessagingHosts` key points to a pinned manifest. Do not register a wildcard host, arbitrary extension origins or an open localhost control port.
- Restrict host binary/config/log directories via NTFS ACL to the intended Windows principal. Never place reusable provider credentials inside extension storage or GitHub.
- Use a per-install owner-approved pairing process. The extension ID establishes allowed *software origin*, not necessarily which Chrome profile or operating-system user is allowed to inspect a task. Bind profile/project access at the trusted host.
- Native stdout is framed JSON protocol only; send diagnostics to bounded stderr/log files, without leaking secrets. Enforce maximum frame lengths before allocation.
- Distinguish `OBSERVER_DISCONNECTED` from `TASK_FAILED`. On host loss display stale timestamp and explicit coverage gap; do not auto-replay a user task.
- Version negotiation: incompatible host/extension versions enter read-only degraded state with a clear upgrade warning. No silent reinterpretation of event IDs.
- Update with signed/hashed artifacts, prior-version snapshot, backup of ledger, stop/restore fencing and tested rollback. A rollback does not restore side effects on third-party systems.

## 6. Multi-profile and 30–50-agent isolation

**Separate identities:** source boot ID, logical task, task attempt, agent instance, current lease fence, local host incarnation, browser extension installation/profile, and viewer/operator permissions. A Chrome extension connection is not proof an agent owns a task. Worker A's approval may never be delivered to worker B. Every mutating write must check the current ledger fence immediately before the effect, not just when the browser clicked a button.

**No last-writer-wins:** resource key format `project_id:repository:base_ref:path` or canonical note/file ID, with expected SHA and per-resource lease. Agents use isolated worktrees. Only one merge arbiter may accept integration, and it must re-run tests after each combined change.

**Provider fairness:** shared rate limit/token bucket across all workers. A 429 produces one provider cooldown, not simultaneous retries by 30 workers. Leases and parent budgets remain finite during replacement and context compaction.

**Telemetry cost:** bounded per-worker queues, per-producer sequence counters, explicit `DROPPED_N` and cursor gap events, low-cardinality aggregate metrics; hashes/IDs live in logs/traces, not uncontrolled metrics labels. Reduce alert noise with deduplication and explicit human-approval wait states.

## 7. Incident root-cause flow and visibility limits

An operator should see: source (host/ledger/API/worker/browser), exact version, last **trusted** observation, current known task state, outstanding reserved effects, approval age, source cursor gaps, candidate reasons with evidence, confidence and permitted recovery.

Example: "The browser status companion disconnected at 10:00:02; durable ledger heartbeat persisted at 10:00:05; browser UI is unavailable, but task execution is not proven stopped."

Counterexample: "No new ChatGPT UI text for 5 minutes; agent died" — REJECTED as an unsupported inference.

The classification engine must be deterministic over trusted events before any LLM may suggest a hypothesis. A model suggestion is never authorization to bypass permission denial, access private pages or repeat an uncertain external write.

## 8. Failure injection and release test matrix

| Injected fault | Expected evidence-preserving behavior |
|---|---|
| Service worker terminated between receive and UI commit | Redeliver and dedupe; no task execution |
| Worker terminated after UI commit before ACK | Redeliver same event ID; no duplicate status row |
| Browser profile changed / second profile connects | Host applies separate authorized viewer scope |
| Host process killed or restarted | New host incarnation, durable exporter state preserved, UI reports stale until resynced |
| Native payload exceeds 32 KiB or malformed JSON | Reject before parsing large allocation; no secret echo |
| Host unregistered / wrong extension ID | No connection; actionable configuration error |
| Out-of-order producer sequence | Causal partial order and bounded gap handling; no false success |
| Source cursor lost or event retention exceeded | `requires_resync` and coverage incomplete, not fabricated missing events |
| Provider 429 across 30 agents | One coordinated cooldown; finite attempts and no thundering herd |
| External write succeeds, ack lost | Preserve reserved unknown; independent read-back before retry |
| Stale agent after lease expiry | Tool gateway rejects write using current fence |
| GitHub branch advances mid-review | CAS/recheck exact SHA and re-run CI |
| ACP approval for agent A delivered to B | Deny, log attempt metadata and preserve separate scope |
| Windows restart / service unavailable | Last-known observation only, durable ledger recovered; no "continuous" claim while host off |

**Release gates:** a concrete source commit/hash for the existing local extension; Native Messaging manifest/OS ACL security review; schema/ADR convergence; authenticated exporter and independently verified receipts; deterministic event-replay corpus; MV3 restart lifecycle end-to-end; 30/50-worker concurrency and 100-request duplicate stress tests; exact-HEAD CI; staged rollback; explicit owner decision. Until these pass, integration state is **NOT DEPLOYED**.

## 9. Rationale from primary technical sources

- Chrome official service worker lifecycle explicitly requires resilience to unexpected termination: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome Native Messaging, host allowlist, Windows registration and message size: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Chrome message passing and untrusted content script boundary: https://developer.chrome.com/docs/extensions/develop/concepts/messaging
- Chrome storage: https://developer.chrome.com/docs/extensions/reference/api/storage/
- OpenTelemetry event semantic conventions, metadata sensitivity: https://opentelemetry.io/docs/specs/semconv/general/events/
- W3C trace context: https://www.w3.org/TR/trace-context/

**Conclusion:** instrument and protect the authoritative Hermes task/effect ledger first; make the browser extension an optional minimally privileged observability surface. Any "full process understanding" claim must be accompanied by a quantified coverage manifest and independently authenticated evidence; otherwise the honest state is `UNKNOWN`.
