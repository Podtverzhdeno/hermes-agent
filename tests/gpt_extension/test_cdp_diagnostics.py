"""Offline CDP lane diagnostics: no browser or network is used."""
from dataclasses import replace
import unittest

from gpt_extension.cdp_diagnostics import BrowserLaneSnapshot, diagnose_browser_lane


class BrowserLaneTests(unittest.TestCase):
    def setUp(self):
        self.base = BrowserLaneSnapshot(
            task_id="t", lane_id="owner-tab", expected_fence=5, observed_fence=5,
            last_command_seq=3, last_ack_seq=3, now=1000., last_transport_event_at=997.,
            bridge_connected=True, extension_connected=True, tab_attached=True,
        )

    def case(self, code, **kw):
        r = diagnose_browser_lane(replace(self.base, **kw))
        self.assertEqual(code, r.code)
        self.assertFalse(r.permits_task_completion)
        return r

    def test_healthy_transport_not_task_success(self):
        self.case("CDP_TRANSPORT_HEALTHY")

    def test_stale_fence(self):
        self.case("CDP_FENCE_MISMATCH", observed_fence=4)

    def test_future_fence(self):
        self.case("CDP_FENCE_MISMATCH", observed_fence=6)

    def test_ack_ahead_of_command(self):
        self.case("CDP_ACK_INCONSISTENT", last_ack_seq=4)

    def test_bridge_offline(self):
        self.case("CDP_BRIDGE_DOWN", bridge_connected=False)

    def test_extension_offline(self):
        self.case("CDP_EXTENSION_DOWN", extension_connected=False)

    def test_tab_detached(self):
        self.case("CDP_TAB_DETACHED", tab_attached=False)

    def test_unknown_ownership(self):
        self.case("CDP_FENCE_UNVERIFIED", observed_fence=None)

    def test_unacknowledged_command(self):
        self.case("CDP_ACK_PENDING", last_ack_seq=2)

    def test_missing_observation(self):
        self.case("CDP_NO_TRANSPORT_OBSERVATION", last_transport_event_at=None)

    def test_silent_transport_is_not_model_failure(self):
        r = self.case("CDP_TRANSPORT_SILENT", last_transport_event_at=800.)
        self.assertEqual(r.cause_status, "unknown")

    def test_canary_or_message_not_task_success(self):
        self.case("CDP_UI_MESSAGE_ONLY", ui_message_observed=True)

    def test_invalid_seq(self):
        with self.assertRaises(ValueError):
            diagnose_browser_lane(replace(self.base, last_ack_seq=-1))

    def test_invalid_fence(self):
        with self.assertRaises(ValueError):
            diagnose_browser_lane(replace(self.base, expected_fence=0))

    def test_invalid_lane(self):
        with self.assertRaises(ValueError):
            diagnose_browser_lane(replace(self.base, lane_id=" "))

    def test_respects_custom_slo(self):
        self.case("CDP_TRANSPORT_SILENT", last_transport_event_at=950., transport_silence_slo_seconds=30.)


if __name__ == "__main__":
    unittest.main()
