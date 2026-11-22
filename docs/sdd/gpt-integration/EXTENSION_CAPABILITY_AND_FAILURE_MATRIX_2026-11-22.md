# SDD ADDENDUM — GPT/browser companion: verified protocol, trust and failure matrix

**2026-11-22; READ-ONLY SOURCE AUDIT.** Not installed, not deployed, and no live user browser/ChatGPT access verified.

## 1. Identified repositories and exact baselines

- Current fork: [Podtverzhdeno/hermes-agent](https://github.com/Podtverzhdeno/hermes-agent) main `7e9100901819ee44c16b4ddcb79a6bcb7909f591`, package version `0.6.0`.
- Modern upstream: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) main `da8e7d71abe4ac165760cd813c0c18c53e697b90` at audit; Kanban state machine is already present in modern builds. Treat as candidate migration, not a patch that can be blindly overlaid.
- Independently maintained community [abundantbeing/hermes-browser-extension](https://github.com/abundantbeing/hermes-browser-extension) main `d6ba3223da762b262cfe403fcf17fd8376244748` at audit, `manifest.json` + `package.json` both identify version **0.4.1**. This is an *available public candidate*, **NOT evidence that it is the user's currently installed GPT extension**.
- The community `companion-plugin/README.md` says Hermes Agent **0.22 or newer**; builds after October 24, 2026 move Control into the plugin. An old fork advertising 0.6.0 is therefore not a verified host; fail the compatibility handshake. The documented status probe is authenticated `GET /api/plugins/hermes-browser-extension/status` and returns `object=hermes.browser_companion.status`, plugin version, profile, tool names and `live:false` (loaded state, **not current browser liveness**).

The inspected fork's `gateway/platforms/api_server.py` has `/v1/models`, `/v1/chat/completions` and `/v1/health` but does not implement the exact extension plugin status path, `/v1/capabilities`, `/v1/profiles`, or `browser.controller.register` in that file. This is file-local evidence, not a global negative codebase proof. Never assume a simple bearer-auth success on /v1/models proves compatibility with complex control flows.

## 2. What the community extension really exposes

The Chromium `manifest.json` declares MV3 service worker, minimum Chrome 116, permissions including `activeTab`, `debugger`, `scripting`, `tabs`, `downloads`, `storage`, `unlimitedStorage`, `offscreen` and broad HTTP/HTTPS/file host permissions. This is a significant privileged browser surface; opt-in tab attachments and explicit consent are essential and must be tested, not merely documented. A browser UI badge is not a trust anchor.

The companion plugin declares **20 tab control tools** (e.g. `tab_snapshot`, `tab_click`, `tab_type`, `tab_navigate`, `tab_create`) and **7 context tools**. The tool names are deliberately separate from built-in `browser_exec`. It also has pre-LLM, pre-tool and post-tool hooks. `companion-plugin/control_broker.py` specifies Control protocol version 1, 30s registration tickets, 35s command timeout, 180s principal-binding grace period and a single-controller-per-scope rule. It explicitly refuses ambiguous owner/controller identity and staled capabilities; the control timeout is **not** proof an action failed before external effects.

`DATA-FLOW.md` describes typed `hermes.browser.turn.v2` envelopes with owner, conversation, session and turn identity, retaining compatibility with prompt-embedded v1; `companion-plugin/protocol.py` still defines a separate `hermes.browser.context.v1` identifier. These are **two different protocol surfaces**, not interchangeable fields. Before integrating any observer, produce a canonical mapping and test version negotiation; do not interpret all payloads tagged "browser" as one schema.

The community plugin has metadata-only journaling (`companion-plugin/journal.py`) and a deliberately bounded in-memory context capability. It is **not** itself proof of provider effects or GitHub write completion. The extension's `DATA-FLOW.md` states it keeps connection settings and keys in Chrome local storage, has optional remote connections and per-connection/context-sharing consent; profile switches must not reuse the previous cached state.

## 3. Mandatory compatibility negotiation (proposed, not yet implemented)

Perform only authorized, read-only probes:

1. Record exact extension build/version/manifest SHA and host Hermes commit/profile. If unknown: `HOST_UNVERIFIED`, **disable control**.
2. Verify local gateway address and TLS/loopback scope. Do not use an exposed unauthenticated public port or send bearer keys in URLs. Test `/health`, authenticated `/v1/models`, independent profile capability discovery and plugin `/status`. Classify 401 vs 403 origin vs 404 route missing vs timeout explicitly.
3. Verify status object, expected plugin ID, version range, exact profile and permitted tool names. `live:false` from a status route means static readiness only, not an offline controller; no false outage.
4. Negotiate `hermes.browser.turn.v2` versus legacy `context.v1` and `browser.controller` wire protocol independently; no silent downgrade of authorization requirements.
5. For every control action, assert exact principal/profile/session/controller/browser-profile/tab/frame/document-generation/fence, current opt-in, action capability, freshness and reviewer approval. Stale documents and cross-origin frame changes require refusal and new snapshot.
6. Give each attempted effect a durable server-side action reservation. The extension ACK only records transport, not external effect. Complete only after independent authoritative receipt or read-back.
7. On browser service-worker suspension, extension unload, network reconnect, profile switch or Chrome restart: invalidate cached capability/turn state, replay diagnostic events by cursor, verify authority from server anew; **never resend an unknown write**.

A compatibility matrix must be reviewed for each transport: local REST, remote REST, signed-in Hermes Cloud dashboard WebSocket, remote dashboard WebSocket, Chromium versus Firefox. Browser control, account sign-in, page context consent, attachment upload, background tabs and session authority differ across these modes. Report capability `unsupported`, `unreachable`, `unknown` and `not authorized` as distinct statuses.

## 4. Stage-specific failure injection required

| Stage | Inject fault | What to prove |
| --- | --- | --- |
| Extension install | Older pinned Hermes, missing plugin, old plugin name | No silent control activation; exact missing dependency |
| Auth | Invalid token, changed profile, rejected origin, stale bearer | No fallback to different profile or insecure host |
| Session routing | Two controllers same session, wrong principal, stale owner | Refuse ambiguous attach and cross-agent continuation |
| Tab lease | Tab closed/reused, doc navigates, frame origin changes | No action through old tab/frame/ref |
| MV3 lifecycle | Service worker suspended/restarted mid-turn | No false terminal / no duplicate prompt |
| Browser action | Click submitted then transport lost | Effect outcome UNKNOWN, reconcile before retry |
| Human approval | Approval expired, denied, different action digest | Fail closed; no approval replay |
| Rate limits | 429, 401, 403, 5xx, reverse-proxy buffering | Codes separated, budgeted safe retry only |
| Context data | Prompt injection embedded in web page, open-tab list | Untrusted text never becomes policy or instruction authority |
| Multi-profile | Switch connection/account during cached status or turn | Clear scope; prevent context leakage between profiles |
| Event transport | Duplicate, delayed, reordered or forged status | Source-seq gap, signature verification, idempotent ingest |
| Reviewer proof | Agent says "done", CI SHA stale or missing | Remain awaiting independent verification |
| Recovery | Crash after external reservation before receipt | No blind external write; manual/provider reconciliation |
| Load | 10/30/50 worker claims and reconnect storms | Bounded queue, fair resource admission and no split-brain owner |

## 5. Deep integration policy and scoring

Integrate upstream Kanban first behind a sandboxed migration/canary, pin revisions, compare task/lease/effect contracts. Do not create a second Autopilot scheduler. Integrate **one** GPT API-handler implementation (#4/#5/#6/#11 collide) and **one** canonical observer schema (#8/#9/#12 compete). This PR's audit gate is independent and advisory. Actual browser control should begin read-only, per-tab opt-in, with read-only diagnostics; mutating actions need a tested trusted effect gateway and user-authorized policy.

Severity ranking: P0 false-success, duplicated external write, privilege leakage and cross-profile action; P1 silent stopped task and lost progress; P2 stale capability/missed alerts; P3 display quality. A feature with P0 risk remains blocked regardless of its weighted attractiveness.

Acceptance must include exact-revision CI on Python 3.11/3.12, extension Node tests (upstream has `npm run verify` and separate browser-control E2E scripts), isolated Windows/WSL gateway smoke, MV3 restart, replay, redaction, approval, stale-fence and provider reconciliation. **A model-generated "success" never substitutes for these.**

## 6. Audit, uncertainty and next handoff

Verified public source components above at extension commit `d6ba3223da762b262cfe403fcf17fd8376244748`. Current fork cannot claim this extension is installed; Local_WorkSpace MCP returned `Session terminated`. No live events or local fixes have been observed. Add to the incident log only verified outcomes with exact version/commit, UTC timestamp, operator owner and supporting test; unknown is not healthy or failed.

For the next agent: determine the **actual installed extension** by inspecting its manifest/version from the user-authorized local host, then compare the exact build with the pinned public source before changing any runtime permissions. Do not infer it from GitHub presence. The first output is a compatibility table, not a deployment.

Source anchors: [manifest](https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/manifest.json), [data flow](https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/DATA-FLOW.md), [controller broker](https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/companion-plugin/control_broker.py), [status route](https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/companion-plugin/status_route.py), [plugin tools](https://github.com/abundantbeing/hermes-browser-extension/blob/d6ba3223da762b262cfe403fcf17fd8376244748/companion-plugin/README.md), [modern Hermes](https://github.com/NousResearch/hermes-agent/tree/da8e7d71abe4ac165760cd813c0c18c53e697b90).
