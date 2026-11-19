"""Local read-only view of the Part 2 workload. Requires kubectl and kind-kubeops."""

import json
import subprocess
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KUBECTL = [
    "kubectl", "--context", "kind-kubeops", "--namespace", "kubeops-demo",
    "--as=system:serviceaccount:kubeops-demo:kubeops-viewer", "--request-timeout=5s",
]


def read(*args):
    result = subprocess.run([*KUBECTL, "get", *args, "-o", "json"], capture_output=True, text=True, check=True, timeout=10)
    return json.loads(result.stdout)


def snapshot():
    deployment = read("deployment", "kubeops-utility")
    pods = read("pods", "-l", "app=kubeops-utility")["items"]
    service = read("service", "kubeops-utility")
    return {
        "image": deployment["spec"]["template"]["spec"]["containers"][0]["image"],
        "desired": deployment["spec"].get("replicas", 1),
        "ready": deployment.get("status", {}).get("readyReplicas", 0),
        "service": service["spec"].get("clusterIP", "Pending"),
        "pods": [{
            "name": p["metadata"]["name"],
            "phase": p.get("status", {}).get("phase", "Unknown"),
            "node": p.get("spec", {}).get("nodeName", "Unscheduled"),
            "restarts": sum(c.get("restartCount", 0) for c in p.get("status", {}).get("containerStatuses", [])),
        } for p in pods],
    }


def page(data=None, error=None):
    rows = "" if data is None else "".join(
        "<tr>" + "".join(f"<td>{escape(str(p[key]))}</td>" for key in ("name", "phase", "node", "restarts")) + "</tr>"
        for p in data["pods"]
    )
    content = f'<p role="alert">{escape(error)}</p>' if error else (
        f"<p>Image: {escape(data['image'])}</p><p>Ready replicas: {data['ready']} / {data['desired']}</p>"
        f"<p>ClusterIP: {escape(data['service'])}</p>"
        '<table><thead><tr><th>Pod</th><th>Phase</th><th>Node</th><th>Restarts</th></tr></thead>'
        f"<tbody>{rows or '<tr><td colspan=4>No Pods yet.</td></tr>'}</tbody></table>"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>KubeOps Console</title><style>
body{{font:16px system-ui;margin:3rem auto;padding:0 1rem;max-width:1000px;background:#f5f7fb;color:#18263a}}
main{{background:white;padding:2rem;border:1px solid #dce2ec;border-radius:12px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.7rem;text-align:left;border-bottom:1px solid #dce2ec}}
a{{color:#1753ad}}p{{line-height:1.6}}
</style></head><body><main><h1>KubeOps Console</h1>
<p>Read-only · kind-kubeops / kubeops-demo / kubeops-utility</p>
<p><a href="/">Refresh workload</a></p>{content}
<p>This is a point-in-time snapshot. Refresh to see changes.</p></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Host") not in {"127.0.0.1:8000", "localhost:8000"}:
            self.send_error(403, "Localhost access only")
            return
        if self.path != "/":
            self.send_error(404)
            return
        try:
            body, status = page(snapshot()).encode(), 200
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            body = page(error="Cannot read the demo workload. Check kubectl, the kind-kubeops context, and apply -k k8s.").encode()
            status = 503
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8000), Handler) as server:
        print("KubeOps Console: http://127.0.0.1:8000", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
