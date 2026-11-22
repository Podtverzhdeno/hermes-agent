"""Single-host WAL contention regression for a 30-agent prototype workload.

This proves only atomic SQLite queue claims on ONE host, not distributed Kanban,
cross-process resource locking, external side-effect exactly-once, or real CDP
browser throughput. No network access and no provider credentials are used.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from autopilot import AutopilotLedger


def test_30_workers_claim_30_distinct_tasks_without_duplicate_claims(tmp_path):
    db_path = tmp_path / "multiagent.sqlite3"
    ledger = AutopilotLedger(db_path)
    submitted = {
        ledger.submit(
            request_key=f"request-{i}",
            project=f"project-{i % 3}",
            goal=f"Safe simulated task {i}",
            revision="git:sha-for-fixture",
            required_evidence=["tests", "ci"],
            max_attempts=2,
        )
        for i in range(30)
    }
    assert len(submitted) == 30
    barrier = Barrier(30)

    def worker(i):
        barrier.wait(timeout=20)
        # Separate connections are used internally for each claim.
        return ledger.claim(f"agent-{i}", lease_seconds=60)

    with ThreadPoolExecutor(max_workers=30) as pool:
        claimed = list(pool.map(worker, range(30)))
    assert len(claimed) == 30
    assert all(c is not None for c in claimed)
    assert {c["id"] for c in claimed} == submitted
    assert all(c["status"] == "running" and c["fence"] == 1 and
               c["attempts"] == 1 for c in claimed)
    assert ledger.claim("agent-31") is None
    for task in submitted:
        assert sum(e["kind"] == "claimed" for e in ledger.history(task)) == 1


def test_30_competing_workers_cannot_both_take_one_task(tmp_path):
    ledger = AutopilotLedger(tmp_path / "single.sqlite3")
    task = ledger.submit(
        request_key="single", project="project",
        goal="Read-only simulated work", revision="git:sha",
        required_evidence=["ci"], max_attempts=1,
    )
    barrier = Barrier(30)

    def claim(i):
        barrier.wait(timeout=20)
        return ledger.claim(f"agent-{i}", lease_seconds=30)

    with ThreadPoolExecutor(max_workers=30) as pool:
        rows = list(pool.map(claim, range(30)))
    winners = [x for x in rows if x is not None]
    assert len(winners) == 1
    assert winners[0]["id"] == task
    assert winners[0]["fence"] == 1
    assert ledger.get(task)["attempts"] == 1
    assert sum(e["kind"] == "claimed" for e in ledger.history(task)) == 1
