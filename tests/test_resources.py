import unittest
from unittest.mock import patch

from dashboard.main import page, resource_rows, snapshot


class ResourceTests(unittest.TestCase):
    def test_quantities_are_preserved_and_missing_values_are_not_zero(self):
        rows = resource_rows({"containers": [{"name": "app", "resources": {
            "requests": {"cpu": "0", "memory": "64Mi"}, "limits": {"cpu": "0.5"},
        }}, {"name": "helper", "resources": None}]}, "Deployment template")
        self.assertEqual(rows[0]["cpu_request"], "0")
        self.assertEqual(rows[0]["memory_request"], "64Mi")
        self.assertEqual(rows[0]["cpu_limit"], "0.5")
        self.assertEqual(rows[0]["memory_limit"], "Not set")
        self.assertEqual(rows[1]["cpu_request"], "Not set")
        self.assertEqual(resource_rows({}, "Pending Pod"), [])

    def test_init_containers_have_separate_rows(self):
        rows = resource_rows({"containers": [{"name": "web"}], "initContainers": [{
            "name": "prepare", "resources": {"limits": {"memory": "1Gi"}},
        }]}, "Pod/web-1")
        self.assertEqual([(r["container"], r["kind"]) for r in rows], [("web", "App"), ("prepare", "Init")])
        self.assertEqual(rows[1]["memory_limit"], "1Gi")
        self.assertEqual(rows[1]["source"], "Pod/web-1")

    def test_snapshot_keeps_template_and_actual_pod_values_separate(self):
        template = {"containers": [{"name": "app", "image": "test:v1"}]}
        pod = {"metadata": {"name": "web-1"}, "spec": {"containers": [{
            "name": "app", "resources": {"requests": {"cpu": "100m"}},
        }]}}
        with patch("dashboard.main.read", side_effect=[
            {"spec": {"template": {"spec": template}}}, {"items": [pod]}, {"spec": {"clusterIP": "10.0.0.1"}}, {"items": []},
        ]) as read:
            rows = snapshot()["resources"]
        self.assertEqual(rows[0]["source"], "Deployment template")
        self.assertEqual(rows[0]["cpu_request"], "Not set")
        self.assertEqual(rows[1]["source"], "Pod/web-1")
        self.assertEqual(rows[1]["cpu_request"], "100m")
        self.assertEqual(read.call_count, 4)

    def test_resource_display_is_escaped_and_explains_its_scope(self):
        rows = resource_rows({"containers": [{"name": '<script>bad()</script>'}]}, "Pod/web")
        html = page({"image": "test:v1", "ready": 0, "desired": 1, "service": "10.0.0.1", "pods": [], "resources": rows})
        self.assertIn("CPU request", html)
        self.assertIn("Memory limit", html)
        self.assertIn("not live usage", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
