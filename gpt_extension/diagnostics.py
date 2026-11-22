"""Pure, read-only diagnosis of Hermes orchestration snapshots.

No tool dispatch, network I/O, credentials, or model decisions. The caller must
obtain a consistent snapshot from a trusted ledger adapter and supply its own
wall-clock UTC seconds. A diagnosis is an observation, never an authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True)
class Effect:
    action_key: str
    status: str


@dataclass(frozen=True)
class Evidence:
    kind: str
    revision: str
    conclusion: str
    trusted: bool


@dataclass(frozen=True)
class Snapshot:
    task_id: str
    status: str
    revision: str
    attempts: int
    max_attempts: int
    now: float
    lease_until: float | None = None
    available_at: float | None = None
    last_event_at: float | None = None
    cancel_requested: bool = False
    effects: tuple[Effect, ...] = ()
    required_evidence: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    connector_status: Literal["unknown", "up", "down"] = "unknown"


@dataclass(frozen=True)
class Diagnosis:
    code: str
    severity: Severity
    observation: str
    cause_status: Literal["observed", "unknown"]
    next_action: str
    unresolved_evidence: tuple[str, ...] = ()


_ACTIVE = frozenset({"running", "verifying"})
_STATES = frozenset({
    "queued", "running", "verifying", "retry_wait", "waiting_approval",
    "needs_reconciliation", "blocked", "failed", "cancelled", "succeeded",
})


def diagnose(snapshot: Snapshot, *, progress_slo_seconds: float = 900.0) -> Diagnosis:
    """Classify observed blockers with conservative precedence.

    This function cannot infer *why* a worker disappeared (crash, network,
    context loss, throttling). It never asserts root cause from a timeout.
    """
    s = snapshot
    if not isinstance(s.task_id, str) or not s.task_id.strip():
        raise ValueError("task_id required")
    if not isinstance(s.revision, str) or not s.revision.strip():
        raise ValueError("revision required")
    if s.status not in _STATES:
        raise ValueError("unknown task status")
    if not (0 <= s.attempts <= s.max_attempts and s.max_attempts > 0):
        raise ValueError("invalid attempt counters")
    if progress_slo_seconds <= 0:
        raise ValueError("progress SLO must be positive")
    if s.connector_status not in ("up", "down", "unknown"):
        raise ValueError("invalid connector status")

    # An externally reserved effect is never safe to replay just because a
    # task/session died or a connector stopped responding.
    uncertain = tuple(sorted(e.action_key for e in s.effects if e.status == "reserved"))
    if uncertain or s.status == "needs_reconciliation":
        return Diagnosis(
            "EXTERNAL_EFFECT_UNCERTAIN", "critical",
            "An external action has no confirmed, independently checked outcome.",
            "observed", "Block retries; reconcile each action against its provider receipt.",
            uncertain,
        )

    complete = {
        e.kind for e in s.evidence
        if e.trusted and e.revision == s.revision and e.conclusion == "success"
    }
    missing = tuple(sorted(set(s.required_evidence) - complete))
    if s.status == "succeeded":
        if not s.required_evidence:
            return Diagnosis("EVIDENCE_POLICY_MISSING", "critical",
                             "A terminal success has no declared verification policy.",
                             "observed", "Reject success; restore the required-evidence contract.")
        if missing:
            return Diagnosis(
                "UNVERIFIED_SUCCESS", "critical",
                "Task claims success without all trusted evidence for the target revision.",
                "observed", "Reject success and obtain independent revision-bound verification.",
                missing,
            )
        return Diagnosis("VERIFIED_SUCCESS", "info", "All required evidence is verified.",
                         "observed", "No action required.")

    if s.cancel_requested and s.status not in {"failed", "cancelled", "blocked"}:
        return Diagnosis("CANCELLATION_PENDING", "warning",
                         "Cancellation is requested but not terminal.", "observed",
                         "Stop issuing new actions; reconcile in-flight effects.")

    if s.status == "waiting_approval":
        return Diagnosis("APPROVAL_PENDING", "warning",
                         "The task is waiting for an independent authorization decision.",
                         "observed", "Request an exact-action approval or deny and block.")

    if s.status in _ACTIVE:
        if s.lease_until is None:
            return Diagnosis("LEASE_MISSING", "critical",
                             "An active task has no lease deadline.", "observed",
                             "Quarantine worker and inspect ledger consistency.")
        if s.lease_until <= s.now:
            return Diagnosis("LEASE_EXPIRED", "warning",
                             "The worker lease has expired; the underlying cause is not established.",
                             "unknown", "Recheck worker health and fence before safe recovery.")

    if s.status == "retry_wait":
        if s.attempts >= s.max_attempts:
            return Diagnosis("RETRY_BUDGET_INCONSISTENT", "critical",
                             "Retry state persists although attempt budget is exhausted.",
                             "observed", "Block dispatch and repair the state transition.")
        return Diagnosis("RETRY_BACKOFF", "info",
                         "The task is waiting for its bounded retry window.",
                         "observed", "Recheck when eligible; do not bypass backoff.")

    if s.status in {"blocked", "failed", "cancelled"}:
        return Diagnosis("TASK_" + s.status.upper(), "warning" if s.status != "failed" else "critical",
                         "The task has a terminal non-success state; the cause is not in this snapshot.",
                         "unknown", "Inspect event history and cited external evidence.")

    # Transport failure is a symptom, not a diagnosis of model/provider failure.
    if s.connector_status == "down":
        return Diagnosis("CONNECTOR_UNAVAILABLE", "warning",
                         "The observed connector is down; agent execution may be independent.",
                         "observed", "Check transport and persist evidence freshness as unknown.")

    if s.status in _ACTIVE and s.last_event_at is not None and s.now - s.last_event_at >= progress_slo_seconds:
        return Diagnosis("NO_PROGRESS_OBSERVED", "warning",
                         "No progress event was observed within the SLO; execution may still be active.",
                         "unknown", "Inspect model/tool/transport spans and heartbeat separately.")

    if s.status == "queued" and s.available_at is not None and s.available_at > s.now:
        return Diagnosis("NOT_YET_ELIGIBLE", "info", "The queue availability time is in the future.",
                         "observed", "Wait for the eligibility time without duplicating intake.")

    if s.status == "verifying" and missing:
        return Diagnosis("VERIFICATION_PENDING", "info",
                         "Trusted evidence for the current revision is incomplete.",
                         "observed", "Check pending verifier jobs; never promote a stale CI result.", missing)

    return Diagnosis("NO_BLOCKER_OBSERVED", "info",
                     "No deterministic blocker was detected in the supplied snapshot.",
                     "unknown", "Continue monitoring; do not infer success or liveness.")
