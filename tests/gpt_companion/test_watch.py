"""Read-only transition monitoring tests; no model, network or browser needed."""

import json
from concurrent.futures import ThreadPoolExecutor

from gpt_companion import EventJournal
from gpt_companion.watch import StatusWatch, main


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def jump(self, seconds):
        self.t += seconds


def ev(seq, kind, **kwargs):
    return {"schema_version": 1, "event_id": f"event-{seq}", "source": "worker",
            "run_id": "run-42", "attempt": 1, "sequence": seq, "kind": kind, **kwargs}


def test_status_transition_dedup_and_restart(tmp_path):
    c = Clock()
    journal = EventJournal(tmp_path / "events.db", clock=c)
    journal.ingest(ev(1, "worker.started"))
    monitor = StatusWatch(journal.path, tmp_path / "alerts.db", clock=c)
    first = monitor.sample("run-42")
    assert first["diagnosis"]["state"] == "RECENT_TELEMETRY"
    assert monitor.sample("run-42") is None
    c.jump(130)
    second = monitor.sample("run-42")
    assert second["diagnosis"]["state"] == "WORKER_UNRESPONSIVE"
    assert len(monitor.history("run-42")) == 2
    after_restart = StatusWatch(journal.path, tmp_path / "alerts.db", clock=c)
    assert after_restart.sample("run-42") is None
    assert len(after_restart.history("run-42")) == 2


def test_external_effect_remains_reconciliation_only(tmp_path):
    c = Clock()
    journal = EventJournal(tmp_path / "events.db", clock=c)
    journal.ingest(ev(1, "tool.effect_reserved", action_id="publish-pr"))
    monitor = StatusWatch(journal.path, tmp_path / "alerts.db", clock=c)
    assert monitor.sample("run-42")["diagnosis"]["state"] == "EFFECT_IN_FLIGHT"
    c.jump(130)
    current = monitor.sample("run-42")["diagnosis"]
    assert current["state"] == "NEEDS_RECONCILIATION"
    assert current["next_action"] == "RECONCILE_EFFECT_RECEIPT"


def test_parallel_watch_instances_do_not_duplicate_same_transition(tmp_path):
    c = Clock()
    journal = EventJournal(tmp_path / "events.db", clock=c)
    journal.ingest(ev(1, "run.accepted"))
    path = tmp_path / "alerts.db"
    workers = [StatusWatch(journal.path, path, clock=c) for _ in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        result = list(pool.map(lambda w: w.sample("run-42"), workers))
    assert sum(x is not None for x in result) == 1
    assert len(workers[0].history("run-42")) == 1


def test_no_missing_run_auto_success(tmp_path):
    w = StatusWatch(tmp_path / "events.db", tmp_path / "alerts.db")
    result = w.sample("run-missing")
    assert result["diagnosis"]["state"] == "NOT_OBSERVED"
    assert w.sample("run-missing") is None


def test_cli_snapshot_and_restart_dedup(tmp_path, capsys):
    journal = EventJournal(tmp_path / "events.db")
    journal.ingest(ev(1, "run.reported_completed"))
    args = ["--db", str(journal.path), "--status-db", str(tmp_path / "alerts.db"),
            "--run-id", "run-42"]
    assert main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["diagnosis"]["state"] == "AWAITING_VERIFICATION"
    assert main(args) == 0
    assert capsys.readouterr().out == ""


def test_status_db_must_not_overlap_source(tmp_path):
    path = tmp_path / "events.db"
    try:
        StatusWatch(path, path)
    except ValueError as exc:
        assert "distinct" in str(exc)
    else:
        raise AssertionError("journal DB and status DB must be separate")


def test_cli_all_runs_and_bounded_inventory(tmp_path, capsys):
    journal = EventJournal(tmp_path / "events.db")
    journal.ingest(ev(1, "worker.started"))
    other = {**ev(1, "run.accepted"), "run_id": "run-43", "event_id": "event-run43"}
    journal.ingest(other)
    assert journal.list_runs(limit=1) == ["run-43"]
    assert set(journal.list_runs()) == {"run-42", "run-43"}
    args = ["--db", str(journal.path), "--status-db", str(tmp_path / "alerts.db"), "--all"]
    assert main(args) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert {json.loads(line)["diagnosis"]["run_id"] for line in lines} == {"run-42", "run-43"}


def test_status_watcher_records_second_prior_attempt_effect(tmp_path):
    """A new unresolved effect requires a fresh incident even with unchanged state."""
    c = Clock()
    journal = EventJournal(tmp_path / "effects.db", clock=c)
    journal.ingest(ev(1, "tool.effect_reserved", action_id="write-one"))
    journal.ingest({**ev(1, "worker.started"), "attempt": 2,
                    "source": "replacement-worker", "event_id": "attempt-2-start"})
    watcher = StatusWatch(journal.path, tmp_path / "incidents.db", clock=c)
    before = watcher.sample("run-42")
    assert before["diagnosis"]["state"] == "NEEDS_RECONCILIATION"
    assert [x["action_id"] for x in before["diagnosis"]["unresolved_effects_prior_attempts"]] == ["write-one"]
    journal.ingest(ev(2, "tool.effect_reserved", action_id="write-two"))
    after = watcher.sample("run-42")
    assert after is not None
    assert after["diagnosis"]["state"] == "NEEDS_RECONCILIATION"
    assert [x["action_id"] for x in after["diagnosis"]["unresolved_effects_prior_attempts"]] == ["write-one", "write-two"]
    assert len(watcher.history("run-42")) == 2


def test_watcher_tracks_partial_repair_of_prior_attempt_sequence_gap(tmp_path):
    c = Clock()
    journal = EventJournal(tmp_path / "events.db", clock=c)
    journal.ingest(ev(1, "worker.started"))
    journal.ingest(ev(4, "worker.stopped"))
    journal.ingest({**ev(1, "worker.started"), "source": "replacement",
                    "event_id": "replacement-1", "attempt": 2})
    watcher = StatusWatch(journal.path, tmp_path / "alerts.db", clock=c)
    first = watcher.sample("run-42")
    assert first["diagnosis"]["state"] == "TRACE_INCOMPLETE"
    assert first["diagnosis"]["missing_sequences_prior_attempts"] == 2
    journal.ingest(ev(2, "worker.heartbeat"))
    second = watcher.sample("run-42")
    assert second is not None
    assert second["diagnosis"]["state"] == "TRACE_INCOMPLETE"
    assert second["diagnosis"]["missing_sequences_prior_attempts"] == 1
    journal.ingest(ev(3, "worker.progress"))
    third = watcher.sample("run-42")
    assert third["diagnosis"]["missing_sequences_prior_attempts"] == 0
    assert third["diagnosis"]["state"] == "RECENT_TELEMETRY"
    assert len(watcher.history("run-42")) == 3
