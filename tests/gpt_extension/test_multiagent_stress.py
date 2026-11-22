"""Synthetic deterministic concurrency contracts; no live Hermes worker is started."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest

from gpt_extension.diagnostics import Effect, Evidence, Snapshot, diagnose
from gpt_extension.cdp_diagnostics import BrowserLaneSnapshot, diagnose_browser_lane


class MultiAgentSyntheticStress(unittest.TestCase):
    def test_thirty_two_concurrent_observers_do_not_share_state(self):
        """Each independent read-only classifier gets an immutable own snapshot."""
        def inspect(agent: int):
            # 100 iterations per agent; alternate unrelated tasks and effects.
            codes = []
            for seq in range(100):
                status = (agent + seq) % 4
                base = Snapshot(
                    task_id=f"agent-{agent}-step-{seq}", status="running",
                    revision="sha", attempts=1, max_attempts=3, now=1000,
                    lease_until=1100, last_event_at=999,
                    required_evidence=("ci",),
                    evidence=(Evidence("ci", "sha", "passed", True),),
                )
                if status == 0:
                    sample, expected = replace(base, status="succeeded"), "VERIFIED_SUCCESS"
                elif status == 1:
                    sample, expected = replace(base, lease_until=990), "LEASE_EXPIRED"
                elif status == 2:
                    sample, expected = replace(base, effects=(Effect("write", "reserved"),)), "EXTERNAL_EFFECT_UNCERTAIN"
                else:
                    sample, expected = replace(base, status="succeeded", evidence=()), "UNVERIFIED_SUCCESS"
                output = diagnose(sample)
                if output.code != expected:
                    return False, agent, seq, output.code, expected
                codes.append(output.code)
            return len(codes) == 100, agent, len(codes)

        with ThreadPoolExecutor(max_workers=32) as executor:
            results = list(executor.map(inspect, range(32)))
        self.assertTrue(all(item[0] for item in results), results)
        self.assertEqual(sum(r[2] for r in results), 3200)

    def test_no_terminal_success_for_uncertain_effect_matrix(self):
        for status in ("succeeded", "running", "failed", "queued", "verifying"):
            for effect_state in ("reserved", "unexpected", "acknowledged", "not_executed"):
                sample = Snapshot(
                    task_id="t", status=status, revision="s", attempts=1,
                    max_attempts=3, now=0, lease_until=100,
                    required_evidence=("ci",),
                    evidence=(Evidence("ci", "s", "passed", True),),
                    effects=(Effect("action", effect_state),),
                )
                with self.subTest(status=status, effect_state=effect_state):
                    self.assertNotEqual(diagnose(sample).code, "VERIFIED_SUCCESS")

    def test_browser_lanes_never_grant_completion_for_observed_ui(self):
        for agent in range(32):
            sample = BrowserLaneSnapshot(
                task_id=f"t-{agent}", lane_id=f"lane-{agent}",
                expected_fence=agent + 1, observed_fence=agent + 1,
                last_command_seq=1, last_ack_seq=1, now=10,
                last_transport_event_at=9, bridge_connected=True,
                extension_connected=True, tab_attached=True,
                ui_message_observed=True,
            )
            outcome = diagnose_browser_lane(sample)
            self.assertEqual(outcome.code, "CDP_UI_MESSAGE_ONLY")
            self.assertFalse(outcome.permits_task_completion)


if __name__ == "__main__":
    unittest.main()
