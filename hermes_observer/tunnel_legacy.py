"""Untrusted, offline summary of Tunnel Web Companion's rolling 60-event JSON.

This is a compatibility *negative-test adapter*, NOT a production telemetry
source and NOT a conversion into authenticated Hermes causal events. The real
bridge.py stores only at/stage/reason, with no producer sequence or event IDs.
All outcomes remain unverified. Never execute, retry, approve or close tabs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any

MAX_BYTES = 32_768
MAX_EVENTS = 60
MAX_REASON_LENGTH = 48

# Exact allowlist from Podtverzhdeno/Tunnel bridge.py _event at 2026-11-22,
# bridge blob eaf301ac15ad301464159438d6431cbc91d3e323.
STAGES = frozenset({
    "tab_opening", "tab_created", "assigned", "editor_found", "prompt_filled",
    "send_clicked", "message_saved", "handoff_failed", "done", "submitted",
    "unknown", "watchdog_timeout", "receipt_accepted", "receipt_failed",
    "tab_closed", "tab_close_failed", "tab_missing", "tab_close_skipped",
    "tab_preserved", "auth_context_changed", "runtime_error",
    "report_pending", "report_acked", "report_watchdog", "report_disputed",
    "tab_recovered", "tab_restored", "tab_identity_unverified",
    "tab_binding_disputed", "send_ui_diagnostic",
})

# Only public fixed reason codes may be surfaced; do NOT echo any novel reason.
REASON_MAP = {
    "account_context_changed": "AUTH_CONTEXT_DISPUTED",
    "unexpected_close": "TAB_DISAPPEARED",
    "browser_tab_unavailable": "BROWSER_TARGET_UNAVAILABLE",
    "receipt_rejected": "BRIDGE_RECEIPT_UNCONFIRMED",
    "claim_paused_race": "CLAIM_PAUSE_RACE",
    "tab_open_failed": "TAB_OPEN_FAILED",
    "editor_absent": "EDITOR_ABSENT",
    "button_absent": "SEND_CONTROL_ABSENT",
    "button_disabled": "SEND_CONTROL_DISABLED",
    "button_not_scoped": "SEND_CONTROL_NOT_SCOPED",
    "button_ambiguous": "SEND_CONTROL_AMBIGUOUS",
    "report_not_acked": "REPORT_ACK_UNCONFIRMED",
}
STAGE_MAP = {
    "auth_context_changed": "AUTH_CONTEXT_DISPUTED",
    "receipt_failed": "BRIDGE_RECEIPT_UNCONFIRMED",
    "report_disputed": "BRIDGE_REPORT_DISPUTED",
    "tab_identity_unverified": "BROWSER_TARGET_UNVERIFIED",
    "tab_binding_disputed": "BROWSER_TARGET_DISPUTED",
    "tab_missing": "BROWSER_TARGET_UNAVAILABLE",
    "tab_close_failed": "BROWSER_TARGET_UNAVAILABLE",
    "handoff_failed": "HANDOFF_UNCONFIRMED",
    "watchdog_timeout": "WATCHDOG_SUSPECTED_STALL",
    "report_watchdog": "REPORT_WAIT_STALE",
    "runtime_error": "RUNTIME_ERROR_CLAIMED",
    "unknown": "OUTCOME_UNCONFIRMED",
}

class LegacyTraceError(ValueError):
    """Typed, privacy-neutral refusal; never embeds input or filenames."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise LegacyTraceError("duplicate_json_key")
        obj[key] = value
    return obj


def _constant(_: str) -> None:
    raise LegacyTraceError("nonfinite_json")


def _parse_time(s: object) -> datetime:
    if not isinstance(s, str) or not 20 <= len(s) <= 40 or "T" not in s:
        raise LegacyTraceError("invalid_observation_time")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise LegacyTraceError("invalid_observation_time") from None
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise LegacyTraceError("non_utc_observation_time")
    return dt


def summarize_legacy_trace(raw: bytes) -> dict[str, object]:
    """Summarize one untrusted diagnostics/<uuid>.json without side effects.

    An entirely valid, event-rich file is still a partial observation.
    Original rows are never returned; opaque producer/receipt identity cannot
    be inferred from a legacy file that lacks those fields.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise LegacyTraceError("invalid_trace_bounds")
    try:
        parsed = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except LegacyTraceError:
        raise
    except (ValueError, UnicodeDecodeError):
        # Python 3.11+ may raise ValueError for a >4300-digit JSON integer.
        # It is malformed metadata; it must not crash the diagnostic tool.
        raise LegacyTraceError("invalid_json") from None
    except RecursionError:
        raise LegacyTraceError("json_nesting_exceeded") from None
    if type(parsed) is not list or len(parsed) > MAX_EVENTS:
        raise LegacyTraceError("invalid_event_count")

    stages: set[str] = set()
    hypotheses: set[str] = set()
    previous = None
    clock_regressed = False
    last_stage = None
    for record in parsed:
        if type(record) is not dict or not {"at", "stage"} <= record.keys() or (
            record.keys() - {"at", "stage", "reason"}
        ):
            raise LegacyTraceError("invalid_event_shape")
        stage = record["stage"]
        if type(stage) is not str or stage not in STAGES:
            raise LegacyTraceError("unrecognized_event_stage")
        reason = record.get("reason", "")
        if (type(reason) is not str or len(reason) > MAX_REASON_LENGTH or
            any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in reason)):
            raise LegacyTraceError("invalid_reason_shape")
        at = _parse_time(record["at"])
        if previous is not None and at < previous:
            clock_regressed = True
        previous = at
        last_stage = stage
        stages.add(stage)
        mapped = REASON_MAP.get(reason)
        if mapped is not None:
            hypotheses.add(mapped)
        if stage in STAGE_MAP:
            hypotheses.add(STAGE_MAP[stage])

    if clock_regressed:
        hypotheses.add("OBSERVATION_CLOCK_REGRESSION")
    # Sorted stable output, never dependent on arbitrary input JSON key order.
    hypotheses_sorted = sorted(hypotheses)
    return {
        "contract": "tunnel-web-companion-legacy-60-v0.6.6",
        "evidence_class": "UNTRUSTED_OFFLINE_DIAGNOSTIC_ONLY",
        "source_provenance_authenticated": False,
        "coverage": "unknown_prefix_and_possible_missing_events",
        "coverage_complete": False,
        "window_at_capacity": len(parsed) == MAX_EVENTS,
        "event_count_in_supplied_window": len(parsed),
        "last_observed_stage_claim": last_stage,
        "stage_signals": {
            "send_clicked": "send_clicked" in stages,
            "message_saved": "message_saved" in stages,
            "report_acked": "report_acked" in stages,
            "receipt_accepted": "receipt_accepted" in stages,
        },
        "diagnostic_candidates": hypotheses_sorted[:24],
        "candidate_count": len(hypotheses_sorted),
        "independent_effect_receipt_verified": False,
        "final_delivery_verified": False,
        "action": "read_only_reconciliation_or_operator_review",
        "mutation_allowed": False,
        "external_effect_retry_allowed": False,
        "result": "partial_untrusted_observation" if parsed else "incomplete_observation",
    }
