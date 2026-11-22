# Hermes ↔ GPT Bridge — independent audit patch (2026-11-22)

This package is a **reviewable, isolated patch**, not a live-installed extension and not an automated background service.

## Contents

- `gpt_bridge_metadata_audit.py`: strict metadata-only NDJSON event parser and causal audit, no side effects.
- `scripts/gpt_bridge_pr_collision_audit.py`: PR overlap and SHA-bound CI evidence checker, never auto-merges.
- `tests/`: 65 pure-stdlib unit/negative tests for privacy, malicious input, replay, unknown effects, source gaps, 30+ agent coordination.
- `docs/gpt_bridge/SDD_OBSERVER_REVIEW_AND_INTEGRATION_2026-11-22.md`: architecture evaluation, failure catalog, gates, decisions.
- `docs/gpt_bridge/ENGINEERING_LOG_OBSERVER_2026-11-22.md`: factual audit ledger and remaining blockers.
- `.github/workflows/gpt-bridge-observer-offline.yml`: Python 3.11, 3.12 and 3.13 proposed CI.

## Test offline from repository root

```sh
python -m compileall -q gpt_bridge_metadata_audit.py scripts/gpt_bridge_pr_collision_audit.py
python -m unittest discover -s tests/gateway -p 'test_gpt_bridge_metadata_audit.py' -q
python -m unittest discover -s tests/scripts -p 'test_gpt_bridge_pr_collision_audit.py' -q
python -m gpt_bridge_metadata_audit redacted-events.ndjson --output audit.json
python scripts/gpt_bridge_pr_collision_audit.py reviewed-pr-snapshot.json
```

Input export must follow the v1 envelope described in draft PR #7 SDD. Do not include raw prompts, credentials, messages or tool arguments.

## Integration boundaries

- Do **not** integrate against an unknown / unverified local Chrome extension; Local_WorkSpace exposes only the unrelated shelter workspace, not the Hermes browser extension.
- Do **not** activate a second scheduler competing with recent upstream Kanban.
- Do **not** merge overlapping PR #4/#5/#6/#11 independently; choose a single gateway integration owner.
- Python 3.11/3.12/3.13 isolated GitHub offline checks passed for PR #26 on SHA `8cec46d296e38b156b851dda0fda1b1508048e88`; full Hermes integration suite has not been established as passing. Do **not** treat these as live Hermes E2E success.
- External effects with unknown outcome must be reconciled with independent evidence before any retry.
- The observer is intentionally non-authoritative: it never grants approval, final success, tool effects or retry rights.

Repository source snapshot: `Podtverzhdeno/hermes-agent@7e9100901819ee44c16b4ddcb79a6bcb7909f591`.

## Latest upstream design correction

Official Hermes v0.23.3 (released 2026-11-20) already supplies canonical durable admissions, authenticated per-run controls, `unknown` execution state on canonical owner restart, generation-fenced `resolve-unknown`, and an SSE `replay.truncated` marker. Prefer a version-negotiated, authenticated adapter from the native Runs API rather than creating another authoritative task scheduler. Never treat `[DONE]`, browser worker liveness, or a model success sentence as independent proof of completed side effects.

Project draft PR: https://github.com/Podtverzhdeno/hermes-agent/pull/26
Source-based review of native SSE candidate: https://github.com/Podtverzhdeno/hermes-agent/pull/4 (SSE sequence replay collision / `unknown` diagnosis concerns).

The working GitHub SDD and engineering log on PR #26 include later decisions and are more authoritative than any offline copy if the branch has changed since packaging.