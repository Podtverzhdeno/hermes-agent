# SDD decision gate — ranked Hermes × GPT improvements under 30+ agents

Date: 2026-11-22. Status: **qualitative engineering judgment, not measured production ROI, not autonomous merge or deployment**. Read alongside `EXTENSION_CAUSAL_INCIDENT_PROTOCOL_2026-11-22.md` and the PR integration ADR.

## 1. Why an idea score alone is insufficient

Some changes are **hard safety prerequisites** regardless of attractiveness: do not replay uncertain external writes; do not kill a user's externally attached CDP browser; do not leak prompts or secrets through diagnostics; do not mark a task done from the agent's self-report; do not create two authoritative schedulers or merge conflicting API contracts. A low implementation-feasibility score does not justify violating these gates. Unknown host/extension identity means live/browser integration stays blocked, not just lower priority.

The remaining **ordinal** scores below are recorded as transparent *assumptions* for prioritization, not measurements. Ratings are 0–5 for each criterion: **S** safety/reduction of wrong outcomes; **E** source evidence confidence; **M** value under 30+ agents; **F** feasibility in the actual fork (5 easiest, 0 impossible); **T** objective testability; **C** low incremental operating/maintenance cost; **P** privacy preservation. Higher always means more desirable. Score = Σ(weight × rating) / 100; full-scale maximum 5.0. Subjective ratings are revised as evidence arrives; they must never be represented as an achieved production score or “10/10”.

Baseline weights: S 30%, E 20%, M 15%, F 10%, T 10%, C 5%, P 10%. Sum = 100%. Two sensitivity analyses reweight priorities:
- Safety-heavy: S 45%, E 10%, M 15%, F 5%, T 10%, C 5%, P 10%.
- Evidence-heavy: S 20%, E 30%, M 20%, F 10%, T 10%, C 5%, P 5%.

## 2. Decision matrix (ratings in S/E/M/F/T/C/P order)

| Candidate | Scores /5 | Base | Safety-heavy | Evidence-heavy | Evidence/constraint |
|---|---|---:|---:|---:|---|
| Preserve original run ID on idempotent replay | 5/5/5/4/5/4/5 | **4.85** | **4.90** | **4.85** | P0 source bug in PR #4; user-visible misleading causality; owning PR needs regression |
| Capability-negotiated native Runs API / SSE | 5/5/5/3/5/4/5 | **4.75** | **4.85** | **4.75** | Verified modern upstream; current April fork/installed extension not verified; 24h key ledger, 5min event buffer, authoritative run status |
| Read-only PR collision and stacked-SHA scanner | 4/5/5/4/5/4/5 | **4.55** | **4.45** | **4.65** | PR #22 guard, synthetic tests and atomic report bundle receipts; 3+ rival scanners; full integration unverified |
| Safe externally-owned CDP detach + redaction | 5/5/4/3/4/3/5 | **4.45** | **4.55** | **4.40** | Main source logs raw CDP endpoint and can close attached session; #13/#15 compete |
| One authenticated read-only event schema | 5/4/5/3/4/3/4 | **4.30** | **4.50** | **4.25** | Multiple observers; authentication/retention contract not yet chosen |
| Effect reservation, STOP fencing, unknown quarantine | 5/4/5/2/4/2/5 | **4.25** | **4.50** | **4.15** | Safety must-have, but privileged gateway + external receipts not implemented |
| Canonical upstream Kanban lifecycle | 5/3/5/2/3/2/5 | **3.95** | **4.30** | **3.75** | Upstream source-backed; April fork migration/Windows data risk high |
| Shared provider quotas and queue fairness | 4/3/5/3/4/4/4 | **3.85** | **4.00** | **3.80** | Needs rate-limit data, agent workload budgets and authoritative admission |
| Causal incident timeline UI | 4/3/4/3/4/3/4 | **3.65** | **3.80** | **3.55** | Useful only after reliable event sources; do not infer missing model thoughts |
| Blind automatic retries after timeout | 0/2/3/4/3/5/1 | 1.90 | 1.50 | 2.20 | **REJECT:** violates external effect outcome safety |
| Persist raw prompt/DOM/URL/tool payloads in logs | 1/3/4/4/3/5/0 | 2.45 | 2.10 | 2.85 | **REJECT:** privacy/secret exposure; use typed allowlisted metadata |

All arithmetic derives from the seven explicit ordinal inputs above. Small differences inside the same 0–5 interval do not establish significant engineering superiority; evidence labels and safety dependencies decide.

## 3. Dependency-based release ordering (not simple descending score)

**P0a, merge/integration correctness (deliverable already drafted):** choose ONE read-only PR scanner (#14 vs #18 vs #22/#24); use fork-qualified ancestry and rename-source checks, exact SHA required-check policy and timestamped report. Never merge three scanners because they all look “green”. PR #22's checker is not active on main until reviewed and merged. The 30-agent control plane must have one integration owner.

**P0b, API and native Runs capability lane:** test `GET /v1/capabilities` on a separate Windows canary and prefer the documented read-only `GET /v1/runs/{id}` + SSE observer when supported; no guessed internal ChatGPT DOM. Runs key retention is 24h, SSE unconsumed buffer about 5min, and `resolve-unknown` is authority-scoped and does not prove absence of remote tool effects. Single API integrator reconciles #4/#5/#6/#11. Preserve one canonical `operation_id/run_id` across same-key retries; track each `request_id` separately. Reject or explicitly implement keyed streaming before worker dispatch. Distinguish transport completed from run, tool and independently verified artifact. Without this, an observer can draw a wrong causal graph.

**P0c, browser ownership:** one browser integrator reconciles #13/#15. Neither agent-browser close nor daemon PID kill should terminate externally owned CDP. Redact URL and error paths; prove this in isolated Windows browser tests.

**P0d, durable effect safety:** implement trusted gateway reservation/fencing/reconciliation and STOP revocation before unattended write retries. A timeout followed by unknown result is not retryable merely because the caller has a key.

**P1, canonical event observer:** select one producer-authenticated schema and ONE read-only projection after the API/Browser authority decisions; project explicit incomplete/gap states, no raw event data logging. The public extension's durable session/`unknown` queue behavior and scoped consent are reusable only if local version and mode match.

**P1, upstream migration canary:** a separate pinned working copy tests whether the old Hermes fork's semantics can move to newer Kanban/gateway. Never replace a Windows working install until rollback is proven.

**P2, operator productivity:** timeline UI, incident dedupe, global budget/fairness and targeted recovery suggestions. Start only once root-cause evidence is authenticated; otherwise these make wrong conclusions faster.

## 4. Stop-conditions, review ownership and evidence needed for score changes

For every idea, require a specific proof:
- Run ID replay: two same-key requests, one worker invocation, original `run_id` in both responses, two distinct transport attempt IDs, no duplicated `completed` operation event.
- Integration scanner: 30 agents/435 pair conflicts, 100 disjoint branches, 101+ explicitly incomplete, renamed-old-path and fork same-branch collision tests, Windows casefold and reserved-device/invalid-character path checks; robust current-head PR listing; exact named required CI at final SHA independent of scanner.
- CDP safe detach: external Chrome/Edge stays alive in all close/error/timeout routes; normal owned session closes; no secrets across logs/output; negative Windows tests.
- Effect gateway: crash at each reservation/dispatched/receipt boundary; unknown quarantined; stale fence+STOP denied at privileged effect boundary; destination read-back before uncertain retry.
- Observer: authenticated unknown-producer rejection, per-producer seq gaps, late event counterexample, privacy allowlist/adversarial injected prompt tests; no worker self-verification.
- Upstream canary: data and event migrations, profiles/role permissions, queue restart and rollback, exact Windows/WSL test.
- UI/budget: after a real workload baseline, demonstrate measurable diagnosis time, stale evidence rate, fairness/starvation and incident false classification.

**For any failing proof, revise the idea's feasibility/evidence rating downward and explicitly block deployment.** Do not hide fail states behind model confidence wording. The independent reviewer is separate from the change author and from the event source.

## 5. Current evidence log and calibrated confidence

- 2026-11-22: Source audit found dozens of draft PRs, competing observer APIs and duplicated scanners. P0 code-review comments posted on PR #4 (operation vs transport run ID) and PR #13/#15 (attached CDP cleanup and secret logging); convergence comment on PR #18.
- PR #22: offline Python tests expanded from 19 to 26, including rename old/new names and 30/100 worker metadata. Test success is **scoped to test commit**, not release readiness. Whole-project Tests previously failed 28 unrelated-looking cases; baseline A/B not yet executed; no proof every failure is pre-existing.
- Actual installed GPT browser extension is **NOT OBSERVED**. Scoped Local_WorkSpace connection exists but root list does not include Hermes/GPT source; no current browser monitoring or local file changes.
- Upstream Hermes latest observed release 2026-11-20 (v0.23.3) vs fork main baseline from 2026-04-01. A huge diff cannot replace a canary.
- GitHub issues are disabled in this fork (API 410), so decisions remain in SDD and draft PR review comments, not an invented issue tracker.

## 6. References

Fork PRs: https://github.com/Podtverzhdeno/hermes-agent/pulls ; official runtime docs: https://github.com/NousResearch/hermes-agent/tree/main/website/docs/user-guide/features ; public browser extension: https://github.com/abundantbeing/hermes-browser-extension ; state-machine SDD in the adjacent file; W3C Trace Context https://www.w3.org/TR/trace-context-1/ ; OpenTelemetry https://opentelemetry.io/docs/specs/semconv/gen-ai/ .
