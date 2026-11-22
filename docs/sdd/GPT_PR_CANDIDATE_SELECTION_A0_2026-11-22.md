# A0 Hermes × GPT — выбор архитектуры и конкурирующих PR

Дата: 2026-11-22. Статус: предварительное сравнение исходников и источников, НЕ окончательная проверка качества или разрешение merge. На проверенном этапе — 30 открытых draft PR #1–#30. До решения повторно проверить актуальные точные HEAD SHA, CI и взаимные ветки. Репозиторий: Podtverzhdeno/hermes-agent.

## 1. Подтвержденные основы современной Hermes

Официальная документация NousResearch описывает уже встроенный долговременный Hermes Kanban: отдельная SQLite-доска, задачи со статусами triage/todo/ready/running/blocked/review/done/archived, зависимости и комментарии, история попыток, изолированный OS worker для карточки, повторное захватывание упавших worker и dispatcher с тиком по умолчанию ~60 секунд. Завершение через kanban_complete сохраняет итог попытки и закрывает карточку в одной операции БД; heartbeat сообщает об активности, но не доказывает завершение внешнего эффекта. Для кода есть сохраняемый worktree; scratch-файлы без явных artifacts очищаются после завершения. У worker имеются HERMES_KANBAN_TASK и HERMES_KANBAN_BOARD. Все перечисленное — свойство описанного upstream, не доказательство, что оно присутствует в устаревшем user fork или установленной системе.

Источники: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-tutorial
https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes

Архитектурное правило: каноническое состояние задачи, ее владение, retry budget и зависимости должны оставаться за native Kanban после миграции; независимый GPT event observer — проекция, а не конкурирующая очередь. Прототип #1/#10 нельзя параллельно включать как второй production scheduler.

## 2. Карта ответственности и конфликтов

| Домен | Конкурирующие кандидаты | Обязательное условие интеграции |
|---|---|---|
| API обработчик, поток, идемпотентность | #4/#5/#6, #11 stacked на #4 | Выбрать одну реализацию; исключить blind retry после unknown external effect; сохранить строгую SSE-preflight и безопасный error contract |
| Браузер CDP | #13/#15 | Вместе сохранить внешний браузер и удалить из журналов секретные CDP URL/headers |
| Состояние задач | #1/#10 и native upstream Kanban | Только один authority; migration parity по точному SHA, не два scheduler |
| Разрешения и ACP | #3 | Отрицательные тесты изоляции сессий, scope, expiry, не доверять тексту навыка |
| Skill harness | #2 | Скилл декларирует пожелания, а эффект авторизует отдельная доверенная граница |
| Наблюдаемость и event journal | #8/#9/#12/#16/#17/#19/#21/#23/#25/#26/#30 | Один версионированный inbox и authenticated producer; ack, gaps, dedup, reconciliation, privacy |
| GitHub PR/CI integration audit | #14/#18/#22/#24/#26/#27/#28/#29 | Один поддерживаемый аудитор; чужие уникальные сценарии переносить в общий fixture set |
| SDD и документы | #7/#14/#19/#20/#22/#27/#28/#29 | Одна согласованная базовая архитектура, не тридцать взаимоисключающих решений |

Владелец репозитория назначает ответственного за каждый домен. Это не разрешение A0 самостоятельно сливать, закрывать или заменять PR других агентов.

## 3. Screening восьми кандидатов PR-аудитора по исходникам

Сравнение по чтению доступных файлов 22.11.2026: наличие ключевого слова не означает корректность, поэтому это только матрица для выбора финального эксперимента.

| PR | Файл | Обнаруженное в исходниках | Недоказанное |
|---|---|---|---|
| #14 | scripts/hermes_gpt_coordination_audit.py | GET и файлы/коллизии, offline snapshot | exact CI head и ancestry |
| #18 | scripts/gpt_integration_guard.py | GET, check SHA, ancestry, SQLite journal metadata | целесообразность дополнительного хранилища |
| #22 | scripts/gpt_pr_integration_guard.py | GET, stack/overlap, JSON/strict report | check-runs completeness |
| #24 | scripts/gpt_bridge_pr_gate.py | offline проверка stack/freshness | live retrieval и required check CI |
| #26 | scripts/gpt_bridge_pr_collision_audit.py | компактные offline file-коллизии | stack и CI provenance |
| #27 | scripts/gpt_pr_guard.py | live GitHub API, workflow runs at head SHA, bounded snapshot attempts | полнота проверки skipped/cancelled/required checks |
| #28 | scripts/hermes_pr_gate.py | live+offline, exact check-run SHA, skipped reviews, stack, failure artifact | API O(N), нет истинного cross-ref git ancestry, merge_ready всегда false |
| #29 | scripts/gpt_pr_stack_guard.py | dependency + semantic кандидаты | полнота CI-контракта |

Предварительные кандидаты для полноценного A/B на общих тестах — #27 и #28, но это не рейтинг 10/10 и не финальное решение. #24 имеет полезную идею независимой проверки stale evidence. Все сравнивать только при зафиксированном SHA, одинаковых параметрах и отсутствии live-side-effects.

Обязательные одинаковые fixtures: неизвестный outcome после эффекта; stale check SHA; зеленый reviewer со статусом skipped; отсутствующий или cancelled job; sibling vs stacked PR; rename и orphan base; 429/403 и pagination; рост 30-100 PR; Markdown injection через имя файла; изменившиеся PR heads между GET; отсутствующие real extension permissions; двойное событие с другим hash. Не смешивать успешность offline тестов с полнотой snapshot.

## 4. GPT Browser extension и Native Messaging: реальный контракт

Официальный Chrome Native Messaging: manifest включает allowed_origins с точным ID расширения без wildcard; host использует 32-битную длину сообщения и UTF-8 JSON по stdio. Документированный лимит host->extension — 1 MB, extension->host — 64 MiB; выпускать только малые метаданные, большие артефакты передавать по безопасной ссылке после проверки прав. Windows native host требует зарегистрированного manifest в реестре. Service worker должен проверять sender.origin / sender.url, очищать данные content scripts и не доверять странице как источнику прав. Порт может закрыться без остановки native work. Эти факты относятся к Chrome API, а не к доказанному установленному расширению Hermes.

Источник: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
Источник: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle

План проверки: найти настоящий manifest и установленную сборку, проверить protocol/version, origin, разрешения, host SHA, TLS/loopback, user consent, Windows/WSL boundaries, редактируемые scope и разрешение на CDP. Отрицательные тесты sender spoof, token in URL, permission replay, MV3 suspend, host restarts, broken pipe, duplicate ACK, browser close while job runs. Пока источник расширения недоступен, никакая реализация Browser/GPT не считается интегрированной.

## 5. Как атомарно диагностировать остановки

Обязательные отдельные поля UI/журнала: task/run/attempt/producer/fence, last heartbeat, last non-heartbeat progress, last durable event ACK, action_id и status, pending approval, exact commit/artifact SHA, reason_code, evidence_source, confidence, safe-next-action, owner и time observed. Never infer full hidden model reasoning.

Проверяемая неоднозначность:
- 60-секундный native dispatcher tick не равен зависанию;
- heartbeat без изменения artifact или tool checkpoint не равен прогрессу;
- сервис worker Chrome пропал, но Kanban worker жив: TRANSPORT_DISCONNECTED, не STOP_CONFIRMED;
- внешнее действие выполнилось, ответ потерялся: UNKNOWN_EFFECT, требуется сверка, не auto-retry;
- PR review зелёный, но skipped, а full CI fail: CHECKS_FAIL, не DONE;
- kanban_complete с текстовым резюме — самоотчет, не независимая artifact verification.

Отчёт о ложном успехе — более опасная ошибка, чем временный честный EVIDENCE_UNAVAILABLE. Полный список invariants, reason codes и acceptance G0-G9 см. GPT_HERMES_INTEGRATION_A0_2026-11-22.md.

## 6. Масштабируемый API audit, без самопорождаемых отказов

GitHub рекомендует webhooks вместо агрессивного polling, authenticated conditional GET (ETag/If-None-Match), сериализацию REST-запросов для профилактики secondary rate limit, Retry-After и x-ratelimit-reset. Для 30-100 агентов не строить бесконечный GET каждого PR на каждой секунде: webhook-подсказка + локальный индекс + bounded targeted reconciliation + периодическая точная проверка актуальных HEAD, explicit DEGRADED при 403/429. Без webhook допустим ограниченный read-only CI по расписанию, но его запускать и проверять отдельно. Сейчас PR #28 не является запущенным круглосуточным мониторингом.

Источники: https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

## 7. Невыполненные release gates

| Gate | Требование | Текущий статус |
|---|---|---|
| D0 | Исходники и установленная GPT extension плюс Windows host | BLOCKED: Local_WorkSpace Session terminated |
| D1 | Native Kanban parity с точным upstream SHA | BLOCKED в user runtime; upstream документация проверена |
| D2 | Один безопасный API handler, double-effect, keyed SSE, auth tests | BLOCKED: конкурирующие #4/#5/#6/#11 |
| D3 | Один надёжный event inbox+outbox с ack/reconcile | BLOCKED: competing journals |
| D4 | Chrome CDP ownership + credentials redaction в одной сборке | BLOCKED: #13/#15 надо интегрировать |
| D5 | Аудитор выбран на одинаковых adversarial fixtures и CI | PARTIAL: #28 offline; ещё не проведён A/B |
| D6 | Combined SHA full CI + permission review + E2E | NOT VERIFIED |
| D7 | 30/50/100 реальных concurrent workers, chaos/24h soak | NOT RUN |
| D8 | Rollback, canary и user acceptance | NOT RUN |

Это не утверждение о готовом production. Каждому агенту присваивать единую зону ответственности, immutable baseline SHA и проверяемые артефакты. Обновление прогресса через SDD/PR и исходный task_id, а не многочисленные текстовые заявления «всё готово».
