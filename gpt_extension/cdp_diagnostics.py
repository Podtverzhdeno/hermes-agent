"""Read-only CDP transport diagnosis for an owner-authorized Hermes browser lane.

This module has no CDP client, browser access, secrets, or state mutation. An
independent trusted observer must provide a consistent, authenticated snapshot.
Neither an ACK nor a ChatGPT canary is evidence of successful task execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BrowserLaneSnapshot:
    task_id: str
    lane_id: str
    expected_fence: int
    observed_fence: int | None
    last_command_seq: int
    last_ack_seq: int
    now: float
    last_transport_event_at: float | None
    bridge_connected: bool
    extension_connected: bool
    tab_attached: bool
    ui_message_observed: bool = False
    transport_silence_slo_seconds: float = 120.0


@dataclass(frozen=True)
class BrowserLaneDiagnosis:
    code: str
    severity: Literal["info", "warning", "critical"]
    observation: str
    cause_status: Literal["observed", "unknown"]
    next_action: str
    permits_task_completion: bool = False


def diagnose_browser_lane(snapshot: BrowserLaneSnapshot) -> BrowserLaneDiagnosis:
    """Identify only what supplied CDP transport evidence actually proves.

    A missing response does not imply model inactivity. An unacknowledged
    command must not be blindly resent; it might already have been delivered.
    The returned result never grants tool approval, task completion or retry.
    """
    s = snapshot
    if not s.task_id.strip() or not s.lane_id.strip():
        raise ValueError("task_id and lane_id are required")
    if s.expected_fence < 1:
        raise ValueError("expected_fence must be positive")
    if s.observed_fence is not None and s.observed_fence < 0:
        raise ValueError("observed_fence must be nonnegative")
    if min(s.last_command_seq, s.last_ack_seq) < 0:
        raise ValueError("command and ACK sequence must be nonnegative")
    if s.transport_silence_slo_seconds <= 0:
        raise ValueError("transport silence SLO must be positive")

    def result(code, severity, observation, cause_status, next_action):
        return BrowserLaneDiagnosis(code, severity, observation, cause_status, next_action)

    if s.observed_fence is not None and s.expected_fence != s.observed_fence:
        return result(
            "CDP_FENCE_MISMATCH", "critical", "The browser lane has a different active fence.",
            "observed", "Reject commands and re-establish exclusive lane ownership.",
        )
    if s.last_ack_seq > s.last_command_seq:
        return result(
            "CDP_ACK_INCONSISTENT", "critical", "Transport ACK exceeds the recorded command sequence.",
            "observed", "Quarantine the lane; inspect sequence continuity and source authenticity.",
        )
    if not s.bridge_connected:
        return result(
            "CDP_BRIDGE_DOWN", "warning", "The CDP bridge is not connected.",
            "observed", "Check authorized bridge health; do not resend uncertain commands.",
        )
    if not s.extension_connected:
        return result(
            "CDP_EXTENSION_DOWN", "warning", "The browser extension transport is disconnected.",
            "observed", "Re-establish the authenticated extension transport and reconcile pending commands.",
        )
    if not s.tab_attached:
        return result(
            "CDP_TAB_DETACHED", "warning", "No authorized browser tab is attached to this lane.",
            "observed", "Stop issuance and verify tab ownership before attaching a new target.",
        )
    if s.observed_fence is None:
        return result(
            "CDP_FENCE_UNVERIFIED", "warning", "Lane ownership fence has not been verified.",
            "unknown", "Verify the owner and fence before allowing any browser command.",
        )
    if s.last_command_seq > s.last_ack_seq:
        return result(
            "CDP_ACK_PENDING", "warning", "The last command has no observed transport acknowledgement.",
            "unknown", "Query command status; never blindly resend a non-idempotent command.",
        )
    if s.last_transport_event_at is None:
        return result(
            "CDP_NO_TRANSPORT_OBSERVATION", "warning", "No transport event timestamp was supplied.",
            "unknown", "Probe transport health independently without inferring model completion.",
        )
    if s.now - s.last_transport_event_at >= s.transport_silence_slo_seconds:
        return result(
            "CDP_TRANSPORT_SILENT", "warning", "No transport event observed inside the configured SLO.",
            "unknown", "Check bridge, browser and backend spans separately; preserve task state.",
        )
    if s.ui_message_observed:
        return result(
            "CDP_UI_MESSAGE_ONLY", "info", "A UI message was observed, not an independently verified task result.",
            "observed", "Correlate to task ID and obtain independent artifact/effect verification.",
        )
    return result(
        "CDP_TRANSPORT_HEALTHY", "info", "No CDP transport blocker observed in this snapshot.",
        "unknown", "Continue monitoring; do not infer model liveness or task success.",
    )
