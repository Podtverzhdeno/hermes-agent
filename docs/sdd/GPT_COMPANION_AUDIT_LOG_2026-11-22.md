# Hermes / GPT Companion — журнал расследования и фиксов, 2026-11-22

> Статус: engineering audit / draft branch, не live-monitoring и не проверка браузера. Записываются только проверенные факты, гипотезы и ссылки на код. Логи с текстом чатов, токенами и ключами запрещены.

## Реальный срез

- Repository: `Podtverzhdeno/hermes-agent`; fork of `NousResearch/hermes-agent`.
- Default `main` на момент чтения: `7e9100901819ee44c16b4ddcb79a6bcb7909f591` (upstream commit 2026-04-01). Нельзя считать его upstream HEAD ноября.
- GPT Companion находится в draft PR #12, head при ветвлении `586a3e5436289f9c56ad69eefb53893ed11eff67`.
- Открыты 12 draft PR (#1–#12); GitHub compare показывает пересечение `gateway/platforms/api_server.py` и `pyproject.toml`. Нужен назначенный integration owner, нельзя параллельно merge all.
- Local_WorkSpace MCP на попытке `list_workspaces` ответил `Session terminated`; локальные процессы, реальная extension установка, Obsidian и live log не проверены.
- `gpt_companion` на PR #12 — только offline untrusted diagnostic inbox, без producer auth, внешних эффектов, background monitor и independent verifier. Нельзя путать с production GPT bridge.

## Подтверждённые source-level наблюдения

| ID | Состояние до правки | Почему опасно | Принятое исправление |
| --- | --- | --- | --- |
| C-01 | `assess()` считал только `MAX(attempt)` | новый worker скрывает outstanding write старого | prior-attempt effect scan; `NEEDS_RECONCILIATION` |
| C-02 | cross-source `effect_acknowledged` снимал reservation | разные emitter sequences не образуют причинного порядка | cross-source ack требует reconciliation |
| C-03 | latest terminal выбирался по seq, failure reason — по delivery order | неверная причина stop на incident timeline | reason из того же terminal |
| C-04 | отрицательный live_age ограничивался нулём | rollback часов создаёт false-fresh telemetry | `CLOCK_ANOMALY` |

Каждое наблюдение основано на чтении кода `gpt_companion/journal.py`, а не на production telemetry. Приоритет C-01/C-02 — P0; C-03/C-04 — P1. Проверить regression tests прежде чем менять статус на "verified".

## Изменения и evidence ledger

1. Создана изолированная ветка `audit/gpt-companion-causal-failclosed-20261122-a13` от PR #12 (не main), чтобы не перезаписывать работу других агентов.
2. `09903d3972cc96b5e0d1eb0cee5313124cd7e82e` — исправления `gpt_companion/journal.py`.
3. `29757173cfad2a144bd6d6f6c77ac7d1e16c4546` — 9 offline causal regression tests.
4. `649b658db64362bde77c4bf355e0941f4a1c7b6d` — SDD section 14 / ADR-016..021, integration ownership matrix.
5. CI evidence и exact pull request head: см. GitHub checks после PR creation; не объявлять успех по коду без выполнения.

## Что осталось открытым и почему

- **P0 production:** отсутствуют auth-bound producer identity и доказуемые provider receipts. Нельзя безопасно подключить авто-retry по телеметрии.
- **P0 integration:** четыре+ ветки GPT/API потенциально конкурируют за gateway API; нужна явная canonical choice, общий schema contract и воспроизводимый merge.
- **P0 live monitoring:** Local Workspace недоступен; нельзя подтвердить, что сборщик вообще видит реальный runtime. Требуется восстановление подключения и supported adapter handshake.
- **P1 testing:** Python 3.11/3.13 checks, wheel smoke, load/fault injection, upstream drift report, operator signoff — ожидают реальных результатов.
- **P1 accuracy:** audit chain защищает от случайной правки, но не от подмены хвоста/полной БД; нужен внешний anchor и backup restore test.
- **P1 observability:** `assess` при прямом вызове не выполняет `verify_chain`; caller MUST verify integrity prior to trusting result. Упаковать это требование в будущий safe facade.

## Контрольный сценарий при воспроизведении

```text
attempt 1 worker-X seq1 tool.effect_reserved(action=github-pr)
attempt 2 worker-Y seq1 worker.started
EXPECTED: NEEDS_RECONCILIATION, prior=[{attempt:1,action_id:github-pr}]
FORBIDDEN: auto retry, success claim, release old resource fence
```

Другие тесты: ack из второго source, backfill с другим failure reason, rollback wall clock. Полная матрица и ADR в `docs/sdd/GPT_COMPANION_SDD.md`.

## Следующая честная проверка

- На точном SHA ветки выполнить offline `python -m pytest tests/gpt_companion -q` для 3.11 и 3.13.
- Проверить `python -m gpt_companion --db ... --run-id ...` и отсутствие raw payload в логах.
- Подтвердить, что CI запущена на head, а не на merge base. Если Actions отсутствуют — статус `NOT_VERIFIED`, не зелёный.
- До release провести независимое ревью thread, ownership lock, интеграцию только согласованного API bridge.
- После восстановления локального MCP — *отдельно* добавить действующий observer adapter и runtime snapshot. Не симулировать фоновый монитор там, где процесса нет.

## Источники

- Текущий код / PR #12: https://github.com/Podtverzhdeno/hermes-agent/pull/12
- SQLite WAL: https://www.sqlite.org/wal.html
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OTel GenAI conventions: https://opentelemetry.io/docs/specs/semconv/
- OpenAI sessions: https://developers.openai.com/api/docs/guides/agents-api/sessions
- OpenAI webhooks: https://developers.openai.com/api/docs/guides/webhooks
