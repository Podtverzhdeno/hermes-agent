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

На локальной изолированной копии нового модуля выполнено `PYTHONPATH=. pytest -q tests/gpt_companion/test_journal.py`: **56 passed** (локальный Python 3.13.5; минимальная поддерживаемая Hermes-версия Python 3.11 требует отдельной проверки в CI); проверки: replay, conflict, sequence gap, reordering, delayed backfill cannot refresh liveness, heartbeat-only stagnation, invalid clock, unknown effect, approval, false completion, heartbeat vs progress, per-attempt isolation, reason code, strict redaction, chain mutation, 32 competing writers, conflicting terminal sources, CLI fail-closed import and redacted errors. Это **unit tests**, не реальный live integration smoke и не полный regression suite репозитория. При переносе в GitHub перепроверить content/hash файлов и CI PR.

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

### ADR-022: Противоречивые terminal reports одного источника (P0 implemented)

Нельзя выбирать последний красивый статус: если один source сообщает `run.reported_failed`, затем `run.reported_completed` в том же attempt, либо присылает `worker.progress` **после** terminal report, состояние признаётся `TRACE_INCOMPLETE`, запрашиваются согласование/сопоставление source-локальных событий и причины нарушения жизненного цикла. Событие `worker.stopped` после terminal допускается как нормальное завершение процесса. Никакого автоматического восстановления на основании последнего сообщения.

### ADR-023: Crash-before-commit и конкурентные процессы (P0 synthetic regression)

Добавлены `tests/gpt_companion/test_process_recovery.py`: дочерний процесс в реальной отдельной ОС-процедуре изменяет SQLite row внутри `BEGIN IMMEDIATE`, затем аварийно завершает себя через `os._exit(73)` до commit; повторное открытие БД сохраняет исходную chain-интегральность. Отдельная проверка запускает 8 независимых Python процессов для безопасной одновременной записи разных source. Это **не** тест реального выключения компьютера, дискового контроллера/FS flush, 100-процессной нагрузки или распределённой работы.

## 15. Журнал контрольных проверок

Сводка доказательств, известных рисков, устранённых дефектов и оставшихся блокеров — [`GPT_COMPANION_QA_LOG_20261122.md`](./GPT_COMPANION_QA_LOG_20261122.md). При будущих исправлениях агент обязан обновлять запись и указывать exact SHA, а не только количество тестов.

---

## 16. Causal safety hardening — review 2026-11-22 (stacked on PR #12)

**Статус:** реализовано в изолированной ветке `audit/gpt-companion-causal-failclosed-v2-20261122-a13`; тесты добавлены, результаты CI на точном HEAD должны быть проверены отдельно. Это **не** утверждение о production-интеграции. Базовая ветка: PR #12, head на момент ветвления `586a3e5436289f9c56ad69eefb53893ed11eff67`. В main реализации GPT Companion по-прежнему нет до одобренного merge.

### 14.1 Обнаруженные причинные ошибки

**C-01 / P0 / confirmed by source:** `EventJournal.assess` выбирал `MAX(attempt)` и анализировал внешние эффекты только последней попытки. Сценарий: A#1 зарезервировал GitHub write, потерял ответ, A#2 начал новую попытку; диагностический ответ A#2 мог стать `RECENT_TELEMETRY` при незакрытой операции A#1. Это не обязательно означает реальный повтор записи (модуль read-only), но создаёт опасную операционную иллюзию. **Fix:** сканирование неразрешённых резервирований *предыдущих* попыток, ключ `(run_id, attempt, action_id)`, результат `unresolved_effects_prior_attempts`, приоритет `NEEDS_RECONCILIATION` над видимой активностью новой попытки. Подтверждение новой попытки **не** закрывает старую.

**C-02 / P0 / confirmed by source:** `tool.effect_acknowledged` от другого `source` снимал pending effect, хотя `sequence` двух эмиттеров несопоставим. В отсутствие доверенной причинной связи нельзя доказать, что подтверждение относится к зарезервированному эффекту, даже при совпадении `action_id`. **Fix:** cross-source acknowledgement остаётся `NEEDS_RECONCILIATION`; `approval.resolved` от другого эмиттера не снимает `pending_approvals` и помечает trace неполной. Это консервативная мера V1: будущая доверенная связь будет валидироваться у Autopilot ledger, а не угадываться по metadata.

**C-03 / P1 / confirmed by source:** при запоздавшей доставке двух terminal-событий одного источника `last_terminal` выбирался по sequence, но `reason_code` — по обратному *порядку получения*. Причина могла относиться к **другому** отказу. **Fix:** причина и тип терминального события берутся из одной записи с максимальным source-local sequence.

**C-04 / P1 / detected concurrently in base PR #12:** системные часы могут идти назад. Обновлённый код базового PR #12 уже реализовал `clock_reversed`, `CLOCK_SKEW_DETECTED` и `CHECK_MONOTONIC_CLOCK_AND_TIME_SYNC` (ADR-020). При интеграции обнаружено несовпадение нового названия и тестового контракта; наш дублирующий обработчик удалён, тесты приведены к базовому контракту. Возраст по-прежнему ограничен нулём, но diagnosis явно сигнализирует об аномалии времени.

**Критические ограничения fixes:** диагностические ack/cross-source события остаются **неаутентифицированными**. Даже ack того же источника не равен подтверждённому receipt провайдера. `assess` не вызывает внешние инструменты. Untrusted telemetry не даёт права менять status в task ledger. Неподписанный hash-chain журнала не защищает от удаления всей базы или хвоста цепочки. Прямой вызов `assess()` не выполняет автоматическую глобальную `verify_chain()`; требование к потребителю — сначала integrity gate (как в CLI), либо будущий API возвращает explicit integrity state.

### 14.2 Инварианты, обязательные для всех десятков агентов

| Инвариант | Триггер сбоя | Запрещённое действие | Правильный выход |
| --- | --- | --- | --- |
| I-01: неизвестный эффект переживает смену attempt | process crash после reservation | blind retry, другой agent пишет повторно | read-back provider, ledger reconcile |
| I-02: actor identity ≠ строка `source` | spoofed source / несколько вкладок | доверять approval по event metadata | authenticated emitter principal + scoped grant |
| I-03: cross-source события не имеют локального total-order | ack из второго потока | считать `sequence=20` «после» seq другого агента | связать через доверенный `action_id` + provider receipt |
| I-04: событие task terminal ≠ verified final outcome | GPT отвечает «готово» | закрыть DAG / merge | exact SHA + независимые CI/artifact checks |
| I-05: поздний ack не обновляет живость worker | queued outbox replay | выдавать worker свежий lease | проверка supervisor, актуальный fence |
| I-06: часы наблюдателя могут ошибаться | NTP rollback/suspend | сбросить таймер до нуля без алерта | CLOCK_SKEW_DETECTED + monotonic runtime probes |
| I-07: lease/fence проверяют перед *каждым* write | lease expired / duplicate owner | cherry-pick/commit старого worker | re-authorize на current resource token |
| I-08: неразрешённый эффект блокирует повтор во всех дочерних задачах | retry fan-out | независимый повтор операции детьми | блокировка на provider action/resource id |
| I-09: телеметрия не должна включать содержимое переписки | browser/plugin ingress | хранить prompts/cookies/tool payloads | allowlisted metadata + redaction before ingress |
| I-10: нет репорта без версии доказательств | CI от старого HEAD | заявить green | exact SHA+run id+commit+timestamp |

### 14.3 Слои причинности / внедрение event contract v2 (не реализовано)

Для интеграционного v2 proposal (не расширять v1 без миграции): `project_id,task_id,run_id,attempt,agent_instance_id,lease_id,fence,resource_key,stage,action_id,provider_request_id,provider_response_id,trace_id,span_id,parent_span_id,source_seq,emitter_principal,observed_at,received_at,evidence_ref,schema_version`. Каждое поле классифицируется по privacy/security, происхождению и доверенности. Следует отделить **наблюдаемые**, **подписанные провайдером** и **утверждённые control-plane** значения; избегать «универсального» dict, который позволяет агентовским полям переопределять системные. В v1 сохранять metadata-only schema.

Допустимые переходы для *внешних эффектов* в доверенном ledger: `PROPOSED → APPROVED → RESERVED → DISPATCHED → CONFIRMED`, либо `UNKNOWN_OUTCOME → RECONCILING → {CONFIRMED,NOT_EXECUTED,REQUIRES_HUMAN}`. Переход `DISPATCHED → NOT_EXECUTED` запрещён только на основании timeout или отсутствия SSE final. Точки commit должны соответствовать **долговечным** транзакциям; `event.received` обозначает лишь фиксацию факта наблюдения.

Для GPT API stream: `stream.connected`, `response.created`, `response.in_progress`, `response.completed/failed`, `stream.disconnected` не эквивалентны `tool.effect.confirmed`. При наличии provider ID сначала retrieval/reconciliation; 429/5xx политики и Retry-After относятся к **новым безопасным** calls, а не к автоматически повторяемому write.

### 14.4 Единоличная зона владения при 12 конкурирующих PR

**GitHub-проверка на 2026-11-22 10:39 UTC:** в форке были открыты PR #1–#12. Перекрытия из `compare main...head` подтверждают, что `gateway/platforms/api_server.py` меняют по меньшей мере PR #4/#5/#6; PR #11 является дочерним к ветке API bridge. PR #9 реализует отдельный `gpt_bridge`, PR #12 — отдельный `gpt_companion`. На этом этапе нельзя автоматически выбирать одного из них как canonical bridge.

| Контракт / файл | Кандидаты | Владелец решения до merge | Merge gate |
| --- | --- | --- | --- |
| `gateway/platforms/api_server.py` | #4, #5, #6, #11 (наследует #4) | один назначенный API интегратор | consolidated diff + request/stream backward compatibility |
| `autopilot/*` | #1, #10 (наследует #1) | Autopilot owner | ledger invariants and fence tests |
| `gpt_bridge/*` | #9, API bridge PRs | GPT Bridge integrator | выбрать один contract path, проверить trace + SSE preflight |
| `gpt_companion/*` | #12, этот stacked audit | GPT Companion owner + независимый reviewer | 100% safety regressions + wheel integration |
| `pyproject.toml` | #1, #2, #9, #12 | packaging integrator | preserve all necessary package includes without duplicate imports |
| `docs/sdd/*` | #5–#9, #10, #12, audit | documentation owner | сохранить ADR и incident findings, не брать чужой документ целиком |
| `acp_adapter/*` | #3 | ACP owner | no permission/cache leakage across sessions |

Интеграция должна использовать **один** manifest с immutable candidate SHA, base SHA, author, file ownership, dependencies, verification status, approved changes, conflict decisions, rollback refs. Никакой агент не изменяет чужой PR head ради «быстрого исправления» без explicit handoff. Автоматическое объединение всех 12 PR запрещено.

### 14.5 Экспертная оценка следующих вложений (не эмпирический benchmark)

Шкала по критериям 1–5: безопасность 35%, предотвращение неясных остановок 30%, реализуемость 15%, операционная стоимость 10%, интеграционная совместимость 10%; итог = 20× взвешенная сумма. `N/A` в метриках означает «не измерялось», а не нулевую деградацию.

| Идея | Безоп. | Диагност. | Реализ. | Цена | Совм. | Оценка /100 | Решение |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Cross-attempt unknown-effect fence | 5 | 5 | 5 | 4 | 5 | 98 | P0; implemented in stacked audit |
| Authenticated receipts + single effect ledger | 5 | 5 | 3 | 3 | 4 | 88 | P0; blocked on adapter & owner contract |
| Causal trace graph + stage-specific stop codes | 5 | 5 | 3 | 3 | 4 | 88 | P1; design first, no silent retry |
| Durable outbox + at-least-once dedup | 5 | 5 | 3 | 2 | 4 | 86 | P1; implement before 30-agent scale |
| Global quotas + fair admission + circuit breakers | 4 | 4 | 4 | 3 | 4 | 78 | P1 |
| Full browser DOM autopilot | 1 | 2 | 2 | 1 | 1 | 29 | Reject |

Обязательное сравнение после реализации: p50/p95/p99 ingest latency, WAL SQLITE_BUSY rate, unknown effects per 1000 attempts, stale-fence write attempts blocked, mean time to explain stop, time to reconcile ack-loss, false-success incidents, redaction leaks (zero tolerated). Отчёт с реальными samples по нагрузкам 1/10/30/100 workers и repeatable fixtures. Нельзя делать вывод о производительности по unit tests.

### 14.6 Fault injection / независимая проверка

Тестовый контракт в `tests/gpt_companion/test_causal_safety_regressions.py` включает (a) prior attempt outstanding write, (b) same action id reused by newer attempt, (c) late but causally ordered ack on original attempt, (d) cross-emitter effect ack on active attempt, (e) cross-emitter effect ack on old attempt, (f) cross-emitter approval reply, (g) late terminal reason mix-up, (h) NTP wall clock rollback, (i) latest failure with clean history. **Факт наличия теста не равен прохождению теста.**

Предстоят независимые сценарии: kill после отправки GitHub POST до ответа; webhook duplicate/tamper; replay старого worker после потерянного lease; backlog > local quota; полный диск; SIGKILL на SQLite COMMIT и restart; беспорядок трёх источников; bounded memory при 100k events; corrupted/tail-truncated journal; восстановление резервной копии; обновление upstream Hermes; wheel на Python 3.11; Windows supervisor/suspend; safe cancellation. Для каждого сценария обязателен observed state, expected state, evidence, pass/fail, verifier identity.

**Release blocking:** пока нет signed provider receipts, работающего локального MCP, exact-SHA CI и независимого ревью, разрешены только документация и offline read-only diagnostics. Ниже стоящий monitor не вправе переводить задачу в `SUCCEEDED`, делать повторный external write, либо переключать на auto-repair.

### 14.7 ADR registry

- **ADR-024 Accepted (in branch):** Сохранять нерешённые эффекты предыдущих attempts в run assessment; нельзя скрывать их «здоровой» следующей попыткой.
- **ADR-025 Accepted (in branch):** Cross-emitter ack/approval без доверенной цепи причинности не закрывает операцию или approval; консервативная reconciliation.
- **ADR-026 Accepted (in branch):** Terminal `reason_code` привязан к самому source-local latest terminal, а не к порядку доставки.
- **ADR-027 Superseded by base ADR-020:** проверяем защиту от rollback часов, но не создаём новую конкурирующую реализацию или имя status; отталкиваемся от `CLOCK_SKEW_DETECTED`.
- **ADR-028 Proposed:** central integration manifest и owner-file lock для параллельных PR; merge только после cut-over/canary и exact-SHA проверки.
- **ADR-029 Proposed:** для производственного трассирования использовать W3C Trace Context и version-pinned OpenTelemetry GenAI semconv без секретов в baggage; semantic version binding проверять в CI.

**Первичные источники для решений:** [W3C Trace Context](https://www.w3.org/TR/trace-context/); [OpenTelemetry GenAI SemConv](https://opentelemetry.io/docs/specs/semconv/); [OTel baggage security](https://opentelemetry.io/docs/concepts/signals/baggage/); [SQLite WAL](https://www.sqlite.org/wal.html); [OpenAI sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions); [OpenAI webhooks](https://developers.openai.com/api/docs/guides/webhooks). Их рекомендации не подменяют проверки реально установленного Hermes/ChatGPT-клиента.

**Integration update (2026-11-22):** после четырёх новых коммитов PR #12 исходная ветка устарела; аудит перенесён на `d522250470796cd24db31953b055c09414ddddf4` без удаления его per-worker liveness logic. В этом разделе оценки подтверждены по source review; тесты и внешняя CI ещё требуют проверки.

**Rebase for ongoing parallel work:** latest PR #12 base at this audit is `6a5ef0f4d27ce6d6d309ed20fe9335102eed9aab`; reviewed and overlaid causal fixes preserving additional base-code changes. Compare exact SHA again before merging.

**Арифметический QA audit:** матрица перепроверена по указанным весам 35/30/15/10/10; исправлены пять первоначальных ошибок суммирования (89→88, 89→88, 87→86, 79→78, 28→29). Оценки остаются экспертными, не экспериментально измеренными.

**Cross-agent SDD collision QA (2026-11-22):** обнаружена коллизия ADR-016..020 с новыми ADR PR #12; дополнения перенумерованы в ADR-024..029, а не переопределены. CI 53 passed/1 failed на Python 3.11/3.13 выявил конфликт имени clock state с новым тестом PR #12; исправлен код, синхронизированы контракт и regression cases. Повторное CI обязательно для нового HEAD.

### ADR-030: Fingerprint of unknown effects across attempts (P0, implemented in stacked audit)

Read-only `StatusWatch._fingerprint` previously omitted the new field `unresolved_effects_prior_attempts` from the event diagnosis. If an already incidented run gains another unresolved external write from a past attempt, the state string `NEEDS_RECONCILIATION` need not change and the watcher could silently suppress that transition. Fix: include stable sorted prior-effect metadata in the fingerprint. Test `test_status_watcher_records_second_prior_attempt_effect` checks that two effect reservations with unchanged overall status produce two durable status transitions. No network, no effect dispatch. This change is stacked on PR #12 and must not be deployed without the PR #23 journal schema change.


### ADR-031: Cross-attempt sequence holes remain visible (P0, implemented in stacked audit; offline CI pending)

**Finding C-05 / source-reviewed:** `EventJournal.assess` originally tested `missing_sequences` **only for the highest numbered attempt**. If an old attempt contained `source:sequence` values 1 and 3 (with event 2 lost) and a new attempt started, the new worker could look healthy even though the old gap might conceal a reservation, failed write or terminal report. Merely incrementing `attempt` must not erase causal uncertainty.

**Fix:** when selecting the latest attempt, run a grouped SQL query on all *earlier* `(attempt, source)` streams and calculate `sum(MAX(sequence)-COUNT(*))`, relying on unique `(source,run_id,attempt,sequence)` index invariant. New additive diagnostic field: `missing_sequences_prior_attempts`. If nonzero, return `TRACE_INCOMPLETE` and `FETCH_MISSING_EVENTS`, except a currently known unresolved effect retains higher-priority `NEEDS_RECONCILIATION`/read-back. An old event that arrives later may repair the gap but does not refresh the newest worker's heartbeat. Include the prior gap counter in `StatusWatch` transition fingerprint so partial gap repair is visible even when `TRACE_INCOMPLETE` remains unchanged.

**Tests introduced:** `test_missing_sequence_in_earlier_attempt_does_not_disappear`, `test_prior_missing_event_has_lower_priority_than_unresolved_write`, `test_watcher_tracks_partial_repair_of_prior_attempt_sequence_gap`. They assert multi-attempt state, priority and durable status transitions after late backfill. Actual passing result requires the GitHub Actions jobs on exact head SHA; creating test code is not execution evidence.

**Scale caveat:** grouped SQL scan grows with prior attempt history and is safe for an offline inspector but unbenchmarked for 100-worker high-volume polling. Before deploying a continuous observer, measure query p95 and DB lock rate under 10/30/100 worker replay; consider a materialized per-stream frontier/holes table with correctness-preserving recovery if needed. Do not optimize by ignoring prior gaps.

**Interoperability reference:** see [Hermes Browser Extension compatibility audit](./HERMES_BROWSER_EXTENSION_INTEROP_2026-11-22.md). The externally maintained extension v0.4.1 claims Hermes Agent >=0.22 support, while this fork's main declares v0.6.0. Until an installed runtime/version handshake is verified, local browser/ChatGPT integration remains disabled and no live monitoring is claimed.


### ADR-032: Conflicting duplicate effect reports never discharge a write (P0, implemented in stacked audit)

**Finding C-06 / source-reviewed:** the initial journal only kept the *last* reservation and *last* acknowledgement for an `action_id`. Multiple acknowledgements for the same action could be contradictory, but if the last acknowledgement matched the last reserving emitter, `reserved` became empty and the incident was reduced to generic `TRACE_INCOMPLETE`, losing the explicit unresolved external effect. A duplicated reservation from a different source could create the same ambiguity. In a many-agent workflow this obscures the need for direct read-back and encourages accidental retry.

**Fix:** maintain an `effect_conflicts` set for duplicate reservations / resolutions in the same attempt; never let the last arrival silently resolve an ambiguous action. The action remains in `unresolved_effects`, and state is immediately `NEEDS_RECONCILIATION`. This is *diagnostic conservatism*, not a claim of an actual duplicate external API effect. The system must eventually distinguish delivery duplicates from true duplicate executions through authenticated provider receipts and a trusted action ledger.

**Tests:** `test_duplicate_ack_order_must_not_mask_uncertain_effect` permutes three source-local and cross-source messages through all six delivery orders, `test_duplicate_reservations_remain_unresolved_even_after_ack` covers mixed reservations, `test_single_same_source_resolution_is_not_false_duplicate` prevents unnecessary alarms on a normal same-source ack. The results require exact SHA CI evidence before release.

**Scale and trust:** The extra Python set is proportional only to distinct conflict actions in the selected attempt; historical attempt query cost is discussed in ADR-031. No browser/GPT content is recorded. Even a perfect telemetry record is not a trusted third-party effect confirmation.


### ADR-033: Worker stop is not the final task outcome (P0, implemented in stacked audit)

**Finding C-07 / confirmed by source:** the diagnostic selected the highest-sequence event among `run.reported_completed`, `run.reported_failed` and `worker.stopped`. A normal `worker.stopped` after an explicit failure could overwrite the useful failure signal and `reason_code` with generic `STOPPED_UNCONFIRMED`. It could likewise hide that a purported completion still required independent artifact verification. This is especially damaging when dozens of agents hand off context and the operator asks **why** a run stopped.

**Fix:** distinguish *task report* (latest source-local `run.reported_completed` or `run.reported_failed`) from *worker process lifecycle* (`worker.stopped`). Prefer explicit task report if present; otherwise preserve `STOPPED_UNCONFIRMED`. Do not turn a reported completion into verified success. Existing contradictory report checks still apply, so `failed→completed` in one attempt remains `TRACE_INCOMPLETE`, not success.

**Offline regressions added:** `test_worker_stopped_does_not_erase_reported_failure_reason`, `test_worker_stopped_does_not_erase_completed_verification_gate` and `test_worker_stopped_without_run_report_stays_unconfirmed`. Exact SHA CI required before merge.

**V2 contract:** task outcome and worker lifecycle should become separately structured fields (`reported_task_state`, `worker_process_state`) and not compete for a single last-terminal slot. A trusted verifier alone may promote a task to success; worker exit codes and model text are evidence pointers, not approval.


### ADR-034: Duplicate approvals do not silently grant authority (P0, implemented in stacked audit)

**Finding C-08:** within the highest attempt `approval_requests` and `approval_resolutions` were dictionaries keyed by `action_id` only. Multiple requests or multiple resolutions from distinct emitters overwrite earlier entries. The final last-writer-wins pair could remove `pending_approvals` despite an unresolved, ambiguous approval history. That is unsafe for browser actions, deployment, deletion, spending, and any step requiring a person.

**Fix:** track `approval_conflicts` for repeated requests or repeated resolutions, preserve the action in `pending_approvals` and classify the contradictory trace as `TRACE_INCOMPLETE`, even if a last same-source reply appears ordered. Cross-source approval messages remain untrusted in V1; a v2 verifier may recognize an authenticated reviewer principal, durable grant ID, intended resource and scope. The journal itself **never** authorizes or executes an action.

**Tests:** duplicate requests from multiple emitters, duplicate resolutions and a normal single-source pair. Distinguish telemetry conflict from authorization: *no* user-consent grant can be inferred from the new diagnostic.

### ADR-035: Run-reporter identity vs worker-process identity (P0, implemented in stacked audit)

**Finding C-09:** `terminal_sources` treated `run.reported_failed/completed` and `worker.stopped` as a single class. A coordinator's explicit run failure and a worker's normal stop would be incorrectly marked contradictory simply because they came from different emitters. Two distinct workers stopping could also trigger generic trace contradiction without an actual conflict in run outcome.

**Fix:** source conflict applies to **run reports** only. `worker.stopped` remains independent process lifecycle evidence and may coexist with a run report from another authenticated source. Two different *run reporters* are still contradictory and must be reconciled. This fix is coupled with ADR-033, which ensures a stop does not erase a reported failure or a pending verification gate.

**Tests:** cross-emitter coordinator failure + worker stop remains `REPORTED_FAILED`; two separate run reporters remain `TRACE_INCOMPLETE`; multiple worker stops without task report remain `STOPPED_UNCONFIRMED`.

**Future model:** `{task_report, worker_processes[], controller_state, verified_outcome}` is preferable to flattening all terminal events into one scalar. A worker death does not prove the run failed; an LLM report does not prove the artifacts passed checks; a browser page rendering does not imply the provider committed an effect.

**Verification status:** code and test cases are committed to a stacked draft PR. No automatic background monitoring, deployed Hermes upgrade, or user/browser authorization has been conducted. CI must be checked at the final exact SHA before readiness claims.


### ADR-036: A busy database is not a corrupted database (P1, implemented in stacked audit)

**Finding C-10:** the newly added watcher caught every `sqlite3.DatabaseError` and always emitted `JOURNAL_INTEGRITY_FAILED`. This mislabeled normal SQLite lock/contention, storage exhaustion and I/O faults as corruption. For dozens of workers, `SQLITE_BUSY` is materially different from hash-chain tampering or `SQLITE_CORRUPT`: the operator would otherwise waste effort on the wrong repair.

**Fix:** use SQLite primary result code (mask extended error code with `0xFF`) and metadata-only, stable diagnosis: `WATCH_DB_LOCKED` for `SQLITE_BUSY/LOCKED`; `WATCH_STORAGE_FULL` for `SQLITE_FULL`; `WATCH_IO_ERROR` for `SQLITE_IOERR`; `JOURNAL_INTEGRITY_FAILED` only for `SQLITE_CORRUPT/NOTADB`; `WATCH_DB_UNAVAILABLE` for absent/unknown code. Do **not** copy SQLite exception text or filesystem paths into stderr output. All these are hard failures of the watcher, not evidence that a GPT model stopped.

**Tests:** table-driven SQLite code classification including unknown codes and one CLI injection of `SQLITE_BUSY` with a sensitive local path in error text, verifying only the normalized reason appears. Release metrics should distinguish lock wait p95, disk pressure, I/O faults and true journal integrity failures; do not automatically delete or rebuild the event DB.

**Future enhancement:** reason-code taxonomy must be shared with the operator dashboard and alert routing. A single `JOURNAL_INTEGRITY_FAILED` banner for all SQLite failures is unacceptable for incident diagnosis.
