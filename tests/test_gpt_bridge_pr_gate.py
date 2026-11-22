"""No network, GitHub write, or live-browser side effects."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gpt_bridge_pr_gate.py"
spec = importlib.util.spec_from_file_location("gpt_bridge_pr_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
HEAD_1 = "b" * 40
HEAD_2 = "c" * 40


def entry(n, *, base="main", base_sha=SHA, head_sha=HEAD_1, files=None, domains=None):
    return {"pr": n, "head": f"change/{n}", "head_sha": head_sha,
            "base": base, "base_sha": base_sha, "files": files or [],
            "domains": domains or ["docs"], "draft": True}


def snapshot(*items):
    return {"schema_version": 1, "captured_at": NOW.isoformat().replace("+00:00", "Z"),
            "main_sha": SHA,
            "source_verification": {"local_extension_verified": True, "live_monitor_connected": True},
            "decisions": {"api_pr": None, "observer_pr": None, "control_plane": "upstream_kanban"},
            "proposals": list(items) or [entry(1)]}


def codes(s):
    return [f["code"] for f in gate.evaluate(s, now=NOW)["findings"]]


def test_release_always_requires_external_approval():
    s = snapshot(entry(1, domains=["api", "observer"]))
    s["decisions"].update(api_pr=1, observer_pr=1)
    r = gate.evaluate(s, now=NOW)
    assert r["status"] == "STRUCTURAL_ONLY_NOT_APPROVED"
    assert r["release_authorized"] is False


def test_independent_file_conflict_is_fatal_even_if_different_roles():
    s = snapshot(entry(1, files=["gateway/platforms/api_server.py"]),
                 entry(2, head_sha=HEAD_2, files=["gateway/platforms/api_server.py"]))
    assert "FILE_OWNERSHIP_CONFLICT" in codes(s)


def test_stacked_shared_file_is_review_not_false_independent_conflict():
    s = snapshot(entry(1, files=["a.py"]),
                 entry(2, base="change/1", base_sha=HEAD_1, head_sha=HEAD_2, files=["a.py"]))
    found = codes(s)
    assert "FILE_OWNERSHIP_CONFLICT" not in found
    assert "STACKED_SHARED_PATH_REVIEW" in found


def test_stale_stacked_head_cannot_be_silently_accepted():
    s = snapshot(entry(1, files=["a.py"]),
                 entry(2, base="change/1", base_sha="d" * 40, head_sha=HEAD_2, files=["a.py"]))
    assert "STALE_STACK_BASE" in codes(s)


def test_stale_main_branch_is_detected():
    assert "STALE_MAIN_BASE" in codes(snapshot(entry(1, base_sha="d" * 40)))


def test_unrecognized_parent_is_blocked():
    assert "UNKNOWN_STACK_PARENT" in codes(snapshot(entry(1, base="other/branch")))


def test_stack_cycle_is_reported_without_infinite_loop():
    a, b = entry(1), entry(2, head_sha=HEAD_2)
    a["base"], a["base_sha"] = b["head"], HEAD_2
    b["base"], b["base_sha"] = a["head"], HEAD_1
    assert "STACK_CYCLE" in codes(snapshot(a, b))


def test_duplicate_observer_proposals_and_canonical_choice():
    s = snapshot(entry(1, domains=["observer"]), entry(2, domains=["observer"], head_sha=HEAD_2))
    assert "DUPLICATE_OBSERVER_PROPOSALS" in codes(s)
    assert "CANONICAL_OBSERVER_UNDECIDED" in codes(s)
    s["decisions"]["observer_pr"] = 2
    assert "CANONICAL_OBSERVER_UNDECIDED" not in codes(s)


def test_unverified_local_source_is_not_success():
    s = snapshot(entry(1))
    s["source_verification"] = {"local_extension_verified": False, "live_monitor_connected": False}
    assert {"LOCAL_EXTENSION_UNVERIFIED", "LIVE_MONITOR_UNAVAILABLE"} <= set(codes(s))


def test_old_and_future_snapshots_rejected():
    old = snapshot(entry(1))
    old["captured_at"] = (NOW - timedelta(hours=2)).isoformat()
    assert "SNAPSHOT_STALE_OR_FUTURE" in codes(old)
    future = snapshot(entry(1))
    future["captured_at"] = (NOW + timedelta(hours=1)).isoformat()
    assert "SNAPSHOT_STALE_OR_FUTURE" in codes(future)


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(schema_version=True),
    lambda x: x.update(main_sha="bad"),
    lambda x: x["proposals"][0].update(pr=True),
    lambda x: x["proposals"][0].update(files=["../secret.env"]),
    lambda x: x["proposals"][0].update(files=["a.py", "a.py"]),
    lambda x: x["proposals"][0].update(domains=["api", "api"]),
    lambda x: x["proposals"][0].update(domains=[["api"]]),
    lambda x: x["proposals"][0].update(head="../../evil"),
    lambda x: x["source_verification"].update(live_monitor_connected="yes"),
    lambda x: x["decisions"].update(observer_pr=999),
    lambda x: x.update(captured_at="not-a-date"),
])
def test_invalid_snapshot_fails_closed(mutate):
    s = snapshot(entry(1))
    mutate(s)
    with pytest.raises(gate.InvalidSnapshot):
        gate.evaluate(s, now=NOW)


def test_cli_redacts_untrusted_json_on_invalid_file(tmp_path):
    bad = tmp_path / "snapshot.json"
    bad.write_text('{"credentials":"super-secret"}', encoding="utf-8")
    run = subprocess.run([sys.executable, str(SCRIPT), str(bad)], capture_output=True, text=True)
    assert run.returncode == 2
    assert "super-secret" not in run.stdout + run.stderr
    assert json.loads(run.stdout)["release_authorized"] is False


def test_snapshot_not_modified():
    s = snapshot(entry(1))
    prior = copy.deepcopy(s)
    gate.evaluate(s, now=NOW)
    assert s == prior


def test_cli_does_not_signal_merge_approval_on_clean_snapshot(tmp_path):
    s = snapshot(entry(1, domains=["api", "observer"]))
    s["decisions"].update(api_pr=1, observer_pr=1)
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(s), encoding="utf-8")
    # Even clean structural snapshots must not translate into a green release job.
    # The deterministic test fixture is an old snapshot at runtime; result is BLOCKED.
    # Override max age just for this test in a runtime-local snapshot.
    s["captured_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(s), encoding="utf-8")
    run = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
    assert run.returncode == 3
    assert json.loads(run.stdout)["status"] == "STRUCTURAL_ONLY_NOT_APPROVED"
    run2 = subprocess.run([sys.executable, str(SCRIPT), str(path), "--structural-only-ok"], capture_output=True, text=True)
    assert run2.returncode == 0
    assert json.loads(run2.stdout)["release_authorized"] is False