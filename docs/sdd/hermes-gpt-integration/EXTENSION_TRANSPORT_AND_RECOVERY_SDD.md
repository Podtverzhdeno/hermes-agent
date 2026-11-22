# Hermes ↔ GPT Companion: Extension Transport and Recovery SDD

Version: 1.0 / 2026-11-22.
State: DESIGN ONLY; NO extension source, local native host, installed manifest, browser trace, or active session verified in this investigation.
Depends on: INTEGRATION_AND_ATOMIC_DIAGNOSIS_SDD.md and the evidence journal in this folder.
Target: Chrome/Chromium Manifest V3 optional UI companion + trusted native host; the preferred model transport is official supported API and the canonical task lifecycle is modern Hermes Kanban.

## 0. Core decision: never make a browser tab the scheduler

A ChatGPT web page is not an agent work queue. A text bubble or a browser DOM state is not reliable proof that a Hermes worker started or finished an external action. The extension MUST NOT infer task success from ChatGPT UI content; MUST NOT bypass authentication, usage limits, CAPTCHA, approvals or other access controls; MUST NOT scrape unrelated conversations or store credentials in site scripts. The owner may use the UI for reviewing statuses, explicitly approving individual supported actions and linking to trusted evidence. Autonomous work occurs in the explicitly authorized Hermes host/SDK/API, not in a browser service worker.

The extension must work safely when the browser, content script or host disappears at any moment.

## 1. Deployment boundaries

~~~text
                     Optional browser UI
                           (read-only)
                    Chrome MV3 side panel
                              |
                    extension service worker
                       (ephemeral client)
                              |
               chrome.runtime.connectNative()
                              |
       pinned native messaging host, Windows/WSL owner machine
               (capabilities: read-status by default)
                              |
             scoped authenticated local service
               / observer / trusted policy gateway
                              |
              Hermes Kanban task/run identifiers
                              |
            append-only observation + remote receipt
~~~

### Responsibility matrix

- **Hermes Kanban**: authoritative task status, worker assignment, retries/dispatch.
- **Trusted gateway**: authorized effects, owner approvals, project STOP policy, action journal.
- **Observer/event service**: metadata-only append log, diagnostic snapshots, causality and replay.
- **Native messaging host**: signed/pinned distribution, fixed extension allowlist, authenticated local IPC, bounded subscriptions and sender checks. It is a client of the gateway, not its own scheduler.
- **MV3 service worker**: version negotiation, status subscription, cursor checkpoint, reconnect and bounded fan-out to visible UI. It must never own a lease or irreversible effect.
- **Side panel/popup**: dashboards and explicit operator choices. It cannot directly publish trusted task completion.
- **Content scripts**: not required for core design. Any later content integration demands a separately reviewed, explicit owner-approved use case; webpages and their messages remain untrusted.

Use Chrome's nativeMessaging permission only when needed, keep host permissions limited to reviewed origins, and do not use broad host permissions for a purely side-panel status view. The local HTTP API, even at loopback, requires authentication and OS-scoped permission checks. No credentials in extension storage or trace exports.

## 2. Durability and replay model

**At-least-once event delivery, idempotent application.** An observation delivered twice is not an action executed twice. The native host stores a durable event sequence or retrieves it from the authoritative event store. The extension stores only the last fully applied consumer cursor, a schema version and non-secret display preferences in chrome.storage.local; any relevant private task details must be fetched after authorization and not persisted in browser storage by default.

Each event has:
- protocol_version, event_id, source_id, source_sequence and canonical task/run IDs;
- causal parent event, previous same-producer sequence, timestamp and phase;
- public-safe reason code and reference to evidence, not evidence payload;
- explicit security principal and project scope enforced by host rather than trusted from message content.

All receivers deduplicate by event_id. A client acknowledges the highest *contiguous* applied cursor, not the highest observed sequence. On resume, a host may replay events and should preserve causal links. A gap is displayed as OBSERVATION_GAP and triggers a bounded snapshot/replay request. If retention has expired, issue an explicit RESYNC_REQUIRED: reset display projection from a verified snapshot, not from a model story.

Causal ordering is not global time ordering. Out-of-order events must be queued by producer sequence, correlated by causal edges, or rendered as incomplete until a gap is resolved. Unknown events from future minor versions can be ignored only if optional; incompatible major protocol versions must fail closed.

## 3. Versioned message contracts (DESIGN, not code deployed)

All examples use allowlisted metadata only.

Host handshake:

~~~json
{
  "v": 1,
  "kind": "hello",
  "client_instance_id": "random-session-uuid",
  "extension_build_digest": "sha256",
  "supported_versions": [1],
  "last_applied_cursor": "opaque-sequence",
  "requested_scope": "read_project_status",
  "nonce": "random"
}
~~~

Host reply:

~~~json
{
  "v": 1,
  "kind": "hello_ack",
  "host_instance_id": "boot-uuid",
  "accepted_version": 1,
  "scope_granted": ["read_project_status"],
  "server_cursor": "opaque-sequence",
  "retention_floor": "opaque-sequence",
  "nonce_ref": "validated-client-nonce",
  "policy_revision": "opaque-policy-revision"
}
~~~

An authenticated hello is insufficient to authorize mutations. Actual origin and process identity must be checked outside JSON. A nonce mitigates session confusion, not an authorization substitute.

Event:

~~~json
{
  "v": 1,
  "kind": "event",
  "event_id": "uuid",
  "cursor": "sequence",
  "project_id": "opaque",
  "task_id": "kanban-task-id",
  "run_id": "kanban-run-id",
  "phase": "WORKER_PROMPT_DELIVERED",
  "outcome": "OBSERVED",
  "reason_code": null,
  "producer_sequence": 173,
  "causation_event_id": "uuid-or-null",
  "evidence_ref": "opaque-safe-reference"
}
~~~

Ack:

~~~json
{
  "v": 1,
  "kind": "ack",
  "cursor": "last-contiguously-applied-sequence",
  "client_instance_id": "uuid"
}
~~~

Explicit owner action request (not accepted directly from an untrusted web page):

~~~json
{
  "v": 1,
  "kind": "operator_action_request",
  "action_id": "uuid",
  "project_id": "opaque",
  "task_id": "kanban-task-id",
  "action": "request_cancellation",
  "expected_policy_revision": "exact-fence",
  "expected_task_revision": "exact-revision",
  "user_intent_receipt": "trusted-short-lived-consent-reference"
}
~~~

Host returns ACCEPTED_FOR_PROCESSING or REJECTED, and later a separate VERIFIED_STOP or STOP_UNCERTAIN event. A successful message delivery is not a successful cancellation. Any irreversible command requires a trusted authorization flow and mutation/effect journal bound to normalized parameters, expiry, principal and revision. The client must never invent a consent receipt.

## 4. Browser extension state machine

States:
- DISCONNECTED: no authenticated native host.
- CONNECTING: attempt with deadline, no side effects.
- HANDSHAKING: negotiated version, identity, scope.
- REPLAYING: consuming events after durable cursor; duplicates harmless.
- SYNCED: a validated snapshot and cursor are current.
- DEGRADED: stale heartbeat or observer gap; continue to show LAST VERIFIED STATE with timestamp and uncertainty.
- REAUTH_REQUIRED: host rejects identity/permissions; do not retry indefinitely.
- VERSION_MISMATCH: no compatible major version; stop.
- RESYNC_REQUIRED: cursor older than retention floor; request exact state snapshot.
- SHUTDOWN_REQUESTED: owner chose to stop UI subscription; no task state mutation implied.

Transitions require explicit evidence; no transition from DEGRADED to "task failed" solely on silence. The MV3 service worker can stop and restart at any state. On activation, load cursor/version from chrome.storage, then reconnect and ask the host. Any unacked event can be replayed. After a host reboot, preserve producer identity/incarnation boundaries and never treat a newly restarted sequence counter as old events.

Use bounded exponential backoff with full jitter and a maximum retry horizon. A browser reconnect budget and a model retry budget are distinct, with an explicit single retry authority per logical action to prevent multiplication across extension, gateway and provider.

## 5. Native host security review requirements

- Manifest allowlist pins the exact extension ID, distributed under a controlled signing/update scheme.
- Any content script messages are classified as untrusted and cannot contain authority-bearing claims.
- Validate message type, size, version, UTF-8/JSON structure, sender/origin and project scope before forwarding.
- Use OS file ACLs to protect the host executable, config, authorization record and event store.
- Native host process identity is not sufficient; use policy-scoped access control on service calls.
- Enforce maximum subscribed projects, queues, event/snapshot size and rate limits to contain abusive or faulty clients.
- No programmatic discovery/export of ChatGPT cookies, private conversation texts, API keys or browser auth headers.
- Default telemetry allowlist includes status enums, stage timings, stable pseudonymous IDs and code revisions only.
- Any detailed debug trace requires owner consent, short retention, filesystem protections and explicit redaction tests.
- Auth/permission failures are non-retryable unless authorized credentials/permissions change.
- Avoid sending arbitrary shell commands through native messaging. Supported read-only commands are enumerated; mutating commands belong to trusted policy gateway with explicit approvals.
- Default-deny for unknown message types and future incompatible major versions.

Threat model: hostile webpage message, extension tampering, compromised native host or local process, prompt injection in GitHub/Obsidian data, replayed operator action, stale task lease, inter-agent token leak, and malicious "status succeeded" signal. The scope is system hardening; this SDD is not a claim that a particular attack was observed.

## 6. Why a task stopped: evidence-based diagnostic projection

Display both task lifecycle and transport health separately:

| Situation | User-facing status | System action |
|---|---|---|
| No prompt-delivery acknowledgement although Kanban claimed task | Task dispatched, delivery unconfirmed | alert worker-lane owner; keep task outcome unknown |
| Provider request accepted but no first token | Awaiting model, deadline tracked | inspect provider receipt/deadline before retry |
| Tool waiting on owner approval | Approval required | never consume retry budget as error |
| 429 with Retry-After | Rate limited | coordinated project backoff |
| Browser service worker shutdown | Interface reconnecting | no task retry |
| Native host connection lost | Monitoring unavailable | stale-but-visible last verified state |
| Last event has no causal parent or missing sequence | Event history incomplete | request replay / verify ingest |
| User closes tab after effect reservation | External action outcome uncertain | reconcile effect against remote service |
| SSE completed without success terminal | Incomplete response | show failed/incomplete; no "done" |
| Task cancelled by project STOP | Cancellation requested | wait for acknowledgements and effect receipts |
| Verified task artifact and exact SHA CI success | Work verified | show completed only if Kanban review gate agrees |

Every incident card must show observation source, last known phase, elapsed wall-clock (not assumed model computation), confidence class, possible explanations, next safe action, and verified operator revision. A model may write a hypothesis, never the authoritative reason code without corroborating signals.

## 7. E2E acceptance / deliberate fault injections

The extension cannot be called production-ready until these are exercised against the exact extension ID, browser version and Hermes host revision. Offline simulated messages are useful but insufficient:

- Service worker killed before and after ack; replay exactly the unacked range, no lost or doubled status transition.
- Host killed before/after event persist; new host incarnation sequence must reconcile.
- Chrome relaunch, machine reboot, extension upgrade and native host upgrade; checkpoint survives correctly.
- Two tabs/panels subscribing to one project; read-only projection stable, no double execution.
- Extension message arrives twice; event dedup and action idempotency.
- Host event source changes schema major version; rejection rather than silent misparse.
- Missing event sequence and retention cutoff; RESYNC_REQUIRED and verified snapshot.
- Browser page navigates/replaces target; no inference of task completion from DOM.
- Unauthorized content script message, spoofed action receipt, wrong extension ID and localhost unauthorized request all rejected.
- API 401/403 and missing host manifest treated as authorization/install problem rather than model stall.
- Provider 429/503 across 30/100 workers follows project-wide retry budget, no stampede.
- Client disconnect after model completion persists; response replay does not generate extra token costs.
- Client disconnect after tool intent but before remote ack; no unsafe duplicate mutation.
- STOP while queued, running, approval-pending, streaming, effect-unknown or retry-scheduled; no new post-STOP actions.
- 30-agent test, 100-agent test and sustained recovery soak: exact run IDs, bounded memory, no unauthorized data logged, p95 diagnosis latency measured not invented.
- Windows/WSL: canonical worker receives task contract and actually starts model request, not merely a PID spawn or Kanban claim.
- Full disaster recovery: encrypted backup of config and SQLite using backup API, restore to isolated host, verify event cursor and project policy.
- Rollback reverts UI/host deployment without dropping or replaying unconfirmed effects.

Test artifacts must record current extension build digest, host revision, repository commit, browser version, workload seed, injected fault, evidence IDs, intended/actual status and verified reviewer. No E2E tests in this list have yet been run in this audit.

## 8. Delivery and evolution sequence

Phase A (source discovery): locate actual browser extension project, manifest.json, build pipeline, current native host, supporting OS/browser versions and installed permissions. Audit only; no change to installed copy.

Phase B (protocol skeleton): schema, validator, event cursor, replay simulator, privacy tests, no mutation capabilities. Build read-only status panel backed by a test event stream.

Phase C (real host): signed/pinned nativeMessaging manifest, least-privilege local service and read-only Kanban observer. Separate installation paths and data directory for canary.

Phase D (safe operator control): audited, explicitly consented cancellation or approval requests, verified project policy revision and trusted effect journal; never direct page-to-shell.

Phase E (reliability): 30/100-agent failure injection, START/STOP, upgrade/rollback, cross-version recovery, last verified state, zero false-success claims.

Phase F (production): owner-approved roll-forward, CI tied to exact merge-group/HEAD SHA, operational SLO baselines and a local restore drill. The main Windows installation remains unchanged until gate approval.

## 9. Requirements for transport selection

Official GPT/OpenAI-compatible APIs and the Hermes native API are the primary supported automation transport; they provide structured requests, reliable identities and documented response status. Browser extension is OPTIONAL observability/consent UX; no DOM-driven unattended ChatGPT automation is a required feature. If the actual project has a different documented external interface, measure compatibility and run security review before replacing this decision. Do not treat browser availability as a capability grant.

## 10. Primary references

Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
Chrome native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
Chrome migration to MV3: https://developer.chrome.com/docs/extensions/develop/migrate/to-service-workers
Hermes Kanban worker lanes: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
OpenTelemetry GenAI traces: https://opentelemetry.io/docs/specs/semconv/gen-ai/
W3C Trace Context: https://www.w3.org/TR/trace-context/
AWS retries and jitter guidance: https://docs.aws.amazon.com/wellarchitected/latest/framework/rel05-bp03.html
AWS mutating operation idempotency: https://docs.aws.amazon.com/wellarchitected/latest/framework/rel04-bp04.html
Temporal activity heartbeat/retry: https://docs.temporal.io/activities
GitHub latest-HEAD checks: https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks

**Status:** SDD ONLY. No browser extension, native host, ChatGPT session or local workstation files were modified by this document.
