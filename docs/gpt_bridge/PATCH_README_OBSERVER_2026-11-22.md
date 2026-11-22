# Hermes ↔ GPT Bridge — independent audit patch (2026-11-22)

This package is a **reviewable, isolated patch**, not a live-installed extension and not an automated background service.

## Contents

- `gateway/gpt_bridge_event_audit.py`: strict metadata-only NDJSON event parser and causal audit, no side effects.
- `scripts/gpt_bridge_pr_collision_audit.py`: PR overlap and SHA-bound CI evidence checker, never auto-merges.
- `tests/`: 58 pure-stdlib unit/negative tests for privacy, malicious input, replay, unknown effects, source gaps, 30+ agent coordination.
- `docs/gpt_bridge/SDD_OBSERVER_REVIEW_AND_INTEGRATION_2026-11-22.md`: architecture evaluation, failure catalog, gates, decisions.
- `docs/gpt_bridge/ENGINEERING_LOG_OBSERVER_2026-11-22.md`: factual audit ledger and remaining blockers.
- `.github/workflows/gpt-bridge-observer-offline.yml`: Python 3.11, 3.12 and 3.13 proposed CI.

## Test offline from repository root

```sh
python -m compileall -q gateway/gpt_bridge_event_audit.py scripts/gpt_bridge_pr_collision_audit.py
python -m unittest discover -s tests/gateway -p 'test_gpt_bridge_event_audit.py' -q
python -m unittest discover -s tests/scripts -p 'test_gpt_bridge_pr_collision_audit.py' -q
python -m gateway.gpt_bridge_event_audit redacted-events.ndjson --output audit.json
python scripts/gpt_bridge_pr_collision_audit.py reviewed-pr-snapshot.json
```

Input export must follow the v1 envelope described in draft PR #7 SDD. Do not include raw prompts, credentials, messages or tool arguments.

## Integration boundaries

- Do **not** integrate against an unknown / unverified local Chrome extension; local Workspace MCP was disconnected during the audit.
- Do **not** activate a second scheduler competing with recent upstream Kanban.
- Do **not** merge overlapping PR #4/#5/#6 independently; choose a single gateway integration owner.
- Do **not** treat offline tests as GitHub CI or live Hermes E2E success.
- External effects with unknown outcome must be reconciled with independent evidence before any retry.
- The observer is intentionally non-authoritative: it never grants approval, final success, tool effects or retry rights.

Repository source snapshot: `Podtverzhdeno/hermes-agent@7e9100901819ee44c16b4ddcb79a6bcb7909f591`.