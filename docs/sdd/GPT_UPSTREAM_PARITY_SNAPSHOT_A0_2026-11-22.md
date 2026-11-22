# ADR-A0-04: исходный аудит миграции Hermes к native Runs/Kanban (точные Git SHA)

Дата сравнения: 2026-11-22. Статус: READ-ONLY CODE INVENTORY / BLOCKING MIGRATION DESIGN. Данный документ НЕ утверждает, что upstream собран, установлен или тестирован на компьютере владельца. Код в main форка не обновлялся.

## 1. Снимки дерева и воспроизводимые ссылки

FORK = Podtverzhdeno/hermes-agent, branch main, SHA 7e9100901819ee44c16b4ddcb79a6bcb7909f591, дата исходного коммита 2026-04-01.
https://github.com/Podtverzhdeno/hermes-agent/tree/7e9100901819ee44c16b4ddcb79a6bcb7909f591

UPSTREAM = NousResearch/hermes-agent, branch main, SHA 0f602c5f6f18615632535251d62a2db74ce93b69, подтвержденный точный HEAD 2026-11-22, время изменений ветки постоянно движется.
https://github.com/NousResearch/hermes-agent/tree/0f602c5f6f18615632535251d62a2db74ce93b69

Сравнивались два Git Trees recursive=true (оба без truncation). Итоги:
- fork: 1 261 blob-path;
- upstream: 27 462 blob-path;
- common by exact path: 667;
- upstream-only paths: 26 795;
- fork-only paths: 594.
Число путей НЕ является числом необходимых code changes, package versions или отсутствующих функций. В upstream много приложений, assets, тестов и собранных plugins. Историческое происхождение веток по совпадающим путям не установлено: нужен git merge-base и diff в контролируемой копии.

По критически важным подсистемам (число blob путей):
- gateway: fork 33 / upstream 421;
- hermes_cli: fork 36 / upstream 909;
- agent: fork 20 / upstream 478;
- tools: fork 63 / upstream 405;
- tests: fork 391 / upstream 9 389;
- apps: upstream 5 120 (fork нет такого верхнеуровневого дерева);
- plugins: upstream 553.
Оценка стоимости только по общему числу файлов была бы недостоверной.

## 2. Структурно подтвержденные отсутствующие ключевые пути

Все пути ниже существуют именно в upstream@0f602c5f, но отсутствуют в fork@7e910090:
- gateway/platforms/api_server_runs.py
- gateway/platforms/api_server_run_idempotency.py
- gateway/platforms/api_server_authority_runs.py
- gateway/platforms/api_server_openai_routes.py
- gateway/platforms/api_server_response_admissions.py
- gateway/platforms/api_server_response_identity.py
- gateway/platforms/api_server_store.py
- gateway/run_api.py
- gateway/session_kanban.py
- gateway/kanban_watchers.py
- hermes_cli/kanban_db.py
- hermes_cli/kanban_diagnostics.py
- hermes_cli/kanban_ops.py
- hermes_cli/kanban_swarm.py
- hermes_cli/kanban_worker_client.py
- agent/kanban_stop.py
- agent/kanban_turn_recovery.py
- tests/gateway/test_kanban_recovery.py

Не переносить эти модули по одному без их реального dependency graph, DB migrations, session authority, access-control and tests. Это не самостоятельные файлы. Если набор этих функций появится в другой форме в старом форке, детектировать по интерфейсам, а не только именам; в текущем снимке нет указанных модулей.

Исходники по exact SHA:
https://github.com/NousResearch/hermes-agent/blob/0f602c5f6f18615632535251d62a2db74ce93b69/gateway/platforms/api_server_runs.py
https://github.com/NousResearch/hermes-agent/blob/0f602c5f6f18615632535251d62a2db74ce93b69/gateway/platforms/api_server_run_idempotency.py
https://github.com/NousResearch/hermes-agent/blob/0f602c5f6f18615632535251d62a2db74ce93b69/gateway/platforms/api_server_authority_runs.py
https://github.com/NousResearch/hermes-agent/blob/0f602c5f6f18615632535251d62a2db74ce93b69/hermes_cli/kanban_db.py

Точечно прочитанный upstream code:
- api_server_runs.py строка ~285–293 объявляет POST /v1/runs, GET /v1/runs/{run_id}, GET /events, POST /approval, /clarify, /steer, /resolve-unknown, /stop.
- api_server_runs.py ~768+ исполняет canonical admission, keyed scope, request fingerprint, durable reservation, session authority.
- api_server_run_idempotency.py имеет RunIdempotencyStore с UNIQUE(scope,idempotency_key) и durable SQLite status fields; при восстановлении необходимо сохранять owner pid/start и retention semantics.
- api_server_authority_runs.py защищает admission, run projection, stop и unknown-resolution через каноническую сессию.
- hermes_cli/kanban_db.py — многофайловая БД с board namespaces, tasks, runs, comments, events, claim identity, failure budgets; потребуется инвентаризация schema v1/v2.
- README/документация современного upstream согласуются с наличием Runs API, но установленные capabilities на Windows НЕ проверены.
- tool/browser_tool.py есть и в форке, и upstream, но путь/наличие файла не означает бинарную или семантическую совместимость; пересечения #13/#15 решаются отдельной интеграцией.

## 3. Необходимый migration blueprint для владельца

Вариант A (предварительно предпочтителен, условно): собрать новую изолированную ветку/рабочую копию от ЗАКРЕПЛЕННОГО ПОДДЕРЖИВАЕМОГО upstream release/tag, затем перенести отобранные авторские изменения форка с отдельными compatibility shims и тестами. Последний движущийся main не использовать как автоматическую production зависимость; выбор конкретного release/tag ещё не подтвержден. Нельзя разрушать текущую рабочую установку.
Вариант B: портировать десятки native Runs/Kanban модулей в старый fork. По наблюдаемой структурной разнице это высокий риск неполной authority/DB migration, и он допустим только при независимом dependency mapping.
Вариант C: сохранить старый fork временно, добавить только безопасную READ-ONLY GPT диагностику его существующего legacy API, но НЕ обещать canonical Runs/resolve-unknown. Это временный совместимый режим, не эквивалент A.

Решение A vs B должно основываться на реальном git merge-base, diff, тестовом образе, сохранении пользовательских patches и локальной схеме БД. Никакой автоматической миграции на основе одного сравнения деревьев.

## 4. Обязательная последовательность и отрицательные проверки

P0 snapshot: создать read-only inventory с локальной машины после отдельного доступа к Hermes workspace: version, HEAD SHA, Python dependencies, lock files, REST capabilities, DB schema_version, active agent sessions and release channel. Не выгружать secret files, cookies, credential stores и private chat. Сделать резервную копию БД/конфигураций с разрешением пользователя, проверить восстановление.
P1 migration inventory: git merge-base, range-diff, rename detection, привязка 594 fork-only путей к owner/domain; не считать все 594 пользовательскими правками.
P2 capability matrix: native /v1/capabilities vs legacy, run API status/event/request idempotency, session ownership, approval, unknown recovery, stop/steer, Kanban durable state and API auth. Unknown/missing => отказ от опасного writer вызова.
P3 DB forward/rollback: readonly schema diff, transactional migration on cloned data, migration rollback exercise, permission scopes and encrypted secrets; test Windows-specific path, case sensitivity, WSL.
P4 browser lifecycle: integrate #13 redaction + #15 no-close external CDP, isolate human browser, fixed target identity, no secret-bearing logs.
P5 gateway admission: single implementation only, full permission tests, 409/422 safe contracts, nonstream+SSE idempotency, effect receipt uncertainty, orphan worker and stale fence handling.
P6 staged testing: targeted unit -> offline mutation fixtures -> full CI exact SHA -> Windows/WSL/Tunnel E2E -> 30/50/100 native agents / bounded isolated CDP pool -> chaos/rollback -> owner review.
P7 release: latest exact integrated SHA independent verifier, explicit human acceptance, canary, rollback with retained evidence and UNKNOWN_EFFECT reconciliation. No unreviewed auto-merge.

## 5. Точки конфликтов с текущими параллельными PR

- PR #4/#5/#6/#11 реализуют идемпотентность и обработку gateway в старом API, а upstream native run admission уже делает durable key and scope. Без планирования миграции можно внедрить две конкурирующие truth authorities. Их полезные preflight/privacy tests можно переносить; два production dedup stores — нет.
- PR #1/#10 создают prototype task ledger при существующем upstream Kanban. Одна authority.
- PR #9/#12/#16/#21/#25 и др. создают отдельные event stores. Для native Runs lifecycle их запуск обычно не нужен; оставить external effect receipt, transport health и независимую artifact evidence.
- PR #13/#15 меняют browser_tool.py старого форка, после миграции patch следует портировать на upstream version с E2E, не прямым cherry-pick.
- PR #27/#28 и ещё ~6 PR создают аудиторы; выбрать один проверяемый read-only инструмент на общих adversarial fixtures.

Эти пункты являются проектными решениями, НЕ выполненной интеграцией. Никакой код upstream не скопирован, зависимости не обновлены и локальная установка не затронута.

## 6. Контроль достоверности

Уверенность высокая в точных SHA, наличии файлов и структуре текущих trees; средняя в оценке сложности миграции (кода на зависимости ещё нет полного графа); неизвестная в состоянии фактического Hermes host. Следующее действие, требующее полномочий владельца: подключить workspace Hermes, а не посторонний vault.

Обязательная ссылка на этот документ в PR #28. Менять baseline после upstream обновления только через новый датированный snapshot с точным SHA.
