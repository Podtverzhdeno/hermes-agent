# SDD: Hermes ↔ GPT Companion — наблюдаемость, восстановление, десятки независимых агентов

**Версия:** proposal 0.1.0 · **Аудит:** 2026-11-22 · **Владелец компонента:** GPT-connector / наблюдаемость · **Режим:** fail closed, read-only prototype

> Документ является инженерной спецификацией, не заявлением о готовности production. Каждое утверждение о реализации, проверке и текущей версии должно иметь отдельное доказательство.

## 0. Проверенное состояние и границы

- Проверен `Podtverzhdeno/hermes-agent`, основная ветка `main`, SHA `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (2026-04-01). Нельзя автоматически считать её актуальным Hermes на ноябрь 2026.
- На момент аудита существуют **отдельные, не слитые с main** ветки `feat/autopilot-durable-ledger-20261122` (`bc66ef436253e552d5b206f5b4d757f0214ed92d`) и `feat/skill-harness-contracts-20261122` (`a361eae6dcc92bf797e30c83bd17999fd0c72f8e`). Первая реализует SQLite lease/fence/effect ledger, вторая — контракты навыков. Не изменять их в обход владельцев.
- У main есть Hermes AIAgent, gateway, ACP и cron. **В main нет подтверждённого отдельного GPT/ChatGPT browser companion**, а публичный Hermes и сторонний `abundantbeing/hermes-browser-extension` развиваются независимо. Проверить выбранную фактически установленную версию и compatibility handshake **до** включения любого интеграционного кода.
- Локальный `Local_WorkSpace` MCP при проверке отвечал `Session terminated`. Поэтому **не проверены** локальные рантаймы, телеметрия браузера, состояние ChatGPT-вкладок, общее хранилище Obsidian. Ни одно локальное изменение не объявляется внесённым.
- Работать через документированные API/SDK/Hermes hooks. Не обходить авторизацию, интерфейсные ограничения, CAPTCHA, ограничения провайдера, платный доступ и человеческое подтверждение. Чтение DOM/ответов ChatGPT не источник истины о результате.

## 1. Проблема, которую решаем

При десятках GPT-агентов теряются события, перепутываются сообщения, завершаются сессии, происходят смены моделей, контекст обрывается, UI перестаёт отвечать, внешний write может завершиться без подтверждения, а следующий агент может повторить действие. «Ответ агента выглядит завершённым» не означает, что задача завершилась; «ответа нет» не означает, что её можно запускать повторно.

**Цель:** для каждой задачи уметь восстановить точную цепочку `intake → admission → claim/lease → preparation → model request → tool proposal → authorization → side effect → receipt → external verification → outcome`, с ответами: что подтверждено, что неизвестно, почему остановилось, что безопасно делать дальше, кто владеет ресурсом и какое доказательство закрывает задачу.

**Не-цели текущего PR:** включить бесконтрольный автозапуск, скрытый контроль ChatGPT, чтение пользовательских сообщений, автоматические внешние изменения, production deploy, самостоятельный merge, «exactly once» для внешних API, доказать доступность локального ПК в offline-среде.

## 2. Выбор архитектуры на основании критериев

Оценка вариантов по критериям 1–5, веса: надёжность 30%, безопасность 30%, наблюдаемость 20%, совместимость 10%, эксплуатация 10%. Общий балл = сумма `вес × оценка / 5`; это **проектная экспертная оценка, а не измеренный бенчмарк**.

| Путь | Над. | Без. | Набл. | Совм. | Экспл. | Итог / 100 | Решение |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Официальные provider API + Hermes observer hooks + централизованный журнал | 5 | 5 | 5 | 4 | 4 | **96** | Основной путь |
| Сторонний browser companion + opt-in сигналы, без DOM как источника статуса | 3 | 3 | 3 | 4 | 3 | **62** | Вспомогательный слой |
| Автоматизация ChatGPT DOM как control plane | 2 | 1 | 2 | 2 | 1 | **32** | Отклонить |
| Скрипты управления вкладками без стойкого task ledger | 1 | 1 | 2 | 3 | 2 | **30** | Отклонить |

**Ключевой выбор:** GPT — один из адаптеров *исполнения*; Hermes/Autopilot — контроллер жизненного цикла; observer journal — отдельный источник диагностических сигналов. Адаптер не присваивает себе полномочия ни утверждения внешних write, ни оценки успешности задачи.

Слой browser companion нужен только для явно разрешённых функций UI и сигналов состояния подключения. Он не подменяет официальный инструментальный контракт GPT/ChatGPT и не получает доступ к неразрешённым данным. Возможность пользоваться подпиской ChatGPT **не означает** наличие API-кредитов или разрешение автоматизировать web UI.

## 3. Целевая архитектура

```text
User / ticket / webhook / timer (authenticated ingress)
      ↓ idempotency key, immutable request contract
AUTOPILOT CONTROL PLANE (tasks + leases + fences + approvals + effect ledger)
      ↓ admission + scoped execution grant (capabilities, TTL, quota)
GPT ADAPTER ─────── Hermes / GPT provider official API / supported plugin hooks
      │                                     │
      │ event envelopes (minimal only)      │ artifacts / receipts
      ▼                                     ▼
OBSERVATION INBOX (SQLite WAL, dedup, seq, hash chain) ──► independent verifier
      │                           │                        │
      ├─► diagnostic state        ├─► alerts                 └─► revision-bound evidence
      └─► incident/runbook       └─► reconcile ticket
                 ↓
        Operator decision / gated repair / next lease
```

### 3.1 Архитектурные границы

- **Task ledger** — единственный источник статуса задач/аренд/разрешений и внешних эффектов; не смешивать с диагностическим event inbox.
- **Diagnostic journal** — принимает лишь не доверенные метаданные событий; опознаёт пропуски и неизвестные эффекты; **не** вызывает инструменты и **не** устанавливает `succeeded`.
- **Verifier** — независимо читает GitHub (точный commit SHA, заключения checks), результат тестов, подтверждённые артефакты и источник разрешений. Речевой ответ GPT не проходит как evidence.
- **API adapter** — осуществляет request_id correlation, token budget, provider call, receipt capture; документированную остановку/продолжение; не обещает гарантированной доступности всех моделей.
- **UI/browser adapter** — подключается только через разрешённую extension surface и capability negotiation. Если capability отсутствует, состояние `UNSUPPORTED`, а не автоматическая попытка обойти интерфейс.

### 3.2 Контракт агента

Обязательные поля work item: `project_id`, `task_id`, `request_key`, `role`, `parent_id`, `dependencies`, `scope`, `input_revision`, `expected_outputs`, `acceptance`, `budget`, `risk_tier`, `approval_policy`, `lease_id`, `fencing_token`, `deadline`, `capabilities`, `artifact_manifest`.

Каждая роль получает уникальный `agent_id`, **не общий** токен доступа, и право менять только свой `resource_key` (ветка/worktree/заданная папка). Контроль A0 не позволяет A0 самостоятельно заверять реализацию A0. Любой агент, включая будущих, наследует один и тот же контракт и правила внешних эффектов.

### 3.3 Состояния по уровню достоверности

- L0 — **не наблюдалось:** нет входного события; подтвердить intake.
- L1 — **наблюдается:** приходят события, но нет подтверждения реальной работоспособности или результата.
- L2 — **остановлено / неизвестно:** потеря heartbeat, stream disconnect, истёк lease, внешнее действие может существовать. Запрещены слепые повторы.
- L3 — **агент сообщил результат:** `run.reported_completed`, требуется независимая проверка.
- L4 — **доказано:** только контрольный слой с подлинными доказательствами и exact revision закрывает `succeeded`.

Нельзя переходить L1→L4 только потому, что stream завершился `200 OK`; нельзя переходить L2→L1 с повторной попыткой неповторимого внешнего действия.

## 4. Версионируемый контракт событий

Envelope V1 (без промптов, текстов сообщений, персональных данных, секретов, tool args):

```json
{"schema_version":1,"event_id":"evt-01","source":"gpt-adapter","run_id":"run-42","attempt":1,"sequence":1,"kind":"worker.started","trace_id":"trace-42","subject_revision":"gitsha"}
```

Поддержанные `kind` в прототипе: `run.accepted`, `worker.started`, `worker.heartbeat`, `worker.progress`, `llm.request_started`, `llm.response_received`, `tool.effect_reserved`, `tool.effect_acknowledged`, `tool.effect_not_executed`, `approval.required`, `approval.resolved`, `run.reported_completed`, `run.reported_failed`, `worker.stopped`. Для эффекта и approval обязателен непрозрачный `action_id`; ошибка кодируется только нормализованным `reason_code`.

Свойства:

1. `event_id` глобально уникален; повтор идентичного тела — идемпотентен, повтор с другим телом — конфликт.
2. `(source,run_id,attempt,sequence)` уникален; номера монотонны у одного эмиттера. Пропуск в потоке — `TRACE_INCOMPLETE`.
3. Источник времени для watchdog — серверный `received_at`; **не** клиентские часы. Даже свежий receipt запоздалого события не равен доказательству живого процесса.
4. Порядок поступления не равен порядку выполнения. По одной последовательности одного эмиттера можно проверить causality; при конкурирующих источниках без явной корреляции переход считается неопределённым.
5. Журнал только дополняется, WAL + `BEGIN IMMEDIATE`, hash chain фиксирует случайное повреждение, но **без внешнего якоря и защищённого хранилища не защищает от переписывания злоумышленником**.
6. Клиентские поля `source`, `run_id`, `reason_code` сами по себе не удостоверяют личность; emitter auth/allowlist, limit и replay protection обязаны стоять на входе.
7. Producer: локальный bounded outbox, fsync перед ack, повтор до подтверждения, по достижении quota — backpressure + `OBSERVABILITY_DEGRADED`; никогда не блокировать критическую отмену агента.
8. Consumer: signature verification до парсинга внешних webhook; дедуп по authenticated delivery ID; 2xx только после durable inbox commit; reconciliation polling после разрыва.

Внешнее действие требует **в другом, доверенном ledger** `approval → reserve_effect(digest) → invoke(idempotency key) → provider receipt → reconcile/ack`. Telemetry `tool.effect_acknowledged` сама по себе такого доказательства не заменяет.

## 5. Диагностика: что означает остановка

Два независимых таймера: `last_received` (поступление телеметрии) и `last_progress` (продвижение, а не heartbeat). Лимиты настраиваются под операции и бюджеты; 120/300 секунд в прототипе — лишь проверочные значения, не production SLA. Нужен также **источник проверки lease и PID/process status**: нельзя выводить «процесс жив» только из пришедшего события.

| Симптом | Возможные корни | Проверка | Консервативное действие |
| --- | --- | --- | --- |
| `NOT_OBSERVED` | не было intake / ingress disconnected | запись ingress, auth и idempotency key | проверить вход; не создавать повтор вслепую |
| `TRACE_INCOMPLETE` | потеря/перестановка событий, рестарт outbox, multi-source conflict | source seq / replay cursor / durable outbox | запросить пропуски; не считать outcome доказанным |
| `ALIVE_NO_PROGRESS` | deadlock, модель думает, tool ожидает, остановка из-за бюджета | конкретный этап + per-stage timeout + tool heartbeat | снять дамп состояния, сверить budgets |
| `WORKER_UNRESPONSIVE` | процесс погиб, сеть отсутствует, PC спит | OS supervisor, lease, server reachability | сделать диагностику; перед переclaim сверить эффекты |
| `EFFECT_IN_FLIGHT` | внешний write ещё идёт | action_id, provider idempotency key, receipt | мониторить, не вызывать повтор |
| `NEEDS_RECONCILIATION` | запись ушла, ack потерян; crash после reservation | прямое чтение внешнего объекта / receipt | reconciliation, human fallback |
| `WAITING_APPROVAL` | человеку требуется точное разрешение | digest/action/TTL/reviewer identity | запросить утверждение; истёкший approval = отказ |
| `AWAITING_VERIFICATION` | агент ответил «готово» | CI и артефакты на **том же SHA** | проверить независимо |
| `REPORTED_FAILED` | 401/403/429/5xx/schema/context/budget | нормализованный reason_code + provider receipt | классифицировать; не универсальный retry |
| `STOPPED_UNCONFIRMED` | остановлена только вкладка/stream | task ledger + worker supervisor | сверить реальное состояние |

**Классы отказов:**

- `AUTH_DENIED`/`PERMISSION_DENIED`: проверить scoping и учётные данные, без автоматического расширения прав.
- `RATE_LIMITED`/`QUOTA_EXCEEDED`: `Retry-After`, глобальный rate/budget; очередь и jitter, без агрессивного многократного запроса.
- `UPSTREAM_TIMEOUT`/`STREAM_LOST`: может существовать provider response; сначала получить `response_id`/webhook/read-back.
- `TOOL_SCHEMA_INVALID`: зафиксировать версию входного контракта и изменить адаптер, не переписывать исходную задачу.
- `CONTEXT_EXHAUSTED`: сохранять task spec, progress manifest, checkpoint; новый агент не восстанавливает внутренние скрытые рассуждения.
- `BROWSER_TAB_CLOSED`: UI не работает ≠ задача упала. Восстановить только поддержанный клиент, источник результата — gateway/provider.
- `CI_FAILED`: воспроизвести лог конкретной job/check на exact SHA; отличить flaky test от продуктовой ошибки.
- `LEASE_EXPIRED`: новый агент получает новый fence; старому запрещён commit, write и `succeeded`.
- `BUDGET_EXCEEDED`: остановить выдачу новых вызовов, не «продлить» таймер за счёт другого агента.

## 6. Параллельная работа 10–100 агентов

Нужен coordinator, который обеспечивает **per-project concurrency cap**, общий бюджет родительского DAG, fair admission (старение ожидающих задач), отдельно quotas на GPT API, GitHub writes и Local MCP, circuit breakers по провайдеру. Пример конфигурации для нагрузочных испытаний (не production default): 30 workers, 6 per project, 2 external writes per project, global 60 requests/min; значения подбираются по метрикам и тарифам.

Разделить уровни конфликтов: `task lease`, `resource_lock(repository:path or Obsidian:note)`, `provider_action_id`. GitHub write — CAS по SHA; безопасная локальная работа — отдельный worktree; PR — только после проверки владения и head. Обмен между агентами — через versioned artifact manifest, не через взаимную пересылку длинного чата. Изменения SDD — ADR с owner, статусом, конкурирующими предложениями и измеримым критерием принятия.

При замене агента новый worker получает `goal + state snapshot + known proof + unresolved effects + permitted tools`, а не «продолжай с того же места». Отмена связанного DAG распространяется дочерним задачам, но не скрывает незавершённые external effects. Запрещать одновременно две реализации одного и того же пути/ресурса даже при разных ролях.

### Вопрос о десятках агентов-контролёров

Много проверяющих агентов ≠ много источников истины. Агенты могут параллельно составлять гипотезы и эксперименты, но только единый журнал с fencing/ownership позволяет коммитить их решения. Ревью одного агента не считается независимым, если он читает только отчёт другого: нужна прямая проверка evidence.

## 7. Приоритеты улучшений / ADR

Матрица баллов — инженерная гипотеза; `P` определяется как severity × частота × необнаруживаемость с проверкой реального incident-rate после запуска.

| ID | Идея | Польза | Риск / издержки | Решение |
| --- | --- | --- | --- | --- |
| ADR-001 | Отдельный event inbox и causal-gap detector | атомарная диагностика и replay | двойное хранилище, миграции | **Implement P0** (текущий прототип) |
| ADR-002 | Effect reservations только в Autopilot ledger | не повторять неизвестный write | требуется доверенный gateway | **Integrate P0** после review другой ветки |
| ADR-003 | Provider API + Hermes native hooks | контроль результатов без ChatGPT DOM | version skew fork/upstream | **Design P0**, adapter после compatibility check |
| ADR-004 | Per-stage deadlines + heartbeat vs progress | меньше false alarms | конфиг и базовые метрики | **P1** |
| ADR-005 | Independent evidence verifier по SHA | не принимать ложное «сделано» | необходимость auth источника | **P0 gate** |
| ADR-006 | Global rate/budget governor | убрать retry storm, экономить | справедливость очередей | **P1** |
| ADR-007 | Secure operator dashboard incident timeline | объяснить, где стоп и почему | PII, role-based access | **P2** |
| ADR-008 | Repair planner с ограниченными, обратимыми патчами | автоматические рутинные исправления | регрессии/самоутверждение | **P3**, dual verification |
| ADR-009 | Full ChatGPT DOM extraction/control | кажущаяся универсальность | ломкость, privacy, ограничения | **Reject** |
| ADR-010 | Temporal для multi-host / долгих workflows | durable execution/heartbeats/replay | overhead и миграции | **Defer** до измеренного роста |
| ADR-011 | Hash-chain anchor в remote WORM/S3 + retention | обнаружить ретроактивные правки | секреты, стоимость, доступ | **P2** |
| ADR-012 | Adapter capability negotiation + contract tests | пережить обновления Hermes | maintenance matrix | **P1** |

## 8. План изменений по этапам

**P0 — в этом изменении:** отдельный модуль `gpt_companion/journal.py`, безопасный разовый CLI `python -m gpt_companion`, тесты и package discovery `pyproject.toml` + offline unit tests; строгий allowlist, WAL, durable event ingest, дедуп, per-source seq gaps, conservative diagnosis, hash integrity check. Нет live-адаптера, tool calls, webhook endpoint, установленного scheduled observer и обещаний непрерывного мониторинга. Состояния журнала не равны статусам task ledger.

**P1 — после интеграции Autopilot:** version-pinned Hermes observer hook adapter, `local outbox → authenticated inbox`; schema negotiation, source authorization, heartbeat/progress probes, reconciliation poller для OpenAI Responses webhooks и GitHub; shadow mode только чтение и реальные fault-injection тесты. Перед кодом выяснить, какая Hermes версия запускается реально, какие hook имена поддерживает, где хранится gateway и какая auth схема.

**P2 — operator-friendly monitoring:** timelines с `trace_id`/`action_id`, sandbox replay, escalation, budgets, resource-lock dashboard, privacy and audit anchor; dry-run до любых действий.

**P3 — исправления:** автоматические *только* обратимые и проверяемые локальные изменения с lease/fence, ограничением попыток, root cause statement, тестами и откатом. Внешние/необратимые операции — отдельное разрешение.

**P4 — масштабирование:** perf/load test 10, 30, 100 worker; эксперимент по queue latency, DB lock rate, 429 rate, duplicate effect rate, recovered incidents; при росте multi-host рассмотреть workflow engine/queue и migration plan.

## 9. Release gates и проверка реальных гарантий

- G0: documented adapter version handshake, все неизвестные capability отказываются безопасно.
- G1: integration auth; credentials не попадают в GitHub/Obsidian/трассы, webhook signature проверяется *до* записи.
- G2: no duplicate external effect in crash/retry matrix; каждый unknown outcome требует reconciliation.
- G3: stale fence cannot write; TTL approval bound to digest, resource & actor; killed workers не получают новые permits.
- G4: no false `succeeded` under missing/stale/failed CI or hallucinated model report.
- G5: offline tests + fault injection: 429 + Retry-After; 401/403; 5xx; lost 2xx ack; power-off after reservation; browser crash; event reordering/duplicate; old worker heartbeat; NTP jump; SQLite `database is locked`; outbox full; disk full; corrupted DB; concurrent changes to one file; prompt-injection in PR/comment.
- G6: compatibility: Windows 10/11 (isolated local runner), WSL2/Linux Hermes, Chrome extension version, TLS/local adapter, cold restart, stale session, version rollback.
- G7: perf: test 100 agents (not 100 concurrent remote API calls) and synthetic multi-source events; report real p50/p95/p99 and confidence intervals, avoid guessing throughput.
- G8: deployment requires explicit release tag + reproducible checklist, operator can stop/revoke + restore snapshot, backup tested by restore, not just created.

## 10. Runbook / инцидентный разбор

1. Зафиксировать инцидент: `run_id`, `task_id`, `attempt`, `lease`, `fence`, last stage, exact revision, provider response ID, artifact manifest. **Никогда не записывать ключи, session cookies, полный промпт.**
2. Проверить integrity/holes telemetry; если есть `TRACE_INCOMPLETE`, получить события из outbox/replay, не предполагать, что callback завершается в порядке отправки.
3. Отделить: нет наблюдения / нет прогресса / процесс умер / approval / внешний эффект неизвестен / доказательства не прошли.
4. Для любого `reserved` без receipt — сначала read-back у провайдера и ledger reconciliation, **не retry**.
5. Для flaky CI — перепроверить конкретный head SHA и workflow run, не подменять failed зелёным старым запуском.
6. Для разрыва GPT stream — проверить provider `response_id`/официальную retrieval возможность. При недоступности сделать статус `UNKNOWN`, не «не получилось».
7. Выдать remediation с риском, ожидаемым эффектом и rollback plan; для риска R2/R3 запросить точное разрешение. При ошибке отправить на независимую проверку.
8. Обновить SDD ADR и incident postmortem: воспроизводимость, причина (confirmed/hypothesis), детектор, permanent fix, предотвращение повторений, ссылка на tests и commit.

Пример атомарного статуса: `run=run-42, attempt=3, status=NEEDS_RECONCILIATION, reason=tool.effect_reserved without provider receipt, last_verified_SHA=..., next=read-back GitHub PR by action_id, auto_retry=false, approval=none, evidence=missing`. Это **пример**, не обнаруженный live-инцидент.

## 11. Проверки текущего прототипа

Разовый разбор событий — `python -m gpt_companion --db path/events.sqlite3 --run-id run-42 --jsonl path/events.jsonl`; исходный JSONL должен приходить только из разрешённого локального экспорта. CLI не является фоновым сервисом. Дополнительные ограничения и пример — в `gpt_companion/README.md`.

На локальной изолированной копии нового модуля выполнено `PYTHONPATH=. pytest -q tests/gpt_companion/test_journal.py`: **52 passed** (локальный Python 3.13.5; минимальная поддерживаемая Hermes-версия Python 3.11 требует отдельной проверки в CI); проверки: replay, conflict, sequence gap, reordering, delayed backfill cannot refresh liveness, heartbeat-only stagnation, invalid clock, unknown effect, approval, false completion, heartbeat vs progress, per-attempt isolation, reason code, strict redaction, chain mutation, 32 competing writers, conflicting terminal sources, CLI fail-closed import and redacted errors. Это **unit tests**, не реальный live integration smoke и не полный regression suite репозитория. При переносе в GitHub перепроверить content/hash файлов и CI PR.

## 12. Основные первоисточники и смежные реализации

Все URL проверялись в ходе исследования 2026-11-22; они подтверждают **свойства внешних платформ**, не факт того, что они уже внедрены в данном форке:

1. [Hermes hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks), [Plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [Middleware](https://hermes-agent.nousresearch.com/docs/developer-guide/middleware), [API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server): интерфейсы интеграции, отличаются по релизам.
2. [Hermes Browser Extension](https://github.com/abundantbeing/hermes-browser-extension) и [Companion Plugin README](https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md): подход side panel/companion, не собственный проверенный код текущего форка.
3. [OpenAI Responses background](https://developers.openai.com/api/docs/guides/background), [OpenAI webhooks](https://developers.openai.com/api/docs/guides/webhooks), [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data): background response lifecycle, подписи/dedup, сроки доступности результатов.
4. [OpenTelemetry GenAI agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) и [model spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md): трассировка с версионированием семантики.
5. [GitHub webhook best practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks), [Actions concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency): authenticity, dedup, competing runs.
6. [Temporal durable execution](https://docs.temporal.io/durable-execution): оценка next-tier orchestration.
7. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet), [AI Agent Security](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet): sensitive data exclusion, separation of duties.

## 13. Открытые решения / не выдавать за реализованное

- Какая **точная** версия Hermes gateway/плагинов и Chrome extension установлена на рабочем ПК? Пока локальный MCP недоступен, неизвестно.
- Как будет оформлена аутентификация emittter и независимого verifier? Только дизайн, код не развёрнут.
- Есть ли поддерживаемый официальной платформой путь для конкретных ChatGPT GPT-сессий? Не смешивать с доступом к Responses API.
- Кто операционный владелец secrets, local outbox, retention и kill switch? Должен быть назначен до P1.
- В ветке Autopilot coordinator ещё нет adapter dispatcher/real watchdog и host auth; интеграция с неслитой веткой откладывается до её ревью.
- Локальный Obsidian не изменён: нужна отдельная явная синхронизация SDD после восстановления MCP, нельзя сообщать, что запись выполнена.

### ADR-013: Late backfill не является свежим heartbeat (P0, implemented)

При передаче старого события `sequence=2` после `sequence=3` сам факт получения данных сегодня не означает, что worker ещё жив. Наивная диагностика по `MAX(received_at)` превращала такой replay в ложную доступность. Реализован source-local frontier (максимальный `sequence`, виденный **на момент получения**): backfill сохраняется для целостности, но не освежает таймеры; для worker без прогресса baseline — первое наблюдение, а не последняя попытка heartbeat. Тесты: `test_delayed_backfill_does_not_fake_worker_liveness`, `test_heartbeat_only_worker_eventually_has_no_progress`. Ограничение: frontier основан на входящей ненадёжной телеметрии, без доверенной аутентификации worker и независимой lease-проверки это **только гипотеза**, а не proof of liveness.

### ADR-014: CLI должна входить в устанавливаемый wheel (P0, implemented)

Изначально `scripts/gpt_event_inspect.py` запускался только из checkout: каталог `scripts` не входит в `pyproject.toml` setuptools discovery. Чтобы не выдавать пример локального запуска за установленную функциональность, CLI вынесена в `gpt_companion/inspect.py` и `gpt_companion/__main__.py` (устанавливаемая команда `python -m gpt_companion`). `scripts/gpt_event_inspect.py` оставлен тонким wrapper для обратной совместимости checkout. Покрыто unit/subprocess тестами; полная сборка wheel на base fork остаётся отдельной CI-проверкой.

### ADR-015: Повреждённая БД — не `NOT_OBSERVED` и не сбой модели (P0, implemented)

Ошибки `sqlite3.DatabaseError` в CLI теперь преобразуются в `JOURNAL_INTEGRITY_FAILED` (exit code 3) без вывода payload или сырых traceback; такой инцидент нельзя смешивать с отвалившимся GPT. БД нельзя «исправлять» автоматическим пересозданием поверх повреждённого файла: сначала сохранить форензик-копию, восстановить последнюю backup + outbox replay, подтвердить `verify_chain`.

### ADR-016: Несовместимость версий Hermes/browser plugin — hard stop (P0 design)

Проверен опубликованный README **community** Hermes Browser Extension v0.4.1 (`abundantbeing/hermes-browser-extension`, не официальная часть данного форка): совместимый Hermes **0.22+**, extension plugin для текущего поколения работает с canary после 2026-10-24/релизами после 0.22.5, умеет 7 browser-context tools, 20 opt-in browser-control tools, три hooks, browser-context receipts. При этом README плагина прямо указывает **«no background processes, no telemetry»**. Текущий анализируемый GitHub fork на `main` имеет **v0.6.0**, коммит датирован 2026-04-01. Поэтому **нельзя обещать**, что новая extension side-panel/plugin установится в рассматриваемый fork: требуется отдельная проверка версии *реального* локального Hermes и pinned compatibility test; установка плагина вслепую считается hard stop. Версия установленного на ПК Hermes НЕ проверена из-за `Session terminated` Local_WorkSpace MCP.

Основной канал мониторинга — собственный авторизованный Hermes host/provider hook и долговечный outbox; браузерный UI-bridge можно применять только как вспомогательный добровольный источник, без прочтения ChatGPT DOM как скрытого API. Существующий browser-event-log не равнозначен непрерывной контролируемой телеметрии. Минимальный handshake: `fork_sha`, `hermes_version`, `hooks_supported`, `extension_version`, `plugin_version`, `gateway_profile`, `auth_ready`, `outbox_ready`; отсутствие критического поля → `INCOMPATIBLE_HERMES_VERSION`/`HOOK_UNAVAILABLE`, запуск не разрешён. Ссылки: https://github.com/abundantbeing/hermes-browser-extension/blob/main/README.md и https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md .

### ADR-017: События другого агента не маскируют остановку одного worker (P0 implemented)

У нескольких агентов в одном run может быть общий gateway. Свежие события `gateway:llm.response_received` не доказывают, что worker A продолжает работу. Добавлены `worker_sources_count`, `stale_worker_sources`, статус `PARTIAL_WORKER_OUTAGE` для частичного сбоя. Отдельные source-local frontiers сравниваются по времени; при наличии worker-сигналов generic gateway events не продлевают их lease-гипотезу. Важно: реальные lease/fence сверяет только доверенный координатор Autopilot; источник `source` в этом модуле сам по себе не аутентифицирован. Тесты: `test_gateway_traffic_cannot_mask_known_dead_worker`, `test_partial_outage_among_independent_workers`.

### ADR-018: Heartbeat vs substantive progress у нескольких источников (P0 implemented)

Таймер прогресса по worker-source больше не продлевается событиями gateway/observer, даже если они приходят «свежими» (`llm.response_received` от другого source). Иначе активная интеграция маскирует застывший полезный процесс. Тест `test_unrelated_gateway_events_cannot_mask_worker_stagnation`. Это консервативная эвристика: подтверждение успеха инструмента остаётся на независимом verifier, не на эвристике активности.

### ADR-019: Проба 100 независимых источников (P0 synthetic smoke)

Offline тест `test_100_sources_concurrently_ingested_and_partial_outage_is_counted` использует 16 concurrent writer threads для приёма 100 независимых source-id, затем heartbeat 10 из 100: ожидаемый `PARTIAL_WORKER_OUTAGE` и точное число 90 stale источников без потери событий или нарушений SHA-chain. Это **не** 100 работающих LLM-агентов, не сквозная проверка API и не заявка на throughput/SLO; требуются отдельные multi-process + restart/fault-injection bench и реальные latency/lock метрики перед продакшн запуском.

### ADR-020: Время wall-clock не является монотонным (P0 implemented)

Секунды жизни и стадии вычисляются по `received_at` локального journal server, а не по клиентскому wall time. Изменение системного времени назад на >1 c внутри последовательности событий либо между последним событием и проверкой маркируется `CLOCK_SKEW_DETECTED`, следующая операция — `CHECK_MONOTONIC_CLOCK_AND_TIME_SYNC`. Это предотвращает ошибочное объяснение сбоев как «worker умер» при сбое NTP/часов. Ограничение: нет настоящего monotonic-clock timestamp, переживающего перезапуск хоста, поэтому lease и budget гарантии должны оставаться у trusted Autopilot coordinator; измерение времени после рестарта требует независимого времени/boot ID.

## 14. Долговременная передача задач между десятками агентов

Контракт независимых инженерных агентов, owner/fence, инцидентная форма, правила передачи смены и фактически подтверждённые/неподтверждённые гарантии вынесены в [`GPT_COMPANION_AGENT_MANDATE.md`](./GPT_COMPANION_AGENT_MANDATE.md). Этот документ следует читать при каждом новом агентском запуске — **не** заменять его доверие устным отчётом предшественника.

### ADR-021: Локальный read-only watcher, согласованное persist-before-notify (P0 implemented; not deployed)

Создан `gpt_companion/watch.py`: только явный пользовательский запуск, by default один polling cycle, режим `--max-cycles 0` = непрерывный local polling до отмены. Обрабатывает один или до 500 последних `run_id`, пишет изменения diagnosis в *отдельную* SQLite WAL БД, предотвращает дубли одинаковых состояний после рестарта и при нескольких watcher-процессах. Не повторяет provider/API/tool actions, ничего не отправляет через сеть, не выполняет auto-repair. Время heartbeat не является реальным доказательством жизни worker без аутентификации и leases.

**Семантика доставки:** переход записывается в SQLite **до** вывода JSON в stdout. Если процесс упадёт между commit и выводом, уведомление на stdout может потеряться, но запись останется в таблице `transitions`: это **at-most-once best-effort notification**, не exactly-once. Возможность подтверждённых внешних уведомлений требует отдельного outbox dispatcher с receipt и dedup у получателя. Source event journal и status watcher DB физически разделены; наблюдатель остаётся неавторитетным.

Команда snapshot: `python -m gpt_companion.watch --db ./gpt-events.sqlite3 --status-db ./watch-history.sqlite3 --all`. Непрерывный режим **не активирован** и требует владельца процесса, автозапуска и безопасной остановки. Unit tests: restart dedup, concurrent watch CAS-like transaction, absence-of-run, unconfirmed effect, CLI snapshot, inventory 2 runs.


---

## 15. Аудит продолжения: события, факты, неизвестное (2026-11-22)

**Версия дополнения:** 0.2.1-proposal (reconciled parent head 85db47caedb8). **Контекст:** независимое stacked-изменение от PR #12 на исходном head 586a3e5436289f9c56ad69eefb53893ed11eff67; ветка fix/gpt-companion-terminal-causality-20261122-r01. Не подменяет отчёт о готовности работающего расширения. Права записи есть только в GitHub-ветке; подключение Local_WorkSpace вернуло Session terminated, альтернативный read-only MCP вернул HTTP 429. Состояние живых GPT/ChatGPT-сессий, Windows-установки, Obsidian и локальных файлов не подтверждено.

### 14.1 Подтверждённые ошибки анализатора и исправления данной ветки

| ID | Доказательство в исходном коде PR #12 | Риск | Изменение | Проверка |
| --- | --- | --- | --- | --- |
| OBS-001 | last_terminal выбирался из всех terminal_events максимальным sequence, включая worker.stopped | финальная очистка скрывала REPORTED_FAILED и AWAITING_VERIFICATION | worker.stopped не отменяет outcome report в той же попытке | test_failure_is_not_hidden_by_later_worker_stop, test_reported_completion_still_needs_verification_after_stop |
| OBS-002 | completion и failure одного эмиттера в одной попытке не считались противоречием | один источник мог задекларировать одновременно оба исхода | помечать как TRACE_INCOMPLETE; запретить доказательство успеха | test_conflicting_outcomes_from_one_source_never_pass_as_final |
| OBS-003 | contradictory без seq hole предлагал только FETCH_MISSING_EVENTS | оператор получал бесполезное действие, потому что пропущенных событий нет | различать RECONCILE_CONFLICTING_EVENTS и FETCH_MISSING_EVENTS; diagnostic_flags | test_causally_impossible_effect_resolution_is_not_a_simple_gap, test_gap_has_distinct_recovery_step_from_conflict |
| OBS-004 | reason_code извлекался из порядка прихода, а не только из failure reports по source sequence | backfill мог подменять актуальную причину отказа | выбирать код из подходящего failure report; не выставлять reason как подтверждённый при конфликте | test_failure_is_not_hidden_by_later_worker_stop, test_replay_after_restart_preserves_diagnostic_flags |
| OBS-005 | live_age = max(0, now-last_seen) при откате wall-clock | давно умерший worker мог выглядеть свежим | состояние CLOCK_SKEW_DETECTED + диагностический флаг CLOCK_REGRESSION; supervisor check | test_observer_wall_clock_regression_is_not_fresh_liveness |

Только source-review и добавленные тесты; до зелёного exact-HEAD CI это **кандидат исправлений**. Сохранён приоритет: неизвестный внешний эффект выше остальных диагностик и никогда не разрешает слепой повтор. CLOCK_SKEW_DETECTED не означает, что worker погиб; это недоверие ко времени наблюдателя.

### 14.2 Строгая типизация доказательств

Для каждого stage хранить не одно status, а кортеж:

- **claim:** утверждение worker/provider/UI с source_id, attempt, sequence, received_at;
- **observation:** событие приёма + проверка подписи и source-role; очередь и квитанция ingestion;
- **effect receipt:** независимо доступная идентичность внешнего действия/объекта;
- **verification:** точный target revision, критерий acceptance, независимый verifier и timestamp;
- **decision:** действие control plane, его lease/fence, субъект разрешения, reason и rollback.

Нельзя выводить факт исполнения внешней записи из любого значения "tool.effect_acknowledged" в ненадёжной телеметрии. Это всего лишь наблюдаемое заявление. У текущего прототипа отсутствует доверенный контур для положительного подтверждения; значения unresolved_effects и состояние RECENT_TELEMETRY не являются разрешением retry, даже если telemetry сообщает resolution. Этот контракт должен быть закреплён в UI, SDK и проверках.

### 14.3 Часы и причинность

Использовать две шкалы времени: received_wall_utc для audit, process monotonic для измерения интервалов внутри непрерывного процесса, а после рестарта — новую epoch и независимый supervisor/lease. Wall-clock regression, невозможное будущее, зависшая очередь, backfill и задержанный webhook — отдельные причины. Временные метки эмиттера не доказывают порядок между источниками; causal edges обязательны через action_id, parent_event_id, attempt, fence и receipt_id. Source-local seq устанавливает только локальный порядок.

Новые diagnostic_flags — диагностические признаки, не разрешения или надёжные причины. Контракт вывода должен быть версионирован до подключения чужих клиентов.

## 16. Реальная архитектура Hermes и правило одного владельца

Публичная документация актуального Hermes описывает Kanban board, durable task_runs, worker lanes, heartbeat, hooks и plugins. См. первоисточники:

- Hermes Kanban: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- Worker lanes: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes
- Hooks/plugins: https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks и https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
- Observer hooks: https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks

**ADR-021 (P0, architecture):** если установленная версия Hermes поддерживает durable Kanban, именно её verified version-pinned task_runs / worker lease / dispatcher являются единственным источником task lifecycle. Соседняя ветка Autopilot PR #1 — исследовательский ledger; без явной миграции не вводить вторую очередь, второй dispatcher, второй success status. GPT Companion хранит только диагностические наблюдения. Старый main fork от апреля 2026 не доказывает, что текущий установленный Hermes действительно имеет перечисленные hooks: перед адаптером проверить actual binary/version/profile, module availability, hook timing/payload/auth и совместимость.

**ADR-022 (P0, safety):** один source of truth на каждой оси: Kanban task/run; external effect ledger gateway; trusted provider receipts; immutable GitHub SHA/CI evidence; append-only telemetry inbox для расследований. Обязательный конфликтный тест: старый worker и новый worker одновременно считают себя владельцами после lease expiry — только действующий fencing token может коммитить; observer лишь сообщает конфликт.

**ADR-023 (P1, compatibility):** один manifest для конкретной установки: Hermes commit/release, Python, gateway API version, enabled hook list, browser/extension ID+version+permissions, auth mechanism, OS, repo SHA и supported features. Любое неизвестное или несовместимое поле -> UNSUPPORTED/DEGRADED, не silent fallback на DOM. ChatGPT web UI не эквивалентен Responses API, а подписка ChatGPT не равна API-доступу.

## 17. Двенадцать параллельных PR: коллизии и порядок интеграции

На аудите обнаружены открытые draft PR #1–#12 в Podtverzhdeno/hermes-agent. Их описания и changed files проверены точечно; полный сквозной review всех diff и матрица совместимости ещё не завершены.

| Ownership / класс | Конкурирующие изменения | Gate до интеграции |
| --- | --- | --- |
| Lifecycle / approvals / fencing | #1 + stacked #10 | выбрать single owner на базе version-pinned Kanban, миграция, не запускать оба dispatchers |
| API ingress / idempotency / SSE | #4, #5, #6, stacked #11 | единый обработчик preflight и scope ключа, contract tests: concurrent same key, changed payload, crash, SSE, stream disconnect; owner gateway |
| Diagnostic observer | #9 gpt_bridge и #12 gpt_companion | **не объединять два отдельных журнальных драйвера** в production; выбрать canonical schema/adapter, обеспечить миграцию и dual-read-only сравнение |
| Документирование и координация | #7, #8 и документы остальных | ADR de-dup, один индекс и один журнал решений, точные ссылки на provenance |
| Skill contracts | #2 | advisory manifests ≠ real authorization; контроль только через trusted gateway |
| ACP permissions | #3 | проверить cross-session isolation и не ослаблять permission gates при подключении наблюдателя |
| Этот PR | stacked на #12, отдельный путь test_terminal_causality.py | merge только после #12, CI на итоговом SHA, independent review |

**Интеграционная последовательность:** audit main/upstream → согласовать Kanban source of truth → устранить API handler duplication и синхронизировать идемпотентность → выбрать одного observer → подключить signed ingress/outbox и independent verifier → проверить платформы и fault injection → только затем включить monitoring. Нельзя автоматически делать merge нескольких draft PR только потому, что каждый из них зелёный: GitHub checks относятся к разным HEAD и base.

**Ресурсный замок для десятков агентов:** claim включает repository, path-prefix, owner_agent_id, base SHA, lease expiry, fencing token и head commit. Изменять чужой path только через явный transfer/review. При CAS conflict — refresh, semantic reconcile, rerun tests; не force-push и не overwrite. У независимых проверяющих нет права одновременно утверждать собственную работу.

## 18. Deep observability: событие, причина остановки и следующее действие

Схема для будущего live-адаптера (не реализована):

1. ingress записывает authenticated request_key и causal trace в canonical Kanban task;
2. worker получает grant и пишет в durable outbox события стадий, без prompts/tool args/secret;
3. adapter подписывается на поддерживаемые Hermes hooks (pre/post tool, pre/post LLM, stream/session/approval, kanban task changes) и сопоставляет события с task_run;
4. journal commits+ACK только после fsync; consumer сохраняет gaps, duplicate IDs, причинный граф и source trust tier;
5. independent verifier проверяет artifacts/provider receipt/exact Git SHA и CI независимо от worker;
6. watchdog без управления задачами указывает STALL_STAGE и PROBABLE_CAUSE, Evidence и разрешённые operator actions; ошибку source transport отличает от реального agent stop;
7. fix planner сначала создаёт incident и тест на воспроизведение, затем в отдельном ограниченном worktree даёт reversible PR, требует reviewer и не маскирует unknown effects.

**Таблица stop-предикатов:**

| Сигнал | Запрещённый вывод | Требуемое подтверждение | Разрешённое действие |
| --- | --- | --- | --- |
| no new SSE bytes | worker погиб | gateway/provider response id, OS supervisor, run lease | inspect transport, не replay write |
| stream end without final receipt | succeeded | signed/provider receipt + independent evidence | reconcile |
| worker.stopped after run.reported_failed | task просто stopped | source-local report + reason code | сохранить REPORTED_FAILED |
| worker.stopped after run.reported_completed | verified success | exact revision artifact + verifier | AWAITING_VERIFICATION |
| completion and failure same attempt | последняя строка победила | causal order + independent task evidence | TRACE_INCOMPLETE |
| watchdog clock moved backward | свежая активность | clock epoch, supervisor, lease | CLOCK_SKEW_DETECTED |
| GPT claimed fix | merged/fixed | exact diff, tests, independent review | открыть draft PR |
| effect_reserved and missing receipt | safe to retry | read-back external effect + ledger | reconciliation only |
| approvals expired/ambiguous | silently continue | bound subject/action digest/reviewer/TTL | request new approval |
| GitHub job green on previous SHA | new code passed | job/check suite tied to exact HEAD SHA | re-run on current HEAD |
| producer drops outbox messages | all tasks completed | sequence gap + durable outbox replay | OBSERVABILITY_DEGRADED |
| browser tab closed | model task cancelled | task_run and gateway state | inspect UI adapter separately |

**Задача мониторинга**: показать оператору полный ответ "последний доказанный stage → блокирующий предикат → evidence provenance → recommended safe next step → owner → deadline", не одну зелёную/красную лампу. Unknown — допустимый и часто правильный итог.

## 19. Конкурирующие идеи — строгий отбор

Экспертная матрица, НЕ измеренная эффективность: снижение риска 35%, проверяемость 25%, совместимость с единственным owner 20%, трудозатраты 10%, обратимость 10%; баллы 1–5, сумма приведена к 100. Пересчитывать после реального тестирования, не выдавать за научное доказательство.

| Идея | Снижение риска | Проверяемость | Совместимость | Cost | Обратимость | Балл | Решение |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Исправить causal diagnostics + negative clock jump | 5 | 5 | 5 | 5 | 5 | 100 | реализован кандидат, P0 |
| Independent SHA/provider evidence verifier | 5 | 5 | 4 | 4 | 4 | 92 | gate P0 |
| Supervisor + clock epoch/progress separation | 4 | 5 | 5 | 4 | 5 | 91 | P1 |
| Authenticated durable outbox + ACK | 5 | 5 | 4 | 3 | 4 | 90 | gate P0 |
| Version-pinned Kanban observer adapter | 5 | 4 | 5 | 3 | 4 | 89 | P1 |
| Operator dashboard + drill-down | 3 | 3 | 3 | 3 | 4 | 62 | P2 |
| Agent auto-fix of privileged workflows | 2 | 2 | 2 | 1 | 2 | 38 | defer |
| DOM scraping as primary task control | 1 | 1 | 1 | 2 | 1 | 22 | reject |

Для P0 не достаточно высокой оценки: нужен unit/property/fault-injection тест, falsifiable acceptance, explicit owner и rollback. **Десятки одинаковых голосов агентов не превращают гипотезу в доказательство.**

## 20. Fault injection и измеримые release gates

Перед включением live-monitoring необходима reproducible test matrix (10 / 30 / 100 workers × 1 / 2 / 10 producers per run × 0 / 1 / N side effects), включая out-of-order events, event ID collision, late backfill, high sequence gaps, SQLite busy/locked, corrupted WAL, power loss before/after ACK, clock jump ±, full disk, expired lease/fence, 401/403, 429 + Retry-After, 5xx, dropped SSE, provider request with unknown outcome, user approval timeout, GitHub check for wrong SHA, stale Chrome tab, agent restart and supervisor restart.

**Инварианты при приёмке:**
- ни один тест с unknown external effect не вызывает автоматический replay;
- ни один противоречивый outcome не переводит задачу в SUCCEEDED;
- ни один GPT-reported completion не удостоверяет собственную работу;
- 0 невидимых дубликатов по одному event_id/source seq в симулированном потоке;
- все результаты claims привязаны к конкретным attempt/revision/evidence;
- секреты, message body, DOM text, URL with credentials, cookies и tool arguments отсутствуют в сохранённой телеметрии;
- тесты выполнены на exact head SHA и в установленном wheel на минимальной версии Python, подтверждена работа Windows/WSL.

Считать **и публиковать как измерения**, а не угадывать: percent event gaps, queue lag p50/p95/p99, observer end-to-end lag, unknown-effect reconciliation latency, false-positive stalled-run rate, SQLite write contention, API 429, retry counts, per-source auth rejects и storage per 1000 events. Пока нет истинной live-системы, baseline и SLO численно неизвестны; критерии нацелены на нулевые опасные ложные успехи в тестовых сценариях, а не на фиктивные 100% uptime.

## 21. Агентный режим работы и сложность проекта

**Operational constraint / owner mandate:** считать Hermes GPT bridge + observability проектом высокой сложности с недоказанной live-интеграцией. Запрещено объявлять задачу завершённой после быстрого единичного code review, нескольких зелёных unit-тестов или собственных модельных выводов. Агентам разрешены параллельные гипотезы, но каждая должна иметь issue/ADR с ID, owner, evidence, failure reproduction, exact revision, CI run, roll-back и независимым reviewer. Письменное самооценивание не заменяет внешнюю проверку.

Для каждого предложения завести: hypothesis → alternative designs → risk/benefit score → experimental falsification → implementation owner → tests → release gate → decision + rationale. Спорные предложения остаются OPEN, duplicate ADR сливается с существующим только через review. Оценка и audit trail переживают перезапуск любого агентного контекста.

Ни один процесс ChatGPT в этой беседе не является круглосуточным monitor. Реальный always-on режим потребует отдельного разрешённого host service, процессов и supervision на Windows/WSL, а также соответствующего доступа. До их появления статусы "continuous monitoring enabled", "local Obsidian synced", "repair deployed" недопустимы.


## 22. Cross-attempt effect stickiness — integrity gate

**Confirmed source defect (OBS-006):** prior to this change, `assess(run_id)` selected `MAX(attempt)` and examined only that attempt. An unresolved external write in attempt 1 disappeared from the visible diagnostics as soon as attempt 2 emitted `worker.started`. This was a *diagnostic omission*, not proof that real API duplication occurred; the live connector is absent.

**Patch in stacked branch:** fetch prior attempts' effect reservations and matching claimed resolutions, scope them by `(attempt, action_id)`, and return `NEEDS_RECONCILIATION / RECONCILE_PREVIOUS_ATTEMPT_EFFECTS` when an earlier reservation has no valid matching resolution. Add `prior_attempt_unresolved_effect_count`, a bounded display of 50 records, and `PRIOR_ATTEMPT_EFFECT_UNKNOWN` / `PRIOR_EFFECT_LIST_TRUNCATED`. Only metadata ID fields; no payloads. Any `tool.effect_acknowledged` is still untrusted; the gateway needs independent provider read-back and a fence-bound receipt before *any* replay. This observer cannot authorize retries.

**Counterexamples to test:** new worker starts after an unacknowledged effect, ACK belongs to a later attempt with identical action_id, effect ACK arrives before reserve from same source, report failure in new attempt while old effect remains unknown, 52 earlier attempts with bounded output, matching same-attempt source-local ACK. Cases added under `test_terminal_causality.py`.

**Known gaps:** a claimed cross-source ACK cannot establish true causality; authenticated ingress and external verified receipt remain release blockers. A missing `tool.effect_reserved` event could conceal a real write, so absence of entries is not proof of absence. Full history is scanned on each call: on large runs, replace with indexed durable per-attempt effect-state projection with transactional updates, reconciliation and migration tests; measure p95/p99 inspect latency and WAL contention at 10/30/100-worker load. The diagnostic schema is additive but any downstream parser must be version-gated. No automatic remediation and no production patch without versioned control-plane integration.


## 23. Upstream Hermes hook contract — documented compatibility requirements

**Verified external contract (not proof of installed version):** Hermes [Observer Hooks](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks) describes `telemetry_schema_version = "hermes.observer.v1"`, fail-open callbacks, explicit `session_id` / `task_id` / `turn_id` / `api_request_id` / `tool_call_id`, request-scoped `pre_api_request` / `post_api_request` / `api_request_error`, and tool `pre_tool_call` / `post_tool_call`. It distinguishes `on_session_end` (turn/run scope) from `on_session_finalize` or `on_session_reset` (identity lifetime). `pre_llm_call` is turn-scoped, not a per-provider-request boundary. Observer hooks may contain raw-compatible fields (e.g. conversation history), so a subscriber must **only copy explicit safe metadata**, never serialize a whole callback payload. Tool results and error_message may contain sensitive data and must not be stored.

**ADR-024 (P0):** instrumentation is *observation*, not an enforcement or durable commit boundary. Observer callbacks are intentionally **fail-open**: an exception is logged and the worker continues. Thus hook-only event collection cannot guarantee lossless causality or prevent a tool effect. Required producer observability contract: health/counters (`callback_attempts`, `dropped_events`, `queue_lag`), source-local sequence allocation, bounded in-memory queue, optional durable outbox with acknowledged delivery, and a fail-closed gate only at the **trusted control plane**, never invented inside a best-effort observer. On untrusted hook gaps, output `OBSERVABILITY_DEGRADED` / `UNKNOWN`; do not infer that a missing callback means a tool never ran.

**ADR-025 (P1):** version-pinned mapping table, verified *per installed runtime*, not per README:

| Hermes hook or canonical source | Companion event | Correlator | Trust boundary |
| --- | --- | --- | --- |
| `kanban_task_claimed` + task_runs | `run.accepted` / worker claim | board/task_id/run_id | canonical lifecycle requires independently queried task_runs |
| `pre_api_request` | `llm.request_started` | session/turn/api_request_id | no request bodies or URLs |
| `post_api_request` | `llm.response_received` | api_request_id | response arrival ≠ task verified |
| `api_request_error` | normalized reason_code | api_request_id, status class | redact error message, capture retryable/429 class only |
| `pre_tool_call` | tool proposal/timing (v2) | tool_call_id | this callback may modify/block; observer returns no mutation |
| `post_tool_call` | tool outcome (v2) | tool_call_id | `ok` ≠ independently verified external effect |
| `on_human_input_request/resolved` | approval wait/resolution (v2) | request_id | no approval text/answer; signed control plane decides |
| `subagent_start/stop` | nested agent lineage (v2) | parent/child IDs | no child summaries, goals or raw histories |
| `on_session_end` | turn ended | session/turn | NOT necessarily session identity finalized |
| `on_session_finalize/reset` | session identity handoff | old/new session | not proof of task cancelled |
| `kanban_task_completed/blocked` | worker-reported outcome | canonical task/run | review+independent evidence before `verified` |

Existing companion schema **v1** has no `task_id`, `provider_request_id`, `parent_event_id` or `fence`; do not force unversioned fields into current strict allowlist. Propose v2 envelope with separate validated optional opaque identifiers, authenticated actor binding and a migration/dual-read test. The installed version might lack these observer hooks; successful software import is not a capability handshake.

**Specific fault injection:** make a hook throw while a tool successfully executes; observer must show degraded telemetry without claiming the tool did not execute. Reset a session identity while task run continues; do not classify `on_session_end` as task success. Reuse API request IDs across producer boundaries and ensure isolated provenance. Verify legacy callback payload with huge/sensitive `conversation_history` is never stored.

## 24. Browser companion and transparent operational UI

The independent [Hermes Browser Extension companion plugin](https://github.com/abundantbeing/hermes-browser-extension/blob/main/companion-plugin/README.md) supports opted-in browser context and scoped tab control on compatible versions; its permissions, routes and profile requirements must not be copied into this project as assumed installed capabilities. It advertises per-profile version constraints, browser attach and background-task-tab controls, and a metadata-only diagnostic route. In particular, closing/revoking a tab does not prove a Hermes task was cancelled; previous background tabs can remain open but no longer be controllable.

**ADR-026 (P1):** source matrix must distinguish (a) Hermes API, (b) Hermes Kanban, (c) browser extension/plugin, (d) ChatGPT web UI, (e) OpenAI Responses API. Only use a feature when the exact owner/version and explicit user consent authorize it; never collapse these into one global `GPT_CONNECTED` light. Recommended capability handshake response is `source_id, source_version, gateway_release, extension_version, profile, browser_session_id, supported_events, supports_receipts, approval_surface, read_only, last_verified_at, expires_at` with opaque IDs. Mismatch -> `UNSUPPORTED` or `DEGRADED`, not background UI instrumentation.

**ADR-027 (P1):** observability dashboard for every card/run must show a causal, three-plane timeline:

- **Canonical lane** — task lifecycle from verified Kanban records, attempt, lease/fence, review status, last run and source revision;
- **Observed lane** — best-effort hook journal with source identity and sequence, queue delay, missing spans, recorded stage and heartbeat/progress distinction;
- **Evidence lane** — trusted provider receipt, GitHub commit SHA, exact CI checks, manually approved action and independently verified artifact.

Each expanded stage displays **what was expected, what was observed, what was independently proven, why it might have stopped, confidence tier (confirmed/probable/hypothesis/unknown), safe next operation, responsible owner and correlation IDs**. Distinguish `NOT_OBSERVED`, `TRANSPORT_DISCONNECTED`, `REPORTED_FAILED`, `WAITING_APPROVAL`, `EFFECT_UNKNOWN`, `AWAITING_VERIFICATION`, `VERIFIED`, `OBSERVER_UNHEALTHY`, `UNSUPPORTED`. Disabled or unknown must not appear green. All UI drilling must be read-only until a separately approved control action is issued with time-bound permission.

Demo acceptance (synthetic only): inject a 30-worker run with a failed provider call, hook delivery gap, expired approval, prior attempt effect unknown, browser tab revocation, stale CI SHA and one confirmed success. Dashboard must show seven **different** causal reasons and no inferred success/retry on missing evidence. Emit a machine-readable incident export containing only opaque metadata (no prompts, URLs with secrets or browser contents).

## 25. Watcher source-review findings — PR #12 ownership

Latest reviewed parent implementation introduced `gpt_companion/watch.py` with a durable transitions database. It is **not the same SQLite transaction as the event inbox**, so event commit and transition alert are not atomic together; correctness must be eventual, monotonic and reconstructible. A crash after transition commit but before stdout emission can suppress notification after restart, which the code correctly documents. An external alert channel needs a durable delivery outbox with independent ACK and dedup; avoid claiming exactly-once notification.

**OBS-007 (open, handed to parent owner):** `_fingerprint(assessment)` currently hashes attempt/state/next_action/unresolved_effects/pending_approvals/missing_sequences/reason/stale_worker_sources, but omits newer `diagnostic_flags` and `prior_attempt_unresolved_effect_count`. Thus a new prior-attempt unknown effect or causal flag can be silently absent from transition history while headline state remains unchanged. Extend the fingerprint to include stable proof-relevant fields (not continuously changing age) and regression-test that a new unresolved prior action causes a transition.

**OBS-008 (open, handed to parent owner):** `StatusWatch.sample` calls `EventJournal.assess` without first validating event chain. The one-shot CLI does verify_chain, but watch runs could persist a diagnosis from corrupted/unverified event history. Choose an integrity strategy that verifies once per snapshot or incremental verified checkpoint, fails explicitly `JOURNAL_INTEGRITY_FAILED`, and avoids O(number_of_runs × entire_history) hashing at each poll. Add tampered SQLite record test; count integrity-check latency. This branch does **not** modify parent-owned watch.py to avoid concurrent collisions.

**Priority:** OBS-006 cross-attempt safety diagnostic implemented in stacked patch; OBS-007/008 open review. Neither patch by itself can prove external effects, guarantee atomic cross-store writes, or create a live GPT monitor.
