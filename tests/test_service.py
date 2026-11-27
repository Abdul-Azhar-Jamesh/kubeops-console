import unittest

from dashboard.main import page, service_summary


class ServiceTests(unittest.TestCase):
    def test_named_and_numeric_targets_and_protocols(self):
        summary = service_summary({"spec": {"type": "ClusterIP", "ports": [
            {"name": "web", "port": 80, "targetPort": "http"},
            {"port": 53, "targetPort": 5353, "protocol": "UDP"},
        ]}})
        self.assertEqual(summary["ports"][0]["target"], "http")
        self.assertEqual(summary["ports"][1]["target"], 5353)
        self.assertEqual(summary["ports"][1]["protocol"], "UDP")

    def test_missing_selectors_and_target_default(self):
        self.assertEqual(service_summary({})["selectors"], "None")
        self.assertEqual(service_summary({})["ports"], [])
        self.assertEqual(service_summary({"spec": {"ports": [{"port": 8080}]}})["ports"][0]["target"], 8080)

    def test_selectors_are_sorted_and_escaped_in_html(self):
        summary = service_summary({"spec": {"selector": {"z": "last", "a": "<script>bad()</script>"}}})
        self.assertTrue(summary["selectors"].startswith("a="))
        html = page({"image": "test", "ready": 0, "desired": 1, "service": "Pending", "pods": [], "service_details": summary})
        self.assertIn("Service ports and selectors", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
