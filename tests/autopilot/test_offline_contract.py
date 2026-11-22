"""Offline stdlib-only smoke contracts for the Autopilot ledger.

Run without installing Hermes or pytest:
    python -m unittest discover -s tests/autopilot -p 'test_offline_contract.py' -v
"""

from concurrent.futures import ThreadPoolExecutor
import tempfile
from pathlib import Path
import unittest

from autopilot import ApprovalRequired, AutopilotLedger, LedgerConflict


class FakeClock:
    def __init__(self):
        self.t = 1800000000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class OfflineLedgerContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = FakeClock()
        self.path = Path(self.temp.name) / "ledger.db"
        self.ledger = AutopilotLedger(self.path, self.clock)

    def task(self, key="one", attempts=3):
        return self.ledger.submit(
            request_key=key,
            project="sandbox",
            goal="Read a test project and verify",
            revision="git:head",
            required_evidence=("tests", "head"),
            max_attempts=attempts,
        )

    def claim(self, name="worker"):
        entry = self.ledger.claim(name, lease_seconds=15)
        self.assertIsNotNone(entry)
        return entry

    def test_concurrent_claim_is_exclusive(self):
        ids = [self.task(f"job-{i}") for i in range(2)]

        def acquire(i):
            worker = AutopilotLedger(self.path, self.clock)
            return worker.claim("worker-" + str(i), lease_seconds=15)

        with ThreadPoolExecutor(max_workers=6) as pool:
            claims = list(pool.map(acquire, range(6)))
        claims = [claim for claim in claims if claim]
        self.assertEqual({claim["id"] for claim in claims}, set(ids))
        self.assertEqual(len(claims), 2)

    def test_reopen_keeps_exact_state(self):
        task = self.task()
        original = self.claim()
        again = AutopilotLedger(self.path, self.clock)
        self.assertEqual(again.get(task)["status"], "running")
        self.assertEqual(again.get(task)["fence"], original["fence"])
        self.assertIsNone(again.claim("rival"))

    def test_untrusted_evidence_never_completes(self):
        task = self.task()
        claim = self.claim()
        self.ledger.begin_verification(task, "worker", claim["fence"])
        self.ledger.record_evidence(task, "tests", "pytest", "git:head",
                                    "passed", "local-report", trusted=False)
        self.ledger.record_evidence(task, "head", "github", "git:head",
                                    "passed", "remote-report", trusted=True)
        self.assertFalse(self.ledger.finalize(task, "worker", claim["fence"]))
        self.ledger.record_evidence(task, "tests", "pytest", "git:head",
                                    "passed", "verifier-report", trusted=True)
        self.assertTrue(self.ledger.finalize(task, "worker", claim["fence"]))

    def test_approval_is_required_for_effects(self):
        task = self.task()
        claim = self.claim()
        with self.assertRaises(ApprovalRequired):
            self.ledger.reserve_effect(task, "worker", claim["fence"],
                                       "push", "sha256:x")
        self.ledger.request_approval(task, "worker", claim["fence"],
                                     "push", "sha256:x", self.clock() + 100)
        self.ledger.decide_approval(task, "push", "sha256:x", "human-owner", True)
        next_claim = self.claim("next")
        self.ledger.reserve_effect(task, "next", next_claim["fence"], "push",
                                   "sha256:x")
        with self.assertRaises(LedgerConflict):
            self.ledger.reserve_effect(task, "next", next_claim["fence"],
                                       "push", "sha256:x")

    def test_unknown_effect_requires_explicit_reconciliation(self):
        task = self.task()
        claim = self.claim()
        self.ledger.request_approval(task, "worker", claim["fence"],
                                     "send", "sha256:y", self.clock() + 90)
        self.ledger.decide_approval(task, "send", "sha256:y", "human-owner", True)
        claim = self.claim("next")
        self.ledger.reserve_effect(task, "next", claim["fence"], "send", "sha256:y")
        self.clock.advance(16)
        self.assertIsNone(self.ledger.claim("recovering"))
        self.assertEqual(self.ledger.get(task)["status"], "needs_reconciliation")
        self.assertEqual(self.ledger.effects(task)[0]["status"], "reserved")
        self.ledger.reconcile_effect(task, "send", "acknowledged", "remote:789")
        self.assertEqual(self.ledger.effects(task)[0]["result_ref"], "remote:789")

    def test_approvals_do_not_exhaust_attempts(self):
        task = self.task(attempts=1)
        claim = self.claim()
        for step in range(3):
            key = "change-" + str(step)
            digest = "sha256:" + str(step)
            self.ledger.request_approval(task, "worker", claim["fence"],
                                         key, digest, self.clock() + 120)
            self.ledger.decide_approval(task, key, digest, "human-owner", True)
            claim = self.claim()
            self.assertEqual(claim["attempts"], 1)

    def test_timeout_is_fenced_exactly_at_lease_end(self):
        task = self.task()
        claim = self.claim()
        self.clock.advance(15)
        with self.assertRaises(LedgerConflict):
            self.ledger.begin_verification(task, "worker", claim["fence"])
        self.assertIsNone(self.ledger.claim("replacement"))
        self.assertEqual(self.ledger.get(task)["status"], "retry_wait")

    def test_approval_expiry_does_not_hang(self):
        task = self.task()
        claim = self.claim()
        self.ledger.request_approval(task, "worker", claim["fence"],
                                     "delete", "sha256:z", self.clock() + 9)
        self.clock.advance(10)
        self.assertIsNone(self.ledger.claim("replacement"))
        self.assertEqual(self.ledger.get(task)["status"], "blocked")
        self.assertEqual(self.ledger.approval_queue(), [])

    def test_cancel_revokes_mutations(self):
        task = self.task()
        claim = self.claim()
        self.ledger.cancel(task)
        with self.assertRaises(LedgerConflict):
            self.ledger.reserve_effect(task, "worker", claim["fence"],
                                       "danger", "sha256:bad")
        self.clock.advance(16)
        self.assertIsNone(self.ledger.claim("replacement"))
        self.assertEqual(self.ledger.get(task)["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
