"""Local read-only view of the Part 2 workload. Requires kubectl and kind-kubeops."""

import json
import subprocess
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

KUBECTL = [
    "kubectl", "--context", "kind-kubeops", "--namespace", "kubeops-demo",
    "--as=system:serviceaccount:kubeops-demo:kubeops-viewer", "--request-timeout=5s",
]


def read(*args):
    result = subprocess.run([*KUBECTL, "get", *args, "-o", "json"], capture_output=True, text=True, check=True, timeout=10)
    return json.loads(result.stdout)


class PodNotFound(Exception):
    pass


def pod_logs(name):
    pods = read("pods", "-l", "app=kubeops-utility")["items"]
    if not any(p["metadata"]["name"] == name for p in pods):
        raise PodNotFound("Demo Pod not found")
    result = subprocess.run(
        [*KUBECTL, "logs", f"pod/{name}", "--container=utility", "--tail=200", "--limit-bytes=65536", "--timestamps=true"],
        capture_output=True, check=True, timeout=10,
    )
    return result.stdout[:65536].decode("utf-8", errors="replace")


def pod_summary(pod):
    status = pod.get("status") or {}
    conditions = status.get("conditions") or []
    readiness = next((c.get("status") for c in conditions if c.get("type") == "Ready"), "Unknown")
    containers = status.get("containerStatuses") or []
    issues = []
    if status.get("reason"):
        issues.append((status["reason"], status.get("message", "")))
    for container in [*(status.get("initContainerStatuses") or []), *containers]:
        state = container.get("state") or {}
        failure = state.get("waiting") or state.get("terminated") or {}
        if failure.get("reason") and failure["reason"] != "Completed":
            issues.append((f"{container['name']}: {failure['reason']}", failure.get("message", "")))
    if not issues:
        issues = [(c["reason"], c.get("message", "")) for c in conditions if c.get("status") == "False" and c.get("reason")]
    if pod["metadata"].get("deletionTimestamp"):
        readiness, issues = "False", [("Terminating", "Pod deletion has been requested.")]
    return {
        "name": pod["metadata"]["name"],
        "phase": status.get("phase", "Unknown"),
        "ready": {"True": "Yes", "False": "No"}.get(readiness, "Unknown"),
        "node": pod.get("spec", {}).get("nodeName", "Unscheduled"),
        "qos": status.get("qosClass") or "Unknown",
        "restarts": sum(c.get("restartCount", 0) for c in containers),
        "reason": "; ".join(reason for reason, _ in issues) or "No reported issue",
        "message": "\n".join(message for _, message in issues if message),
    }


def related_events(resources):
    names = {obj["metadata"]["uid"]: f"{kind}/{obj['metadata']['name']}"
             for kind, obj in resources if obj.get("metadata", {}).get("uid")}
    result = []
    for event in read("events")["items"]:
        reference = event.get("involvedObject") or event.get("regarding") or {}
        if reference.get("uid") not in names:
            continue
        series = event.get("series") or {}
        result.append({
            "object": names[reference["uid"]],
            "type": event.get("type", "Unknown"),
            "reason": event.get("reason", "Unknown"),
            "count": series.get("count") or event.get("count") or 1,
            "time": series.get("lastObservedTime") or event.get("lastTimestamp") or event.get("eventTime")
                    or event.get("metadata", {}).get("creationTimestamp") or "Unknown",
            "message": (event.get("message") or event.get("note") or "")[:2000],
        })

    def observed(event):
        try:
            return datetime.fromisoformat(event["time"]).timestamp()
        except (ValueError, OverflowError, OSError):
            return 0

    return sorted(result, key=observed, reverse=True)[:50]


def resource_rows(spec, source):
    rows = []
    for kind, containers in (("App", spec.get("containers") or []), ("Init", spec.get("initContainers") or [])):
        for container in containers:
            resources = container.get("resources") or {}
            requests = resources.get("requests") or {}
            limits = resources.get("limits") or {}
            rows.append({
                "source": source, "container": container.get("name", "Unknown"), "kind": kind,
                "cpu_request": requests.get("cpu", "Not set"), "cpu_limit": limits.get("cpu", "Not set"),
                "memory_request": requests.get("memory", "Not set"), "memory_limit": limits.get("memory", "Not set"),
            })
    return rows


def snapshot():
    deployment = read("deployment", "kubeops-utility")
    pods = read("pods", "-l", "app=kubeops-utility")["items"]
    service = read("service", "kubeops-utility")
    return {
        "image": deployment["spec"]["template"]["spec"]["containers"][0]["image"],
        "desired": deployment["spec"].get("replicas", 1),
        "ready": deployment.get("status", {}).get("readyReplicas", 0),
        "service": service["spec"].get("clusterIP", "Pending"),
        "pods": [pod_summary(p) for p in pods],
        "events": related_events([("Deployment", deployment), ("Service", service), *[("Pod", p) for p in pods]]),
        "resources": resource_rows(deployment["spec"]["template"]["spec"], "Deployment template")
                     + [row for p in pods for row in resource_rows(p.get("spec") or {}, f"Pod/{p['metadata']['name']}")],
    }


def page(data=None, error=None, logs=None):
    rows = "" if data is None else "".join(
        "<tr>" + "".join(f"<td>{escape(str(p[key]))}</td>" for key in ("name", "phase", "ready", "node", "restarts", "reason"))
        + f'<td>{escape(str(p.get("qos", "Unknown")))}</td>'
        + f'<td><a href="/logs?{escape(urlencode({"pod": p["name"]}))}">Logs</a></td></tr>'
        + (f'<tr><td colspan="8"><pre>{escape(p["message"])}</pre></td></tr>' if p["message"] else "")
        for p in data["pods"]
    )
    if error:
        content = f'<p role="alert">{escape(error)}</p>'
    elif logs is not None:
        content = (
            f"<h2>Logs: {escape(logs[0])}</h2><p>Latest 200 lines, capped at 64 KiB. Current utility container only.</p>"
            f"<pre>{escape(logs[1]) if logs[1] else 'No log output available.'}</pre>"
        )
    else:
        budgets = "".join(
            "<tr>" + "".join(f"<td>{escape(str(row[key]))}</td>" for key in (
                "source", "container", "kind", "cpu_request", "cpu_limit", "memory_request", "memory_limit",
            )) + "</tr>" for row in data.get("resources", [])
        )
        event_rows = "".join(
            "<tr>" + "".join(f"<td>{escape(str(event[key]))}</td>" for key in ("type", "object", "reason", "count", "time", "message"))
            + "</tr>" for event in data.get("events", [])
        )
        content = (
            f"<p>Image: {escape(data['image'])}</p><p>Ready replicas: {data['ready']} / {data['desired']}</p>"
            f"<p>ClusterIP: {escape(data['service'])}</p>"
            '<table><thead><tr><th>Pod</th><th>Phase</th><th>Ready</th><th>Node</th><th>Restarts</th><th>Reason</th><th>QoS</th><th>Logs</th></tr></thead>'
            f"<tbody>{rows or '<tr><td colspan=8>No Pods yet.</td></tr>'}</tbody></table>"
            '<h2>Resource requests and limits</h2><p>Per-container configured budgets, not live usage or Pod totals. '
            'Template and actual Pod values are shown separately; Not set means no value was returned.</p>'
            '<table><thead><tr><th>Source</th><th>Container</th><th>Kind</th><th>CPU request</th><th>CPU limit</th>'
            '<th>Memory request</th><th>Memory limit</th></tr></thead>'
            f"<tbody>{budgets or '<tr><td colspan=7>No container resource configuration returned.</td></tr>'}</tbody></table>"
            '<h2>Related events</h2><p>Latest 50 retained events for the current demo objects; messages capped at 2,000 characters.</p>'
            '<table><thead><tr><th>Type</th><th>Object</th><th>Reason</th><th>Count</th><th>Last observed</th><th>Message</th></tr></thead>'
            f"<tbody>{event_rows or '<tr><td colspan=6>No related events retained.</td></tr>'}</tbody></table>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>KubeOps Console</title><style>
body{{font:16px system-ui;margin:3rem auto;padding:0 1rem;max-width:1000px;background:#f5f7fb;color:#18263a}}
main{{background:white;padding:2rem;border:1px solid #dce2ec;border-radius:12px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.7rem;text-align:left;border-bottom:1px solid #dce2ec}}
a{{color:#1753ad}}p{{line-height:1.6}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style></head><body><main><h1>KubeOps Console</h1>
<p>Read-only · kind-kubeops / kubeops-demo / kubeops-utility</p>
<p><a href="/">Refresh workload</a></p>{content}
<p>This is a point-in-time snapshot. Refresh to see changes.</p></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Host") not in {"127.0.0.1:8000", "localhost:8000"}:
            self.send_error(403, "Localhost access only")
            return
        try:
            route = urlsplit(self.path)
        except ValueError:
            self.send_error(400, "Invalid request path")
            return
        if route.path not in {"/", "/logs"}:
            self.send_error(404)
            return
        try:
            if route.path == "/logs":
                try:
                    query = parse_qs(route.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1)
                except ValueError:
                    self.send_error(400, "Specify one demo Pod")
                    return
                if set(query) != {"pod"} or len(query["pod"]) != 1 or not query["pod"][0]:
                    self.send_error(400, "Specify one demo Pod")
                    return
                name = query["pod"][0]
                body = page(logs=(name, pod_logs(name))).encode()
            else:
                body = page(snapshot()).encode()
            status = 200
        except PodNotFound:
            body, status = page(error="Demo Pod not found. Refresh the workload and select a current Pod.").encode(), 404
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            message = "Cannot read Pod logs. The container may not have started or the Pod may have been replaced." if route.path == "/logs" else (
                "Cannot read the demo workload. Check kubectl, the kind-kubeops context, and apply -k k8s."
            )
            body = page(error=message).encode()
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
