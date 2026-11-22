# Hermes ↔ GPT companion: Windows read-only incident runbook

**Status:** design / operator runbook; **NOT performed on the machine** during this audit. No remote access to the extension installation was available. Do not interpret any line below as a live health measurement.

## Known historical installation context (2026-11-11; must be reverified)

- Root: `C:\Users\Vadim\Tunnel` (generally `$env:USERPROFILE\Tunnel`).
- Candidate unpacked Chromium extension: `chat-launch-smoke-desktop-test\web-extension`.
- Candidate bridge launcher: `chat-launch-smoke-desktop-test\web-companion\start_bridge.py`.
- Local Workspace MCP observer: `127.0.0.1:8765`; separate scoped Obsidian editor: `127.0.0.1:8766`.
- A previous `status-stack.py` observation reported web-companion bridge **not listening on 18763**, extension **v0.6.6 stale**, and subsequent triage stages blocked. This was an earlier observation, **not evidence of today's state**.
- Another earlier canary returned `HERMES_CDP_SINGLE_LANE_OK` for model `web-chatgpt-high-cdp`; this proves only that one connectivity path previously worked, not continual authorization, service health or user-action safety.

No account keys, browser cookies, extension private data, API bearer tokens, session transcripts or complete process command lines should be collected into this diagnostic package.

## Local operator preflight (Windows PowerShell 5.1; read-only)

```powershell
$root = Join-Path $env:USERPROFILE 'Tunnel'
$targets = @(
  (Join-Path $root 'chat-launch-smoke-desktop-test\web-extension'),
  (Join-Path $root 'chat-launch-smoke-desktop-test\web-companion\start_bridge.py'),
  (Join-Path $root 'Local-Workspace-Extensions\mcp-host-source')
)
foreach ($target in $targets) {
    [pscustomobject]@{ Exists = (Test-Path -LiteralPath $target); Path = $target }
}
foreach ($port in @(8765,8766,18763)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        foreach ($item in $conn) {
            $owner = Get-Process -Id $item.OwningProcess -ErrorAction SilentlyContinue
            [pscustomobject]@{ Port = $port; Listening = $true; PID = $item.OwningProcess; ProcessName = $owner.ProcessName }
        }
    } else {
        [pscustomobject]@{ Port = $port; Listening = $false; PID = $null; ProcessName = $null }
    }
}
```

This deliberately doesn't launch a process, change firewall settings, read secrets, modify files, or send prompts to ChatGPT. A listening socket means only *a process* owns the port; it does not prove that it is the expected bridge, authorized, linked to the correct profile, or responding to requests. A missing socket does not establish why it is absent.

## Evidence-first triage

| Observation | Hypotheses to differentiate | Safe next verification | Unsafe shortcut |
|---|---|---|---|
| Unpacked extension path absent | moved directory, wrong Windows account, deleted extension | check versioned install manifest and owner-approved inventory | silently reinstall from an untrusted web download |
| Extension exists but browser UI does not recognize it | disabled or stale MV3 build, invalid manifest, profile mismatch | inspect `chrome://extensions` with human operator, record build/version without private data | infer status from a previous canary |
| Port 18763 closed | bridge intentionally stopped, launcher crash, wrong configured endpoint, firewall/service change | check approved *redacted* bridge health/status and process supervisor | start duplicate bridge blindly or kill unrelated listener |
| Port 18763 listens but no handshake | wrong process, origin restriction, stale challenge, protocol version mismatch | compare authenticated handshake version, allowed origin and clock/skew | switch off origin checks or log raw authorization headers |
| 8765/8766 present, extension absent | MCP and companion are separate lifecycles | test each component against its own expected API and scope | treat healthy MCP as proof that GPT browser is connected |
| Chrome MV3 service worker suspended | normal browser lifecycle or crash | reconnect with durable cursor and current run status | resubmit any previous side-effecting tool call |
| SSE replay.truncated or missing seq | retention buffer expired, subscriber overflow, slow client | show `OBSERVABILITY_GAP`, poll scoped run status, reconcile from durable ledger | invent missing events or claim complete timeline |
| Hermes run status unknown after restart | owner had claimed work but outcome unproven | locate exact admission/generation and independent effect receipts, request owner decision | auto-resolve and repeat external writes |
| Stale Kanban task while worker PID appears alive | long model call, deadlock, max_runtime, stale fingerprint | examine task_runs, claim lock, heartbeat and configured deadline | reclaim based on TTL alone |
| Multiple workers same effect key | duplicate operation race or legitimately reconciled retry | inspect authoritative effect receipt and fencing for **all tasks** | permit both workers to replay |
| API returns HTTP 200 + [DONE] | successful stream OR typed error finish chunk | inspect finish_reason / error and authenticated status | count DONE as success |
| GitHub check is green but on old SHA | PR moved during CI | compare exact PR head SHA, required check names, protection policy | merge based on green badge alone |

## Required causal incident record

For each incident, record exactly one row with: `incident_id`, `observed_at_utc`, `environment/build`, `source_type`, `source_revision_or_cursor`, opaque `run_id_digest`, `task_id_digest`, `attempt_id_digest`, `owner`, `reason_code`, `observed_fact`, `candidate_hypotheses`, `confidence_class`, `evidence_gap`, `next_safe_verification`, `fix_pr`, `exact_test_sha`, `reviewer`, `closed_utc`. Treat any unsupported field as `unknown`, never fabricate it.

Status vocabulary: `OBSERVED_RUNTIME`, `OBSERVED_SOURCE`, `TESTED_OFFLINE`, `INFERRED_CANDIDATE`, `NOT_VERIFIED`. The last two must never be promoted to success solely by an agent's own text.

## Concurrency and recovery invariants

1. One profile/session owner and one approved launcher per native host/browser transport; spawned Chrome process ownership must be tracked so an agent does not kill another agent's CDP browser.
2. All mutating operations use stable effect/admission identity and generation/fence checks, backed by an authoritative server or ledger; a local extension UI cannot grant retry authority.
3. Observation and execution are separate principals. A diagnostics agent may GET scoped status and redacted events but cannot auto-click approvals, restart other workers, revoke tokens or mutate the Kanban database.
4. Persist cursor only after the event batch is durably recorded and validated. On a crash between read and commit, replay must be deduplicated and a changed same-seq event must be reported as a conflict.
5. If the remote outcome is unknown, require an independent remote-effect read-back and explicit owner decision before any potentially duplicate write. In official v0.23.3 canonical mode, `resolve-unknown` acknowledges the previous turn and releases the queue; it is **not** proof that a previous payment, PR merge, repository write or approval did not occur.
6. Stop conditions `crashed`, `timed_out`, `gave_up`, `blocked`, `waiting_for_approval`, `stranded_in_ready`, `stale_running`, `review_dependency_deadlock`, `bridge_disconnected`, `provider_rate_limited` are distinct. Show the source and confidence of each status; don't flatten them into `error`.

## Release gate for actual always-on monitoring

Requires current authenticated Windows extension/native host source inventory, explicit selected Hermes release/API mode, scoped GET adapter, persisted validated event cursor, crash/replay recovery, PII/redaction and integrity review, isolated 30–50 agent fault-injection, exact merged-HEAD CI, human-approved installer/restart controls, and a clear pause/stop mechanism. Until these are satisfied, this is an offline review artifact, not an installed monitor.

Sources: [Hermes v0.23.3 Runs API](https://github.com/NousResearch/hermes-agent/blob/v0.23.3/website/docs/user-guide/features/api-server.md); [Hermes v0.23.3 Kanban lanes](https://github.com/NousResearch/hermes-agent/blob/v0.23.3/website/docs/user-guide/features/kanban-worker-lanes.md); [GPT Bridge draft PR #26](https://github.com/Podtverzhdeno/hermes-agent/pull/26).