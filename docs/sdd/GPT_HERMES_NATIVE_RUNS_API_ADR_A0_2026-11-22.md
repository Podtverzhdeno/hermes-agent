# ADR-A0-02: Hermes native Runs API — первичный источник состояния GPT-интеграции

Дата: 2026-11-22. Статус: ACCEPTED AS TARGET DESIGN; NOT DEPLOYED. Это решение отменяет раннюю гипотезу строить собственную параллельную очередь или дублирующий журнал всех стандартных run events. Подтверждено документацией современного NousResearch Hermes, НЕ проверено на установленном форке Podtverzhdeno/hermes-agent, main от 2026-04-01. Источники:
https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks

## 1. Почему это меняет реализацию GPT-расширения

Современный Hermes документирует durable admission/session authority и Runs API. Вместо "расширение читает ChatGPT DOM и оттуда восстановит все задачи" или "на каждый агент новый SQLite journal" нужен один клиент штатного API с feature negotiation. Надежный GPT-side panel показывает status+SSE projection, а не владеет состоянием. Если задача относится к многoагентной Hermes Kanban, native Kanban остаётся authority для карточки и child workers. Для конкретного run — native run admission/status.

Стандартные интерфейсы:
- GET /v1/capabilities: изучить support run_submission, run_status, run_events_sse, run_stop, run_unknown_resolution; не предполагать наличие.
- POST /v1/runs: только при разрешенном пользовательском действии, с уникальным 1–255 visible ASCII Idempotency-Key, привязанным к session/profile/auth credential и payload; сохранять run_id и ключ до реконнекта.
- GET /v1/runs/{id}: authority для состояния running, completed, failed, cancelled, interrupted, unknown, а также shutdown_requested_at. Ответ не равен proof внешних эффектов.
- GET /v1/runs/{id}/events: lifecycle SSE c run_id, event, seq и timestamp; выбирать события tool.started, tool.completed, subagent.start, subagent.complete, run.*. Отображать только allowlisted IDs, event kind, status, durations, numeric usage, safe reason. НЕ сохранять raw message.delta, rationale или tool argument/result preview. Любые content-bearing events оставлять на сервере, если отдельного пользовательского согласия на конкретные данные нет.
- POST /v1/runs/{id}/stop: состояние stopping означает запросить кооперативную остановку, НЕ означает terminated. Дождаться terminal run.* или GET status.
- POST /v1/runs/{id}/resolve-unknown: отдельный опасный control action; только authenticated owner, admission_id + execution_generation, capability run_unknown_resolution и согласие владельца. Он признаёт потерянный run interrupted и освобождает следующие в FIFO БЕЗ повторения неизвестной работы; не создает глобальную гарантию exactly-once и не отменяет необходимости сверить внешние эффекты.
- POST /v1/runs/{id}/steer: HTTP 200 значит guidance queued, НЕ модель прочитала. Следить за pending_steer в terminal status. Для остановленной, approval-paused или иной нерunning работы требуется 409, не слепой retry.

Документированные важные отличия execution mode:
- Canonical mode: durable admission identity для keyed requests. Legacy API: 5-минутный in-memory cache для nonstreaming и нет dedup streaming. Поэтому нельзя переносить гарантии canonical режима в любой старый билд.
- POST /v1/runs keyed create: 24-hour retention после последнего изменения состояния, exact retry 202 с тем же run_id; mismatch payload/key 409; FIFO и owner/session constraints. Это НЕ "exactly once forever".
- При gateway restart старый run может иметь unknown, что намеренно приостанавливает очередь. Современное control action resolve-unknown должно сначала идентифицировать auth scope/generation, не повторять tool effect.
- SSE и status должны согласовываться по terminal statuses; failed, cancelled, interrupted, completed — разные причины, в том числе shutdown/watchdog/iteration budget. Streaming Chat Completions может иметь HTTP 200 и последнюю ошибку в chunk, не надо интерпретировать 200 как OK.
- SSE event buffer имеет срок хранения: если данные недоступны после долгого отсоединения, пометить GAP и отдельно GET status; отсутствие event в replay не доказывает отсутствие tool call.

## 2. Пограничные состояния: что реально видит оператор

| Наблюдение | Причина/статус панели | Что делать |
|---|---|---|
| POST /v1/runs HTTP 202, run_id есть | ADMITTED; запуск мог ожидать очередь | сохранять run_id и idempotency key; GET status, не дублировать POST |
| Сессия выполняется, heartbeat и SSE растут | RUNNING; progress отдельно от ливнеса | в UI tool/worker checkpoint и actual verified artifact |
| SSE/Native Messaging pipe оборвался, GET status running | CLIENT_DISCONNECTED | подписаться повторно без новой run admission |
| Пропущены SSE seq / replay.truncated | OBSERVABILITY_GAP | backfill если доступен, GET current status, показать невозможность полной истории |
| В status есть shutdown_requested_at | GATEWAY_DRAINING | запретить создание новых эффектов, дождаться terminal |
| status interrupted после restart | RUN_INTERRUPTED | не трактовать как успех, проверить действие могло выполниться |
| status unknown, admission_id/generation | UNKNOWN_EXECUTION | остановить следующую работу, reconcile external side effects, при наличии разрешения owner resolve-unknown; никогда auto re-submit |
| /stop вернул stopping | STOP_REQUESTED | дождаться stop-confirmed; keep lease/owner info |
| /steer ответил 200, но pending_steer остался | STEER_QUEUED_NOT_CONSUMED | не выдавать за выполненный prompt |
| completion с partial=true или iteration exhausted | PARTIAL_OR_FAILED | не ставить VERIFIED_COMPLETED |
| run.completed но тесты/артефакты отсутствуют | SELF_REPORTED_COMPLETE | независимый verification gate; задача не выпущена |
| streaming response HTTP 200, final finish_reason error | FAILED_STREAM | status+SSE final frame, не зеленый HTTP 200 |
| native Kanban task blocked после failure_limit | KANBAN_WORKER_BLOCKED | kanban_show/runs/comments, конкретная ошибка spawn/permission, не бесконечный запуск |

## 3. Где ДОПОЛНИТЕЛЬНЫЙ журнал всё ещё необходим

Native SSE — лучший первичный источник run state, но для операционных доказательств нужны узко scoped источники:
- External side-effect ledger на доверенной границе tool gateway: действие, approval, fencing epoch, external receipt/confirmation, UNKNOWN_EFFECT reconciliation. Даже Hermes canonical admission не гарантирует exactly-once банковской операции или изменения GitHub.
- GPT клиент transport observer: браузер/Native Messaging connection, origin permission, last ACK/cursor, sanitized error code, версия расширения и host. Только метаданные, не содержимое ChatGPT.
- Independent artifact verifier: исходный git SHA / binary digest, проверенные тесты и среда, approval человека, попытка проверки.
- GitHub PR CI proof: exact HEAD SHA, независимый test workflow и skipped reviewer; A0 PR #28, не заменяет native run authority.

Если достаточно штатного Runs API+Kanban, необязательно создавать новый SQLite journal. Варианты #9/#12/#16/#21/#25 могут стать **плагином нормализации метаданных** и источником уникальных отрицательных тестов вместо новых конкурирующих prod-сторов. PR #30 содержит особенно релевантный read-only offline SSE нормализатор под реальную native event shape (event/run_id/timestamp/seq), но ещё не доказан как установленный browser integration — можно сравнить, переиспользовать отдельные контракты при согласовании версии.

## 4. Безопасность и свойства, которые нельзя вывести из telemetry

- Chrome Native Messaging это иной продукт, чем удалённый старый Hermes browser-extension controller. В upstream прежние /v1/browser-control и browser.extension_control удалены, для браузера используется browser_exec через CDP. Не возвращать deprecated control API.
- Native /v1/runs access требует bearer authentication; origin/CORS не заменяет авторизацию. Для чужих CLI/TUI/ACP sessions современный API возвращает permission_denied 409, а не захватывает session. Для работы с общей gateway session нужен штатный WebSocket prompt.submit, не параллельный Runs writer. Scope должен оставаться owner-bound.
- CLI/TUI reasoning stream и ответ модели не дают права серверу телеметрии тайно перехватывать содержимое диалога. Логи принимают только metadata allowlist; без пересылки cookies/prompts/keys/цепочек внутренних мыслей.
- Detect background child completion properly: у detached subagents финал может появиться в session history после конца parent SSE; родительский SSE не переоткрывается. Параллельная работа требует child task/card и отдельной истории, а не ожидания вечного parent stream.
- False-negative absence: source event might not arrive due buffer expiry, process crash, observer drop. Never infer effect not executed merely from missing event.

## 5. Версионированный план миграции stale fork

Gate R0: изучить local host/manifest, установленный Hermes --version + exact git SHA, native API host bind, auth settings, actual browser UI/plugin and permissions. Сейчас Local_WorkSpace MCP = Session terminated, поэтому BLOCKED.

Gate R1: выбрать целевой upstream tag and diff между fork main 7e910090 и target; тесты data migration Kanban schema, session authority, API, stored transcripts, ACP, CDP. Нельзя просто cherry-pick новую половину API поверх старого gateway без ее admission authority.

Gate R2: на изолированной test environment GET /v1/capabilities и /health/detailed; secure transport; capability negotiation (legacy fallback read-only); 401/403 unauthorized, CORS origin, expected feature flags. Не включать write-calls при отсутствии owner grant.

Gate R3: E2E admission + reconnect: 202 run_id, stream seq, tool errors, provider errors, stop, shutdown, restart unknown, reconciliation, explicit resolve-unknown with stale generation 409, no duplicate run or external effect; restart live host vs temporary trial state.

Gate R4: 30–100 concurrent native workers with separate Kanban boards/leases, agent death, stale PID, detached child, tool failure, 429 provider, lost subscriber. Quantitative acceptance targets must derive from environment, not guesses.

Gate R5: combined integration SHA and independent security E2E with owner; allow only staged canary; rollback disables new dispatch and protects immutable evidence.

**Current state:** SDD accepted target only; no code in PR #28 calls native Runs API, no changes merged into production, no live installed extension control, no claims of 24h background monitoring. Apply this ADR to constrain merging existing conflicting PRs.

## 6. Многoагентная идентичность: source_kind != producer_id

Дополнительный аудит PR #12: его отдельный SQLite observer использует UNIQUE(source,run_id,attempt,sequence) и вычисляет liveness по source. Если source означает категорию вроде worker, а десятки реальных worker имеют самостоятельные seq=1, то один worker теряется как sequence collision, а их время прогресса ошибочно смешивается. Схема допускает безопасную работу лишь если producer stream ID является уникальным и включает рабочую инкарнацию; нельзя подменять producer_id значением source_kind из неподписанного события. Нужны trusted producer_id, producer_epoch/fence, source_kind, scoped attempt/run и отрицательный тест двух producers одной категории с seq=1. В выбранной архитектуре native Runs SSE имеет отдельный run_id и seq; дополнительный journal нужен лишь для host/tool effect и должен иметь собственное доказуемое разделение производителей. Замечание на PR #12: https://github.com/Podtverzhdeno/hermes-agent/pull/12 (A0 comment 7078274443).

## 7. CDP target clarification from prior owner-authorized experiments

Direct-CDP canary of a web-chatgpt-high-cdp model route was observed in user project Nov 14/15 2026; this does NOT establish live status today. The owner later preferred an isolated Agent Control Center without required browser extensions or interference with ordinary Chrome. Consequently native Runs API is the authoritative Hermes execution lane while a separate opt-in CDP browser lane can remain a frontend/model transport. Do not confuse this lane with the removed legacy Hermes browser-extension controller. See [isolated CDP Control Center ADR](GPT_ISOLATED_CDP_CONTROL_CENTER_ADR_A0_2026-11-22.md).
