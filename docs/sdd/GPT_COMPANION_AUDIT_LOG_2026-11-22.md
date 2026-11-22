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
| H-006 | CONFIRMED → PATCHED | отрицательный delta(now,received_at) clamp-ился к 0, создавая ложную свежесть | observer wall clock rollback | CLOCK_ANOMALY, CLOCK_REGRESSION; запрет сделать вывод о liveness |
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
