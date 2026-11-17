"""Small HTTP workload for the KubeOps Console project."""

import argparse
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/health/live", "/health/ready"}:
            status, payload = 200, {"status": "ok"}
        elif self.path == "/":
            status, payload = 200, {
                "version": os.getenv("APP_VERSION", "v1"),
                "hostname": socket.gethostname(),
                "pod": os.getenv("POD_NAME"),
                "node": os.getenv("NODE_NAME"),
                "message": os.getenv("MESSAGE", "hello from KubeOps"),
            }
        else:
            status, payload = 404, {"error": "not found"}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
