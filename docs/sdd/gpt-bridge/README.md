# Hermes × GPT — SDD integration hub for many collaborating agents

**Last evidence review:** 2026-11-22. **Status:** draft, read-only findings, no automatic production changes. **Runtime owner:** TBD / requires approval. **Guard worktree:** PR #22 (not merge-ready). **Integration preference:** use an authenticated read-only ChatGPT MCP plugin over a Hermes-side durable Runs/gateway monitor when the installed version advertises compatible capabilities; browser/CDP is a separate permissioned control lane, not the source of run truth. Neither plugin nor scheduled observer is currently deployed.

**Important:** This is a durable project instruction hub, **not** a replacement for system instructions, user consent, root `AGENTS.md`, upstream Hermes lifecycle or a live monitoring daemon.

## Mission and one-hour-plus quality standard

This is **a hard distributed-systems project**: no agent may pronounce it “done” just because a standalone script or happy-path request succeeds. The deliverable is a causal explanation of each stage, explicit unknown outcomes after crashes, safe recovery from stop reasons, exact-SHA proof and independent reviewers under dozens of concurrent agents. Prefer high-quality authoritative sources and source-level reproductions to unverified quantity claims. No access to a model's hidden reasoning is assumed.

**Required reading, ordered:**
1. `EXTENSION_CAUSAL_INCIDENT_PROTOCOL_2026-11-22.md` — canonical identities, evidence types, state machines, browser/API modes (including upstream native `/v1/runs`, `/v1/capabilities` and an official-supported scoped ChatGPT MCP plugin path), incident taxonomy and 30-agent chaos cases.
2. `ENGINEERING_DECISION_SCORECARD_2026-11-22.md` — safety gates first; weights and sensitivity behind prioritization.
3. `GUARD_CONVERGENCE_AND_EXTENSION_ADR_2026-11-22.md` — how to converge #14/#18/#22 into ONE integration scanner rather than duplicate monitors.
4. `HERMES_GPT_INTEGRATION_GUARD_SDD_2026-11-22.md` — actual PR #22 read-only scanner behavior, exact limitations, test gates and GitHub Actions mode.
5. Existing root `AGENTS.md` and `CONTRIBUTING.md` — baseline repository development policy; do not edit those broad-scope files without assigned ownership.

## Confirmed baseline and blocked reality

- Fork `Podtverzhdeno/hermes-agent` `main` HEAD `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (2026-04-01); current upstream considerably newer (v0.23.3 release 2026-11-20 observed). Native upstream Runs supports 202 admission, read-only status/SSE, scoped stop/approval/unknown reconciliation; the fork's support is not yet confirmed.
- GitHub PR count was observed increasing from 12 to 22 to 30 during this audit; the number is not a continuous monitor and must be re-read before action.
- Read-only scanner #22 has Python offline regressions and CI; scheduler/scheduled reports cannot run on main until workflow review/merge.
- Full Hermes CI has 28 failures on prior PR22 candidate; no `main` baseline runs were returned by GitHub API at inspection. Do not suppress with live API keys or attribute without A/B comparison.
- Local MCP connection later returned `shelter` and read-only D: workspace roots, but neither included the actual installed Hermes/GPT extension. **No running browser, user-host version, native bridge or private GPT session was read or changed.**
- Repo GitHub Issues disabled (HTTP 410). Coordination happens in SDD/PR comments until another **explicitly approved** durable project tracker exists.

## Golden questions every agent's journal must answer

| Operator question | Mandatory evidence | Invalid shortcut |
|---|---|---|
| What is executing? | Authenticated task/run/attempt and lease/fence | Browser open tab or model text |
| Where did it stop? | Last durable stage-specific receipt, collector coverage timestamp and gap indication | Generic timeout message |
| Why did it stop? | Confirmed cause with trusted provenance or explicit hypothesis/unknown | Model-generated guess |
| Did it mutate something externally? | Effect reservation, result receipt or destination reconciliation | HTTP connection lost/returned |
| Is retry safe? | Effect certainty and provider-enforced idempotency + original operation key | Re-sending on 429/timeout |
| Can agent A overwrite agent B? | Exact owned paths/worktree branch, conflict scanner, integrator role | Shared checkout with optimism alone |
| Is it complete? | Independent verifier at exact artifact SHA and all named required checks | “Done” or optional check green |
| Does STOP work? | Gateway revocation generation and fenced effect denial, including cron descendants | UI button closing |
| Is monitoring healthy? | Event inbox seq, authenticated source and fresh collection | Schedule configured in unmerged PR |

## Agent operating contract

**Before any edit:** enumerate exact PR HEAD, base SHA, renamed paths and owner; read newest relevant SDD and existing parallel PR diff. Work in a separate branch/worktree. If another agent owns the same privileged module or critical path, record a review proposal/comment; do not commit on top of its moving branch. Document assumptions and unknowns and consult source-level evidence.

**During an edit:** keep an append-style change log in own PR/SDD: date, source commit SHA, hypothesis, reproduction, code touched, expected failure mode, tests run, failed scenarios, rollback. Verify initial permissions and if disabled, do not bypass. If local monitoring source is unavailable, label `NOT_OBSERVED`; never imply continuous tracking.

**Before merging:** test at the exact proposed HEAD, inspect full required named checks and all dependent PR bases, reconcile renamed/old paths, and obtain independent reviewer approval. Cross-project impact requires explicit owner sign-off. Read-only GitHub guard does not authorize auto-merge, model/tool retries, filesystem writes or browser operations.

**Before autonomous recovery:** classify effect certainty. `OUTCOME_UNKNOWN` is a STOP/QUARANTINE, not an invitation to retry. Do not bypass approval, user consent, or STOP generation. Recovery writer and incident verifier should be independent.

**When context expires:** resume from this hub, exact latest commit, branch SDD and redacted evidence IDs; do not invent memory of live events. Treat work as unfinished until gates demonstrably pass. One chat/session cannot guarantee infinite background monitoring; an approved durable scheduler and observability owner must supply it.

## Lanes, conflicts and ownership

| Lane | Draft PRs / affected code | Enforcement |
|---|---|---|
| REST OpenAI-compatible gateway | #4/#5/#6 and stacked #11, shared `gateway/platforms/api_server.py` | One gateway integrator; original replay run ID; keyed SSE before dispatch; exact-head tests |
| API process-local dedupe | #4/#5 differing in-flight duplicate policy | One canonical fingerprint/expiry contract; process cache is NOT durable effect dedupe |
| Browser/CDP | #13/#15 share `tools/browser_tool.py` | One integrator; attached browser never auto-close; redact all CDP endpoints |
| GPT observer | #8/#9/#12/#16/#21/#25/#26/#30; #17/#23 stacked | One authenticated event schema and read-only projection; no competing scheduler |
| PR integration watch | #14/#18/#22/#24/#27/#28/#29 | Provisional integration base #18; select one canonical read-only scanner only |
| Autopilot | #1; #10 on pinned snapshot base | Upstream Kanban remains candidate single task authority; no second task queue |

The lists are snapshots, not locks or an up-to-date inventory. A separate human-authorized integrator must confirm ownership.

## Read-only guard commands

- Python offline suite: `python -m unittest discover -s tests -p 'test_gpt_pr_integration_guard.py' -v`.
- Offline replay: `python scripts/gpt_pr_integration_guard.py --snapshot-in snapshot.json --report-out report.json --markdown-out report.md --strict`.
- Live read-only GitHub scan only in a trusted environment with a scoped read-only GitHub token after workflow promotion: `python scripts/gpt_pr_integration_guard.py --repo Podtverzhdeno/hermes-agent --report-out report.json --snapshot-out snapshot.json`.
- `--strict` returns 2 when blocking metadata collisions exist; malformed/incomplete snapshot returns 3; default scheduled mode is observational and does not automatically stop unrelated PRs.

`collection_status=COMPLETE_METADATA_SNAPSHOT` never implies `runtime_verdict=HEALTHY` or `ci_verdict=PASS`. No privileged program is launched by the scanner.

## Document change log

2026-11-22: Initial audit and PR #22, then 19/19 offline tests at historical SHA. Additional review found moving source repo identity, missing pagination cardinality, rename-source collision, possible Authorization forwarding on urllib redirect, and missing provenance on offline snapshots; schema advanced to v3 and regression suite to 35 scenarios including 30/100 agents, rename aliases, Windows casefold/NFC checkout hazards, reserved device/invalid-character paths, redirect rejection and offline/live differentiation. Added public extension protocol reuse comparison, P0 API replay and CDP ownership code-review findings, broad CI 28-failure forensic groups and safety-gated idea ranking. **No unmerged main workflow or local GPT monitor has become active from these commits.**
