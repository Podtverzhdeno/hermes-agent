# SDD: Hermes × GPT — доказуемое исполнение, причины остановок и интеграция десятков агентов

Дата: 2026-11-22. Версия проекта: 0.1. Статус: DRAFT / independent integration review; не готово к production. Owner: A0 / integration gate. Базовый проверенный fork SHA: 7e9100901819ee44c16b4ddcb79a6bcb7909f591. Этот документ НЕ является доказательством существования работающего расширения GPT в данном форке. Доступ к Windows-host/Obsidian через Local_WorkSpace MCP отсутствовал: Session terminated.

## 1. Конкретная цель, критерии доказательства

Цель: оператор должен видеть каждую подтверждаемую фазу задания с exact revision, причинной связью событий, источником, ответственным агентом, статусом tool-side-effect, безопасной следующей операцией. Обычные heartbeat, HTTP 200, LLM "готово", исчезновение вкладки, остановка SSE и зелёный статус внешнего reviewer не являются доказательством выполнения.

Четыре уровня утверждений:
- OBSERVED: факт принятого валидного события; доказан только факт его получения.
- SELF_REPORTED: самостоятельное сообщение worker/model/браузера. Нельзя повышать до VERIFIED без независимого источника.
- INFERRED: гипотеза root cause с доверительным уровнем и альтернативами, не команда на исправление.
- VERIFIED: независимый trusted checker проверил точный commit/artifact SHA, ожидаемый результат и состояние внешних эффектов.

Секреты, пользовательский prompt, ответ модели, hidden chain-of-thought, cookies, заголовок Authorization, аргументы инструментов и содержимое внешних файлов не входят в общий event journal. Истинный hidden reasoning модели не наблюдаем: необходимо объяснять операции и последствия, а не имитировать знание внутренних мыслей.

## 2. Подтверждённые факты: 22 ноября 2026

- Репозиторий: https://github.com/Podtverzhdeno/hermes-agent. main = 7e9100901819ee44c16b4ddcb79a6bcb7909f591 (коммит от 2026-04-01), отстаёт от текущих функций upstream. До архитектурной миграции проверить современный native Kanban/worker механизм NousResearch Hermes; второй production task scheduler запрещён.
- Одновременно открыты 12 draft PR (#1–#12); #4, #5, #6 меняют gateway/platforms/api_server.py с разными single-flight решениями; #11 является stacked на ветку #4. #10 stacked на #1. #1/#9/#12 меняют pyproject.toml, #9/#12 реализуют конкурирующие SQLite event observers. Проверка mergeable=true по отношению к main не тестирует совместимость независимых PR.
- PR #4 exact SHA 5b8497b510b0a8543e8a2e30aaac5861bf30f264: полный Tests workflow failed (29 failed, 7513 passed, 171 skipped). В том числе confirmed test/API contract mismatch: старый test_agent_error_returns_500 ожидает "Provider failed" после того, как handler перестал раскрывать ошибку backend и возвращает безопасный корреляционный ID. Обновлять тест и документировать код ошибки, не возвращать leak внутренних сообщений. Остальные падения включают credentials unavailable, Codex и timeout: происхождение каждого требует сравнения с main. https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013330331
- PR #9 exact SHA 8fb2d37e5df6344ecb96ce5a56fa08e0f4ebdfe6: Tests workflow failed (28 failed, 7540 passed, 171 skipped), преимущественно CI credential/environment и другие классы ошибок; регрессии не доказаны для каждого. https://github.com/Podtverzhdeno/hermes-agent/actions/runs/45013244320
- Legacy commit status Devin Review может быть "success" при описании "Full review skipped: trial expired and no credits remaining". Он не является проверенным review или CI pass. Каждый check должен соответствовать exact PR head; после объединения нужен новый проверенный combined SHA.
- Local_WorkSpace MCP list_workspaces завершился Session terminated. Ни локальное расширение, ни Windows daemon, ни живые логи, ни Obsidian в этом проходе не наблюдались. GitHub Issues API для репозитория ответил 410: Issues disabled. Координацию вести в PR и SDD, не заявлять существование Issue.

## 3. Архитектурное решение A0: один владелец каждого действия

Control plane: native Hermes Kanban/worker после подтверждённой совместимости версии; единственный authority для задания, попытки, lease/epoch, retry budget, STOP/cancel, owner. Автопилот PR #1 остаётся прототипом инвариантов без второго активного production-диспетчера.

Effect plane: реальный tool dispatcher / MCP gateway авторизует scope, applies CAS/fencing к изменяемому ресурсу, обеспечивает explicit approval и side-effect reservation. Манифест skill, текст prompt и read-only observer сами по себе никогда не дают права запускать команды. До применения внешнего эффекта проверяется LIVE fencing токен на доверенной границе, не только локальное значение worker.

Observation plane: один выбранный read-only event inbox с authenticated producer envelope + allowlisted metadata. Отдельно per-producer durable sequence; transactional outbox; ingestion ACK. Примеры #9 и #12 — конкурирующие кандидаты, не два production источника истины. Отрицательное свидетельство (нет сообщения) НЕ доказывает, что действие не происходило.

Evidence plane: независимый verifier по exact SHA и зафиксированным acceptance tests. PR/CI и artifact proof связаны с head commit, версиями среды и тестовыми входами. Список CI check-runs учитывает FAIL/CANCEL/SKIP/TIMED_OUT/MISSING/QUEUED/PENDING; legacy success не подменяет проверки.

Presentation plane: GPT/ChatGPT companion, browser extension, websocket, CLI только отображают projection. Ни UI, ни чат не владеют состоянием, не сохраняют auth secrets в telemetry, не утверждают выполнение по сообщению worker.

Документированный поток:

~~~text
authenticated ingress -> validate scope -> durable task/attempt on native Hermes Kanban
                                      -> scoped worker -> privileged effect gate
                                      -> local transaction + outbox -> authenticated event inbox
                                      -> read-only diagnoses -> independent exact-SHA verifier
                                      -> operator projection / GPT panel
~~~

При отсутствии доступа к реальному расширению транспорт остаётся НЕВЫБРАННЫМ: возможны loopback OpenAI-compatible API с обязательной проверкой bind/key/origin, подписанный Native Messaging Host при verified MV3 permissions/sender, либо официальный разрешённый API. Не строить production на автоматическом извлечении cookies, скрытом DOM-scraping ChatGPT, обходе логина или предположении, что UI-сессия — постоянный worker.

## 4. Версионированный атомарный event contract

Пример схемы (дизайн, НЕ текущий runtime API):

~~~json
{
  "schema_version": 1,
  "event_id": "evt_opaque_01",
  "task_id": "task_opaque_01",
  "run_id": "run_opaque_09",
  "attempt_id": "attempt_03",
  "producer_id": "worker_17",
  "producer_seq": 42,
  "fence": 7,
  "kind": "tool.effect.uncertain",
  "reason_code": "EFFECT_ACK_UNKNOWN",
  "action_id": "action_opaque_33",
  "parent_event_id": "evt_opaque_00",
  "trace_id": "opaque_trace",
  "subject_revision": "git-or-artifact-sha",
  "producer_time": "2026-11-22T10:30:00Z"
}
~~~

Приёмник записывает receipt timestamp, validated producer identity, digest и storage sequence сам, не доверяет client timestamp. Индекс (task_id, attempt_id, producer_id, fence, producer_seq) уникален. Повтор event_id с тем же canonical hash => идентичный ACK; с другим hash => EVENT_CONFLICT. Sequence gap => EVENT_GAP; backfill с ранее низким seq не должен обновлять liveness/current progress. Между производителями НЕТ автоматически определённого полного порядка; parent_event_id задаёт только частичный порядок. Correlation ID / W3C traceparent полезен, но не заменяет action_id и fence. Персональные и секретные данные запрещены схемой (strict allowlist; никаких свободных objects/strings).

Для атомарности запись control transition + локальная outbox запись находится в одной транзакции только в пределах одной БД. Доставка в удалённый collector происходит с at-least-once через stable event ID и durable ACK, не через повтор выполняемого tool action. Требование exactly-once execution across systems без общей транзакции не выдвигать. В случае недоступности журнала явно OBSERVABILITY_DEGRADED и backpressure, а не умолчание.

Хэш-цепочка локального SQLite обнаруживает случайную порчу, но НЕ подтверждает отсутствие вмешательства атакующего, имеющего доступ к БД; для высокой целостности нужен внешний доверенный anchor/подпись.

## 5. Машина состояний и безопасное восстановление

~~~text
ACCEPTED -> VALIDATED -> QUEUED -> LEASED -> RUNNING -> VERIFYING -> VERIFIED_COMPLETED
               |           |         |        |           |
            REJECTED       |      EXPIRED     |       VERIFICATION_FAILED
                         APPROVAL_WAIT        |
                              |        BLOCKED(reason) / FAILED
                         APPROVED             |
                         DENIED           UNKNOWN_EFFECT -> RECONCILING
                                                |
                                        EXTERNAL_CONFIRMED / NOT_EXECUTED / MANUAL
~~~

- STOP_REQUESTED не равно STOP_CONFIRMED. Потеря HTTP/SSE или закрытая вкладка не равна отмене work.
- После отправки внешнего запроса и обрыва связи outcome неизвестен. Запрещён автоматический повтор неидемпотентного эффекта, пока не получен receipt/reconcile. Повтор enqueue-event — не повтор action.
- Lease epoch монотонен; после owner death новый worker получает новый fence. Старый worker отвергается на стороне tool/effect gateway. Смена модели сама по себе не обнуляет action_id/effect budget.
- Одобрение относится к конкретной версии команды, resource scope, actor, task, action, expiry; хранить только безопасную ссылку/хэш для telemetry. После DENIED/EXPIRED не переиспользовать.
- Verified completion требует exact subject revision и независимо доверенных checks. Наличие терминального события "done" — SELF_REPORTED, не VERIFIED.
- Backpressure, retry policy и circuit breaker располагаются в control/effect plane, не в prompt. Ошибка или таймаут коллектора не разрешает повтор эффекта.

## 6. Причины остановок: typed reason + evidence + safe next action

| Reason code | Признак | Безопасная реакция |
|---|---|---|
| AUTH_MISSING / AUTH_EXPIRED / AUTH_DENIED | auth handshake/refresh fail | проверить scoped grant, не записывать token |
| APPROVAL_PENDING / DENIED / EXPIRED | approval receipt отсутствует/отклонён | остановить write, запросить explicit scope |
| PROVIDER_RATE_LIMIT / QUOTA_EXCEEDED | server 429/usage | honour Retry-After, проверить бюджет |
| MODEL_CONTEXT_EXHAUSTED | response truncation/provider error | checkpoint + replan без side-effects |
| PROVIDER_TIMEOUT / STREAM_LOST | ответ/stream не подтверждён | проверить response/run ID, не запускать снова вслепую |
| TRANSPORT_DISCONNECTED / MCP_SESSION_TERMINATED | channel ack lost, 429, disconnect | восстановить channel, запросить статус task |
| BROWSER_TARGET_GONE / MV3_SUSPENDED | detach/tab closed/service worker suspended | reattach к прежнему run без side-effect |
| INVALID_TOOL_SCHEMA / SKILL_SCOPE_DENIED | schema/contract mismatch | исправить contract + тест |
| LEASE_EXPIRED / STALE_FENCE | old owner continues | блокировать effect, пересоздать lease |
| EFFECT_ACK_UNKNOWN | внешний эффект мог произойти | только reconcile, иначе MANUAL |
| EVENT_GAP / COLLECTOR_UNAVAILABLE / DB_CORRUPT | seq, storage integrity | наблюдаемость деградировала, никогда не "success" |
| HEARTBEAT_ONLY_STALL | heartbeat есть, progress нет | diagnostic probe без side-effect |
| CHECKS_FAIL / CHECKS_MISSING / CHECK_SHA_MISMATCH | CI не доказывает revision | выполнить тесты на exact SHA |
| ARTIFACT_REVISION_DRIFT / VERIFICATION_FAILED | файл не совпадает с подтверждённым | CAS/re-verify, не объявлять done |
| INCONCLUSIVE | причинное доказательство недоступно | операторская диагностика с confidence LOW |

Панель обязана показывать task/run/attempt, exact SHA, last heartbeat, last real progress, last durable ACK, active effect/approval, вероятную причину, её evidence-source, степень доверия и next safe action. Никогда не показывать только бесполезное "агент завис".

## 7. Сорок и более агентов: владение, коллизии, интеграция

Перед каждой задачей назначать (task_id, worker_id, owner_paths, target_revision, lease_epoch, allowed_effects, retry/LLM budget, expiry). Один PR на одну узкую область и независимый review. Текущий интегратор A0 владеет ТОЛЬКО read-only gate + SDD; он не редактирует одновременно gateway handler, который меняют #4/#5/#6/#11.

Прямые пересечения файлов: сравнивать все open PR changed filenames. Stacked PR при совпадении parent branch — зависимость, не независимая коллизия. У разных PR с пересекающимися файлами нет автоматического права merged; добавить owner arbitration. Независимые файлы могут конфликтовать семантически (#9 vs #12 duplicate journal), поэтому отдельно нужен semantic candidate report.

Не запускать второй engine рядом с native Kanban. Прототип #1/#10 разрешено исследовать офлайн как specification/effect ledger, но перед внедрением сделать upstream parity audit. Владелец API выбирает единственный single-flight implementation на основе тестов, памяти, streaming, безопасного error contract и реального E2E. Переносить уникальные патчи #6/#11 после rebase и повторного полного CI; не совмещать автоматически два idempotency cache.

Для работы множества независимых авторов использовать immutable baseline SHA, CAS on branch head, строгие code owners, lease на обработку shared files, изолированные worktrees, синхронизацию только по versioned proposals, не по слухам. Модель должна отправлять SUMMARY с evidence IDs, а не полные prompt/body и не "100% готово" без проверок.

## 8. Критический сравнительный анализ идей

Оценка экспертная, НЕ эмпирическая: безопасность/устранение P0 (40%), масштабирование 30–100 агентов (30%), внедряемость (20%), качество текущих оснований (10%); каждая от 1 до 5.

| Предложение | S/M/F/E | Score | Решение |
|---|---|---|---|
| Single native Kanban control plane, отказ от второго scheduler | 5/5/4/5 | 4.8/5 | ADR-A0-01, MUST |
| Exact-head CI + collision graph + independent integration gate | 5/5/4/4 | 4.7/5 | внедрено как advisory metadata tool |
| Reconcile unknown external effect + live fencing | 5/5/2/4 | 4.3/5 | P0 design, needs effect gateway |
| Typed reason codes + separate progress/heartbeat | 4/5/4/4 | 4.3/5 | P1, read-only |
| Authenticated outbox/ACK + one journal + verifier | 5/5/2/3 | 4.2/5 | P0, only after contract arbitration |
| Проверить реальные источники и permissions расширения | 5/4/2/2 | 3.8/5 | discovery gate; unavailable |
| OpenTelemetry GenAI metadata-only trace | 4/4/3/4 | 3.8/5 | optional after schema freeze |
| MV3 offline observer with explicit user consent | 4/4/2/3 | 3.6/5 | contingent, requires runtime/source |
| LLM autocommit/automerge/retry side-effects | 1/3/3/1 | 2.0/5 | REJECTED until trust gates |
| Silent DOM scraping of ChatGPT as worker queue | 1/2/2/1 | 1.5/5 | REJECTED |

Веса и числа — предварительная экспертная гипотеза; validation/fault injection имеют приоритет над числом. Вне зависимости от score вариант, не прошедший security gate, блокируется.

## 9. Acceptance: опровергаемые fault-injection испытания

G0 — обнаружить исходники и installed build реального GPT extension/plugin, разрешения, transport, host, OS, scope, privacy consent. Иначе нет основания подключать browser.
G1 — сравнить современную native Hermes Kanban и форк, зафиксировать upstream version+SHA, подготовить миграцию без второй очереди.
G2 — auth negative tests: invalid/expired bearer, origin/sender spoof, non-loopback no-key, approval expiry, prompt injection via telemetry, secret redaction. Никаких privilege escalations.
G3 — append/replay 1000 раз с одним event_id; conflicting hashes and producer sequence reject; packet loss, order inversion, delayed backfill, sqlite lock, corruption. No silent loss.
G4 — before/after external commit crash, unknown ACK, stale fence, retry-after, cancelled tool, worker death, approved-then-revoked. No repeated unknown side effects.
G5 — API request invalid JSON, keyed SSE *before dispatch*, concurrent single-flight 100 requests, 409/422 consistency, streaming error as error—not success, response IDs stable on replay, bounded dedup memory.
G6 — browser close/reattach, MV3 suspend, host restart, WSL/Windows tunnel disconnect/429, agent replacements, tab mismatch and loopback transport under real owner environment; none claimed today.
G7 — independent CI on combined integration commit SHA, no missing/cancelled/skipped required jobs; human review, no more false green Devin.
G8 — exact artifact SHA, Obsidian permissible directory only, no overwrite of newer documents, operator acceptance and rollback rehearsed.
G9 — 30/50/100-worker chaos, including 24+ hour soak after G0–G8; target: zero duplicated unauthorized external effects, zero silently lost unknown outcomes, zero stale fences accepted. These are acceptance TARGETS, not measured results.

Rollback: disable new dispatch and tool side effects, preserve read-only ledger/journal, mark ambiguous attempts UNKNOWN_EFFECT, reconcile each receipt, keep original logs and revisions, restore per approved operator workflow; do not delete evidence or blindly compensate.

## 10. Implementation scope of this PR / integration arbitration

- scripts/hermes_pr_gate.py is a NO-WRITE metadata-only collector using GitHub GET for open PR, exact head, changed file lists, check-runs and legacy statuses; it re-reads PR heads to detect snapshot drift and fails closed on incomplete/invalid data.
- Offline snapshot mode is deterministic and does not need GitHub token; report JSON/Markdown includes exact SHA, required test, skipped review, file conflict pairs, stacked dependencies and semantic duplicate candidates.
- merge_ready is deliberately always FALSE. A green check on this PR is only evidence of the gate tests, not permission to ship Hermes or execute effect.
- Branch is isolated from all existing #1–#12; no changes to existing gateway/ACP/autopilot/observer code and no production activation.
- GitHub Actions workflow runs read-only tests and optionally produces evidence. Monitoring across time requires a separately deployed/scheduled trusted runner; a chat response itself is not a daemon.
- Limitations: per-PR GitHub API retrieval is not transactionally atomic; head double-read narrows race but exact combined-commit rechecks remain mandatory. File conflicts are heuristics. Legacy status cannot prove security review. API GET rate-limit may make snapshot unavailable; do not treat as "zero conflicts".
- GitHub Issues disabled (410), use the PR review thread and SDD as coordination ledger; no invented Issue IDs.

**Integration sequence:** (1) name one owner for gateway handler; (2) arbitrate #4/#5/#6/#11 on exact code and tests; (3) select one outbox/journal from #9/#12/#8; (4) rebase stacked #1/#10 for parity review; (5) audit ACP #3 and skill harness #2 for real policy boundaries; (6) source-discover actual extension; (7) combined E2E + independent review + staged canary only.

## 11. Primary source set

Hermes upstream: https://github.com/NousResearch/hermes-agent/releases and https://hermes-agent.nousresearch.com/docs/developer-guide/architecture
Fork PRs: https://github.com/Podtverzhdeno/hermes-agent/pulls
Chrome MV3 lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
Chrome Native Messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
W3C Trace Context: https://www.w3.org/TR/trace-context/
OpenTelemetry GenAI: https://opentelemetry.io/docs/specs/semconv/gen-ai/
Temporal Activity Idempotency: https://docs.temporal.io/activity-definition

This is a staged verified engineering review, not a claim of examining millions of sources or live user session data. Next gate is authorized Windows/WSL extension inspection and real fault-injection evidence.
