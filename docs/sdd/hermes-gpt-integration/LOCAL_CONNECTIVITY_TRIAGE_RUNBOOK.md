# Hermes GPT Companion — Local Connectivity Triage (Windows / MCP / Browser)

Revision: 2026-11-22. This is an operator runbook, not a record of commands executed on the user's PC.
Investigation evidence: the authenticated Local_WorkSpace connector returned Session terminated; a separate temp_folder_readonly probe returned MCP SSE probe HTTP 429. These results establish unavailable observation in this session, NOT a proved failure of the local Hermes process, Windows listener, browser extension or tunnel.

## 1. Decompose the path

~~~text
ChatGPT connector invoke
    |
    v
connector control plane / session / rate budget
    |
    v
tunnel client connection and runtime process
    |
    +-- local observer MCP on 127.0.0.1:8765 (read scope)
    |
    +-- scoped editor MCP on 127.0.0.1:8766 (write scope if separately authorized)
    |
    v
Hermes host process / event ledger / optional native messaging
    |
    v
optional Chromium MV3 extension and visual status
~~~

Every link has its own independent health signal. A healthy local /healthz does NOT prove the connector or browser is connected. A disconnected connector does NOT prove Hermes work stopped. A running process PID does NOT prove a worker received a prompt. Avoid combining all failures under "agent silent".

## 2. Safe, read-only diagnostics on the Windows host

Run only on the user's authorized machine, using ordinary unprivileged PowerShell. No credentials or secrets are needed for these checks.

~~~powershell
# Listener and owning PID; verify which process actually owns each port.
Get-NetTCPConnection -LocalPort 8765,8766 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalPort, LocalAddress, OwningProcess

# Loopback access only: report HTTP status, do not print authorization headers.
try {
  $r = Invoke-WebRequest -Uri http://127.0.0.1:8765/healthz -UseBasicParsing -TimeoutSec 5
  Write-Output ("observer_health_status=" + $r.StatusCode)
} catch {
  Write-Output ("observer_health_failed=" + $_.Exception.GetType().Name)
}

try {
  $r = Invoke-WebRequest -Uri http://127.0.0.1:8766/healthz -UseBasicParsing -TimeoutSec 5
  Write-Output ("editor_health_status=" + $r.StatusCode)
} catch {
  Write-Output ("editor_health_failed=" + $_.Exception.GetType().Name)
}

# Process metadata only, after identifying listener PIDs above.
Get-Process python,tunnel-client -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, StartTime
~~~

The specific port assignments are an historical configuration reference, not a live confirmed value. Do not expose the local MCP listener on a non-loopback interface without independent authentication, authorization and firewall review. No "fix" should disable sandboxing or widen an editor scope.

When available on the user's machine, run the existing tunnel's doctor/status commands from its documented installation directory; record only boolean service readiness, target port, authentication VALID/INVALID, tool count and error class. Never paste runtime keys, OAuth tokens, client secrets or full headers into GitHub or shared logs.

## 3. Interpretation matrix

| Observation | Possible layer | Next non-mutating test | Not yet justified |
|---|---|---|---|
| No Windows listener | local host process | inspect process status and startup logs | regenerating tokens or changing browser |
| Listener present, healthz refused | local HTTP server/port mismatch | inspect bind address, owning PID, TCP errors | blaming GPT model |
| healthz healthy, tunnel runtime not ready | tunnel/runtime | run tunnel doctor/status; inspect target host/port | restarting running agents |
| local tunnel healthy, connector Session terminated | connector control plane/session | correlate connector request ID and auth validity | declaring Hermes STOPPED |
| SSE probe HTTP 429 | probe/platform/rate control | inspect retry-after and operator quota, bounded retry | deleting local state |
| Browser UI disconnected, host healthy | MV3/native messaging | inspect service-worker restart and native host handshake | rerunning external tools |
| Kanban task claimed, no prompt request | worker-lane dispatch | correlate process spawn with prompt ack and model request | marking task completed |
| Chat output absent after tool call | stream/delivery/action outcome | inspect last persisted event and remote effect receipt | blind repeat of mutation |
| Short heartbeat gap | observer ingestion/backpressure | compare broker cursor, queue depth and producer sequence | immediate worker kill |
| STOP requested but cron still starts work | revocation propagation | inspect project generation at every dispatch boundary | assuming operator STOP applied |

Do not assign a root cause with confidence HIGH unless a directly observed component supports it. A failed connector request at time T can be an OBSERVATION_GAP even while the host continues authorized local tasks.

## 4. Incident record for agents

Append one metadata-only record per incident:

~~~json
{
  "incident_id": "UUID",
  "observed_at_utc": "ISO8601",
  "source": "connector|local_health|tunnel|host|extension",
  "phase": "CONNECTOR_HANDSHAKE",
  "symptom_code": "SESSION_TERMINATED",
  "local_host_verified": false,
  "affected_project_id": "opaque-or-null",
  "affected_run_id": "opaque-or-null",
  "evidence_refs": [],
  "hypotheses": [
    {"code": "CONTROL_PLANE_UNAVAILABLE", "confidence": "LOW"}
  ],
  "next_test": "CHECK_INDEPENDENT_LOCAL_HEALTH",
  "recovery_allowed": "NO_AUTOMATIC_MUTATION",
  "verified_fix_commit": null
}
~~~

Keep event sequence and causal links; if one source is inaccessible, record that rather than fill missing facts with a model assumption. Distinguish investigation status from Hermes worker state.

## 5. Ordered recovery, only with evidence

1. Check connector status and recorded error code without writing any local files.
2. Verify local TCP listeners and /healthz responses.
3. Verify tunnel runtime ready and points to the intended MCP observer, not the scoped editor unless that scope is explicitly authorized.
4. Inspect structured process logs with user data redacted; correlate boot ID, startup revision, last heartbeat and error ID.
5. Retry only a safe read probe after bounded delay; do not loop past quota limits or bypass rate restrictions.
6. If the observer alone failed, repair the observer while preserving all running worker tasks and effect reservations.
7. If worker state is genuinely unknown, reconstruct from authoritative Kanban and effect receipts before reassignment.
8. Only promote a validated fix after independent source test, host E2E test and rollback checkpoint.

## 6. Checkpoints and acceptance

A restored connector is not sufficient for release. Require:
- observed local host boot identity and healthy listener;
- tunnel handshake to the correct read-only observer;
- actual message delivery and measured duration;
- a task/event stream with stable cursor and replay on reconnect;
- no sensitive data in structured errors or shared diagnostics;
- no outstanding unknown external effects auto-retried;
- no unexpected access to scoped editor/owner's private workspace;
- a verified STOP drill, not just a "stopped" UI message.

## 7. Disposition of this session

Observer: BLOCKED, exact error "Session terminated".
Alternative observer: BLOCKED, HTTP 429 during MCP SSE probe.
Windows host: UNKNOWN; no local shell or process inspection performed.
Hermes server runtime: UNKNOWN.
GPT browser companion source / installation: UNKNOWN.
GitHub source/PR audit: AVAILABLE via connected GitHub; evidence and diagnostics SDD updated in an isolated Draft PR.
Next safe action upon restored local access: run read-only layered diagnostics; do not widen scope or restart unknown effects.

Related specs: EXTENSION_TRANSPORT_AND_RECOVERY_SDD.md and INTEGRATION_AND_ATOMIC_DIAGNOSIS_SDD.md.
