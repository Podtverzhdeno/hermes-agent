import json

from gpt_bridge.cli import main
from gpt_bridge import ObservationStore


def test_diagnose_cli(tmp_path, capsys):
    db = tmp_path / "obs.db"
    s = ObservationStore(db)
    s.append(event_id="e1", run_id="r1", task_id="t1", agent_id="a1",
             fence=1, source_seq=1, kind="worker.heartbeat", source="worker")
    assert main(["--db", str(db), "status", "t1"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["task_id"] == "t1"
    assert output["confidence"] == "reported_only"


def test_integrity_cli(tmp_path, capsys):
    db = tmp_path / "obs.db"
    ObservationStore(db)
    assert main(["--db", str(db), "integrity"]) == 0
    assert json.loads(capsys.readouterr().out)["chain_intact"] is True
