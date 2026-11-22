# Decision: how Hermes should connect to GPT, not merely display a browser tab

**ADR-GPT-TRANSPORT-001 — proposed, 2026-11-22.** No extension source or credentials were accessed; no production method selected. This is an integration decision, not an implementation claim.

## Actual goal and non-goal

The owner requires dozens of agents that (a) receive work without duplicate execution, (b) emit trustworthy causal metadata, (c) explain stops and uncertainty, (d) preserve local working copies and safe tools, and (e) can be inspected through an optional GPT/ChatGPT companion extension. The extension is **not** a source of authoritative task/side-effect state. A ChatGPT conversation in a tab does not expose a transactional external-effects ledger or a supported generalized "30 background agents" execution contract.

## Four candidate integration modes

| Mode | Supports server-managed durable workflow? | Principal risks | Decision |
|---|---|---|---|
| A. Hermes runner → supported provider API (e.g. OpenAI Responses) + durable Hermes ledger | Provider API can return response IDs / support background request status; Hermes MUST implement its own tool/ledger state | API cost and quotas, provider retention, API/project credentials, multiple response vs workflow statuses | **Recommended execution lane** when owner explicitly authorizes API billing/privacy/access |
| B. Read-only Chrome MV3 companion + allowlisted Windows Native Messaging host | **No**; renders ledger status, cursors, approvals, last trusted observations | Worker suspension, host disconnect, Chrome profile authorization, untrusted web content | **Recommended operator UI lane** after local-source security audit |
| C. Short-lived owner-driven browser/CDP diagnostic lane | **No**; troubleshooting only with explicit user approval | External browser ownership, session cookies, brittle page DOM, browser restart | **Conditional troubleshooting lane**; no task/approval authority |
| D. Browser ChatGPT DOM/CDP as unbounded autonomous agent execution API | **No supported transactional guarantees** | UI/version fragility, hidden state, unobservable effects, privacy and browser account risk | **Reject for reliability-critical automation** |

"Using GPT" is not equivalent to "controlling the ChatGPT site". API credentials and billing are separate from access to the browser ChatGPT subscription. A compatible local Hermes `/v1/responses` endpoint also does NOT magically inherit OpenAI's background/webhook semantics.

## Provider background API nuance — explicitly limited scope

Official OpenAI Responses background mode supports long-running provider requests with `background: true`, a response ID, retrieval and optional authenticated webhook delivery. The current official guide describes terminal event retrieval and explicit continuation across tool-call follow-ups. **The background provider request is NOT an autonomous Hermes execution ledger:** after response/tool call generation, Hermes still must perform external tool dispatch under task/effect reservation, auth and fence; then send an explicit follow-up request with the exact tool result and correlate it to the persisted provider response ID/call ID.

Persist in one durable admission transaction: `task_id`, parent `run_id`, `attempt_id`, provider `response_id`, provider project/model, webhook correlation IDs, next step, budget and expected revision. Provider IDs must be treated as scoped identifiers, not secrets for authorization. Reject an incoming webhook unless signature verification passes; after validation, dedupe by stable webhook delivery ID, match response ID to an admitted task, retrieve the authoritative provider response, and recheck current task state before scheduling a safe continuation. Webhook `response.completed` proves only that the provider response reached that status, **not** that Hermes performed or verified an external effect.

Use bounded polling by response ID only when webhooks are unavailable; never create a new request merely because an HTTP read timed out. Handle independent provider project quotas, statuses `queued`/`in_progress`/terminal and explicit cancellation. Before replaying a tool effect after provider continuation failure, reconcile the previous reserved effect.

**Data controls:** The current official background guide says background processing temporarily stores response data even where `store=false` or ZDR is used, for later retrieval. Therefore the owner must approve data handling and retention assumptions before sending private prompts/artifacts; this integration cannot promise zero storage based on the API `store` flag alone. Prompts/completions remain excluded from standard incident logs regardless.

## Browser extension should ask only "what can I safely observe?"

Proposed startup capabilities, **not a deployed protocol**:

```json
{
  "protocol": "hermes.gpt.observer.v1",
  "requested": ["project.read_status", "task.read_evidence_summary"],
  "disallowed": ["task.execute", "task.mark_succeeded", "effect.retry",
                 "approval.grant", "secret.read", "browser.remote_debug"],
  "extension_version": "source-build-digest",
  "native_host_version": "source-build-digest",
  "viewer_authorized_scope": "resolved-by-native-host"
}
```

The native host may return a *sub-set* of read-only capabilities based on OS principal, configured project ACL and exact user-consented pairing. It may not rely on a claimed project name or JSON role; source origin ID alone does not establish the user's task permissions. An extension update should not expand capabilities silently. A screen showing `succeeded` is a projection of a verified ledger state anchored to the task revision and receipt, never the extension's independent conclusion.

## Runtime and causal contract for 30–50 agents

**Independent identities:** `client_http_request_id` (every retry), `logical_run_id` (same work), `task_id`, `task_attempt_id` (new attempt), `provider_response_id`, `webhook_delivery_id`, `tool_effect_key`, `lease_fence`, `agent_worker_boot_id`, `extension_install_id`, `source_event_seq`, `git_target_sha`, and `verifier_receipt_id`. Do NOT collapse them into a single `session_id`: it causes both misdiagnosis and accidental replay.

**Partial order, not fantasy atomic visibility:** local DB transition and local outbox event can be committed atomically in one transaction. Remote provider/API responses, GitHub writes and Chrome state **cannot** share that SQLite transaction. Treat them as Saga-like effects with reservation, an outcome state `UNKNOWN`, independent provider read-back, and fenced compensation *where appropriate*. No exactly-once blanket claim across remote boundaries.

**Admission and fairness:** one project budget and owner policy, per-agent scoped task leases, global provider rate-limit controller, per-file expected SHA and resource claims, one canonical code merge arbiter, per-attempt deadline. The retry budget is inherited; context exhaustion or provider throttling must not create a new budget via agent replacement.

**Completeness visibility:** a source gap detector can identify internal missing sequence ranges in captured producer streams. It cannot prove absence of missing prefix/suffix or a completed remote effect without a trusted exporter checkpoint and receipt. Rate-limit "incident closed" requires verified evidence, not an LLM summary.

## Scored decision rule (proposal, not experimentally measured)

Weights: correctness 30%, safety 25%, deployability 20%, 50-agent isolation 15%, maintenance 10%, each dimension 1–5; weighted sum / 5 ×100. Ratings are architecture review judgments pending implementation tests.

| Mode | Correctness | Safety | Deployability | Isolation | Maintain | Score |
|---|---:|---:|---:|---:|---:|---:|
| A. Official API + durable Hermes ledger | 5 | 4 | 4 | 5 | 4 | **89** |
| B. Read-only MV3/native projection | 4 | 5 | 3 | 5 | 4 | **84** |
| C. Owner-supervised CDP diagnostics | 3 | 3 | 3 | 2 | 2 | **55** |
| D. Unbounded ChatGPT DOM as autonomous runner | 1 | 1 | 2 | 1 | 1 | **24** |

These scores don't measure operating cost. A + B are **complementary** rather than competing: A executes with trusted adapters/ledger, B displays observer projection. A remains optional if the owner does not approve API billing or data handling. B cannot substitute for A.

## Crash and recovery examples

- Browser popup closes while provider request continues: browser UI disconnect is not a provider stop. Native host remains read-only; provider response ID is saved at ledger.
- Webhook delivered twice: verifier checks signature, dedupes event ID, fetches response; must not rerun an already-reserved GitHub write.
- Provider response expires before follow-up: checkpoint provider output/call IDs before expiry in protected storage, then explicitly reconstruct supported conversation items rather than inventing missing context.
- Webhook never arrives: bounded retrieve by saved provider response ID; do not submit a second provider job blindly.
- Native host path/manifest missing: display distinct `NATIVE_HOST_NOT_FOUND` (no worker death claim); Chrome logs + Windows registry diagnostics in owner-controlled installer.
- Managed browser service worker suspends: hydrate UI from durable metadata checkpoint; a Chrome extension port may influence lifecycle but is not a dependable business daemon.
- Parent task cancelled after external side effect reservation: revoke new effect authorization, preserve `NEEDS_RECONCILIATION`, avoid false "cancelled successfully".
- 50 workers encounter a 429: shared provider cooldown and jitter, no 50 individual retry storms. Provider capacity and parent attempt budgets are separate ceilings.
- User manually approves a risky write: approval must bind digest, exact target and TTL; extension cannot directly mutate the ledger from an unverified callback.

## Test and release gates

**GATE A:** verify the installed local extension source digest, actual Chrome/Edge version, manifest, registry host path and feature compatibility; no source currently available.  
**GATE B:** ratify canonical response/idempotency contract across #4/#5/#6/#11; fix false-success SSE and cross-session cache isolation.  
**GATE C:** define and verify the approved API project/pricing/data policy, webhook signature/polling flow, provider response status mapping and consent.  
**GATE D:** integration tests for 100 concurrent retries; 30–50 workers; provider 429; webhook duplication; response expiration; crash after effect; Windows reboot and service-worker suspension.  
**GATE E:** exact integrated Git SHA CI, ability to abort new effects, backup/restore of ledger, rollback runbook, independent operator authorization.

No gate has been represented as passing for the installed extension or live workflow. The offline trace inspector's **60 synthetic tests** demonstrate only its internal diagnostic consistency, not provider implementation behavior.

## Primary technical sources (current as of 2026-11-22)

- OpenAI official Responses background mode: https://developers.openai.com/api/docs/guides/background
- OpenAI official webhook delivery and signature verification: https://developers.openai.com/api/docs/guides/webhooks
- Chrome official Manifest V3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
- Chrome official Native Messaging host, Windows manifest/registry, sender and size limits: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- OpenTelemetry GenAI sensitive content opt-in: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
- W3C Trace Context: https://www.w3.org/TR/trace-context/
