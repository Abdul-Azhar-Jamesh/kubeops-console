import unittest

from dashboard.main import page, rollout_summary


class RolloutTests(unittest.TestCase):
    def test_missing_status_is_unknown(self):
        summary = rollout_summary({})
        self.assertEqual(summary["fresh"], "Unknown")
        self.assertEqual(summary["conditions"], [])

    def test_stale_generation_does_not_look_current(self):
        deployment = {"metadata": {"generation": 3}, "status": {"observedGeneration": 2}}
        self.assertEqual(rollout_summary(deployment)["fresh"], "No")
        deployment["status"]["observedGeneration"] = 3
        self.assertEqual(rollout_summary(deployment)["fresh"], "Yes")

    def test_failure_and_unknown_conditions_are_preserved_and_escaped(self):
        summary = rollout_summary({"status": {"conditions": [
            {"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded", "message": "<script>bad()</script>"},
            {"type": "Available", "status": "Unknown"},
        ]}})
        html = page({"image": "test", "ready": 0, "desired": 1, "service": "test", "pods": [], "rollout": summary})
        self.assertIn("ProgressDeadlineExceeded", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertEqual(summary["conditions"][1]["status"], "Unknown")
