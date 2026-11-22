# Runbook — read-only GPT/Hermes run observer (prototype)

**Implementation**: `scripts/hermes_gpt_run_observer.py`
**Tests**: `tests/test_hermes_gpt_run_observer.py`
**Target**: modern NousResearch Hermes `/v1/capabilities` + `GET /v1/runs/{id}`; NOT the April fork's older API.
**Status**: authored on a draft branch. No current local Hermes runtime connection; no claim of ongoing background monitoring or production validation.

## Purpose

A minimal, conservative operator tool to record exactly what the API
**reports** about a particular run without reading user prompts, full tool
payloads, conversation history or agent-private reasoning.

It is deliberately **read only**. It cannot start, cancel, approve, retry,
resume, steer or mutate a run. It cannot certify remote side effects.
The monitor's heartbeat only proves that its polling loop is running.

## Prerequisites

1. Know the installed Hermes version and check that
   `GET /v1/capabilities` advertises `features.run_status=true`.
2. Obtain the actual run ID from `POST /v1/runs` or an operator UI.
   Never guess run IDs. The script validates ASCII `[A-Za-z0-9_-]`.
3. Configure authentication via environment variable
   `HERMES_OBSERVER_API_KEY`. Never put keys in the command line or SDD.
4. Use the loopback API server if possible. Remote access requires HTTPS and
   the explicit `--allow-remote` option; never transmit a token over remote HTTP.
5. Verify the host process can write a private log directory. Default is
   `get_hermes_home()/logs/gpt_run_observer/`; Windows ACL hardening must be
   evaluated separately, POSIX files are created with mode 0600.

## Example: Windows PowerShell

```powershell
# Set privately in this PowerShell session (do not paste real keys into reports).
$env:HERMES_OBSERVER_API_KEY = "<load privately from your secret manager>"

python scripts/hermes_gpt_run_observer.py `
  --base-url http://127.0.0.1:8642 `
  --run-id "<actual-run-id>" `
  --poll-seconds 2 `
  --stale-seconds 120 `
  --max-seconds 3600
```

The tool writes a unique file named
`run-<run_id>-<random>.jsonl`, prints its final path and exits:
- 0: observed a terminal Hermes status (not proof of remote side effects).
- 2: compatibility/capability probe failed or authentication denied.
- 3: observer deadline reached or interrupted; NOT a run failure.
- 4: unsafe configuration or local log storage problem.

No implicit long-running service is installed. To monitor while the desktop
is unattended, **the user must explicitly run it through their chosen
service manager** with bounded restart/backoff policies. This draft does not
create such a service.

## Emitted events (only metadata)

- `observer_started`: launch and run-id identity.
- `unsupported_capabilities`: old/mismatched gateway, no false fallback.
- `durability_warning`: `runs_idempotency.durable=false` or unavailable.
  Operators should avoid automatic high-risk retries in this state.
- `state_observed`: transition or changed last-event marker; records
  only status, sanitized event name, boolean error/control flags.
- `observer_heartbeat`: monitor observed a response; includes age since
  status/event change, NOT a worker heartbeat.
- `progress_stale_suspected`: no changed status or last-event marker
  for a configured threshold **while reported RUNNING**. Investigation
  candidate, never an assertion of failure.
- `transport_error`: HTTP status or generic transport category; no response
  body, URL with credentials, traceback, or raw exception text.
- `terminal_observed`: terminal API status seen. A job could still have
  an ambiguous external effect; check actual tool receipt separately.
- `observer_deadline_reached` or `observer_interrupted`: local process
  exited, not Hermes cancellation.

Records include UTC observation time, versioned schema and random event ID.

## Guarantees and limitations

- File creation is exclusive per observer instance. Each JSONL event is
  written and fsync'd; a power loss can still truncate the last record.
  Do not claim multi-host event-store transactions or globally atomic state.
- Polling can **miss intermediate states** between polls. That is an intrinsic
  limitation: only native `/v1/runs/{id}/events` (with replay cursor) can
  approach a complete step-by-step trace. SSE event capture is a future
  feature, NOT present in this script.
- Remote status can be unavailable when the gateway restarts; it is not
  valid to interpret 404 as "never executed".
- Status `unknown` is not terminal. Preserve unknown effects and ask for
  authorized reconciliation.
- A stale observation may be a long-running LLM/tool call, empty event stream,
  or delayed progress propagation; don't restart work solely on this signal.
- Logging permissions on Windows depend on ACLs, not POSIX chmod. Test
  Windows 10/11 under an unprivileged user before unattended deployment.
- No automatic log rotation, aggregation, cross-host consistency or
  deletion policy has been implemented. Set retention and privacy rules
  before enabling this continuously.
- The `--run-id` is a caller-supplied opaque identifier; don't expose it in
  public issue comments if it reveals private infrastructure context.
- The script does not record secrets by design, but its code has not had
  an independent security review. Reject any future patch that captures raw
  prompts or tool arguments by default.

## Required validation

```bash
python -m pytest tests/test_hermes_gpt_run_observer.py -q
python -m pytest tests/gateway/test_api_idempotency.py -q
```

In addition to isolated tests, the final gate must include:
- Actual modern upstream release and authenticated `/v1/capabilities`.
- Real run queued → running → approval → finished, with observer log.
- Gateway restart during run and status/receipt read-back.
- Wrong API key; missing permissions; unknown run ID; malformed JSON.
- 429/503 bursts and the absence of log leaks.
- Disk full/permissions, Windows ACL, abrupt monitor SIGKILL, restart.
- Multiple concurrent observers; separate log files, no shared state.
- Independent comparison against run events SSE, counting missing
  intermediate events (expected until streaming support is added).
- A clear human-operated retention/deletion procedure.

## Suggested next iteration

Implement a **separate opt-in SSE observer** that persists event
`Last-Event-ID` cursors, deduplicates sequence numbers and reconciles with
GET status before declaring terminal. The server's own event retention and
permissions must be measured. Keep status polling as fallback, not a second
authority. Index sanitized events by operation/step/attempt/agent ID and
include independent receipt references. Avoid storing raw SSE payloads.
