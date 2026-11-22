"""Offline contract tests: no browser access, no provider calls, no durable ledger."""
import uuid

import pytest

from gateway.gpt_bridge_observer import (
    InvalidBridgeEvent, ReadOnlyEventObserver, validate_event,
)


def evt(producer="p-1", seq=1, **kw):
    e = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "producer_id": producer,
        "source_event_seq": seq,
        "run_id": "run-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "trace_id": "1" * 32,
        "span_id": "2" * 16,
        "occurred_at_utc": "2026-11-22T10:00:00Z",
        "observed_at_utc": "2026-11-22T10:00:01+00:00",
        "kind": "worker.heartbeat",
        "trust_level": "adapter_observed",
    }
    e.update(kw)
    return e


def test_valid_metadata_only_event():
    x = evt()
    assert validate_event(x) == x


@pytest.mark.parametrize("patch", [
    {"schema_version": 2},
    {"source_event_seq": True},
    {"source_event_seq": 0},
    {"source_event_seq": -1},
    {"trace_id": "0" * 32},
    {"trace_id": "1" * 31},
    {"span_id": "0" * 16},
    {"observed_at_utc": "2026-11-22T10:00:00"},
    {"trust_level": "verified_by_ai"},
    {"kind": "tool.run_unsafe"},
    {"kind": []},
    {"kind": {}},
    {"trust_level": []},
    {"event_id": "not-a-uuid"},
    {"causation_event_id": "bad"},
    {"reason_code": "contains secret"},
    {"evidence_refs": ["/home/private/token.txt"]},
    {"effect_key": "x" * 129},
    {"lease_fence": -1},
    {"access_token": "SECRET"},
    {"payload": {"prompt": "private"}},
])
def test_fail_closed_validation(patch):
    with pytest.raises(InvalidBridgeEvent) as exc:
        validate_event(evt(**patch))
    assert "SECRET" not in str(exc.value)
    assert "private" not in str(exc.value)


def test_reject_oversized_event_and_nonfinite():
    with pytest.raises(InvalidBridgeEvent, match="event_too_large"):
        validate_event(evt(agent_id="a" * 100), max_bytes=300)
    with pytest.raises(InvalidBridgeEvent):
        validate_event(evt(lease_fence=float("nan")))


def test_idempotent_event_replay_and_event_id_collision():
    o = ReadOnlyEventObserver()
    e = evt()
    assert o.ingest(e).accepted
    assert o.ingest(e).code == "duplicate_event"
    assert o.ingest({**e, "source_event_seq": 2}).code == "event_id_collision"
    assert o.snapshot()["recent_events"] == 1


def test_sequence_collision_rejected():
    o = ReadOnlyEventObserver()
    first = evt(seq=2)
    assert o.ingest(first).code == "gap_suspected"
    assert o.ingest(evt(seq=2)).code == "sequence_collision"
    assert o.snapshot()["recent_events"] == 1


def test_gap_fills_without_fabricated_failure():
    o = ReadOnlyEventObserver()
    third = o.ingest(evt(seq=3))
    assert third.code == "gap_suspected"
    assert third.pending_gap == (1, 2)
    assert o.ingest(evt(seq=1)).pending_gap == (2, 2)
    resolved = o.ingest(evt(seq=2))
    assert resolved.code == "observed"
    assert resolved.contiguous_through == 3
    assert resolved.pending_gap is None


def test_parallel_producers_may_each_start_at_one():
    o = ReadOnlyEventObserver(max_producers=40)
    for i in range(30):
        result = o.ingest(evt(producer=f"worker-{i}", seq=1))
        assert result.accepted and result.contiguous_through == 1
    assert o.snapshot()["producers"] == 30
    assert o.snapshot()["out_of_order_events"] == 0


def test_one_bad_producer_does_not_corrupt_others():
    o = ReadOnlyEventObserver(max_reorder=8)
    assert o.ingest(evt("p-1", 20)).code == "reorder_window_exceeded"
    assert o.ingest(evt("p-2", 1)).accepted
    assert o.snapshot()["producers"] == 1


def test_stale_beyond_cache_not_mistaken_for_duplicate():
    o = ReadOnlyEventObserver(max_recent=1)
    assert o.ingest(evt(seq=1)).accepted
    assert o.ingest(evt(seq=2)).accepted
    assert o.ingest(evt(seq=1)).code == "stale_unverifiable"


def test_causation_missing_is_not_failure_and_later_resolves():
    o = ReadOnlyEventObserver()
    parent = evt(seq=1)
    child = evt(seq=2, causation_event_id=parent["event_id"])
    x = o.ingest(child)
    assert x.missing_causal_parent
    assert o.snapshot()["unresolved_causal_links"] == 1
    o.ingest(parent)
    assert o.snapshot()["unresolved_causal_links"] == 0


def test_self_causation_rejected_without_state_mutation():
    o = ReadOnlyEventObserver()
    e = evt()
    e["causation_event_id"] = e["event_id"]
    assert not o.ingest(e).accepted
    assert o.snapshot()["recent_events"] == 0


def test_contiguous_publisher_then_gap_and_reorder():
    o = ReadOnlyEventObserver(max_reorder=16)
    for i in range(1, 6):
        assert o.ingest(evt(seq=i)).code == "observed"
    assert o.ingest(evt(seq=8)).pending_gap == (6, 7)
    assert o.ingest(evt(seq=7)).pending_gap == (6, 6)
    assert o.ingest(evt(seq=6)).contiguous_through == 8


def test_producer_capacity_is_bounded():
    o = ReadOnlyEventObserver(max_producers=1)
    assert o.ingest(evt("p-1")).accepted
    assert o.ingest(evt("p-2")).code == "producer_capacity"


def test_boolean_or_fake_fence_is_never_accepted():
    for value in (True, -1, 2**63):
        assert ReadOnlyEventObserver().ingest(evt(lease_fence=value)).accepted is False


def test_no_external_action_or_agent_failure_inferred():
    o = ReadOnlyEventObserver()
    e = evt(seq=2, kind="worker.lease_expired")
    outcome = o.ingest(e)
    assert outcome.code == "gap_suspected"
    assert o.snapshot()["status"] == "partial_observation"
    assert not hasattr(o, "retry") and not hasattr(o, "execute")


def test_thirty_producers_out_of_order_but_eventually_contiguous():
    """Deterministic 30x50 replay; gaps are transient, not task failures."""
    import random
    rng = random.Random(20261122)
    o = ReadOnlyEventObserver(max_producers=40, max_reorder=64)
    events = [evt(producer=f"worker-{w}", seq=s)
              for w in range(30) for s in range(1, 51)]
    rng.shuffle(events)
    outcomes = [o.ingest(e) for e in events]
    assert all(x.accepted for x in outcomes)
    assert o.snapshot()["producers"] == 30
    assert o.snapshot()["out_of_order_events"] == 0
    assert o.snapshot()["recent_events"] == 1500


def test_offline_cli_only_outputs_metadata(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path
    cli = Path(__file__).resolve().parents[2] / "scripts" / "gpt_bridge_observe.py"
    e = evt()
    secret = "SECRET_NEVER_LOG"
    payload = (json.dumps(e) + "\n" + json.dumps({**e, "prompt": secret}) + "\n").encode()
    proc = subprocess.run([sys.executable, str(cli)], input=payload,
                          capture_output=True, timeout=10, check=True)
    output = proc.stdout.decode()
    assert "observed" in output and "unsupported_event_shape" in output
    assert secret not in output and secret not in proc.stderr.decode()


def test_invalid_max_event_bytes_does_not_create_fake_acceptances():
    o = ReadOnlyEventObserver(max_event_bytes=10)
    assert not o.ingest(evt()).accepted


def test_cli_rejects_duplicate_json_keys_without_raw_leak():
    import subprocess
    import sys
    from pathlib import Path
    cli = Path(__file__).resolve().parents[2] / "scripts" / "gpt_bridge_observe.py"
    event = evt()
    import json
    raw = json.dumps(event)
    poisoned = raw[:-1] + ', "kind": "task.completed"}'
    proc = subprocess.run([sys.executable, str(cli)], input=(poisoned + "\n").encode(),
                          capture_output=True, timeout=10, check=True)
    summary = json.loads(proc.stdout)
    assert summary["outcomes"]["invalid_json"] == 1
    assert summary["observer"]["recent_events"] == 0
    assert "task.completed" not in proc.stdout.decode()


def test_same_event_id_and_seq_with_changed_payload_is_conflict():
    observer = ReadOnlyEventObserver()
    original = evt()
    assert observer.ingest(original).accepted
    mutated = {**original, "kind": "task.completed"}
    assert observer.ingest(mutated).code == "event_id_collision"
    assert observer.snapshot()["recent_events"] == 1
