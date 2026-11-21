import subprocess
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from dashboard.main import KUBECTL, Handler, PodNotFound, pod_logs


class LogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def get(self, path):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("GET", path, headers={"Host": "localhost:8000"})
            response = connection.getresponse()
            return response.status, response.read().decode()
        finally:
            connection.close()

    def test_unknown_pod_never_starts_log_command(self):
        for name in ("unrelated", "../default/pod", "--all-pods=true"):
            with self.subTest(name=name), patch("dashboard.main.read", return_value={"items": []}), patch("dashboard.main.subprocess.run") as run:
                with self.assertRaises(PodNotFound):
                    pod_logs(name)
                run.assert_not_called()

    def test_log_command_is_bounded_and_uses_viewer_identity(self):
        with patch("dashboard.main.read", return_value={"items": [{"metadata": {"name": "demo"}}]}), patch("dashboard.main.subprocess.run") as run:
            run.return_value.stdout = b"\xff" + b"x" * 70000
            text = pod_logs("demo")
        self.assertEqual(len(text), 65536)
        self.assertTrue(text.startswith("\ufffd"))
        self.assertEqual(run.call_args.args[0], [
            *KUBECTL, "logs", "pod/demo", "--container=utility", "--tail=200", "--limit-bytes=65536", "--timestamps=true",
        ])
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_log_page_escapes_output_and_handles_empty_logs(self):
        with patch("dashboard.main.pod_logs", return_value='<script>alert("bad")</script>'):
            status, body = self.get("/logs?pod=demo")
        self.assertEqual(status, 200)
        self.assertIn("Latest 200 lines", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>", body)
        with patch("dashboard.main.pod_logs", return_value=""):
            self.assertIn("No log output available", self.get("/logs?pod=demo")[1])

    def test_invalid_queries_never_read_logs(self):
        for query in ("", "?pod=", "?pod=one&pod=two", "?pod=one&tail=99999", "?pod"):
            with self.subTest(query=query), patch("dashboard.main.pod_logs") as logs:
                self.assertEqual(self.get("/logs" + query)[0], 400)
                logs.assert_not_called()

    def test_missing_and_unavailable_logs_do_not_leak_backend_errors(self):
        for error, expected in [(PodNotFound(), 404), (subprocess.TimeoutExpired("private-command", 10), 503)]:
            with self.subTest(status=expected), patch("dashboard.main.pod_logs", side_effect=error):
                status, body = self.get("/logs?pod=demo")
                self.assertEqual(status, expected)
                self.assertNotIn("private-command", body)
