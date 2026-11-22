# Hermes Browser Extension ↔ GPT Companion — compatibility & trust audit

**Date:** 2026-11-22
**Classification:** design review only; **no installed client, local runtime, browser tab, credential or ChatGPT session inspected**
**Owner:** GPT Companion observability audit; integration gated by PR #12 and Autopilot owners
**Source pinning:** Hermes fork main `7e9100901819ee44c16b4ddcb79a6bcb7909f591`; upstream NousResearch main `da8e7d71abe4ac165760cd813c0c18c53e697b90` (as of audit); third-party `abundantbeing/hermes-browser-extension` main `d6ba3223da762b262cfe403fcf17fd8376244748` (2026-11-21). These are inspected **remote references**, not locally installed versions.

## 1. Integration-blocking discrepancy (confirmed)

Current fork main `pyproject.toml` declares `hermes-agent 0.6.0` and contains no proven live GPT/ChatGPT browser companion. The externally maintained Browser Extension (manifest version `0.4.1`) explicitly requires **Hermes Agent 0.22 or newer**, `API_SERVER_KEY` length >=16, an enabled companion plugin per Hermes profile and a gateway restart. The plugin README also documents that Hermes Control for builds later than 0.22.5 may require its twenty `tab_*` tools. The installed fork and extension compatibility is **UNKNOWN / unsupported by evidence**. Do not silently assume the fork's old API server supports current extension readiness, route registration, session ownership, background-task tabs, or approval contracts.

`NousResearch/hermes-agent` upstream main was updated on 2026-11-22, whereas the fork main points to an April commit. A GitHub compare from fork main commit `7e9100...` to upstream `da8e7d...` reported ~72,983 commits ahead; this is a tool-reported count over an oversized comparison and **not an audited per-commit migration estimate**. The hard fact is major version/date drift. Before patching the actual runtime: choose a supported upstream baseline, create a deterministic manifest of API/SDK versions, and run contract tests on that baseline.

**Release gate COMPAT-0:** exact installed Hermes runtime version, gateway API capabilities, extension manifest version, companion-plugin version+status, profile identity, browser supported capability handshake. Any unknown or mismatched field => `UNSUPPORTED_VERSION`, read-only diagnostics only, no browser control or autonomous refresh.

## 2. Actual companion plugin capabilities and authoritative boundaries

Verified in the public extension's pinned README, plugin `status_route.py`, `policy.py`, `journal.py` and browser manifest:

| Capability | Current external implementation | Trust / impact for GPT observability |
| --- | --- | --- |
| Status | `GET /api/plugins/hermes-browser-extension/status`, `object=hermes.browser_companion.status`, version, profile, tools/hooks/routes, `live:false`; authenticated gateway check | Presence of status route **does not** prove live worker, GPT completion, or ChatGPT tab ownership |
| Control | 20 `tab_*` tools in supported builds, only current attached/browser-owned sessions, approvals for consequential actions; no password/payment fields | Browser actions are **explicitly authorized** and bounded by tab/session. Their returns are not proof of server-side effect success |
| Context | Seven read-only `browser_*` context/tools; received page data is explicitly untrusted | Page/ChatGPT content cannot be used as privileged instruction or verified task outcome |
| Plugin hooks | `pre_llm_call`, `pre_tool_call`, `post_tool_call` on supported gateway | Proposed source of metadata-only stage signals if version handshake and security review pass |
| Journal | Owner-scoped metadata-only bounded `journal.jsonl` (up to 500 entries), mode 0600 where available | Not a durable global task ledger or authoritative proof; no plaintext pages, args, tokens or tool result bodies should be copied |
| Background task tabs | Opt-in, session-scoped, owner-bound; no automatic reuse of orphan tabs after extension restart | Browser-only task tabs must not be assumed to survive agent lease replacement or grant new owner write capabilities |
| Context expiry | In-memory page context with maximum 300-second retention (per README) | Historical content should not be retained by GPT diagnostic log; replay only trusted metadata with user consent |
| Runtime monitor | Plugin declares **no background processes, no telemetry, no outbound connections** | Our offline StatusWatch is separate and not an existing extension monitoring feed |
| Permissions | Chromium manifest v3, extension version 0.4.1, broad `host_permissions`, `debugger`, `tabs`, `scripting` | High-power browser surface: threat model must include extension updates, origin changes, consent revocation, session identity and tab boundary |

**Warning:** The extension supports actual browser control with user-mediated approvals. Our `gpt_companion` is *only* a metadata-only diagnostic journal. Never bind `journal.assess().next_action` to a browser `tab_click`, `tab_type`, or `tab_batch` command. Reconciliation and operator decisions remain elsewhere.

## 3. GPТ/ChatGPT bridge policy (proposed)

There are at least three distinct sources of truth:

1. **Hermes official provider/API path:** model API responses, tool call metadata and authentic provider status/receipts; supported SDK contract.
2. **Browser companion:** an **opt-in** UI context controller for tabs the user has intentionally attached or created, with explicit rights and consent; not a generic hidden ChatGPT session manager.
3. **GPT Companion diagnostic observer:** receives only authenticated, allowlisted `kind`, source-local sequences, stable opaque IDs and incident metadata. No message contents, tokens, cookies, browser localStorage, prompts or private chain of thought.

ChatGPT plan/subscription, the OpenAI API, a GPT in the ChatGPT UI and an Hermes provider connection are distinct integration surfaces. Do not assume API permissions/credits from a ChatGPT subscription. Do not circumvent CAPTCHA, login/MFA, rate limits, subscriptions, provider access restrictions or consent mechanisms.

**COMPAT-1 authoritative event producer:** an opt-in, version-pinned Hermes plugin hook publishes **metadata only** through a dedicated authenticated adapter (`emitter_principal` taken from verified transport, not caller's `source` string); local bounded WAL outbox and replay sequence gap contract. Never scrape arbitrary ChatGPT DOM to assert durable progress.

**COMPAT-2 controller lifetime:** carry `browser_controller_id` (opaque), `profile`, `session_id`, `run_id`, `attempt`, `lease_id`, current `fence`, status route version, extension version, consent state. Do not reuse an orphan tab or stale controller after stop/restart.

**COMPAT-3 stream ambiguity:** distinguish (a) request never admitted, (b) request admitted, response ID unknown, (c) response ID known and recoverable, (d) external effect reserved without receipt, (e) terminal model text without independent verifier. Transport disconnect is not proof of cancellation.

**COMPAT-4 cause-coded connection probes:** `PLUGIN_MISSING`, `PLUGIN_STALE`, `PROFILE_ROUTE_UNAVAILABLE`, `GATEWAY_UNREACHABLE`, `GATEWAY_AUTH_DENIED`, `CONTROLLER_NOT_ATTACHED`, `CONSENT_REVOKED`, `EXTENSION_VERSION_UNSUPPORTED`, `BROWSER_UNSUPPORTED`, `MODEL_PROVIDER_DOWN`, `UNKNOWN_WRITE_RECEIPT`. Each diagnosis must carry direct evidence pointer, certainty, last successful stage, next safe action and whether auto-retry is forbidden. These codes are **proposed**, not currently implemented as event kinds.

## 4. Stop diagnosis and fault-injection priorities

| Scenario | Likely cause (hypothesis) | Decisive check | Safe response |
| --- | --- | --- | --- |
| Extension visible, control tools missing | Plugin not enabled for profile / stale gateway / host isolation / version mismatch | Status route actual `tools`, profile and release | `CAPABILITY_MISSING`, do not fabricate tool |
| Browser attached, `tab_click` refused | Wrong tab/session, consent revocation, controller lease expired | trusted controller identity + current user approval | no fallback to raw CDP or unauthorized scripting |
| Gateway health says running but GPT turn hangs | Streaming route stall, model provider failure, invalid budget, deadlock | session/task receipts, progress+heartbeat, per-stage deadline | incident with bounded operator diagnosis |
| Chrome tab closed / browser restarted | Service-worker lifecycle / consent / tab orphaned | extension controller registry, session key, exact tab ownership | do not assume task failed, do not replay external write |
| Reply text visible in ChatGPT | LLM text completed but task may still have unconfirmed effect | independent provider/GitHub receipt + verifier at exact revision | `AWAITING_VERIFICATION`, never `SUCCEEDED` |
| 401/403 after restart | Gateway key rotated; plugin profile mismatch | version-pinned signed/bound auth and profile status | ask for legitimate re-auth, no secret log or bypass |
| Replayed listener messages | at-least-once delivery + stale browser queue | source-local seq, idempotency key, task attempt/fence | dedup and reconcile; never duplicate write |
| Ambiguous `fetch` error | Gateway saw POST but connection reset before response | gateway request ledger, provider action read-back | `UNKNOWN_OUTCOME`, not automatic retry |
| Two browser windows operate one run | Conflicting controller ownership | per-session browser owner and lease | fail closed, require explicit handoff |

The extension already has a realistic `tests/e2e-gateway-failure-diagnostics.mjs` that models Windows `pydantic_core` wheel mismatch, gateway disappearance mid-session, stale boot ID, reset-in-handler, restarted gateway and unreliable fetch. **Reuse test concepts and fixtures by reference**, not brittle copies or unauthorized live browser automation. Verify compatibility at pinned extension commit before any integration.

## 5. Safe staged implementation

- **D0 (now):** source audit, compatibility contract, PR coordination and offline diagnostic fixes. No local / browser deployment claimed.
- **D1:** upgrade fork on isolated branch to pinned supported Hermes runtime (or document why not), canary with extension/plugin status route and explicit per-profile gateway restart; keep rollback and original config.
- **D2:** opt-in hook emitter `pre_llm_call/post_tool_call` behind allowlist and authentication. Integration test source identity/sequence and complete denial conditions. Never include full context or user prompts in observer DB.
- **D3:** bind diagnostic watcher to observer outbox with independent control-plane lease and known provider receipt handling; combine per-stage stop diagnosis without taking control actions.
- **D4:** inject errors from external extension test scenarios into isolated harness: profile mismatch, stale Chrome controller, browser restart, 401/403/429, SSE lost ack, content leak, downstream effect unknown, host shutdown and resumable outbox.
- **D5:** 1/10/30/100 agents synthetic load with per-profile isolation, bounded queues, worker-stop detection, deterministic replay; independently validate no false positive success and duplicate-effect attempts.

**Owner approvals:** one owner for `gateway/platforms/api_server.py`, one for browser extension adapter, one for `gpt_companion`, one for `autopilot`, independent release reviewer. No single GPT or Hermes worker can approve its own production cutover.

## 6. Verified source map

- Hermes fork package version: https://github.com/Podtverzhdeno/hermes-agent/blob/7e9100901819ee44c16b4ddcb79a6bcb7909f591/pyproject.toml
- Official Hermes upstream (pinned inspected HEAD): https://github.com/NousResearch/hermes-agent/tree/da8e7d71abe4ac165760cd813c0c18c53e697b90
- Extension repository / pinned HEAD: https://github.com/abundantbeing/hermes-browser-extension/tree/d6ba3223da762b262cfe403fcf17fd8376244748
- External companion README: https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/companion-plugin/README.md
- Plugin status contract: https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/companion-plugin/status_route.py
- Browser permissions: https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/extension/manifest.json
- Ownership metadata journal: https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/companion-plugin/journal.py
- External real-Chrome diagnostics design: https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/tests/e2e-gateway-failure-diagnostics.mjs
- Related current audit: https://github.com/Podtverzhdeno/hermes-agent/pull/23

**Strict conclusion:** a browser plugin status response is not a live GPT execution monitor. The current Hermes fork is not verified to satisfy the plugin's minimum declared version. Current safe artifact is a proposed compatibility contract, not a working connector.


## 7. Manifest V3 service-worker lifecycle (official Chrome guidance)

The pinned extension's `manifest.json` uses `background.service_worker: background.js`, MV3 and minimum Chrome 116. Chrome documentation explicitly warns that extension service workers can be shut down unexpectedly and must recover state after reinitialization. Worker globals and in-memory timers are **not** durable source-of-truth. This is not a bug that can be fixed by asking the GPT model to continue longer.

**Root-cause taxonomy additions (design only):** `EXT_SERVICE_WORKER_RESTARTED`, `EXTENSION_CONNECTION_LOST`, `CONTROLLER_OWNERSHIP_EXPIRED`, `OUTBOX_REPLAY_PENDING`, `BROWSER_PROFILE_REPLACED`. Require a durable resume cursor and authenticated session/controller handshake before accepting new events. Chrome's `chrome.storage` is supported for state; the Web Storage API is not available to extension service workers. For a protected producer outbox with ordered writes, favor a narrow extension-specific persistent API with schema validation and bounded capacity; test abrupt worker suspension after enqueue and before acknowledgement.

**Verification cases:** idle service worker terminated with active Hermes gateway; extension reloaded while a browser tab remains; gateway process restarts and presents a new boot id; Chrome exits with an in-flight authorization; background task tab orphaned; controller reattaches under a new session; browser restores previously open tabs after update. Every case must prove no silent re-approval and no duplicate external effect. The old worker's delivered events must not freshen the liveness of the new worker without authenticated instance-bound heartbeat.

Reference: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/

## 8. Provider response continuity and privacy (primary sources)

OpenAI Responses background mode can return a stable response ID and later be retrieved; signed webhooks can report completion. The correct observer design stores opaque response references and the **fact** of final status or receipt, not user messages, private reasoning traces, or raw payloads. Verify webhook signatures on raw bodies before trust, deduplicate deliveries, and reconcile after lost transport acknowledgements. The browser extension's UI or service worker cannot by itself prove upstream provider completion.

Reference: https://developers.openai.com/api/docs/guides/background and https://developers.openai.com/api/docs/guides/webhooks

OpenTelemetry GenAI conventions are useful to name model/tool spans, but some instrumentation can optionally include full model inputs, outputs and tool definitions. **Default deny all such content-bearing attributes**; use only allowlisted metadata for GPT Companion. Trace headers/baggage must not carry credentials or page data. Pin semconv version in adapter contract tests.

Reference: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md

**Gate COMPAT-5:** a synthetic 30-agent Chrome MV3 suspend/restart test with opt-in session ownership, bounded outbox, replay cursor, no false task completion and no duplicate provider effects. Browser consent revocation must win over reconnect retries. The user must be able to stop monitoring without residual page data collection.
