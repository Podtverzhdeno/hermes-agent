# Hermes GPT browser extension: component contracts and failure-isolation SDD

**Status:** architectural design and historical environment reconciliation, 2026-11-22. **Not deployed.** The local user-specific extension files were not reachable in this session; don't claim edits, smoke-test passes, or runtime evidence for the Windows files.

**Historical deployment information from the owner's earlier project discussions (NOT newly observed today):**
- Unpacked Chrome/Chromium extension: \`C:\Users\Vadim\Tunnel\chat-launch-smoke-desktop-test\web-extension\`
- Known source names: \`manifest.json\`, \`background.js\`, \`background_content.js\`, \`content.js\`, \`core.js\`, \`popup.html\`, \`popup.js\`, \`same_chat_bg.js\`, \`same_chat_loop.js\`.
- Previous state: extension version v0.6.6 described as stale; browser bridge not running (historical local port 18763); extra \`bridge-config.json\` triggered preflight failure.
- Previous control plane: tunnel root \`C:\Users\Vadim\Tunnel\`; observer MCP on 127.0.0.1:8765 and scoped editor on 127.0.0.1:8766 (historical). Runtime connection is NOT established here.
- Prior operator constraint: do not use \`nohup\`/\`disown\` for tunnel supervision. Verify \`process_running=true\`, \`healthy=true\`, \`ready=true\` after \`runtimes connect\` and check an independently authenticated request.

These are implementation *targets*, not proof that the corresponding files still exist, carry the stated functions, or are safe to modify now. Before editing extension code, inspect exact current contents and SHA256 and compare to this contract.

## 1. Critical runtime model

A browser message is not a durable task. The extension has at least four independently failing failure domains:

1. **Hermes worker/orchestrator:** accepts tasks, validates ownership, tracks deadline, retry budget, lease and external-action intent.
2. **Local bridge/tunnel:** IPC/WS/HTTP transport; may disconnect while a browser automation command is pending.
3. **Extension background (Manifest V3 service worker if configured):** may suspend/restart without an error; volatile JS variables disappear.
4. **Content script + ChatGPT tab:** may navigate, re-render, be replaced, lose authorization, or have prompt composer DOM changed.

A fifth domain is the **human**: user may type simultaneously, approve a popup, move to another conversation, or press Stop. Human activity must override automation where state could be corrupted.

\`\`\`text
Hermes coordinator
      | command(task_id, action_id, expected_revision, deadline)
      v
Local bridge (authenticated & scoped)
      | command with correlation
      v
background.js / same_chat_bg.js (routing; no durable in-memory truth)
      | tab_id + document_id + ack
      v
content.js / background_content.js / same_chat_loop.js
      | observe composer -> verify intended chat -> checkpoint intent
      | submit once -> observe sent message & assistant completion
      v
Ack + evidence digest -> bridge -> durable ledger -> Hermes

If ack disappears between submit and observation:
  UNKNOWN_SEND_OUTCOME -> READ/RECONCILE -> user approval if ambiguous.
Never automatically submit the same prompt twice.
\`\`\`

## 2. Contract-by-file (hypotheses pending file inspection)

| File | Proposed bounded responsibility | Failure/diagnostic signal |
|---|---|---|
| \`manifest.json\` | MV3 permissions, version, service-worker declaration, only necessary host matches; no broad privileges unless justified | \`MANIFEST_SCHEMA_INVALID\`, \`PERMISSION_DENIED\` |
| \`core.js\` | Shared message schema, version negotiation, stable event types and ID generation | \`SCHEMA_MISMATCH\`, \`UNSUPPORTED_VERSION\` |
| \`background.js\` | Bridge transport, task registry and tab routing; durable recovery handed to local backend | \`EXTENSION_SUSPENDED\`, \`BRIDGE_DISCONNECTED\` |
| \`background_content.js\` | Background ↔ content handshake, per-document lifetime, deadline propagation | \`STALE_DOCUMENT\`, \`MESSAGE_ACK_TIMEOUT\` |
| \`content.js\` | Pure browser-state observation & narrowly scoped UI actions; no authority to approve its own unsafe retries | \`COMPOSER_NOT_FOUND\`, \`DOM_CONTRACT_CHANGED\` |
| \`same_chat_bg.js\` | Single-chat coordination, ordering, capability negotiation | \`WRONG_CONVERSATION\`, \`CONCURRENT_SENDER\` |
| \`same_chat_loop.js\` | State transitions for sending, waiting, response association and completion evidence | \`SEND_OUTCOME_UNKNOWN\`, \`RESPONSE_STALLED\` |
| \`popup.html\` / \`popup.js\` | Show state, error reason, run ID, consent and operator actions; status only, never inferred certainty | \`UI_STALE_STATUS\` |
| \`bridge-config.json\` (historical stray) | Configuration is explicitly validated against manifest/build rules; only allow if legitimately configured | \`PREFLIGHT_EXTRA_FILE\` |

No source role above is yet validated against file contents. Treat it as a proposal pending source inspection, not a statement about code as implemented.

## 3. Protocol v1: extension ↔ bridge envelopes

Each command/reply/event must be small, versioned, validated and correlated:

\`\`\`json
{
  "protocol_version": "hermes-gpt-bridge/1",
  "message_id": "unique uuid",
  "reply_to": null,
  "run_id": "uuid",
  "task_id": "opaque",
  "action_id": "stable idempotency key for this send attempt",
  "attempt_id": "physical attempt uuid",
  "agent_id": "opaque",
  "lease_epoch": 17,
  "sent_at_utc": "2026-11-22T10:00:00Z",
  "deadline_at_utc": "2026-11-22T10:02:00Z",
  "document_epoch": "new on each page load",
  "type": "command|ack|event|result|heartbeat|error",
  "action": "observe|prepare_send|submit|verify|cancel",
  "payload_digest": "sha256; no raw prompt in default log"
}
\`\`\`

Separate command payload storage from diagnostic event storage. Never put raw browser cookies, auth headers, page localStorage, ChatGPT transcripts, screenshots, or any credential into event transport. A privileged local bridge authenticates the extension; \`Origin\` checks alone are NOT authentication. Do not bind a CDP debugger socket to all interfaces.

Proposed response codes:
\`ACCEPTED\` (just enqueued, no send),
\`PREPARED\` (page verified, no send),
\`SUBMITTED_UNVERIFIED\` (input action attempted; effect uncertain),
\`SUBMITTED_CONFIRMED\` (message bubble observed and correlated),
\`RESPONSE_IN_PROGRESS\`,
\`RESPONSE_COMPLETED\` (terminal DOM evidence),
\`OUTCOME_UNKNOWN\`,
\`STOPPED_BY_USER\`,
\`FAILED_BEFORE_SEND\`.

Every \`send\` command must have exactly one stable \`action_id\`; if seen again, return the stored status and never reflexively click the Send button again. Stable \`action_id\` is not a substitute for examining the external chat.

## 4. UI send state machine

\`\`\`text
UNCLAIMED -> OWNED -> TAB_SELECTED -> DOCUMENT_VERIFIED
DOCUMENT_VERIFIED -> COMPOSER_READY -> INTENT_CHECKPOINTED
INTENT_CHECKPOINTED -> INPUT_PREPARED -> SUBMIT_ATTEMPTED
SUBMIT_ATTEMPTED -> SENT_CONFIRMED -> RESPONSE_STREAMING
RESPONSE_STREAMING -> RESPONSE_COMPLETED -> RESULT_PERSISTED -> ACKED

SUBMIT_ATTEMPTED -> OUTCOME_UNKNOWN (disconnect, timeout, navigation)
ANY pre-send state -> FAIL_PRE_SEND (safe to retry after classifying cause)
ANY state -> HUMAN_PAUSED | USER_CANCELLED
RESPONSE_STREAMING -> RESPONSE_STALLED | TAB_LOST | RATE_LIMITED
\`\`\`

Use **two independent observations** before reporting a completed answer where feasible (e.g. target assistant message associated with this action plus completed generation controls). Absence of a spinner alone is not enough. A slow but progressing message must not be called stalled. Record \`last_progress_at\` and DOM generation fingerprint without capturing prompt/answer content. If a tab is refreshed, assign a new \`document_epoch\` and invalidate old content-script handles.

Never confuse (a) command received, (b) composer filled, (c) send button clicked, (d) message appeared in thread, and (e) assistant finished. Those five confirmations are distinct. For ambiguity after click, the safe next action is **observe/reconcile**, not retype and send.

## 5. Stalls and adaptive deadlines

Use a hierarchy, not one global 30-second timeout:
- \`bridge_connect_deadline\` for transport handshake and auth.
- \`tab_discovery_deadline\` for finding an authorized browser tab.
- \`composer_ready_deadline\` for target page/document stability.
- \`submit_ack_deadline\` for observing the user's sent message.
- \`first_response_deadline\` after confirmed submission.
- \`progress_idle_deadline\` reset only on evidence of genuine new response progress.
- \`absolute_run_deadline\` not reset by noisy repeated events.
- \`human_approval_deadline\` with explicit paused state; no timeout-based bypass.

Timeout values are configurable and must be empirically calibrated from real latency traces. Do not specify magic thresholds without baselines. Avoid busy DOM polling: event-driven observation plus bounded heartbeat, debounced mutations and backoff after navigation.

## 6. Version/compatibility handshake

Before any send, perform \`HELLO\` → \`CAPABILITIES\` exchange with fields:
\`extension_version\`, \`manifest_version\`, \`bridge_version\`, \`protocol_major/minor\`, \`browser_name\`, \`document_epoch\`, \`capabilities\`, \`health\`.

- A protocol-major mismatch -> \`UNSUPPORTED_VERSION\` and **block sending**.
- Missing required permission -> \`PERMISSION_DENIED\`, not "UI stalled".
- A historical mismatch like v0.6.6 vs deployed bridge should be visible with exact version strings, not vague "reconnect".
- Extra \`bridge-config.json\` preflight should have an explicit allowlist/expected build manifest and return a nonzero diagnostic code; never silently delete unknown user files.
- Do not log private profile paths except locally with user consent.

## 7. Observable diagnostics with privacy

Each stage event must identify:
\`run_id\`, \`action_id\`, \`attempt_id\`, \`agent_id\`, \`step\`, \`from_state\`, \`to_state\`, \`reason_code\`, \`ts_utc\`, \`duration_ms\`, \`document_epoch\`, \`tab_ref_hash\`, \`bridge_instance_id\`, \`worker_version\`, \`evidence_digest\`, \`pending_dependency\`, \`retry_remaining\`.

Keep events in a bounded local durable queue (e.g. IndexedDB if extension context permits) then upload with ack and de-duplication by \`event_id\`. If worker suspends, replay events, not actions. The central durable ledger is authoritative; UI-local status is a projection. Event retention, access control, encryption and opt-in payload capture must be explicit.

For every run implement a \`why_stopped\` projection:
- last confirmed state and timestamp;
- first missing expected acknowledgment;
- observed symptom vs root-cause hypothesis;
- evidence supporting/refuting it;
- safe recovery action;
- responsible owner/capability;
- link to relevant code SHA, test, incident.
Never replace "unknown" with a confident narrative.

## 8. Coordination for dozens of agents

- One **single writer** per ChatGPT conversation/tab; acquire a server-side lease with epoch and expire it on real liveness evidence.
- Parallel research and code agents work in distinct branches and isolated worktrees. Reviews never mutate the execution state of another agent.
- Global scheduler caps concurrent sends, per-chat writes, request rate, memory and diagnostic log volume. No account swapping to bypass limits.
- Agents can observe the same run but only the owner can issue a \`submit\` command, backed by a valid fencing token.
- If ownership expires during an uncertain send, the successor may **observe** only until reconciliation or explicit operator decision.
- Parent coordinator records \`depends_on\`, \`delegated_to\`, \`blocked_by\`; a child dying does not erase pending action evidence.
- Fencing only inside a database does not stop an already-sent browser click; use both pre-effect claim verification and post-effect reconciliation.
- Human/extension/browser Stop is an auditable event; cancellation requests and confirmed cessation must never be conflated.

## 9. Threats & concrete tests

| Scenario | Expected truth | Minimal fault injection |
|---|---|---|
| MV3 worker suspended mid-send | Persist uncertain send, recover protocol; no second click | Terminate/restart extension SW immediately after click |
| ChatGPT tab navigates after composer fill | Stale document rejected | Navigate before submit and replay old command |
| Bridge process exits after send, before ack | \`OUTCOME_UNKNOWN\` then DOM reconciliation | Kill bridge after UI click |
| Two agents target same conversation | Single valid lease and one send; second blocked | Race 30 requests using same tab/action |
| Chat reloads, existing assistant message seen | Do not mistake old reply for target response | Replay stored transcript on load |
| DOM changed by UI update | Safe failure before send; meaningful diagnostic | Remove/rename composer landmark |
| Browser loses login or requires verification | \`AUTH_REQUIRED\`; human handoff | Show simulated sign-in interstitial |
| User manually types or clicks Stop | Automation paused; explicit user provenance | Human takeover during response |
| HTTP 429/503 on bridge or upstream | Bounded backoff; distinguish source | Inject 429 with and without Retry-After |
| Duplicate event after background restart | Event deduplicated, no action replay | Replay same event_id 100 times |
| Huge response / hours-long run | Bounded memory, event count, disk usage | 30-agent synthetic load |
| Sensitive prompt in exception/screenshot | No raw content in routine logs | Inject marker and grep all exported logs |

For all tests record: version SHA, input fixture, raw *redacted* event bundle, expected state, observed state, evidence hashes, whether the exact external action occurred, retries, and rollback. A mock DOM test is NOT a production ChatGPT compatibility certification.

## 10. Implementation and promotion sequence

**Phase A — discovery (blocked on local access):** collect fresh SHA256, manifest permissions, extension runtime errors, bridge protocol and process state; compare v0.6.6 and present version. Do not modify until code inspected.

**Phase B — passive probes (safe first):** add structured telemetry and \`HELLO\` capability reporting; add status dashboard and no-payload error codes. Leave send path unchanged. Confirm no performance regression.

**Phase C — task state:** implement versioned command envelope, single-writer lease/fence, durable event queue, evidence capture and per-stage deadlines. Integrate existing \`autopilot/ledger.py\` once merged or reviewed.

**Phase D — effect safety:** checkpoint send intent before click, annotate \`SUBMITTED_UNVERIFIED\`, reconcile after uncertain outcomes, suppress duplicate send, human approval where needed.

**Phase E — fault injection:** worker restart, tab navigation, bridge crash, 429, user Stop, simultaneous agents and synthetic load. Feature flag enables 1% opt-in profiles; rollback remains one switch.

**Phase F — production acceptance:** observed 0 duplicate sends in scripted faults, 0 false-success completions, 100% synthetic failures with non-empty reason codes, and operational time-to-diagnosis baselined; do not claim exact percentages on unmeasured real-world runs.

## 11. Current blocker ledger

- **2026-11-22:** \`mcp__Local_WorkSpace__list_workspaces\` failed with \`Session terminated\`; no fresh file SHA, bridge PID, extension version or runtime log available. Cause unknown.
- **2026-11-22:** \`mcp__temp_folder_readonly__list_workspaces\` returned \`MCP SSE probe 429\`; may be transport budget/rate limit, cannot attribute to a specific process.
- **2026-11-22:** Work committed instead to GitHub Hermes fork branch \`feat/gpt-bridge-observability-20261122\`; modifications there cover OpenAI-compatible **API adapter**, not the unpacked Windows extension.
- **2026-11-22:** Historical extension paths and v0.6.6 status recovered from prior owner conversation and must be revalidated before local writes.

**Release rule:** this document plus API patches are a starting point, NOT evidence that Chrome extension behavior has been fixed. Reopen the local control plane first, then implement with SHA-pinned optimistic writes and actual browser replay tests.
