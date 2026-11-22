# ADR-A0-03: Hermes GPT Control Center — изолированный CDP без обязательного браузерного расширения

Дата: 2026-11-22. Статус: proposed target, release BLOCKED. Применимо к ранее выбранному пользователем направлению: не мешать обычной работе на устройстве, работать с GPT через отдельный оркестратор и авторизованный CDP lane, без обязательного Chrome plugin.

## Исторически известно, но не подтверждено сегодня

В предыдущей конфигурации Hermes применялся модельный маршрут web-chatgpt-high-cdp. Авторизованные владельцем direct-CDP canary на 14–15 ноября 2026 проходили успешно. Отдельный эксперимент Tunnel Web Companion включал Chromium extension, local Python bridge и queue, но пользователь позже просил отдельный Agent Control Center с наблюдением без браузерных плагинов. Успешный canary доказывает только прошлую связь конкретного пути, не 24/7 надёжность и не работоспособность актуального хоста.

Local_WorkSpace MCP сегодня первоначально завершился Session terminated, позднее вернул только workspace shelter с read/write — это НЕ доступ к Hermes, Windows installation, CDP host, расширению GPT или логам. Нельзя выдавать обзор GitHub за мониторинг установленного браузера.

## 1. Два контура, одна модель причинных событий

Контур А — Hermes:
- Native Kanban — authority для cards, assignee, status, dependency, run history, lease и task artifacts.
- Native canonical Runs API — authority для run status, durable admission, run_id, SSE, stop/approval/steer/resolve-unknown после feature detection.
- Agent-run cross-link использует идентификаторы run_id, task_id, attempt_id и provenance коммита; отсутствие уникального run_id не компенсируется догадкой по последнему открытому окну.

Контур B — GPT Web/CDP:
- отдельный Chromium user-data-dir / профиль и отдельный host process / таб, не повседневный браузер владельца;
- owner-authorized direct CDP with strong target identity, transport lifecycle and exclusive session lease;
- рабочий профиль и cookies локально защищены; не выгружать credentials, session cookies или raw DOM в централизованный журнал;
- инструменты взаимодействия с ChatGPT не считаются источником прав/истинного состояния Hermes. Отправленный ввод не является ACK исполнения, а DOM изменился не означает что внешнее действие Hermes завершено;
- если единственным путем является browser web, автоматизировать только явно разрешённые операции и не обходить аутентификацию/лимиты провайдера. При наличии поддержанного API предпочтителен поддержанный контракт.

Контур C — Agent Control Center (только проекция+разрешения):
- Python 3.12 + FastAPI / WebSocket + SQLite projection/checkpoint + React dashboard — возможный стек уже обсужденного приложения. Не запускать второй authoritative scheduler; SQLite UI проекция не изменяет native Kanban task status.
- Read-only adapters: native Runs SSE/status, Hermes Kanban, GitHub PR/CI, CDP lane diagnostics, trusted external-effect receipts.
- Writable control path отдельно: explicit user approval, CAS, scoped action, owner session, lease/fencing; контроллер не вправе менять GitHub main или выполнять side-effect по сырому LLM событию.
- UI отображает last owner, task/run/attempt, source+producer_id, last heartbeat, last real progress, active tool, cursor/ACK, checkpoint sha, failure code, confidence, safe next action. Версионированная диагностика, а не художественный пересказ внутренней логики модели.

Схема:

 Hermes native Kanban + Runs API -> read-only adapter ---------+
                                                              |
 Dedicated isolated Chromium/CDP -> transport adapter --------+--> Control Center projection
                                                              |         |
 GitHub CI + effect gateway receipts -> evidence adapter ------+         |
                                                                        v
                                                                review / scoped approval
                                                                        |
                                                   trusted Hermes tool/control API (not browser JS)

## 2. Почему десятки агентов требуют изоляции

Одна обычная браузерная вкладка не является multi-agent execution namespace. Конкурирующие авторы могут одновременно набрать текст, отправить запрос дважды, принять ответ другого run, закрыть вкладку, перезаписать историю или поменять профиль. CDP attach к одному браузеру сам по себе не даёт FIFO, fencing, idempotency, fair scheduling и гарантий принадлежности сообщения.

Рекомендация:
- один writer lease на конкретную идентичность CDP session/tab; остальные агенты читают безопасную проекцию статуса;
- распределить tasks native Kanban по agent/profile scope, хранить execution_generation и attempt независимо от таба;
- pool из выделенных изолированных профилей вместо запуска десятков неограниченных браузеров. Лимит pool не фиксировать без измерений CPU/RAM/login limits;
- одна команда на запись должна иметь action_id + request hash + external receipt; если вкладка зависла после нажатия Send, событие UNKNOWN_UI_SUBMISSION и RECONCILING, не повтор без удостоверения результата;
- новый worker после падения старого видит frozen attempt + stale fence; не наследует полномочия на tool-write только по тексту SDD;
- владелец обычного браузера сохраняет независимость: внешние human-owned Chrome/Edge/CDP sessions разрешены только opt-in и никогда не убиваются cleanup другого агента (#13 + #15 combined);
- не позволять отдельным browser workers менять GitHub branch/head без CAS, утверждённого ownership файла и проверки PR/CI.

## 3. Конкретная диагностика причин остановок

| Симптом | Типизированный инцидент | Доказательство | Допустимое восстановление |
|---|---|---|---|
| CDP WebSocket disconnected | CDP_DISCONNECTED | last protocol ACK, session ID | reattach, не re-submit |
| Попытка потеряла целевую вкладку | BROWSER_TARGET_GONE | tab identity mismatch | новое назначение tab по user consent, старый action UNKNOWN |
| Обычный пользователь закрыл свой Chrome | EXTERNAL_BROWSER_EXITED | ownership=external | не перезапускать и не менять его настройки |
| Изолированный browser worker умер | ISOLATED_PROFILE_WORKER_EXITED | PID+spawn timestamp+lease | новый fence, read-only reconcile, потом план |
| Login UI или auth challenge | GPT_AUTH_REQUIRED | typed DOM signal только локально | уведомление владельца, без обхода challenge |
| Сообщение набрано, но статус отправки неизвестен | UNKNOWN_UI_SUBMISSION | нет подтвержденного response identity | выяснить внешний outcome, не повтор |
| Hermes gateway restart | HERMES_UNKNOWN_OR_INTERRUPTED | native GET /v1/runs/{id} | соблюдать canonical recovery policy, не дублировать |
| Пользователь одобрил одну команду, но модель её переписала | APPROVAL_HASH_MISMATCH | new command digest | отказ до нового approval |
| Событие из старой вкладки/профиля | PRODUCER_EPOCH_STALE | producer_id+epoch | reject, no liveness refresh |
| Два агента записывают в один CDP target | TARGET_LEASE_CONFLICT | competing owner/lease | serialize, не скрывать потерю эксклюзивности |
| Host RPC упал, агент жив в native Kanban | OBSERVER_ONLY_FAILURE | Hermes status running | восстановить только read-only adapter |
| Модель молчит, heartbeat есть | HEARTBEAT_ONLY_STALL | progress_time vs liveness_time | reasoned probe / checkpoint, не blind rerun |

Вся диагностика должна различать OBSERVED, SELF_REPORTED, INFERRED и VERIFIED. Нельзя получить доступ к скрытым внутренним рассуждениям модели; объясняем наблюдаемые действия, транзакции, ошибки, решения по разрешениям и подтверждённый результат.

## 4. Security boundaries

- Separate user-data-dir с правами ОС только для владельца runtime, не экспортировать профиль/cookies.
- Native host/CDP не должен становиться универсальным безусловным bridge в shell/MCP. Для локального файлового write обязателен отдельный editor gateway с разрешенными roots и CAS.
- Любой вывод HTML/DOM/LLM — untrusted input, может содержать prompt injection, не владеет capability. Изолировать UI от business commands.
- Обязательная редукция телеметрии до event type/ID/time/hash, без prompt, hidden reasoning, tool arguments, URL с токенами, текстовых ответов и приватных данных.
- Failure trace persists receipt cursor and correlation IDs, но не credentials. Контент, если его нужно сохранять для независимой проверки, помещается в закрытое хранилище с управляемыми правами и отдельным согласием.
- Browser ownership: PR #15 retains externally attached CDP browser, #13 redacts CDP URLs; оба изменения обязательны совместно после тестов, ни один PR не даёт право на автоматический merge.

## 5. Fault-injection acceptance и состояние сейчас

G0: выявлены точные локальные источники control center/bridge, установленные версии, обязательные permissions, Windows/WSL tunnel. Сейчас blocked по Hermes workspace.
G1: native /v1/capabilities и кодовая миграция из stale fork verified на отдельной копии.
G2: 2 concurrent writers в одной вкладке не выполняют два tool effects, есть детерминированный lease conflict.
G3: browser send -> lost ACK, new worker -> no duplicate message/side effect до внешней сверки.
G4: separate Chrome stays separate, ordinary browser не закрывается/не захватывается; attached external CDP survives cleanup.
G5: protected profile credentials never appear in logs/PR artifacts; injected DOM prompt cannot mint write permission.
G6: reboot Windows, browser process, gateway restart, tunnel disconnect и active tool interruption; post-crash UI shows exact UNKNOWN state.
G7: 30/50/100 actual native agents with bounded browser pool measured CPU/RAM/latency, no unauthorized side effects and zero falsely verified complete.
G8: independent combined SHA test + human approval + recovery/rollback, rollback does not delete evidence.

Ни одно из G0–G8 не обозначено как успешно пройденное live. PR #28 содержит read-only audit code+SDD; реальное Control Center приложение и GPT web browser integration в текущем проходе НЕ запущены и не изменены.

**Решение:** начать с изолированного браузера без расширения как предпочтения пользователя, native Runs API и Kanban как authority; сохранить возможность существующего авторизованного direct CDP, но не давать ему прав на чужие профили или постоянные side-effects без владельца.
