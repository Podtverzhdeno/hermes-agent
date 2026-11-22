# Hermes GPT Companion — журнал инженерной проверки

**Дата:** 2026-11-22  
**Область:** отдельная feature-ветка и draft PR #12, без изменений `main`  
**Источник доказательств:** проверенные файлы и offline тестовый прогон Python 3.13.5; CI на exact SHA — отдельно

## Проверенный объём

Модули: `gpt_companion/journal.py`, `gpt_companion/inspect.py`, `gpt_companion/watch.py`, `gpt_companion/__main__.py`; обратная совместимость `scripts/gpt_event_inspect.py`; тесты `tests/gpt_companion/`; описание запуска в `gpt_companion/README.md`; спецификации `docs/sdd/`.

Команда: `PYTHONPATH=. pytest -q tests/gpt_companion` из checkout GPT Companion → **56 passed** (локально, Python 3.13.5). Затем `python -m compileall -q gpt_companion scripts tests/gpt_companion`. Запуск установленного пакета на Python 3.11 и полный Hermes-suite остаются за CI/отдельным интеграционным стендом.

## Журнал причин, проверок и коррекций

| ID | Риск / дефект | Проверенная коррекция | Доказательство | Остаточный риск |
| --- | --- | --- | --- | --- |
| I01 | Несколько агентов одновременно записывают один файл | отдельный scope + PR + отсутствие прямых изменений `main` | branch compare + remote blob SHA | merge conflict в `pyproject.toml` с Autopilot |
| I02 | Потерян ответ после внешнего эффекта → опасный повтор | `EFFECT_IN_FLIGHT`/`NEEDS_RECONCILIATION`, нет автоматического retry | unit contract на reserve/ack | auth ledger ещё в другой ветке |
| I03 | Поздний backfill превращается в «живой» heartbeat | source-local frontier at receipt time | delayed sequence regression | реальная auth источника отсутствует |
| I04 | Бесконечные heartbeat маскируют отсутствие результата | отдельно liveness и progress | heartbeat-only regression | эвристические пороги — не SLA |
| I05 | Gateway с живыми событиями маскирует умерший worker A | worker-scoped freshness + partial outage | тесты на gateway и 2 workers | нужно подтверждение OS supervisor/lease |
| I06 | Clock/NTP шаг назад → ошибочная диагностика | `CLOCK_SKEW_DETECTED` | backward clock tests | нет durable monotonic time across restart |
| I07 | Повреждение БД принимается за отсутствие агента | `JOURNAL_INTEGRITY_FAILED`, no raw traceback | corrupt SQLite CLI test | нужно проверенное восстановление из backup |
| I08 | После отказа агент пишет «готово» | `AWAITING_VERIFICATION`, запрет trusted pass | false completion + terminal conflict tests | независимый verifier не подключён |
| I09 | CLI запускается из checkout, но отсутствует в installed wheel | `python -m gpt_companion` + packaging discovery | CLI subprocess unit | wheel-install CI требуется |
| I10 | Наблюдатель выдаёт повторные инциденты после restart | durable transition DB + fingerprint dedup | watcher restart/concurrent tests | stdout не guaranteed delivery, но history durable |
| I11 | SQL падение между записью и commit | SQLite rollback on abrupt child exit | subprocess `os._exit(73)` regression | не power loss/FS corruption |
| I12 | SQLite разные процессы одновременно пишут events | 8 independent child processes + WAL | process concurrency test | масштаб 100 процессов не проверен |
| I13 | Неполная трасса/out-of-order/идемпотентность | source sequence unique + replay + gap diagnostic | gap/replay/reorder tests | authenticated ingress/outbox не реализованы |
| I14 | Browser plugin не поддерживает fork | explicit version handshake/reject в SDD | fork v0.6.0 vs companion 0.22+ | реальная версия локального Hermes неизвестна |
| I15 | Локальная связь MCP недоступна | честно зафиксирован blocker | `Session terminated` из connector | live monitoring не запущен |

## Разграничение гарантий

**Подтверждено:** offline безопасный разбор metadata-only событий; SQLite WAL и hash-chain без криптографической аттестации; отличия run/worker/approval/effect statuses; 100 синтетических source в одном локальном прогоне; 8 отдельных процессов; ограниченный polling watcher; дедуп состояний и restart survival.

**Не подтверждено:** чтение происходящего в реальном ChatGPT; установлено ли browser companion расширение; интегрированы ли Hermes hooks и OpenAI/GitHub webhook; версия локального Hermes; работа на Windows 10/11 с локальным Tunnel; автономное исправление кода с последующей независимой верификацией; длительная работа при отсутствии электричества; криптографическая защита журнала от привилегированного администратора.

**Никогда не утверждать:** «уверенность 100%», «прод работает», «все проблемы устранены», «цикл наблюдения работает постоянно» без соответствующих внешних доказательств.

## Выпускные блокеры (не обходить)

1. Точный runtime Hermes + GPT-extension version/capability handshake и безопасное соединение MCP.
2. Доверенный authenticated event ingress + provenance и durable outbox.
3. Интеграция с Autopilot worker leases/approvals/effect reservations, не дублирование прав.
4. Верификация GitHub PR CI exact SHA, Python 3.11 package install и Windows/WSL2 smoke.
5. Операторская политика внешних write/deploy и отдельные approval gates.

Текущий безопасный статус: **review-ready isolated read-only prototype**. Развёртывание и автоматические исправления в этот отчёт не входят.
