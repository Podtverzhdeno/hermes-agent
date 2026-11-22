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


## 22. Cross-attempt effect safety — delegated owner PR #23

**Confirmed OBS-006:** selecting `MAX(attempt)` and reading only the newest attempt can conceal an earlier `tool.effect_reserved` with no authenticated resolution. A candidate local patch was briefly authored and then **removed from this stacked PR** to avoid duplicate implementation with [PR #23](https://github.com/Podtverzhdeno/hermes-agent/pull/23), which covers this defect more conservatively. Do not merge the overlapping code twice.

**Why PR #23 is preferred (pending independent tests):** its source-local causal rule does not allow cross-source `ack` telemetry to clear unknown effects; it also marks cross-source effects in the current attempt and extends watcher deduplication to prior-attempt uncertainties. Review details and unresolved read-snapshot race were sent to PR #23 in GitHub comments. A claimed ACK is not provider proof regardless of source order; only the trusted effect ledger/receipt and exact task version can authorize repetition.

**Gates:** PR #23 receives exact-head isolated tests, cross-source/attempt replay fault injection, WAL concurrency tests and independent reviewer; canonical schema for any added fields is versioned. This PR #17 owns terminal-report precedence, same-attempt outcome conflicts, conflict-specific next actions and additive audit documentation only. `EventJournal.assess` in PR #17 **does not** contain cross-attempt effect reconciliation; do not misrepresent its current safety coverage. No automatic replay of writes is authorized by either branch.

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

**Priority:** OBS-006 delegated to PR #23 (not implemented here); OBS-007/008 open review on the parent watch implementation. Neither patch by itself can prove external effects, guarantee atomic cross-store writes, or create a live GPT monitor.


## 26. Thirty-agent ownership checkpoint — living integration queue

At the 2026-11-22 inspection, **30 distinct draft/open PRs** were visible, not 30 independently validated services. Source review performed on PR #12, #17, #23, #27, #29, #13, #15, as well as file inventories for other GPT-related PRs. PR heads and statuses move rapidly; treat these identifiers as a historical checkpoint, not a pinned live dashboard.

| Concern (single owner per resource) | Candidate primary owner | Competing or dependent work | Decision / remaining gate |
| --- | --- | --- | --- |
| Offline journal source-of-truth | PR #12 | #9, #16, #21, #25, #30 offer additional observer kernels | **DO NOT** ship multiple incompatible event schemas; choose/adapter via independent review |
| Reported terminal outcome precedence and conflict-specific diagnostic | PR #17 (this branch) | #23 also checks multi-report contradiction | keep our narrow feature only, no auto effects |
| Sticky unresolved effects, causal ACK and watcher fingerprint | PR #23 | duplicate candidate removed from #17; parent #12 watch | appoint #23 as candidate owner (pending exact-head tests + snapshot race closure) |
| PR inventory and changed-file/CI collision gate | PR #27 | #14, #18, #20, #22, #24, #26, #28 | read-only primary review engine; no merge permission |
| Stacked-PR ancestry/cycle component | PR #29 | collector overlap with #27 | compose as pure analyzer over #27's pinned snapshot, not second REST collector |
| Browser ownership / attached external CDP cleanup | PR #15 | PR #13 touches `tools/browser_tool.py` too | reconcile explicitly; never close user-owned browser on a task timeout |
| API SSE idempotency and pre-dispatch validation | owner not yet designated | #4/#5/#6/#11 | **P0 unresolved ownership**: jointly review exact handler/handoff to avoid duplicate writes |
| Autopilot ledger vs upstream Kanban | owner not yet designated | #1/#10 and upstream Kanban | **P0 architectural blocker** until one task/lease authority selected |
| Independent artifact/CI verifier | owner not yet designated | #27 evidence gate is advisory, not verifier | define trusted receipts, exact-HEAD matrix and human review |
| SDD consolidation, human escalation and release | A0 steward required | many docs and tests (PRs #7–#30) | update one index/ADR register; don't auto-merge all drafts |

Before every integration freeze, capture GitHub PR numbers, `head_sha`, `base_sha`, mergeable status, changed paths and exact `workflow_run.head_sha` in a **single** snapshot; re-read after scan, because 30 agents may write concurrently. A hash of unsigned JSON is a change detector, not authentication. When any ref moves, mark `SNAPSHOT_STALE`, *not* 'test passed'. Review three-way semantic diffs, migrations and same-file owner handoff. The system may recommend a merge ordering but must never call merge/deploy itself without separate approval. See [#27](https://github.com/Podtverzhdeno/hermes-agent/pull/27) and [#29](https://github.com/Podtverzhdeno/hermes-agent/pull/29).

## 27. GPT/ChatGPT vs provider API — effect boundaries

Official [OpenAI Background mode](https://developers.openai.com/api/docs/guides/background) returns a response ID and status which may be retrieved later; [webhooks](https://developers.openai.com/api/docs/guides/webhooks) send signed event notifications (including `response.completed`), with retries and possible duplicate deliveries. This is an API protocol, **not** a channel for inspecting a ChatGPT web conversation or proof that a downstream tool write occurred.

Adapter contract for an explicitly authorized OpenAI API lane:

1. Persist the request idempotency key and response ID before returning the task to the dispatcher, with the provider/model/project identity and owner fence (no prompt content in observer logs).
2. Verify webhook signature with server-held secret and freshness tolerance; reject replay and duplicate `webhook-id`. Bind payload `event.data.id` to the expected response ID, not just run_id text supplied by an emitter.
3. Treat `queued` / `in_progress` as provider states, not worker liveliness. A `response.completed` event means **response available**; retrieve canonical state/output and independently validate requested artifacts. Tool output remains a distinct effect.
4. For webhook timeout or missed callbacks, poll the **same** saved response ID with bounded backoff; do not issue a new `POST /responses` just because the response stream ended.
5. For terminal failure/expiry, do not assert 'no external write' without receipt. Provision a separate audited action coordinator and ledger before enabling mutating tools.

For browser-only ChatGPT UI integration, do **not** infer API response IDs or guaranteed retry semantics; no invisible UI scraping, cookie extraction, browser control without per-tab opt-in and tool approvals. An extension status `connected` only proves a transport handshake unless paired with a fresh capability probe and trusted run receipts.

## 28. Hard gates trump subjective idea scores

Idea scoring is an aid to resource allocation, **not** validation. The earlier 100-point matrix expresses priority judgment, not reliability percentages or a claim of 10/10. An idea is **inadmissible for production** regardless of aggregate score when any hard invariant fails:

- uncertain external effect might be replayed;
- observer self-report can become `VERIFIED` without independent evidence;
- model or browser extension can grant itself approval;
- source schema/version, active owner/fence or trust tier is unknown;
- rollout cannot be rolled back without corrupting task ledger;
- sensitive content is logged, or the audit trail cannot distinguish truncation/tampering;
- merge candidates lack exact-head test evidence and conflict resolution.

For competing proposals, record severity (impact), expected failure frequency (evidence-supported or unknown), detectability, reversible implementation cost, and compatibility, plus proposed **falsification test**. Scores without a reproducible baseline carry `confidence=low` and must not be promoted to proof. Cross-review requires different author and proof source, not merely a different model invocation on the same prompt.

**Actionable change-freeze rule:** when agents simultaneously modify an owner resource (e.g. `gpt_companion/journal.py`, `gateway/platforms/api_server.py`, `tools/browser_tool.py`), require one integration steward, an explicit selected PR, independent tests, semantic diff reconciliation and a branch freeze; abandon duplicates after transferring unique tests/ADRs. This PR demonstrates deliberate rollback of a duplicate six-test patch in favor of PR #23.


## 29. OBS-009 — source sequence coverage / unknown prefix

**Confirmed in parent + stacked observer source:** the previous `sum(max(sequences)-len(sequences))` formula treated an arbitrary producer's first observed sequence `50` as **49 missing events**, even when `50,51,52` were contiguous. Since `validate_event` accepts any positive sequence and producers have independent local counters, there is no proof that `1..49` belong to this `run_id,attempt` rather than an earlier unobserved source lifetime. Conversely, silently resetting missing to zero would pretend complete coverage.

**Selected conservative semantics (implemented in PR #17):** `missing_sequences = Σ(max-min+1-count)` for **known internal holes**, plus `unverified_prefix_sources` and `UNVERIFIED_SOURCE_PREFIX` for coverage without source checkpoint. With only unverified prefix, `TRACE_INCOMPLETE / VERIFY_SOURCE_CURSOR_OR_CHECKPOINT`; with internal hole, `FETCH_MISSING_EVENTS` and both flags as applicable. Each source is independent; not a global sequence number. Existing unknown external effect states retain priority. Five new offline regression tests cover `50,51,52`, `50,52`, mixed worker/gateway producers, `1,2`, and outstanding effect with unverified prefix.

**Pending follow-on:** signed producer boot ID, explicit per-run cursor/coverage checkpoint, source transition event and export sequence or vector cursor to establish whether the prefix was legitimately absent. The current untrusted source string cannot prove a checkpoint. A strict relay must reject reuse of a source identity with a reset counter unless a new boot ID is established. On restart, retained cursor/projection needs read-back from durable outbox; do not auto-clear `UNVERIFIED_SOURCE_PREFIX`. See PR #19's MV3 native host cursor contract; it explicitly distinguishes producer-local sequences and multi-producer cursor maps.

**Known watcher impact:** PR #12 `watch.py::_fingerprint` hashes headline state/action but currently lacks `unverified_prefix_sources`, so an additional producer's prefix coverage anomaly may be missed if state/action were already incomplete. Parent watcher owner should include stable coverage fields in dedupe fingerprint and test multi-source changes. Avoid modifying the same watch.py here while PR #23 also edits it.

**Standards cross-check:** SQLite WAL snapshot isolation applies to transactions, not unrelated autocommit SELECT calls (https://www.sqlite.org/isolation.html). OpenTelemetry GenAI traces/events capture agent/tool causal context but do not confer tool effect authority (https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/); [Temporal](https://docs.temporal.io/activities) explicitly designs activities to be idempotent under retries. These are evidence for design trade-offs, not claims that Hermes runs Temporal or that OTEL is installed.


## 30. OBS-010 — atomic latest-attempt observation (SQLite)

**Confirmed code-level exposure:** the earlier `EventJournal.assess` executed `SELECT MAX(attempt)` and a separate `SELECT rows WHERE attempt=?` under SQLite `isolation_level=None`, without an explicit reader transaction. A concurrent producer could commit new events between those reads; the resulting diagnosis was not a single reproducible snapshot.

**Chosen minimal fix in this branch:** one correlated `SELECT event_json, received_at, sequence, source, attempt FROM events WHERE run_id=? AND attempt=(SELECT MAX(attempt) FROM events WHERE run_id=?) ORDER BY position`. Derive `attempt` from the selected rows. In WAL, one SELECT uses one database read snapshot; no long read lock or new distributed state machine. This only solves **the latest-attempt/rows consistency within this module** — not atomicity across observer DB, watcher DB, canonical Kanban, provider receipt or GitHub. Two targeted tests assert a single SQL statement and correct attempt selection, with a 30-source interleaving regression. See SQLite [Isolation](https://www.sqlite.org/isolation.html) and [WAL](https://www.sqlite.org/wal.html).

**Boundary:** PR #23 still reads `MAX(attempt)`, current rows and prior effect rows in multiple autocommit statements; integrate its stricter causal rules **inside a consistent read transaction**. An integrity hash chain without a trusted external anchor detects accidental corruption, not malicious rewriting. Watcher status transition and event journal persist in separate SQLite transactions: delivery is *at least once/at most once per local DB cursor depending on crash position*, never globally atomic or exactly once. Build a durable alert outbox with idempotent sink to close this observation gap.

## 31. OBS-011 — progress is not liveness, call-start or model self-report

**Confirmed code-level exposure:** `progress_receipts` previously included all frontier events except `worker.heartbeat` and `run.accepted`. Therefore a worker repeatedly emitting `worker.started` or `llm.request_started`, without completing an operation, could reset its progress clock forever. This was a source-level false-negative in `ALIVE_NO_PROGRESS` detection.

**Minimal fix in this branch:** the progress clock now accepts only explicit successful *stage boundaries* from the known worker source: `worker.progress`, `llm.response_received`, `tool.effect_acknowledged`, `tool.effect_not_executed`, `approval.resolved`, `run.reported_completed`, `run.reported_failed`. Every one is still a **reported**, untrusted event; none by itself certifies successful external execution. `worker.started`, `llm.request_started`, `worker.heartbeat`, `run.accepted` do not reset progress. No event means the first receipt is the baseline. Four regression cases: repeated start, repeated LLM begin, legitimate progress and fresh heartbeat with no progress.

**Limits / alternatives:**
- A complete stage's report can still be spoofed by a compromised emitter. Trusted-progress requires authenticated producer hooks, monotonic stage revision, gateway matching IDs, and separate ledger verification.
- Explicit `llm.response_received` from an independent provider/gateway source cannot currently refresh a worker-only progress timer if any `worker.*` source exists. This is conservative; implement `worker_progress_age` and `provider_response_age` as two different clocks, not a blended liveness proof.
- An LLM stream can legitimately remain active with no final response for a long tool call; give each stage a configured deadline and last-byte telemetry **without** equating token deltas with completed milestones. `PAUSED_APPROVAL`, `RATE_LIMIT_BACKOFF`, `WAITING_IO`, `BUSY_COMPUTE` and `STALL_UNKNOWN` need distinct budget/lease logic.
- In an uncertain effect state, the `EFFECT_IN_FLIGHT` or reconciliation priority remains above `ALIVE_NO_PROGRESS`. A heartbeat must never make a mutation retry safe.

**Evaluation gate:** synthetic 30-agent stream with independent source-local sequence, plus signed owner-fenced run and time-in-stage metrics; count false positives and false negatives against a ground-truth deterministic simulator. Do not set numerical reliability/SLO targets until a baseline is actually measured.

## 32. Standards-backed instrumentation validation (OTel GenAI / Weaver)

The recent OpenTelemetry engineering writeup [Building an Agent Harness for OTel Instrumentation with GenAI Semantic Conventions and Weaver, 2026-11-12](https://opentelemetry.io/blog/2026/agent-harness-genai-instrumentation/) gives an unusually relevant negative lesson: early multi-agent generated telemetry was sometimes incorrectly approved by a reviewing model, until the team compared emitted traces against the GenAI registry using Weaver live-check. It also notes that closed CLI/internal execution cannot be observed via hooks which the framework does not expose. This applies to Hermes' **unobserved** surfaces and GPT browser integration.

**ADR-028 (P1):** a future optional OTLP exporter must be **a projection from the canonical diagnostic envelope**, not a second task/effect ledger. For each vetted callback, map a verified operation/attribute to the active semantic-convention registry version, include safe `trace_id`/span lineage, tool-call ID and stage outcome class, and preserve known unknown-causality; use minimal no-content metadata by default. `gen_ai.tool.call.id`, model request id, role and token counts may come from different sources with different trust tiers. Never serialize model messages/tool arguments/raw browser DOM by default, even if the registry permits them.

**Conformance acceptance:** capture synthetic OTLP telemetry from injected Hermes hook events; run registry/lint validation with Weaver live-check and a project-specific rule that forbids success from an unverified claim; reject `type_mismatch`, missing required correlation fields, hidden dropped spans and sensitive content exposure. Publish exact instrumentation version, registry version, source code commit, test fixture hash, violation count and reviewer verdict. No fabricated 100% coverage when the framework does not expose internal events.

**Cost/operability:** prefer one low-cardinality span per authoritative worker/provider/tool stage, source-level sequence gaps in logs, sampled detail only for high-volume safe read operations, and full fidelity for significant approval/effect/lifecycle transitions within strict storage budgets. `worker_id`, task IDs and URLs must not become unbounded metrics labels. OTel trace sampling must not cause a diagnostic ledger to silently discard mandatory effect reservations; telemetry and the durable ledger have separate retention/consistency obligations.

## 33. API integration P0 review: competing idempotency and SSE contracts

At audited source revisions, the four candidate `gateway/platforms/api_server.py` PRs (#4/#5/#6/#11) conflict in actual behavior, not only in diff hunks.

| Finding | Proven source code mechanism | Risk | Gate/owner |
| --- | --- | --- | --- |
| API-001: keyed SSE bypass | PR #4 enters `if stream` and dispatches `_run_agent` before reaching a non-stream-only `Idempotency-Key` guard | same keyed streaming operation may run twice on disconnect/retry | Use PR #11's reject-keyed-SSE preflight unless a durable resumable contract exists; test agent call count stays zero |
| API-002: failed cache execution retried | PR #5 `IdempotencyCache.execute` removes the active key in `finally`, caches success only; regression test expects second `compute_coro` after exception | runner exception after committed external effect can be blindly retried | sticky unknown-effect tombstone with trusted reconciliation; test side-effect counter remains one |
| API-003: cross-principal scoping | PR #5 cache key is endpoint+raw key; fingerprint uses full body and optional session, but not an authenticated principal | in multi-principal deployment an identical key/body can reuse a result across callers | trusted principal scope or explicit single-principal enforced contract, with isolation test |
| API-004: API error-code incompatibility | #4 proposes 422 for payload mismatch while #5/#6 propose 409; in-flight duplicate may JOIN or fail | clients can't implement one safe recovery protocol | publish versioned 409/422, 503, SSE error and retry policy after one owner arbitration |
| API-005: uncertain effects across process loss | #4/#5/#6 are process-local guards even when good single-flight behavior is achieved | process restart can lose memory fence | durable ledger in canonical task/effect control plane, no untrusted retry |

API-001 and API-002 are **confirmed source paths in draft code**, **not confirmed live incidents**. API-003 is a conditional security risk depending on the actual authentication topology. Review comments were sent to PR #4 and #5; no peer-owned `gateway/platforms/api_server.py` was changed in this branch. Preserve strong pieces of all candidates through a single integration branch and negative test suite, rather than merging four handlers in sequence.

**Integration hard gate:** replicate same-key/same-principal single-flight; same-key/different-principal isolation; changed body conflict; request before dispatch validation; SSE disconnect with unknown effect; thrown runner error after external write; two-process restart; known provider receipt reconciliation; stable response IDs; correct error response without raw secrets; and 30-agent 429 backoff fairness. Every check must be tied to the *final combined head*, not to one author's draft PR. Separate browser/UI capability checks from API idempotency.
