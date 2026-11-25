import unittest

from dashboard.main import pod_summary


class QosTests(unittest.TestCase):
    def test_reports_actual_class_without_inferring_from_resources(self):
        for value in ("Guaranteed", "Burstable", "BestEffort"):
            with self.subTest(value=value):
                pod = {"metadata": {"name": "web"}, "status": {"qosClass": value}}
                self.assertEqual(pod_summary(pod)["qos"], value)

    def test_missing_status_is_unknown(self):
        for status in ({}, {"qosClass": None}):
            with self.subTest(status=status):
                self.assertEqual(pod_summary({"metadata": {"name": "web"}, "status": status})["qos"], "Unknown")
