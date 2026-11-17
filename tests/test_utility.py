import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from workloads.utility.main import Handler


class UtilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def get(self, path):
        return urllib.request.urlopen(self.base_url + path, timeout=5)

    def test_home_returns_only_workload_metadata(self):
        with self.get("/") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "application/json")
            payload = json.load(response)
        self.assertEqual(set(payload), {"version", "hostname", "pod", "node", "message"})
        self.assertTrue(payload["hostname"])

    def test_configuration_and_identity(self):
        values = {"APP_VERSION": "v2", "MESSAGE": "test message", "POD_NAME": "web-123", "NODE_NAME": "worker-1"}
        with patch.dict("os.environ", values), self.get("/") as response:
            payload = json.load(response)
        self.assertEqual(payload["version"], "v2")
        self.assertEqual(payload["message"], "test message")
        self.assertEqual(payload["pod"], "web-123")
        self.assertEqual(payload["node"], "worker-1")

    def test_health_endpoints(self):
        for path in ("/health/live", "/health/ready"):
            with self.subTest(path=path), self.get(path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), {"status": "ok"})

    def test_unknown_path_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.get("/missing")
        with raised.exception as response:
            self.assertEqual(response.code, 404)
            self.assertEqual(json.load(response), {"error": "not found"})


if __name__ == "__main__":
    unittest.main()
