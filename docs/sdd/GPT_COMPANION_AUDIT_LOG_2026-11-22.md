# Hermes GPT Companion — журнал причин, исправлений и интеграционных блокировок

**Дата:** 2026-11-22 (UTC); **автор анализа:** независимый GPT Companion reviewer; **ветка:** fix/gpt-companion-terminal-causality-20261122-r01; **родитель:** PR #12, head при ответвлении 586a3e5436289f9c56ad69eefb53893ed11eff67.

**Никакой непрерывный сервис здесь не запущен.** Ни одна запись этого журнала не доказывает жизнеспособность локального Windows/Chrome/ChatGPT. Тесты добавлены, но до проверки exact-head CI не считаются пройденными. Записи ниже — audit trail, не runtime event log.

## 1. Evidence ledger

| ID | Статус | Что подтверждено | Причина / гипотеза | Исправление / следующий шаг |
| --- | --- | --- | --- | --- |
| H-001 | BLOCKED | Local_WorkSpace list_workspaces → Session terminated; temp_folder_readonly list_workspaces → MCP SSE 429 | Соединение/прокси/ограничение провайдера; точная причина без server logs неизвестна | операторский doctor/health/reconnect, не сообщать про синхронизацию Obsidian или live telemetry |
| H-002 | CONFIRMED | В GitHub открыты draft PR #1–#12, несколько GPT bridge и observer пересекаются | Авторы веток параллельно разрабатывают competing handlers/journals | владелец интеграции должен выбрать один canonical adapter и один lifecycle control plane; не auto-merge |
| H-003 | CONFIRMED → PATCHED | PR #12 journal.py выбирал по max sequence terminal event, включая worker.stopped | lifecycle shutdown ошибочно перекрывал reported failure/completion | outcome report precedence; tests для failure+stop и completion+stop |
| H-004 | CONFIRMED → PATCHED | completed+failed в одной попытке и одном source не считались конфликтом | не определён exclusive terminal outcome invariant | TRACE_INCOMPLETE и CONFLICTING_OUTCOME_REPORTS; test в обоих порядках |
| H-005 | CONFIRMED → PATCHED | conflict без sequence gap выдавал FETCH_MISSING_EVENTS | смешаны два класса восстановительных действий | RECONCILE_CONFLICTING_EVENTS, distinct diagnostic flags, regression tests |
| H-006 | CONFIRMED → PATCHED | отрицательный delta(now,received_at) clamp-ился к 0, создавая ложную свежесть | observer wall clock rollback | CLOCK_SKEW_DETECTED, CLOCK_REGRESSION; запрет сделать вывод о liveness |
| H-007 | DESIGN GAP | Caller supplied event envelopes в PR #12 не проходят authentication/proof | untrusted producer может соврать об event outcome | signed ingress, authn/authz, replay protection, allowlist, trusted ledger verifier до production |
| H-008 | DESIGN GAP | Offline observer и API bridge не привязаны к текущему installed Hermes/Chrome | старый fork main 2026-04-01 и новый upstream могут иметь разные hooks | version-pinned handshake, shadow mode, Windows/WSL integration verification |
| H-009 | DESIGN GAP | Диагностические "acknowledged"/"not_executed" — untrusted hints | ошибочное чтение empty unresolved_effects как safe retry | UI и SDK явно запрещают recovery without independent receipt and ledger authorization |
| H-010 | OPEN | Локальный SQLite observer не имеет real throughput baseline, retention, backups/restore evidence | нагрузка 30–100 workers неизвестна | chaos / performance suite + baseline + production readiness gates |
| H-011 | OPEN | PR #12 CI на исходном 586a3e5: Tests и Nix были in_progress, Supply Chain Audit success, Docker skipped | нельзя называть исходный HEAD fully green | проверить latest PR head SHA после любых изменений и все обязательные jobs |
| H-012 | OPEN | Source review подтвердил два класса causal bugs; собраны отдельные тесты в новой ветке | тесты ещё не запускались в изолированном host checkout | GitHub Actions exact-head и независимый reviewer, затем amend если fail |

## 2. Incident analysis template (append, never rewrite)

- incident_id, observed_utc, environment/build_sha, project/task/run/attempt, source identity and trust level;
- stage before stop, event_id/sequence/action_id (opaque), last independently verified evidence;
- category: CONFIRMED / HYPOTHESIS / UNKNOWN, causal explanation, falsification experiment;
- impact, data retention/privacy check, side effects in unknown state, current owner and fencing;
- fix commit + tests + exact CI run URL + rollout gate + rollback action;
- links to related ADR/PRs; not freeform raw logs, cookie/prompt text or tokens.

## 3. Parallel agent governance

Every new agent must first read the current PR list and exact HEAD of its assigned base. Do not claim a path that is actively owned by another branch. Record the intended touched paths, design alternatives, owner, initial SHA and dependency PR. Code reviews must validate external artifacts directly; a nested agent's prose is not independent proof. A review result is stateful: if head SHA moves, the review evidence becomes stale.

Selected operational path: (1) fix proof and classification, (2) converge duplicate PRs, (3) build version-pinned observer hooks, (4) prove signed durable event ingestion, (5) supply trusted effects/evidence, (6) only then consider guarded repair. No autonomous production deploy or silent browser control.

## 4. References examined

- https://github.com/Podtverzhdeno/hermes-agent/pull/12
- https://github.com/Podtverzhdeno/hermes-agent/pull/9
- https://github.com/Podtverzhdeno/hermes-agent/pull/6
- https://github.com/Podtverzhdeno/hermes-agent/pull/4
- https://github.com/Podtverzhdeno/hermes-agent/pull/1
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency

## 5. Next audit checkpoints

- Check exact-head tests in this stacked PR on supported Python versions, not a generic green badge.
- Review whether stopping an active effect can ever produce a false resolved status without trusted read-back.
- Verify no dual scheduler or duplicate write path between Autopilot prototype and upstream Kanban.
- Confirm fork binary, actual browser extension and permissions through a restored local observer; shadow-only rollout.
- If a test or PR cannot be checked, log the gap as UNVERIFIED instead of inventing success.

## 6. Concurrent parent reconciliation

At integration checkpoint 85db47caedb87490cee58aab70257c4bdf835ef1, PR #12 has canonical CLOCK_SKEW_DETECTED and PARTIAL_WORKER_OUTAGE, a read-only watch implementation and durable agent mandate. The stacked PR deliberately preserves those changes through a parent-tree-based merge commit. Combined code validation remains PENDING at exact merge SHA; previous CI cannot certify it.


| H-013 | CONFIRMED → DELEGATED | `assess` previously inspected only MAX(attempt); old `tool.effect_reserved` disappeared from latest summary | Re-attempt could make unresolved prior write invisible and encourage blind retry | Candidate scan and six tests removed from PR #17 to avoid overlap; canonical owner PR #23 implements stricter same-source ack checks |

**Evidence gate H-013:** Source patch committed in the stacked branch and regression scenarios authored. Exact-head CI not observed, live effect outcomes unverified. The prior-attempt scan is not yet optimized for long histories. This is a metadata-only diagnosis, not a write-blocking policy engine.

## 7. De-duplication decision (2026-11-22)

PR #23 is selected as **candidate canonical owner** of cross-attempt effects and watcher fingerprinting; it must still pass independent exact-head verification. Our PR #17 previously added a similar but less strict implementation; its code and six overlapping tests were intentionally reverted in later commits. OBS-006 remains a confirmed parent defect until PR #23 is integrated; no operator should interpret this PR as fixing that risk by itself. Related review handoff: https://github.com/Podtverzhdeno/hermes-agent/pull/23 .


## 8. Thirty-PR cross-agent integration checkpoint

A read-only listing of all 30 open PRs and their changed-file names was performed in three batches (10 PRs each) using the GitHub connector, rather than relying only on titles. The listing was **not atomic across PR head mutations**; current HEADs must be rechecked by an integration gate before any merge.

**Observed high-risk exact-path collisions:**

- `gateway/platforms/api_server.py`: PR #4, #5, #6, #11 (4 candidate implementations of preflight/idempotency/SSE logic).
- `gpt_companion/journal.py`: #12, #17, #23 (canonical parent, narrow terminal diagnostics, causal effect implementation).
- `tools/browser_tool.py`: #13 and #15 (CDP redaction/diagnostics vs externally owned browser cleanup).
- `autopilot/ledger.py`: #1 and #10 (duplicate reliability/ledger work).
- `gateway/gpt_bridge_event_audit.py`: #4 and #30 (competing audit behavior).
- `pyproject.toml`: #1, #9, #12, #13 (package metadata/dependency changes).
- `gpt_companion/watch.py`: #12 and #23; `tests/gpt_companion/test_watch.py`: #12 and #23.
- `gpt_companion/README.md`: #12 and #17; `docs/sdd/GPT_COMPANION_SDD.md`: #12, #17, #23; our audit log: #17 and #23.
- Additional exact overlaps observed in `tests/gateway/test_api_server.py` (#4/#6), `tests/autopilot/test_ledger.py` (#1/#10), `tests/gateway/test_gpt_bridge_event_audit.py` (#4/#30), and `docs/sdd/HERMES_GPT_EXTENSION_COMPONENT_CONTRACT.md` (#4/#30).

This yields **at least 15 colliding exact paths in the sampled inventory**, excluding the larger problem of semantically competing observer and PR-review implementations with *different* filenames. Proposed queue: canonical lifecycle/effects → gateway idempotency → browser ownership → one observer contract → exact-HEAD verifier → optional UI. No automatic merging of drafts.

## 9. CI evidence: do not confuse passing jobs with a passing release

- Exact SHA `8636373446505a5c21d6736fbaa5499000c62bb4`: targeted [GitHub Actions run 45014924959](https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45014924959) completed **success** in both isolated Python 3.11 and 3.13 jobs, per GitHub workflow-run and job metadata.
- Later code/SDD/workflow commits invalidate this as **exact-current-HEAD** evidence. A dedicated workflow on every push to our stacked branch was installed, with no real API keys and tests constrained to `tests/gpt_companion`. Earlier runs were cancelled by newer commits; cancelled ≠ failed tests nor a clean release.
- Parent PR #12 and safety PR #23 have their own workflows, with head SHAs and statuses changing independently; any green status must be matched to the branch's currently pinned SHA, not a prior code revision.
- GitHub checks alone cannot prove runtime integration, installed Chrome permissions, truthful producer identity, provider effects, or local Windows/Obsidian synchronization.

## 10. Reviewed independent constraints

Official Hermes Observer Hooks are **fail-open** and can surface sanitized provider/tool metadata but do not act as a durable external effect authority: https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks . Upstream Kanban worker lanes already own task lifecycle and review transitions: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes . Browser companion's profile/version/consent capability boundary: https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md . OpenAI API background response ID and signed webhook lifecycle are separate from ChatGPT web UI: https://developers.openai.com/api/docs/guides/background and https://developers.openai.com/api/docs/guides/webhooks .

All of these are **reference contracts**, not evidence that the user's local installed Hermes or browser already exposes them.


| H-014 | CONFIRMED → PATCHED | Journal `missing=sum(max(seq)-len)` counted an unseen source prefix `1..49` as 49 proven holes when first observed seq was 50 | In multi-source or late-attach monitoring, coverage misinformation can cause false gap alarms and incorrect replay operator advice | PR #17 switches to internal `max-min+1-count` + separate unverified-prefix flag and action, 5 regression tests; needs exact-head CI |

**H-014 evidence limits:** no trusted producer cursor or source incarnation is currently available; `unverified_prefix_sources` is a **conservative uncertainty marker**, not a verified missing sequence count. Parent watcher _fingerprint currently omits prefix list, and the signed checkpoint remains an unimplemented release gate. This change is offline only.


## 11. Subsequent concrete findings and source fixes

| ID | State | Evidence (source) | Failure mode | Change / gate |
| --- | --- | --- | --- | --- |
| H-015 / OBS-010 | CONFIRMED → PATCHED | `EventJournal.assess` read `MAX(attempt)` and rows via two SQLite autocommit SELECTs | concurrent ingestion can create a read without a stable point-in-time snapshot | one correlated SELECT; 2 deterministic source-contract tests; not cross-database atomicity |
| H-016 / OBS-011 | CONFIRMED → PATCHED | `progress_receipts` counted `worker.started` and `llm.request_started` as progress | agent repeatedly starting tasks but never finishing could avoid `ALIVE_NO_PROGRESS` indefinitely | only completed-stage event kinds refresh progress, 4 tests with mutable clock |
| H-017 / API-001 | CONFIRMED DRAFT DEFECT | PR #4 keyed `stream=true` path starts `_run_agent` before nonstream-only idempotency check | duplicate keyed streaming requests can be dispatched without a guard | advisory comment PR #4, propose PR #11 safe preflight & negative test; do not change peer handler |
| H-018 / API-002 | CONFIRMED DRAFT DEFECT | PR #5 `IdempotencyCache` removes `_inflight` key on exception; test explicitly expects second invocation | throw after committed effect, then retry may repeat same write | advisory comment PR #5; sticky unknown-effect tombstone & external readback, no blind retry |
| H-019 / API-003 | CONDITIONAL DESIGN RISK | PR #5 cache identity lacks trusted principal; only raw key+endpoint, fingerprint body+session | cross-principal result alias if multiple authenticated principals use one adapter | owner must establish supported auth topology or bind principal; security regression test |

**No production incidents are claimed.** The reviewed gateway PRs are draft proposals; neither source defect proves a successful external duplicate. The source defects do establish that the proposed API contract is unsafe to call "exactly once" without gateway-side reconciliation. At this audit no durable trusted effect coordinator or live browser client was observed.

## 12. Evidence from engineering standards

- SQLite [Isolation](https://www.sqlite.org/isolation.html) verifies transaction-scoped WAL snapshots; one correlated SELECT avoids torn MAX(attempt)/rows access.
- [OpenTelemetry GenAI harness + Weaver experiment, 2026-11-12](https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/) documents why cross-model self-review sometimes missed invalid semantic conventions; deterministic registry validation is needed.
- [Temporal Activities](https://docs.temporal.io/activities) explicitly recommends idempotent external actions because retries are normal. This is an external design comparison, not a claim that Hermes uses Temporal.

**Additional metadata test:** 30 interleaved producer streams, each sequence 1–3, then source 7 jumps to 5; all other producers must not hide its internal gap. This only simulates interleaved events, not 30 simultaneously executing operating-system agents.

**Outstanding release checks:** current exact-head isolated Python 3.11/3.13 jobs, full repo CI on parent+child merged SHA, parent and PR #23 ownership convergence, actual Windows extension source/manifest and trusted ingress health. No code is deployed.
