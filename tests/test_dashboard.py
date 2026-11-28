import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from dashboard.main import KUBECTL, Handler, page, pod_summary, snapshot


class DashboardTests(unittest.TestCase):
    def test_snapshot_handles_pending_pods(self):
        with patch("dashboard.main.read", side_effect=[
            {"spec": {"replicas": 1, "template": {"spec": {"containers": [{"image": "test:v1"}]}}}},
            {"items": [{"metadata": {"name": "pending"}, "spec": {}, "status": {"phase": "Pending"}}]},
            {"spec": {"clusterIP": "10.96.0.1"}},
            {"items": []}, {"items": []}, {"items": []},
        ]):
            data = snapshot()
        self.assertEqual(data["ready"], 0)
        self.assertEqual(data["pods"][0]["node"], "Unscheduled")
        self.assertEqual(data["pods"][0]["restarts"], 0)
        self.assertEqual(data["pods"][0]["ready"], "Unknown")

    def test_cluster_text_is_escaped(self):
        self.assertNotIn('<script>alert(1)</script>', page(error='<script>alert(1)</script>'))
        self.assertIn('&lt;script&gt;', page(error='<script>alert(1)</script>'))

    def test_workload_page_shows_data_without_rendering_markup(self):
        html = page({
            "image": "test:v1", "ready": 1, "desired": 2, "service": "10.96.0.1",
            "pods": [{"name": "<script>bad</script>", "phase": "Running", "ready": "No", "node": "worker", "restarts": 3,
                      "reason": "CrashLoopBackOff", "message": '<img src=x onerror="bad()">'}],
        })
        self.assertIn("Ready replicas: 1 / 2", html)
        self.assertIn("test:v1", html)
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("CrashLoopBackOff", html)
        self.assertIn("&lt;img", html)
        self.assertNotIn("<img", html)

    def test_running_phase_does_not_imply_readiness(self):
        pod = {"metadata": {"name": "web"}, "status": {
            "phase": "Running", "conditions": [{"type": "Ready", "status": "False", "reason": "ContainersNotReady"}],
        }}
        summary = pod_summary(pod)
        self.assertEqual(summary["phase"], "Running")
        self.assertEqual(summary["ready"], "No")
        self.assertEqual(summary["reason"], "ContainersNotReady")
        pod["status"]["conditions"] = [{"type": "Ready", "status": "True"}]
        self.assertEqual(pod_summary(pod)["ready"], "Yes")

    def test_container_and_init_failures_are_reported(self):
        for field, state, reason in [
            ("containerStatuses", "waiting", "ImagePullBackOff"),
            ("containerStatuses", "waiting", "CrashLoopBackOff"),
            ("containerStatuses", "terminated", "OOMKilled"),
            ("initContainerStatuses", "waiting", "CreateContainerConfigError"),
        ]:
            with self.subTest(reason=reason):
                summary = pod_summary({"metadata": {"name": "web"}, "status": {
                    field: [{"name": "app", "state": {state: {"reason": reason, "message": "Kubernetes detail"}}}],
                }})
                self.assertIn(reason, summary["reason"])
                self.assertEqual(summary["message"], "Kubernetes detail")

    def test_unschedulable_and_terminating_pods(self):
        pod = {"metadata": {"name": "web"}, "status": {"phase": "Pending", "conditions": [
            {"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": "Insufficient cpu"},
        ]}}
        summary = pod_summary(pod)
        self.assertEqual(summary["reason"], "Unschedulable")
        self.assertEqual(summary["message"], "Insufficient cpu")
        pod["metadata"]["deletionTimestamp"] = "2026-11-20T12:00:00Z"
        summary = pod_summary(pod)
        self.assertEqual(summary["reason"], "Terminating")
        self.assertEqual(summary["ready"], "No")

    def test_previous_failure_is_not_presented_as_current(self):
        summary = pod_summary({"metadata": {"name": "web"}, "status": {
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [{"name": "app", "restartCount": 2, "state": {"running": {}},
                                   "lastState": {"terminated": {"reason": "OOMKilled"}}}],
            "initContainerStatuses": [{"name": "init", "state": {"terminated": {"reason": "Completed"}}}],
        }})
        self.assertEqual(summary["ready"], "Yes")
        self.assertEqual(summary["restarts"], 2)
        self.assertNotIn("OOMKilled", summary["reason"])
        self.assertNotIn("Completed", summary["reason"])

    def test_reads_use_the_restricted_identity(self):
        from dashboard.main import read

        with patch("dashboard.main.subprocess.run") as run:
            run.return_value.stdout = json.dumps({"items": []})
            read("pods")
        self.assertEqual(run.call_args.args[0], [*KUBECTL, "get", "pods", "-o", "json"])
        self.assertIn("--as=system:serviceaccount:kubeops-demo:kubeops-viewer", KUBECTL)
        self.assertTrue(run.call_args.kwargs["check"])

    def test_missing_cluster_returns_helpful_503_and_rejects_other_hosts(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch("dashboard.main.snapshot", side_effect=OSError("private configuration detail")):
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    connection.request("GET", "/", headers={"Host": "localhost:8000"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 503)
                    body = response.read().decode()
                    self.assertIn("Cannot read the demo workload", body)
                    self.assertNotIn("private configuration detail", body)
                    connection.close()
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("GET", "/", headers={"Host": "attacker.example"})
                self.assertEqual(connection.getresponse().status, 403)
                connection.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
