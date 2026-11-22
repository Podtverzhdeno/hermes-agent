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

**P0 — в этом изменении:** отдельный модуль `gpt_companion/journal.py`, безопасный разовый CLI `python -m gpt_companion`, тесты и package discovery `pyproject.toml` + offline unit tests; строгий allowlist, WAL, durable event ingest, дедуп, per-source seq gaps, conservative diagnosis, hash integrity check. Нет live-адаптера, tool calls, webhook endpoint, scheduled observer и обещаний непрерывного мониторинга. Состояния журнала не равны статусам task ledger.

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

На локальной изолированной копии нового модуля выполнено `PYTHONPATH=. pytest -q tests/gpt_companion/test_journal.py`: **42 passed** (локальный Python 3.13.5; минимальная поддерживаемая Hermes-версия Python 3.11 требует отдельной проверки в CI); проверки: replay, conflict, sequence gap, reordering, delayed backfill cannot refresh liveness, heartbeat-only stagnation, invalid clock, unknown effect, approval, false completion, heartbeat vs progress, per-attempt isolation, reason code, strict redaction, chain mutation, 32 competing writers, conflicting terminal sources, CLI fail-closed import and redacted errors. Это **unit tests**, не реальный live integration smoke и не полный regression suite репозитория. При переносе в GitHub перепроверить content/hash файлов и CI PR.

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
