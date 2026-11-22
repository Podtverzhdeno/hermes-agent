"""Offline contract tests: NO browser, provider key, or external effects."""
import os
import tempfile
import threading
import unittest
import uuid

from gateway.gpt_causal_observer import CausalObserver, InvalidEvent, EventConflict


def event(seq, kind="worker.heartbeat", producer="boot-a", **extra):
    e = {"schema_version": 1, "event_id": str(uuid.uuid4()),
         "producer_id": producer, "source_event_seq": seq, "run_id": "run-a",
         "task_id": "task-a", "attempt_id": "attempt-a", "lease_fence": 7,
         "kind": kind}
    e.update(extra)
    return e


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.db = CausalObserver()

    def tearDown(self):
        self.db.close()

    def test_exact_redelivery_is_idempotent(self):
        e = event(1)
        self.assertEqual("inserted", self.db.ingest(e))
        self.assertEqual("duplicate", self.db.ingest(e))
        self.assertEqual(1, self.db.diagnose("run-a")["event_count"])

    def test_event_identity_conflict(self):
        e = event(1)
        self.db.ingest(e)
        v = dict(e, run_id="run-b")
        with self.assertRaises(EventConflict): self.db.ingest(v)
        with self.assertRaises(EventConflict): self.db.ingest(event(1))
        with self.assertRaises(EventConflict): self.db.ingest(e, trusted_origin=True)

    def test_no_raw_prompt_secrets_or_unbounded_data(self):
        for bad in (dict(event(1), prompt="secret"), dict(event(1), evidence_refs=["secret"]),
                    dict(event(1), task_id="a"*1000), dict(event(1), schema_version=2),
                    dict(event(1), operation_fingerprint="prompt-fragment"),
                    dict(event(1), target_revision="readme text")):
            with self.assertRaises(InvalidEvent): self.db.ingest(bad)
        self.assertEqual(0, self.db.diagnose("run-a")["event_count"])

    def test_python_bool_not_valid_sequence_or_fence(self):
        with self.assertRaises(InvalidEvent): self.db.ingest(dict(event(1), source_event_seq=True))
        with self.assertRaises(InvalidEvent): self.db.ingest(dict(event(1), lease_fence=False))

    def test_out_of_order_source_gap_heals_without_reordering_causality(self):
        self.db.ingest(event(3))
        self.assertEqual(2, self.db.diagnose("run-a")["gap_count"])
        self.db.ingest(event(1))
        self.assertEqual(1, self.db.diagnose("run-a")["gap_count"])
        self.db.ingest(event(2))
        self.assertEqual(0, self.db.diagnose("run-a")["gap_count"])

    def test_interleaved_other_run_not_false_gap(self):
        self.db.ingest(event(1))
        e = event(2); e["run_id"] = "run-b"; self.db.ingest(e)
        self.db.ingest(event(3))
        self.assertEqual(0, self.db.diagnose("run-a")["gap_count"])

    def test_different_producer_restart_can_restart_sequence(self):
        self.db.ingest(event(1, producer="boot-a"))
        self.db.ingest(event(1, producer="boot-b"))
        self.assertEqual(0, self.db.diagnose("run-a")["gap_count"])

    def test_heartbeat_only_does_not_claim_success(self):
        self.db.ingest(event(1))
        result = self.db.diagnose("run-a")
        self.assertEqual("recent_heartbeat_not_proof_of_progress", result["activity"])
        self.assertEqual("UNKNOWN", result["diagnostic"])
        self.assertIsNone(result["authoritative_task_state"])

    def test_repeated_intents_distinct_from_heartbeat(self):
        self.db.ingest(event(1, "worker.heartbeat"))
        for seq in (2, 4, 6):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:"+"c"*64))
        for seq in (3, 5): self.db.ingest(event(seq, "worker.heartbeat"))
        result = self.db.diagnose("run-a")
        self.assertEqual("NO_VERIFIED_PROGRESS", result["diagnostic"])
        self.assertEqual("suspect", result["confidence"])
        self.assertEqual(3, result["repeated_intents"][0]["repetition_count"])

    def test_independent_evidence_stops_false_loop_signal(self):
        for seq in (1, 2, 3):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:"+"c"*64))
        digest = "sha256:" + "a"*64
        self.db.ingest(event(4, "verifier.completed", target_revision="a"*40, evidence_refs=[digest]), trusted_origin=True)
        self.assertEqual("UNKNOWN", self.db.diagnose("run-a")["diagnostic"])

    def test_other_task_verification_cannot_hide_loop(self):
        for seq in (1, 2, 3):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:" + "c"*64))
        other = event(4, "verifier.completed", target_revision="a"*40,
                      evidence_refs=["sha256:" + "b"*64])
        other["task_id"] = "task-other"
        self.db.ingest(other, trusted_origin=True)
        self.assertEqual("NO_VERIFIED_PROGRESS", self.db.diagnose("run-a")["diagnostic"])

    def test_previous_verification_does_not_hide_new_loop(self):
        for seq in (1, 2, 3):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:" + "c"*64))
        self.db.ingest(event(4, "verifier.completed", target_revision="a"*40,
                             evidence_refs=["sha256:" + "b"*64]), trusted_origin=True)
        for seq in (5, 6, 7):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:" + "c"*64))
        result = self.db.diagnose("run-a")
        self.assertEqual("NO_VERIFIED_PROGRESS", result["diagnostic"])
        self.assertEqual(3, result["repeated_intents"][0]["repetition_count"])

    def test_wrong_revision_verifier_does_not_hide_loop(self):
        for seq in (1, 2, 3):
            self.db.ingest(event(seq, "tool.intent", target_revision="a"*40,
                                 operation_fingerprint="sha256:" + "c"*64))
        self.db.ingest(event(4, "verifier.completed", target_revision="b"*40,
                             evidence_refs=["sha256:" + "b"*64]), trusted_origin=True)
        self.assertEqual("NO_VERIFIED_PROGRESS", self.db.diagnose("run-a")["diagnostic"])

    def test_other_attempt_verification_cannot_hide_loop(self):
        for seq in (1, 2, 3):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:" + "c"*64))
        other = event(4, "verifier.completed", target_revision="a"*40,
                      evidence_refs=["sha256:" + "b"*64])
        other["attempt_id"] = "attempt-new"
        self.db.ingest(other, trusted_origin=True)
        self.assertEqual("NO_VERIFIED_PROGRESS", self.db.diagnose("run-a")["diagnostic"])

    def test_untrusted_verifier_cannot_clear_loop(self):
        for seq in (1, 2, 3):
            self.db.ingest(event(seq, "tool.intent", operation_fingerprint="sha256:"+"c"*64))
        self.db.ingest(event(4, "verifier.completed", target_revision="a"*40, evidence_refs=["sha256:"+"a"*64]))
        self.assertEqual("NO_VERIFIED_PROGRESS", self.db.diagnose("run-a")["diagnostic"])

    def test_unknown_effect_preempts_stall_and_gap(self):
        self.db.ingest(event(3, "tool.effect.reserved", effect_key="sha256:"+"d"*64))
        self.assertEqual("EFFECT_OUTCOME_UNKNOWN", self.db.diagnose("run-a")["diagnostic"])
        self.assertEqual("reconcile_external_effect_no_retry", self.db.diagnose("run-a")["next_safe_action"])

    def test_untrusted_ack_does_not_clear_unknown_effect(self):
        self.db.ingest(event(1, "tool.effect.reserved", effect_key="sha256:"+"d"*64))
        self.db.ingest(event(2, "tool.effect.acknowledged", effect_key="sha256:"+"d"*64, evidence_refs=["sha256:"+"a"*64]))
        self.assertEqual("EFFECT_OUTCOME_UNKNOWN", self.db.diagnose("run-a")["diagnostic"])

    def test_trusted_ack_with_evidence_clears_reservation(self):
        self.db.ingest(event(1, "tool.effect.reserved", effect_key="sha256:"+"d"*64))
        self.db.ingest(event(2, "tool.effect.acknowledged", effect_key="sha256:"+"d"*64, evidence_refs=["sha256:"+"b"*64]), trusted_origin=True)
        self.assertEqual("UNKNOWN", self.db.diagnose("run-a")["diagnostic"])

    def test_trusted_ack_wrong_fence_does_not_clear(self):
        self.db.ingest(event(1, "tool.effect.reserved", effect_key="sha256:"+"d"*64))
        self.db.ingest(event(2, "tool.effect.acknowledged", effect_key="sha256:"+"d"*64, lease_fence=8, evidence_refs=["sha256:"+"b"*64]), trusted_origin=True)
        self.assertEqual("EFFECT_OUTCOME_UNKNOWN", self.db.diagnose("run-a")["diagnostic"])

    def test_restart_durable_events_but_not_live_heartbeat_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder,"observer.sqlite")
            a=CausalObserver(path); a.ingest(event(1)); a.close()
            b=CausalObserver(path)
            self.assertEqual(1, b.diagnose("run-a")["event_count"])
            self.assertEqual("unobserved", b.diagnose("run-a")["activity"])
            b.close()

    def test_concurrent_duplicate_event_remains_exactly_one(self):
        e=event(1)
        results=[]
        def put(): results.append(self.db.ingest(e))
        ts=[threading.Thread(target=put) for _ in range(30)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(1, results.count("inserted"))
        self.assertEqual(29, results.count("duplicate"))
        self.assertEqual(1, self.db.diagnose("run-a")["event_count"])

    def test_conflicting_sessions_never_collide(self):
        a=event(1, producer="boot-a")
        b=event(1, producer="boot-b")
        b["run_id"]="run-b"
        self.db.ingest(a); self.db.ingest(b)
        self.assertEqual(1, self.db.diagnose("run-a")["event_count"])
        self.assertEqual(1, self.db.diagnose("run-b")["event_count"])

    def test_policy_denial_not_autoretried(self):
        self.db.ingest(event(1, "approval.denied"), trusted_origin=True)
        r=self.db.diagnose("run-a")
        self.assertEqual("POLICY_DENIED",r["diagnostic"])
        self.assertEqual("stop_await_owner",r["next_safe_action"])

    def test_untrusted_rate_limit_not_confirmed(self):
        self.db.ingest(event(1,"model.throttled"))
        self.assertEqual("UNKNOWN",self.db.diagnose("run-a")["diagnostic"])

    def test_untrusted_cannot_force_loop_resolution_by_claim(self):
        for seq in (1,2,3): self.db.ingest(event(seq,"tool.intent",operation_fingerprint="sha256:"+"c"*64))
        self.db.ingest(event(4,"task.completed"))
        self.assertEqual("NO_VERIFIED_PROGRESS",self.db.diagnose("run-a")["diagnostic"])


class AdditionalAdversarialTests(unittest.TestCase):
    def test_malformed_unhashable_kind_rejected_cleanly(self):
        j=CausalObserver()
        try:
            with self.assertRaises(InvalidEvent): j.ingest(dict(event(1),kind=["worker.heartbeat"]))
        finally: j.close()

    def test_sqlite_int_overflow_rejected(self):
        j=CausalObserver()
        try:
            with self.assertRaises(InvalidEvent): j.ingest(dict(event(1),source_event_seq=2**80))
        finally: j.close()

    def test_cross_connection_same_file_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=os.path.join(folder,"shared.sqlite")
            a,b=CausalObserver(path),CausalObserver(path)
            e=event(1)
            barrier=threading.Barrier(2)
            out=[]
            def add(j):
                barrier.wait()
                out.append(j.ingest(e))
            t1=threading.Thread(target=add,args=(a,))
            t2=threading.Thread(target=add,args=(b,))
            t1.start();t2.start();t1.join();t2.join()
            self.assertEqual(["duplicate","inserted"],sorted(out))
            self.assertEqual(1,a.diagnose("run-a")["event_count"])
            a.close();b.close()


class MultiAgentScaleTests(unittest.TestCase):
    def test_fifty_producers_with_interleaving_and_untrusted_successes(self):
        j=CausalObserver()
        try:
            failures=[]
            def worker(n):
                try:
                    for seq in range(1, 21):
                        e=event(seq,"worker.heartbeat" if seq%2 else "tool.intent",
                                producer="boot-"+str(n),
                                **({"operation_fingerprint":"sha256:"+"f"*64} if seq%2==0 else {}))
                        e["task_id"]="task-"+str(n)
                        e["attempt_id"]="attempt-"+str(n)
                        j.ingest(e)
                except Exception as ex:
                    failures.append(repr(ex))
            threads=[threading.Thread(target=worker,args=(i,)) for i in range(50)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertEqual([],failures)
            r=j.diagnose("run-a")
            self.assertEqual(1000,r["event_count"])
            self.assertEqual(0,r["gap_count"])
            self.assertEqual("NO_VERIFIED_PROGRESS",r["diagnostic"])
            self.assertIsNone(r["authoritative_task_state"])
        finally:
            j.close()


if __name__ == "__main__":
    unittest.main()
