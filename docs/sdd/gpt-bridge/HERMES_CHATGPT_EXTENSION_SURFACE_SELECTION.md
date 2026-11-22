# SDD: Which "Hermes ↔ GPT extension" are we actually operating?

**Date:** 2026-11-22. **Status:** comparative source/document review; implementation-selection ADR; NOT an observed local extension or a deployment. **Owner:** GPT transport/integration QA. **Source:** repository READMEs and technical docs listed below. No code imported from third-party projects.

## Executive decision

The phrase "Hermes ChatGPT extension" is dangerously ambiguous. These **five different codebases are NOT interchangeable**, and even direction of message flow differs. An agent must first resolve the concrete installed binary/repository, connection mode and protocol version, then negotiate capabilities before attempting any prompt, tool call or automatic recovery. A green HTTP health check alone does not prove chat, tool, or remote effect functionality.

**Transport selection (a proposed conditional choice, not a claim of installed software):**
- Want ChatGPT Web/connected MCP to **control local Hermes**: consider asimons81/hermes-gpt behind supported Secure MCP Tunnel or another owner-authorized authenticated private boundary. Its curated read-only/operator policy surface and operation-aware job tools fit multi-agent governance. Inspect pinned release and local config first.
- Want a minimal **ChatGPT Web → Hermes** four-tool start/status/wait/cancel interface: madpower2000/chatgpt_mcp_bridge is an alternative to *evaluate*, not an assumed canonical scheduler. Verify how it persists/reconciles subprocess failures and exposes the HTTP endpoint.
- Want **Hermes embedded inside Codex desktop plugin**: intellectronica/hermes-chatgpt-extension is a local **stdio MCP App** with Hermes desktop management JSON-RPC/WebSocket + REST, not a hosted remote MCP endpoint for ChatGPT cloud. Needs Node.js 22+, Codex plugin support and a newer compatible Hermes backend. Old fork /v1 endpoints by themselves are insufficient.
- Want **Hermes to use ChatGPT Web as a model via Chrome session**: Dworr21/chatgpt-bridge drives the ChatGPT UI DOM via MV3 plus local HTTP/WS. Treat as *non-authoritative UI automation* with lost acknowledgements and high compatibility risk, not a durable task scheduler. Do not bypass auth or product safeguards.
- Want **Hermes to work with real browser tabs in a side panel**: abundantbeing/hermes-browser-extension is a browser-side Hermes UI/context plugin. Its BCP v2 and opt-in control are unrelated to the above ChatGPT MCP direction. Its supported companion-plugin and gateway capabilities are version-gated.

## Comparative protocol and failure map

| Project | Real direction | Protocol, authority and preconditions | Diagnostics to trust | Most likely stop modes |
|---|---|---|---|---|
| intellectronica/hermes-chatgpt-extension | Codex plugin -> Hermes | local MCP stdio to Hermes desktop WebSocket JSON-RPC / REST; Node 22+; plugin install; optional SSH modes | plugin start log; Hermes desktop gateway capability/version; exact request identity and backend receipts | Codex cannot spawn node; source not built; SSH auth/host key; no desktop routes; stale UI cache; lost send ack |
| asimons81/hermes-gpt | ChatGPT/Codex MCP -> Hermes | stdio or Streamable HTTP; loopback by default; private tunnel/OAuth or bearer; operator policy and dry_run/confirmation | MCP initialize/tool discovery, serverInfo version, per-tool policy, bounded job status & provenance | tunnel disconnected; OAuth mismatch; missing tool profile; operator denied; job orphan after restart; caller cannot download embedded resource |
| madpower2000/chatgpt_mcp_bridge | ChatGPT Web MCP -> Hermes job | FastMCP four external tools; Hermes subprocess, SQLite job store, deployment boundary configured separately | explicit job_id + status/cancel + process and receipt recheck | subprocess timeout; orphan after restart; long-running task; Cloudflare exposure/policy issue |
| Dworr21/chatgpt-bridge | Hermes -> ChatGPT browser UI | Chrome MV3 content/background scripts, local Python HTTP :11557 / WS :11558, authorized active chatgpt.com tab | separate localhost health, extension WS ready, tab/session presence, DOM request/response IDs | Chrome/MV3 sleeps, UI selector changes, CDP detach, lost send ack, wrong tab/conversation, silent duplicate |
| abundantbeing/hermes-browser-extension | browser side panel -> Hermes | API server and optional companion plugin; per-tab user opt-in; BCP v2, version capabilities | capability status + reason/source/age, gateway trace, plugin status route | old gateway lacks endpoint, plugin disabled, authorization not granted, browser attached stale tab, transport up but Hermes runtime down |

**Do not conflate protocol states:** MCP transport ACK, HTTP response write, SSE [DONE], browser DOM "assistant stopped typing", subprocess exit 0, tool effect receipt, task completion, verified artifact and CI status are separate events. The last state is proved only by independent revision/receipt verification. In particular, reconnect after an unknown send must query the original conversation/task first; no blind resend.

## Comparison of implementation readiness (proposal only)

Scores 1 to 5, higher is better except integration risk (higher is worse); based on published documentation, not controlled production load tests. **Not a numeric measure of actual product reliability.**

| Candidate | Fits ChatGPT Web -> Hermes | Observability contract | Least-privilege story | Integration risk | Decision |
|---|---:|---:|---:|---:|---|
| asimons81/hermes-gpt | 5 | 4 | 4 | 3 | Primary design to evaluate if user runs ChatGPT MCP |
| madpower2000/chatgpt_mcp_bridge | 5 | 3 | 3 | 3 | Simpler fallback; verify durable restart story |
| intellectronica/hermes-chatgpt-extension | 1 (Codex-only) | 4 | 3 | 4 | Best only for Codex desktop plugin goal |
| Dworr21/chatgpt-bridge | 1 (opposite direction) | 2 | 2 | 5 | Experimental/explicit human-supervised UI adapter |
| abundantbeing/hermes-browser-extension | 1 (browser side panel) | 4 | 4 | 3 | Browser companion, not ChatGPT MCP bridge |

Score rubric: Fit= direction/use-case; Observability= documented event/diagnostic surfaces; Least-privilege= authentication/policy/approval controls; Integration risk= number of unproven compatibility boundaries, runtime and deployment uncertainty. Deployment test results can overrule these judgments. Avoid choosing solely because the name contains ChatGPT.

## One harness contract for dozens of agents

At intake (an authenticated service, not an LLM prompt), assign immutable project_id/task_id/run_id/attempt_id, execution revision, parent/span chain, bounded budget, per-capability owner, explicit risk class, lease fencing token and policy generation.

**Capability handshake (before any work):**
- identity: installed plugin repo, artifact digest/signature if available, version, protocol, endpoint and caller principal;
- read: advertised lifecycle methods, permissible tool profiles, job polling and resume support;
- write: provider-native idempotency, dry-run and exact-action confirmation, approval gates, safe cancellation semantics;
- observability: event IDs, producer sequencing, event cursors, durable retention, elapsed time, protocol-specific terminal codes;
- failure: incompatible version and missing capability are UNSUPPORTED, not a reason to silently fall back to unauthenticated browser/REST routes.

**Canonical state authority:** modern Hermes Kanban (after migration / verified compatibility), not independent GPT/UI observer tables. If current fork 0.6.0 remains in use, first build an adapter proving equivalent state/evidence; do not run a second scheduler by default. One task cannot have two concurrently acting owners of the same mutating resource. Multi-agent expansion should increase parallel READ/REVIEW work and independent verification before increasing writable concurrency.

**Effect protocol:** AUTHORIZED -> INTENT_DURABLE -> INVOKED -> RECEIPT_OBSERVED -> EFFECT_VERIFIED or OUTCOME_UNKNOWN. A transport close after INVOKED may leave a real external action. Quarantine it, consult provider read-back and preserve the same idempotency identity until reconciled. Do not extrapolate exactly-once from a local SQLite journal.

**STOP/CANCEL protocol:** authenticated owner STOP revokes future tool dispatch at the tool gateway immediately; cancelling a UI session or killing a subprocess does not prove remote effect cancellation. Log accepted, requested, acknowledged, effects_pending, reconciled, final. Return status UNKNOWN if unable to prove stronger.

**Diagnostic event properties:** event id and schema version; task/run/attempt/agent; adapter/product/protocol/version/connection ID; source-local seq/epoch; trace id+parent; phase and reason code; server receipt timestamp; target revision, effect evidence hash and permission generation. No prompt content, raw cookies, secrets, file bytes, unredacted browser DOM or auth headers. Trusted verifier must not share the worker's credential/attestation authority.

## High-risk failure injection by transport

| Injection | Observable facts required | Release test |
|---|---|---|
| stale local Codex MCP app with updated Hermes backend | exact plugin build/version + gateway capabilities | explicit incompatible/disabled not connected |
| corrupt/expired SSH token or missing Node 22 | local spawn/handshake vs gateway response | no false working session |
| tunnel disconnect after MCP start-job returned timeout | local durable job id, provider query and session causality | no duplicate accepted work on retry |
| MCP tool profile hides tool but browser offers similar functionality | effective allowlist + runtime policy generation | no fallback privilege escalation |
| 30 concurrent agents claim one repo file | fencing, locks and write scopes | one writer, independent reviewers |
| Chrome MV3 restart during a send | request key, conversation id, last send status | OUTCOME_UNKNOWN until reconciled; no auto resend |
| HTTP SSE finishes stop after failed tool | task exception, final result and stream terminal | typed error and never verified completion |
| orphaned subprocess/PID after host restart | supervisor boot epoch, old lease and job store | do not kill unrelated reused PID |
| GitHub parent PR advances while child CI green | exact compare parent/child SHAs | rebase and rerun tests at integrated head |
| owner STOP while external write awaits reply | revocation fence + effect reservation/read-back | no new write, incomplete effects reconciled |

## Acceptance & evidence checklist for the *actual installed extension*

**Cannot be declared complete** until: local manifest/source and version inspected; live transport reached with explicit owner authority; capabilities negotiated; error and cancellation semantics tested; duplicate request / timeout / restart / stale lease injection passes; 30-agent no-conflicting-writer test passes; telemetry contains no secrets; exact SHA CI successful; independent verifier confirms external effects; recovery produces a durable incident log and operator can explain the last trusted state. All checks must be rerun on deployment artifact, not merely same source branch.

The user/local machine runtime was not reachable from this session (Local_WorkSpace MCP returned Session terminated). No one has established which of these projects is actually installed, so **this matrix is a research and design decision, NOT a compatibility certification**.

## Source ledger (official repositories/docs, inspected 2026-11-22)

1. https://github.com/intellectronica/hermes-chatgpt-extension — README: local stdio MCP in Codex, Node >=22, Hermes desktop WebSocket JSON-RPC and REST, explicit no resend on unknown send.
2. https://github.com/asimons81/hermes-gpt — README and https://github.com/asimons81/hermes-gpt/blob/master/docs/mcp-compatibility.md — ChatGPT MCP options, tool profiles, local HTTP, auth, Operator policy.
3. https://github.com/madpower2000/chatgpt_mcp_bridge — README: 4 tools, local job management, SQLite state.
4. https://github.com/Dworr21/chatgpt-bridge — README/DEVELOPMENT: Chrome/MV3 + localhost :11557/:11558 ChatGPT Web UI bridge.
5. https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md — diagnostics, capability probing and separate browser side-panel role.
6. https://github.com/NousResearch/hermes-agent — current upstream; independent migration/version compatibility audit needed.
7. https://www.w3.org/TR/trace-context/ ; https://opentelemetry.io/docs/specs/semconv/gen-ai/ ; https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/ .

**Version and trust caveat:** Public READMEs can describe features absent from installed artifacts or the older fork. Exact version + handshake + negative-path execution are required to promote a documented feature to a verified fact.
