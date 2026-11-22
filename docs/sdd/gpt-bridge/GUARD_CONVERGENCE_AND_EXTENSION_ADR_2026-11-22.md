# ADR-016 — Converge GPT integration guardians and instrument a real extension without inventing state

Date: 2026-11-22. Status: **integration decision proposal, not merged or deployed**. Authoritative repo: `Podtverzhdeno/hermes-agent`. Original fork baseline `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (2026-04-01).

## Decision first

**Do not operate PR #14, #18 and #22 as independent long-lived “integration guardians.”** They diagnose overlapping GitHub PR risks but are not independent facts about live GPT workers. Their capabilities should be integrated into **one** read-only scanner with a single canonical JSON evidence format. A different owner must verify its results before merging. Current **provisional** base candidate is PR #18, because it already checks the documented GitHub changed-file cardinality, reads exact-SHA check metadata and persists metadata-only audit snapshots. It is not accepted yet: its CI coverage semantics and fork-aware ancestry require strengthening first. PR #14 adds full-branch capability discovery and Python 3.11–3.13 tests; PR #22 adds a global second-pass branch-head check, scheduled report artifacts, source-repository-aware ancestry and explicit guard duplication. No attempt to merge all three modules or SQLite logs.

## A. Evidence and comparative judgment

| Property | #14 `hermes_gpt_coordination_audit.py` | #18 `gpt_integration_guard.py` | #22 `gpt_pr_integration_guard.py` |
|---|---|---|---|
| PRs on non-main bases | **Omit** in primary PR scan (`if base != main: continue`); separately enumerates branches | Includes all open PRs and their base | Includes all open PRs and their base |
| Additional non-PR branches | Yes: compare immutable base/head SHA, subject to GitHub compare size limits | No | No |
| Changed-file completeness | Bounded pagination; no declared count equality in inspected code | Fetches `changed_files` from detail and compares length | v3 verifies detail count and rename source/destination coverage |
| Source-repository identity | Inspected source stores `origin`; ambiguous parent lineage unresolved | Head ref used without source owner in evaluated ancestry | v3 uses (`repo`, `ref`) compound identities and refuses v2 offline snapshots |
| Race checks | Per-PR fresh detail, branch head re-read | Per-PR detail re-read | Complete PR-list second pass + default HEAD second pass; still not atomic |
| Exact-SHA CI status | Not in output | Reads check runs, but passing available checks != all required checks | Deliberately unverified (no claim) |
| Durable audit history | GitHub artifact after manual workflow | Optional local SQLite WAL append-only snapshots | Scheduled GitHub artifact after default-branch merge (30d configured retention) |
| Workflow | Offline 3-Python-version matrix; live manual | No dedicated workflow in inspected PR | Offline PR test + scheduled/manual read-only report |
| Observer duplication | Capability heuristic | Explicit file set | Expanded family prefixes |
| Recommendation | Borrow branch inventory, failure/retry controls | **Provisional single-scanner integration base** | Borrow global recheck, provenance and scheduled reporting |

**Confidence limits:** This matrix is static source/code inspection, not a benchmark or completed security assessment. Earlier v2 PR #22 CI success covered 19 offline synthetic tests at an older SHA; v3 added rename and 30/100-agent test vectors, so exact latest-head CI evidence must be retrieved before any merge. Editing code after a passing run invalidates its relevance.

### Current concurrent PR landscape (observed after initial snapshot)

At subsequent inspection 22 open draft PRs existed, including #13 GPT extension/CDP diagnostics, #14 coordination guard, #15 externally owned browser-cleanup patch, #16 observer, #17 stacked companion patch, #18 second guard, #19–#20 SDD convergence documents and #21 another observer. This is a **measured governance risk**, not evidence of malicious agents. In particular:

- #4/#5/#6 each changes `gateway/platforms/api_server.py` with distinct retry and SSE contracts; #11 targets #4 but its recorded base SHA was stale relative to #4's current HEAD at inspection.
- #10 was retargeted to `snapshots/autopilot-ledger-6c0d2e-20261122`, not current #1 head. A report that simply compares #10 with #1 without checking its actual base will be wrong.
- #13/#15 both edit `tools/browser_tool.py`; require one browser owner and control/lifecycle regression review.
- #14/#18/#22 implement functionally overlapping integration watchdogs. **A tool that detects duplication must also report its own duplication.**

## B. Full GPT↔Hermes observable lifecycle (target architecture, not implemented)

```text
user-authorized GPT / ChatGPT frontend
   -> adapter handshake / capability grant / session binding
   -> request accepted and assigned canonical task/run/attempt IDs
   -> durable ingress receipt (NOT tool success)
   -> upstream Hermes Kanban worker (single task/lease authority)
   -> model request / stream / tool proposal
   -> independent policy gateway (scope + approval + STOP epoch + fence)
   -> external-effect reservation / provider dispatch / receipt reconciliation
   -> immutable output revision / independent verifier
   -> Kanban review or terminal transition
   -> read-only event projection and incident timeline
```

Every arrow may lose its acknowledgement. A timeout following a write is not proof the write never happened. Operators must see a phase, a trustworthy receipt or missing evidence, a **cause classification with provenance**, the effect's uncertainty state and a safe next action. The model's private internal reasoning is not a data source; no design may imply access to hidden reasoning or to a provider's internal task queue.

### Event envelope (proposed `hermes.bridge.event.v1`)

Required: `event_id`, `producer_id`, `producer_incarnation`, `producer_seq`, `schema_version`, `project_id`, `task_id`, `run_id`, `attempt_id`, `phase`, `reason_code`, `outcome`, `origin_receipt_time` and `collector_received_at`. Conditional: `parent_event_id`, W3C `traceparent`, `span_id`, `operation_id`, `lease_epoch`, `stop_generation`, `artifact_sha`, `provider_receipt_digest`, `budget_reservation_id`.

Trust levels: `reported` (browser/model), `observed` (authenticated transport/gateway), `verified` (trusted independent artifact/check receipt). Do not flatten these into Boolean `done`. Per-producer monotonic sequences detect gaps/replay; cross-producer order requires causal parent IDs, not wall-clock sorting. An ACK from the event inbox must assert durable storage only, not successful tool execution. An authenticated collector verifies producer identity and message signature/MAC over the exact canonical envelope before acceptance. A hash chain alone does not authenticate producers.

Reject arbitrary event payload keys. Never collect prompt/answer bodies, raw DOM, cookies, OAuth tokens, native-messaging secrets, open URLs with embedded credentials, raw tool arguments or stack traces with secrets. Retention should be policy-defined; GDPR/PII review and per-project allowlists are needed before user-data collection.

### Browser/CDP and ChatGPT distinction

Current upstream Hermes documents an OpenAI-compatible API server and a CDP browser attachment path. Its API-server documentation explicitly notes that its previous browser-extension control surface was **removed**. A separate public project `abundantbeing/hermes-browser-extension` has a side panel and opt-in companion plugin. Its `controller-protocol`, `gateway-queue`, `session-delivery-state` and `context-consent` components show reusable identity, unknown-admission recovery and consent mechanisms, but they are **not evidence** that the owner's installed extension is the same project. Local_WorkSpace MCP reconnected, yet advertised roots exclude the Hermes installation/extension path.

Treat the browser as a **transient client**, not a durable task store. Chrome MV3 service workers may be suspended; native messaging may change lifetime behavior but cannot guarantee continuous connectivity after host crash. A user-authorized broker must enforce origin, per-tab and per-task capability grants, nonce/anti-replay, short-lived ownership lease, fencing epoch and explicit revocation. CDP errors and tab detachment are distinct from provider/model failure. If the Chrome tab disconnects, pending external actions remain `UNKNOWN` until reconciled.

Do not suggest bypassing session authentication, scraping hidden prompts, auto-solving access barriers or using undocumented ChatGPT DOM as a stable backend. Prefer supported API interfaces and explicit user-controlled browser attachment. A native/local helper cannot manufacture an authoritative GPT run ID; it must use an ID provided by the actual adapter.

## C. Stop-state decision tree

1. **No accepted request receipt:** classify `INGRESS_UNKNOWN`, never as model failure.
2. **Accepted but no worker execution:** inspect Kanban dispatch, OS worker lifecycle, prompt delivery and token budget; classify `DISPATCH_STALLED` only with a meaningful deadline+evidence.
3. **Model call opened but stream lost:** distinguish auth 401/403, rate limit 429, provider 5xx, client cancellation, parser/protocol error and timeout. Record `STREAM_TERMINATION_UNKNOWN`, not success.
4. **Tool intent proposed but no policy receipt:** `POLICY_UNKNOWN`; no privileged writes.
5. **Effect reserved/sent without receipt:** `EFFECT_OUTCOME_UNKNOWN` has highest priority; **never blindly retry** non-idempotent writes.
6. **Artifact exists but check run SHA differs:** `CI_REVISION_MISMATCH`; run exact-head verification.
7. **Worker claims done without verification evidence:** `AWAITING_INDEPENDENT_VERIFIER`; do not increment verified completion.
8. **Only browser heartbeat is present:** `ALIVE_NO_PROGRESS`; a heartbeat does not reset the progress deadline.
9. **Collector is down or event sequence has gaps:** `OBSERVATION_INCOMPLETE`; never infer worker stopped or succeeded.

Preserve `CONFIRMED`, `PROBABLE` and `UNKNOWN` as separate confidence types; each root-cause label must link to the event and its trusted source.

## D. Agent governance (30–100 agents)

Every work assignment must carry a signed/versioned manifest: exact parent commit SHA, owned paths/capabilities, banned paths, project/task/run/attempt IDs, acceptance artifacts, timeout/compute budget, stop generation and reviewer identity. No two agents have direct write authority to the same critical path simultaneously without a designated integrator. Git worktrees are independent. A separate independent reviewer may only approve checks at the precise final HEAD and never an ancestor; GitHub branch protection/rulesets also need verification, not assumption.

Resource locks are **advisory** until enforced by GitHub branch protections and a privileged gateway. For Obsidian local writes use scoped editor, expected file SHA and conflict journal. Do not switch a public GitHub bot to broad Windows administrator access to “fix” one dead connector. Prevent agent self-approval, recursive repair loops, context-loss false completion and hidden resumption of stopped jobs. Agent-generated bug reports must include minimum reproducer, redacted event IDs, verification revision and rollback.

Fairness must be measured, not guessed: queue age, blocked reason, priority starvation, upstream 429 storms, duplicate work and per-project budget consumption, with global rate limiting and bounded retry budgets.

## E. Release / audit acceptance matrix

| Gate | Measurable condition | Failure disposition |
|---|---|---|
| Event trust | Unauthorized producer, wrong scope and sequence collision rejected in simulated replay | Block integration |
| Effect safety | Crash before/after dispatch and lost provider ACK do not blindly reissue external writes | Block autonomy |
| STOP | No new dispatch/tool writes after authoritative generation revocation, including cron children | Block autonomy |
| PR overlaps | 1/8/30/100 PR synthetic cases; no false “clean” when files/CI metadata missing | Block merge |
| GitHub metadata | Detail changed_files count matches pagination; head/source repo and default ref remain stable | Unknown/incomplete |
| CI exact SHA | All required named test/security checks green on the candidate SHA, not skipped | Block merge |
| Multi-agent | Concurrent writers, stale branch base, deep stacks, duplicate package registrations detected | Hold integration |
| Browser | MV3 restart, tab close, CDP detach/reconnect, wrong tab lease, offline host, copied context | No unapproved control |
| Windows | Actual host/WSL smoke including prompt-delivery and persistent worktree rollback | Block production |
| Diagnostics | Every seeded stop has stable code, evidence chain and conservative recovery | Block unattended repair |

Any displayed `100%` must mean the declared test gate passed for a specific SHA, never a subjective estimate of product maturity. Baseline latency/cost targets should be set after measurements; avoid invented thresholds.

## F. Recorded CI investigation (source-backed, not blanket causation)

A GitHub `Tests` run on the initial PR #22 SHA `47055e026704f648df233277d508cf8af8e33f87` concluded **failure**: runner summary reported **28 failed, 7511 passed, 171 skipped**, in ~152 seconds. Failures included multiple model/streaming fixtures raising `Missing credentials`, one Codex model-string regression and several 30-second file-read timeouts. The new dedicated `GPT PR Integration Watch` offline test workflow at that exact old SHA succeeded. These full-suite failures do **not** establish that the new read-only guard caused them; code change scope does not touch inference or file read paths. An independently controlled baseline run is needed to classify them as pre-existing or introduced.

**Important:** PR #22 was subsequently edited. The old green dedicated workflow and old failed full-suite results no longer certify or condemn the final SHA. Fetch fresh run outcomes for the final SHA before any merge claim.

## G. Explicit next integration actions

- Assign a single merger for #14/#18/#22; no automatic merge of all three. Compare one canonical schema and extract verified features (branch coverage, CI evidence, identity, stable snapshot, periodic artifact report).
- Assign a separate API integrator for #4/#5/#6/#11 and browser integrator for #13/#15; do not reuse the same agent as final reviewer.
- Keep #8/#9/#12/#16/#21 observers observational until a single allowlisted event contract, auth and retention pass tests.
- Inspect actual local extension source only after workspace recovery and explicit permission checks; no claim of live monitoring.
- Before enabling periodic watch on default branch, check exact-head test status, GitHub Actions schedule control and rollback. A draft PR alone does not activate it.

## H. Primary documentation (cross-checked)

GitHub REST PR files limit 3000: https://docs.github.com/en/rest/pulls/pulls  
NousResearch Hermes Kanban worker lane: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban-worker-lanes.md  
Hermes API-server: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md  
Third-party browser extension data flow: https://github.com/abundantbeing/hermes-browser-extension/blob/main/DATA-FLOW.md  
Chrome MV3 worker lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/  
OpenTelemetry GenAI tool execution: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md  
W3C Trace Context: https://www.w3.org/TR/trace-context-1/  

## I. Work log

2026-11-22: Initial scan #1–#12, then #1–#22, later #1–#30; opened draft #22. Found multiple competing guard/observer groups. Self-review found fork identity, missing changed-file cardinality, ambiguous HEAD state, and renamed-source path omission; code advanced to snapshot v3 and added 30/100-agent tests. Removed GitHub Actions checkout credential persistence. Full-suite CI failure analyzed at earlier SHA, with no unsupported root-cause claim. Local MCP later reconnected but only unrelated declared roots; no Windows/Obsidian changes were made.
