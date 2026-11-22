"""Offline, concurrent, failure-injection tests; no browser/account is required."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from gpt_bridge import EventConflict, EventValidationError, ObservationStore


class Clock:
    def __init__(self):
        self.value = 1800000000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


@pytest.fixture
def pair(tmp_path):
    clock = Clock()
    return ObservationStore(tmp_path / "events.sqlite", clock=clock), clock


def add(s, event_id="e1", kind="task.started", source_seq=1, fence=1, **kw):
    return s.append(event_id=event_id, run_id="run1", task_id="task1", agent_id="agentA",
                    fence=fence, source_seq=source_seq, kind=kind,
                    source=kw.pop("source", "worker"), **kw)


def test_initial_unobserved(pair):
    s, _ = pair
    assert s.diagnose_task(task_id="task1")["status"] == "unobserved"
    assert s.timeline(task_id="task1") == []
    assert s.verify_chain()


def test_append_replay_idempotent(pair):
    s, _ = pair
    assert add(s) == add(s)
    assert len(s.timeline(task_id="task1")) == 1
    assert s.verify_chain()


def test_conflicting_event_payload_rejected(pair):
    s, _ = pair
    add(s)
    with pytest.raises(EventConflict, match="event_id"):
        add(s, kind="task.failed")


def test_conflicting_source_sequence_rejected(pair):
    s, _ = pair
    add(s)
    with pytest.raises(EventConflict, match="producer sequence"):
        add(s, event_id="e2", kind="worker.heartbeat")


def test_independent_fences_allow_same_source_seq(pair):
    s, _ = pair
    add(s)
    add(s, event_id="newfence", fence=2)
    assert len(s.timeline(task_id="task1")) == 2


def test_reject_free_form_secrets(pair):
    s, _ = pair
    for details in ({"prompt": "private conversation"},
                    {"cookie": "secret"}, {"url": "https://private"},
                    {"error_message": "token=abc"}):
        with pytest.raises(EventValidationError):
            add(s, details=details)
    assert not s.timeline(task_id="task1")


@pytest.mark.parametrize("details", [
    {"reason_code": "some free text"}, {"step_id": "../../credentials"},
    {"http_status": True}, {"http_status": 900}, {"attempt": -1},
    {"detach_reason": "secret"},
])
def test_bad_details(pair, details):
    with pytest.raises(EventValidationError):
        add(pair[0], details=details)


@pytest.mark.parametrize("field,value", [
    ("event_id", "../id"), ("run_id", ""), ("task_id", "hello world"),
    ("agent_id", "url?token=123"), ("fence", True), ("source_seq", 0),
    ("kind", "bad.event"), ("source", "self_assessed_trusted"),
    ("agent_id", "user@example.com"), ("task_id", "token:secret"),
])
def test_invalid_envelope(pair, field, value):
    kw = dict(event_id="e1", run_id="r1", task_id="t1", agent_id="a1",
              fence=1, source_seq=1, kind="task.started", source="worker")
    kw[field] = value
    with pytest.raises(EventValidationError):
        pair[0].append(**kw)


def test_browser_detach_reason_and_recovery(pair):
    s, _ = pair
    add(s, kind="cdp.detached", details={"target_id": "tabA", "detach_reason": "canceled_by_user"})
    assert s.diagnose_task(task_id="task1")["reason"] == "CDP_DETACHED_CANCELED_BY_USER"
    add(s, event_id="e2", source_seq=2, kind="cdp.attached", details={"target_id": "tabA"})
    assert s.diagnose_task(task_id="task1")["status"] == "observed_active"


def test_model_silent_not_asserted_crashed(pair):
    s, clock = pair
    add(s, kind="model.request_started")
    clock.advance(121)
    status = s.diagnose_task(task_id="task1")
    assert status["status"] == "suspected_stall"
    assert status["confidence"] == "reported_only"


def test_heartbeat_not_clear_unresolved_approval(pair):
    s, _ = pair
    add(s, kind="approval.requested", details={"action_id": "editA"})
    add(s, event_id="e2", source_seq=2, kind="worker.heartbeat")
    assert s.diagnose_task(task_id="task1")["status"] == "waiting_approval"


def test_external_uncertain_not_retried_on_heartbeat(pair):
    s, _ = pair
    add(s, kind="effect.uncertain", details={"action_id": "commitA"})
    add(s, event_id="e2", source_seq=2, kind="worker.heartbeat")
    assert s.diagnose_task(task_id="task1")["status"] == "needs_reconciliation"
    add(s, event_id="e3", source_seq=3, kind="effect.reconciled", details={"action_id": "commitA"})
    assert s.diagnose_task(task_id="task1")["status"] == "observed_active"


def test_fenced_late_old_worker_cannot_set_current_status(pair):
    s, _ = pair
    add(s, kind="task.failed", fence=1)
    add(s, event_id="new", kind="task.started", fence=2)
    add(s, event_id="old_late", source_seq=2, kind="task.failed", fence=1)
    assert s.diagnose_task(task_id="task1")["status"] == "observed_active"


def test_reported_completion_not_trusted_completion(pair):
    s, _ = pair
    add(s, kind="task.completed")
    result = s.diagnose_task(task_id="task1")
    assert result["status"] == "reported_completed"
    assert result["confidence"] == "reported_only"


def test_concurrent_writers_and_hash_chain(pair):
    s, clock = pair
    paths = s.path
    def writer(n):
        local = ObservationStore(paths, clock=clock)
        return local.append(event_id=f"evt{n}", run_id="run1", task_id="task1",
                            agent_id=f"agent{n}", fence=1, source_seq=1,
                            kind="worker.heartbeat", source="worker")
    with ThreadPoolExecutor(max_workers=24) as pool:
        seq = list(pool.map(writer, range(60)))
    assert len(set(seq)) == 60
    assert len(s.timeline(task_id="task1")) == 60
    assert s.verify_chain()


def test_hash_chain_detects_modified_payload(pair):
    s, _ = pair
    add(s)
    with sqlite3.connect(s.path) as db:
        db.execute("UPDATE observations SET payload=? WHERE event_id='e1'", ('{}',))
    assert not s.verify_chain()


def test_details_whitelist_roundtrip(pair):
    s, _ = pair
    add(s, details={"step_id": "step-1", "reason_code": "HTTP_RETRY", "http_status": 429,
                    "attempt": 2, "detach_reason": "unknown"})
    assert s.timeline(task_id="task1")[0]["details"]["http_status"] == 429


def test_limit_guards(pair):
    s, _ = pair
    with pytest.raises(EventValidationError):
        s.timeline(task_id="task1", limit=100000)
    with pytest.raises(EventValidationError):
        s.diagnose_task(task_id="task1", stale_after_seconds=0)


def test_two_unresolved_actions_cannot_cross_resolve(pair):
    s, _ = pair
    add(s, kind="effect.uncertain", details={"action_id": "sendA"})
    add(s, event_id="e2", source_seq=2, kind="effect.uncertain", details={"action_id": "sendB"})
    add(s, event_id="e3", source_seq=3, kind="effect.reconciled", details={"action_id": "sendA"})
    result = s.diagnose_task(task_id="task1")
    assert result["status"] == "needs_reconciliation"
    assert result["open_effects"] == 1


def test_reconnect_of_other_tab_does_not_hide_detach(pair):
    s, _ = pair
    add(s, kind="cdp.detached", details={"target_id": "tabA"})
    add(s, event_id="e2", source_seq=2, kind="cdp.attached", details={"target_id": "tabB"})
    assert s.diagnose_task(task_id="task1")["status"] == "integration_unavailable"


def test_effect_uncertainty_outweighs_completed_or_disconnected(pair):
    s, _ = pair
    add(s, kind="effect.uncertain", details={"action_id": "sendA"})
    add(s, event_id="e2", source_seq=2, kind="transport.disconnected",
        details={"channel_id": "gptapi"})
    add(s, event_id="e3", source_seq=3, kind="task.completed")
    assert s.diagnose_task(task_id="task1")["status"] == "needs_reconciliation"


def test_two_producers_for_one_agent_have_independent_sequences(pair):
    s, _ = pair
    add(s, producer_id="worker1")
    add(s, event_id="e2", kind="worker.heartbeat", producer_id="browser1",
        source="browser_extension")
    assert len(s.timeline(task_id="task1")) == 2


def test_missing_action_and_target_ids_rejected(pair):
    s, _ = pair
    for kind in ("effect.uncertain", "effect.reconciled", "approval.requested",
                 "approval.resolved", "cdp.attached", "cdp.detached",
                 "transport.connected", "transport.disconnected"):
        with pytest.raises(EventValidationError, match="requires details"):
            add(s, kind=kind)


def test_concurrent_persisted_events_across_restarts(pair):
    s, _ = pair
    add(s)
    reopened = ObservationStore(s.path)
    assert reopened.verify_chain()
    assert reopened.timeline(task_id="task1")[0]["event_id"] == "e1"


def test_readonly_observer_does_not_mutate_db(pair):
    s, _ = pair
    add(s)
    observer = ObservationStore(s.path, readonly=True)
    assert observer.timeline(task_id="task1")
    with pytest.raises(PermissionError):
        observer.append(event_id="w2", run_id="run1", task_id="task1",
                        agent_id="agentA", source_seq=2, fence=1,
                        kind="worker.heartbeat", source="worker")


def test_abrupt_process_exit_before_commit_rolls_back_partial_event(tmp_path):
    """Kill-equivalent process exit inside an uncommitted SQLite transaction."""
    import subprocess
    import sys

    path = tmp_path / "crash-before.db"
    store = ObservationStore(path)
    script = (
        "import sqlite3,os,sys\n"
        "db=sqlite3.connect(sys.argv[1])\n"
        "db.execute('BEGIN IMMEDIATE')\n"
        "db.execute(\"INSERT INTO observations(event_id,run_id,task_id,agent_id,producer_id,"
        "fence,source_seq,kind,source,received_at,payload,prev_hash,event_hash) "
        "VALUES('crash-1','run1','task1','agent1','process1',1,1,'task.started','worker',"
        "123.0,'{}','0','garbage')\")\n"
        "os._exit(73)\n"
    )
    child = subprocess.run([sys.executable, "-c", script, str(path)], check=False)
    assert child.returncode == 73
    assert store.timeline(task_id="task1") == []
    assert store.verify_chain()
    add(store)
    assert store.verify_chain()


def test_abrupt_process_exit_after_commit_supports_same_id_replay(tmp_path):
    """Crash after durable commit but before ACK is harmless under stable replay."""
    import subprocess
    import sys
    from pathlib import Path

    path = tmp_path / "crash-after.db"
    script = (
        "import os,sys\n"
        "from gpt_bridge import ObservationStore\n"
        "s=ObservationStore(sys.argv[1])\n"
        "s.append(event_id='e1',run_id='run1',task_id='task1',agent_id='agentA',"
        "fence=1,source_seq=1,kind='task.started',source='worker')\n"
        "os._exit(74)\n"
    )
    child = subprocess.run([sys.executable, "-c", script, str(path)], check=False)
    assert child.returncode == 74
    store = ObservationStore(path)
    seq = store.append(event_id="e1", run_id="run1", task_id="task1", agent_id="agentA",
                       fence=1, source_seq=1, kind="task.started", source="worker")
    assert seq == 1
    assert len(store.timeline(task_id="task1")) == 1
    assert store.verify_chain()


def test_uncertain_effect_survives_worker_replacement(pair):
    s, _ = pair
    add(s, kind="effect.uncertain", details={"action_id": "effectA"}, fence=1)
    add(s, event_id="new-worker", kind="task.started", fence=2)
    result = s.diagnose_task(task_id="task1")
    assert result["status"] == "needs_reconciliation"
    assert result["fence"] == 2
    assert result["open_effects"] == 1
    assert result["open_effects_from_prior_fences"] == 1


def test_new_epoch_can_reconcile_old_external_effect(pair):
    s, _ = pair
    add(s, kind="effect.uncertain", details={"action_id": "effectA"}, fence=1)
    add(s, event_id="new-worker", kind="task.started", fence=2)
    add(s, event_id="reconcile-new-worker", kind="effect.reconciled",
        source_seq=2, fence=2, details={"action_id": "effectA"})
    result = s.diagnose_task(task_id="task1")
    assert result["status"] == "observed_active"
    assert result["open_effects"] == 0


def test_late_stale_reconciliation_does_not_clear_external_effect(pair):
    s, _ = pair
    add(s, kind="effect.uncertain", details={"action_id": "effectA"}, fence=1)
    add(s, event_id="new-worker", kind="task.started", fence=2)
    add(s, event_id="stale-reconcile", kind="effect.reconciled", fence=1,
        source_seq=2, details={"action_id": "effectA"})
    result = s.diagnose_task(task_id="task1")
    assert result["status"] == "needs_reconciliation"
    assert result["open_effects_from_prior_fences"] == 1


def test_old_epoch_approval_not_inherited_as_new_approval(pair):
    s, _ = pair
    add(s, kind="approval.requested", details={"action_id": "reviewA"}, fence=1)
    add(s, event_id="new-worker", kind="task.started", fence=2)
    assert s.diagnose_task(task_id="task1")["status"] == "observed_active"


def test_reject_unrecognized_uppercase_reason_instead_of_logging_private_text(pair):
    with pytest.raises(EventValidationError, match="reason catalog"):
        add(pair[0], details={"reason_code": "PRIVATE_API_KEY_VALUE"})
