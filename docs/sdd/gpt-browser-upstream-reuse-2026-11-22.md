# SDD Addendum: Reuse vs rebuild — Hermes Browser Extension and GPT Companion

**Date:** 2026-11-22. **Status:** RESEARCHED DESIGN / NOT DEPLOYED. **Relation:** [Hermes/GPT observability SDD](gpt-extension-observability-2026-11-22.md), [multi-agent integration ADR](agent-integration-collision-adr-2026-11-22.md). **Source-quality rule:** references below describe public upstream code/documentation, *not* the owner's installed browser extension.

## 1. Architecture decision: do not build a second controller by default

A live external reference implementation exists: [abundantbeing/hermes-browser-extension](https://github.com/abundantbeing/hermes-browser-extension), community MIT-licensed browser-native panel and companion plugin for Hermes. Its README describes v0.4.1 for Chromium/Firefox, attached-tab control, diagnostics, session controls, plugin status and an opt-in background task tab capability. This is more functionality than previously assumed in the locally documented custom-bridge concept. It is not proven to be the extension installed on the user's Windows browser, and compatibility with this fork must be tested.

### Facts verified from upstream public docs (not local runtime)
- Upstream Chromium panel exposes scoped tab control; click/type are unavailable in its restricted Firefox controller. It requires explicit opt-in, exact attached-tab policy, and approvals for consequential actions.
- Current Hermes branches after 2026-10-23 / release after `0.22.5` removed the former built-in browser extension controller. For those versions a separate `hermes-browser-extension` companion plugin must be enabled **per Hermes profile** and the gateway restarted; `0.22.5` and earlier may still provide built-in control.
- The companion plugin documents twenty `tab_*` controller tools, seven read-only context tools including `browser_event_log` and `browser_context_journal`, three lifecycle hooks (`pre_llm_call`, `pre_tool_call`, `post_tool_call`) and six API routes. Tool namespace differs from the old built-in `browser_*` controller names to avoid conflicts.
- The documented upstream connection requires `API_SERVER_KEY` of at least 16 characters. The existing fork's legacy API-adapter policy differs and should be evaluated under a migration plan, **not** silently changed for all clients.
- Named-profile routing under one gateway differs across upstream versions; `/p/<profile>/api/plugins/...` support must be probed. Cloud/dashboard connections have different controller routes and capabilities than direct local API connections.
- The upstream extension offers Settings > About & Diagnostics with plugin capabilities, reasons and ages, a redacted support report, and its own JS/manifest/unit verification commands.
- Browser control requires exact user-authorized scope. One chat connected to two competing browsers is rejected rather than guessed. Background task tabs remain isolated from existing tabs and are optional.
- Group-chat page-context delivery is documented as unreliable; no agent should claim it saw the page in a group reply without a per-turn acknowledged context receipt.
- Chrome MV3 service workers are intentionally evicted after inactivity (generally ~30s), or long activity (single event >5min), and a frame ID is not a stable document identity across navigation. Persistent state and `documentId` validation are essential; keep-alive hacks are not an authoritative task ledger.

### Source links (primary / near-primary)
1. Extension README and current compatibility: https://github.com/abundantbeing/hermes-browser-extension/blob/main/README.md
2. Companion plugin and tools: https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md
3. Upgrade history and controller move: https://github.com/abundantbeing/hermes-browser-extension/blob/main/CHANGELOG.md
4. Chrome extension service-worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
5. Chrome document identity and navigation lifecycle: https://developer.chrome.com/docs/extensions/reference/api/webNavigation
6. Chrome runtime MessageSender documentId/origin: https://developer.chrome.com/docs/extensions/reference/api/runtime
7. Chrome extension messaging: https://developer.chrome.com/docs/extensions/develop/concepts/messaging
8. Chrome security and message validation: https://developer.chrome.com/docs/extensions/develop/security-privacy/stay-secure
9. OpenTelemetry GenAI agent observability example (May 2026): https://opentelemetry.io/blog/2026/genai-observability/
10. Upstream Hermes browser tools and CDP attachment: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/browser.md

## 2. Architecture alternatives and decision scoring

Provisional 1–5 scores; weights: user safety 35%, observability 25%, compatibility 20%, implementation feasibility 10%, operational simplicity 10%. Higher is better. **Not benchmark results.**

| Architecture | Safety | Observability | Compatibility | Feasibility | Ops | Score /5 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Completely bespoke ChatGPT DOM/CDP controller | 2 | 3 | 2 | 2 | 2 | **2.25** | Reject as default; narrow fallback only |
| Reuse upstream extension and companion plugin unchanged | 4 | 4 | 3 | 5 | 4 | **3.90** | Strong baseline; may not cover custom task orchestration |
| **Hybrid: upstream extension + thin Hermes adapter + authoritative event ledger** | 5 | 5 | 4 | 3 | 3 | **4.40** | Preferred *conditional on compatibility checks* |
| Plain OpenAI-compatible HTTP gateway (no browser control) | 4 | 3 | 4 | 5 | 5 | **3.95** | Preferred for non-browser jobs; lower moving parts |

Ranking includes *deployment surface*: use **plain API** for tasks not requiring browser state; hybrid only for explicitly user-authorized browser workflows. No automatic authority escalation from a read-only monitor to a tab-control tool.

### Non-duplicated responsibilities

| Component | Authoritative for | Never do |
|---|---|---|
| Hermes `autopilot/ledger` (#1) | Durable task state, owner lease, fencing, effect statuses | Trust browser click as provider commit |
| Gateway `gateway/idempotency` (#5 candidate) | In-process HTTP coalescing, key/fingerprint guard | Claim durable exactly-once execution |
| API instrumentation (#6 unique) | Request/result correlation and safe error semantics | Treat terminal HTTP bytes as completed external tool effect |
| Upstream extension `browser_context_journal` / `browser_event_log` | Tab/document observations and user-authorized context | Mint task ownership leases or mark external effects committed |
| Local GPT Companion journal (separate proposal) | Observational audit/handoff evidence | Become another task/effect database; issue Chrome commands |
| Thin adapter (new, P1 proposal) | Normalize upstream receipts to event schema, handshake version compatibility | Duplicate upstream `tab_*` control loop, bypass approval |
| Human approval module (#3) | Permission for consequential writes | Permit implicit consent or blanket unattended tab control |

## 3. Version/protocol compatibility handshake (before any action)

The client sends **capabilities metadata**, never a raw API key or private page content in logs. The adapter records a redacted discovery receipt, including version and age of each field:

```json
{
  "schema": "hermes.browser.capability.v1",
  "gateway_version": "observed_version_or_unknown",
  "adapter_commit": "git_sha",
  "transport": "local_api",
  "extension_version": "observed_or_unknown",
  "extension_build_sha": "observed_or_unknown",
  "plugin_name": "hermes-browser-extension",
  "plugin_version": "observed_or_unknown",
  "profile_id_hash": "hashed",
  "controller_transport": "plugin_http_or_builtin_or_dashboard_socket_or_none",
  "features": {
    "tab_list": "available_or_unavailable",
    "tab_click": "available_or_unavailable",
    "browser_context_journal": "available_or_unavailable"
  },
  "browser_family": "Chromium",
  "permission_scope": "READ_ONLY",
  "observed_at": "UTC_timestamp",
  "evidence": ["trusted_status_response_reference"]
}
```

**Connection matrix**:
1. Older Hermes with built-in controller: prefer built-in `browser_*` tools only when status probe explicitly confirms; companion context tools may still exist.
2. Newer Hermes with companion plugin: use `tab_*` tools when installed/enabled/ready **for that exact profile**. Detect and report old duplicate plugin name `hermes-browser-companion`, do not register two sets of tool names.
3. Local HTTP API: require strong API key and proven gateway reachability; distinguish 401 wrong secret, 403 CORS, 404 missing plugin route, 502/timeout unreachable, 200 + missing capability.
4. Dashboard/socket/Cloud: do not assume plugin HTTP routes work; require negotiated control registration. If unavailable, restrict to chat and approved context only.
5. Multiple Chrome profiles and browser instances: bind one chat to one browser instance; tab lease also binds `tab_id`, `documentId`, owner generation and window scope.
6. Unsupported browser/extension version: **fail closed for control**, but preserve read-only chat where supported; expose a precise reason instead of pretending feature exists.
7. Unknown version/permissions: do not auto-install or silently update a user's extension; emit `CAPABILITY_UNVERIFIED` and request explicit setup authorization.

## 4. Why tasks seem to stop: evidence tree (for GPT/Chrome)

| Symptom | Check in order | Canonical reason | Do NOT assume |
|---|---|---|---|
| Last event is tab "attached" but nothing follows | Document identity, tab lease epoch, worker/port lifecycle, plugin status | `browser_worker_suspended` / `stale_document` / `controller_unavailable` | Model stopped reasoning |
| Gateway accepted but no tool activity | Auth, plugin route, actual tool manifest, agent budget | `controller_capability_missing` / `tool_not_dispatched` | Chrome received a click |
| ChatGPT composer changed but user sees no response | Message submit receipt, latest chat ID, user Stop/Regenerate, tab navigation | `browser_action_unverified` | Request committed |
| Browser action timeout after dispatch | `effect_id` ledger, browser journal, independent read-back | `effect_outcome_unknown` | Safe to retry a send or post |
| Browser stops after navigating | `documentId` changed, `frameId` reused, content script injection and permissions | `document_generation_changed` | Agent crash |
| Widget shows stopped but logs still stream | Observer heartbeat freshness, browser disconnected, job ledger lease | `observer_stale` | Authoritative worker is dead |
| Older `browser_*` no longer available | Hermes version, built-in vs plugin `tab_*` namespace | `controller_implementation_moved` | User revoked permissions |
| Named bot works in chat but cannot click tab | Per-profile plugin install, per-profile routes | `profile_plugin_unavailable` | Model quality issue |
| Repeated same send after reconnect | Command ID, effect outcome, ACK tier, lease | `duplicate_dispatch_attempt` | Previous send had no effect |
| Group bot describes page incorrectly | Per-turn context receipt, group limitations | `context_not_delivered` | Page content was observed |

Every branch must produce `observed/falsified/unknown` with provenance. A model's narrative explanation alone is not evidence. A `200 OK` from a bridge is only a transport receipt until external action has been confirmed.

## 5. Detailed MV3 / runtime fault-injection matrix

Use a disposable browser profile and a fake local gateway; never run these against production ChatGPT chats containing secrets. Synthetic UI first, explicit real-browser approval afterwards.

| Failure injection | Expected invariant | Evidence to collect |
|---|---|---|
| Kill extension service worker after command accepted | No duplicate send, command status UNKNOWN until reconciliation | command ID, generation, durable receipt |
| Simulate idle suspension at 29s/31s/61s | Recovery on next Chrome event, no need for permanent worker | registered listener/rehydration timestamps |
| Navigate immediately before `tab_type` | Rejected if `documentId` changed | sender documentId, tabId and epoch |
| Replace iframe between snapshot and click | Control does not act on stale target; re-check restricted origins | active frame URL, origin classification |
| Duplicate `runtime.connect` port | One owner per tab, no double action | lease epoch and action count |
| Force websocket close after write | No auto-resend; reconcile effect | last ACK tier and independent read-back |
| Switch Chrome profile or tab mid-turn | Old session action blocked | binding/session revision and tab generation |
| Suspend/restart gateway while tab remains attached | Browser control permission remains scoped; no stale task owner | scope and lease expiry |
| Revoke user approval/turn off background tab control | No action after revocation; old task tabs not reacquired | approved scope/version |
| Introduce 401 / 403 / 404 on plugin status | Accurate and distinct UI diagnosis, never auto key rotation | HTTP code and route version |
| Simulate missing status/partial log | Observer degraded, not worker stopped | independent process vs observer probes |
| Two bots attempt the same tab | Second action denied until lease handoff | epoch, owner id, monotonic expiry |
| Group message has no context receipt | Mark context missing; never hallucinate page inspection | per-turn context reference |
| Update extension and change manifest permissions | Fail closed pending explicit approval of new permissions | build SHA and manifest diff |

### Testing and coverage gates
- For upstream extension itself, run documented `npm test`, `npm run check:js`, `npm run check:manifest`, and `npm run verify` on a **pinned SHA** before integrating; do not interpret source README examples as an executed test.
- For gateway, existing `GPT Gateway Regression` CI is an independent gate; run full suite and compare to main baseline for unrelated failures.
- For bridge adapter, add contract tests of all capability states, controller version modes, profile routes and missing plugin case. Record payload schemas with golden files in `tests/contracts`.
- For browser end to end, require manual gate with explicit owner consent; one tab, then two competing agents, then 50 synthetic agents and tab ownership chaos.
- For safe telemetry, use OpenTelemetry GenAI operation attributes and span names without raw prompts/credentials by default.

## 6. Prioritized roadmap and stop conditions

**P0:** keep #6 safe HTTP fixes isolated; use #5's dedup module as canonical candidate during merge arbitration; verify success/incomplete/failure and SQLite atomic state; implement exact-release CI matrix.

**P1:** perform actual installed-extension inventory over user-approved local bridge; compare hashes to upstream. If upstream already installed, first integrate plugin status/events/hooks rather than changing the extension background scripts. If custom extension installed, compare manifest permissions, command/receipt contract and test fixture against the reference without silently replacing it.

**P1→P2:** add thin observer adapter from journal/status to authoritative run IDs; only then durable lease/fencing via #1. Replace all duplicate unsafe web-send retries with effect reconciliation and approval.

**P2:** run chaos tests with dozens of agents + browsers. Promote to production only with zero duplicated externally committed operations in controlled fault matrix and independent evidence of final state.

**Explicit blockers:** missing actual local browser version, unknown installed extension identity, missing browser control authorization, incompatible upstream Hermes release/plugin profile, concurrent PRs without resolved owner, or absent durable effect ledger. These must not be represented as done simply because API unit tests pass.
