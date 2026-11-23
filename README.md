# KubeOps Console

A Kubernetes operations dashboard project, being developed in small working stages.

## Part 1: HTTP workload service

This first release contains the small application the dashboard will eventually deploy and inspect. It reports its version, hostname, optional Pod/node identity, and a configurable message. It also exposes health endpoints.

Part 2 adds a local Kubernetes deployment for this service. Part 3 adds its first read-only dashboard view.

### Run with Python

Requires Python 3.12 or later. There are no third-party Python dependencies.

```powershell
python workloads/utility/main.py
```

Open http://127.0.0.1:8080/ to view the JSON response. Stop the service with Ctrl+C.

| Endpoint | Response |
| --- | --- |
| `/` | Workload version, identity, and message |
| `/health/live` | Process is responding |
| `/health/ready` | Service can handle requests; there are no external dependencies |
| Other paths | HTTP 404 |

Optional environment variables: `APP_VERSION`, `MESSAGE`, `POD_NAME`, and `NODE_NAME`. The Kubernetes manifest populates Pod/node identity through the Downward API; these values remain null when not supplied.

### Run with Docker

```powershell
docker build -t kubeops-utility:v1 workloads/utility
docker run --rm -p 127.0.0.1:8080:8080 -e MESSAGE="hello from Docker" kubeops-utility:v1
```

The container runs with a non-root user ID. The image uses the Python 3.12 slim tag so it can receive patch updates on rebuild; builds are not digest-pinned yet.

### Test

```powershell
python -m unittest discover -s tests -v
```

Tests start a real HTTP server on a temporary localhost port and verify metadata, environment settings, health responses, and unknown paths. GitHub Actions also builds the container image.

This uses Python's standard-library HTTP server as a small local demonstration workload. It is not intended as a public production HTTP server.

## Part 2: deploy to Kubernetes

Requires Docker Desktop running Linux containers, [kind 0.33.0](https://kind.sigs.k8s.io/docs/user/quick-start/), and kubectl. Run from the repository root. Use a dedicated disposable cluster named `kubeops`; these commands do not deploy to your normal cluster context.

```powershell
kind create cluster --name kubeops --image kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed --wait 3m
docker build -t kubeops-utility:v1 workloads/utility
kind load docker-image kubeops-utility:v1 --name kubeops
kubectl --context kind-kubeops apply -k k8s
kubectl --context kind-kubeops -n kubeops-demo rollout status deployment/kubeops-utility --timeout=90s
kubectl --context kind-kubeops -n kubeops-demo port-forward service/kubeops-utility 8080:8080
```

Open http://127.0.0.1:8080/. The response now includes actual Pod and node names. Stop any previously running local service on port 8080 first.

The manifests create a dedicated namespace, a one-replica Deployment, and an internal ClusterIP Service. The workload has CPU/memory requests and limits, startup/readiness/liveness probes, a non-root identity, a read-only root filesystem, and no mounted Kubernetes API token. The namespace enforces the restricted Pod Security standard.

The Service is internal to the cluster; port-forward provides temporary localhost access. It is not a test of load balancing across replicas. For a check using actual cluster DNS and Service routing, open another terminal and run:

```powershell
python scripts/kubernetes_smoke.py
```

The script creates a temporary in-cluster probe, verifies the JSON response and health endpoints, scales the Deployment to two ready replicas, and restores it to one. Run it only against this disposable demo, without concurrent manual scaling. CI runs this check on a real kind cluster as well as the original HTTP tests and container check.

Inspect and scale manually:

```powershell
kubectl --context kind-kubeops -n kubeops-demo get pods,services
kubectl --context kind-kubeops -n kubeops-demo scale deployment/kubeops-utility --replicas=2
kubectl --context kind-kubeops -n kubeops-demo logs deployment/kubeops-utility
```

Remove the demo resources with `kubectl --context kind-kubeops delete -k k8s`. This deletes the dedicated `kubeops-demo` namespace and everything inside it, so keep that namespace exclusive to this demo. Remove the disposable cluster with `kind delete cluster --name kubeops` when finished.

## Part 3: read-only dashboard

After completing the Part 2 setup, apply the updated manifests and start the local dashboard:

```powershell
kubectl --context kind-kubeops apply -k k8s
python dashboard/main.py
```

Open http://127.0.0.1:8000/. It shows the image, ready/desired replicas, Service IP, and each Pod's phase, node, and restart count. Refresh the page to update the snapshot. Missing cluster access produces a helpful error instead of a blank page.

This first view uses Python's standard library and kubectl, with no new Python dependencies. It binds only to localhost and accepts localhost Host headers. Cluster-provided text is HTML-escaped. It has no mutation endpoints, arbitrary commands, kubeconfig upload, or remote access option.

Every Kubernetes read impersonates `system:serviceaccount:kubeops-demo:kubeops-viewer`. Its Role permits listing Pods and reading only the named demo Deployment and Service. It cannot change workloads or read Secrets. The local kind administrator credentials must allow impersonating this identity; these credentials remain on the host, so this is not a credential-isolated production deployment. Do not expose this development server publicly.

CI checks the rendered page against a live cluster and verifies that the viewer cannot patch Deployments or read Secrets. Unit tests cover Pending Pods, escaped text, the restricted read command, and unavailable-cluster/Host handling.

## Part 4: Pod readiness and diagnostics

The dashboard now separates Pod phase from readiness: a `Running` Pod is not necessarily ready to serve traffic. The Ready column shows `Yes`, `No`, or `Unknown` from the Pod's Ready condition. Missing status is not treated as success.

The Reason column shows Kubernetes-reported scheduling and current container/init-container issues, such as `Unschedulable`, `ImagePullBackOff`, `CrashLoopBackOff`, or `OOMKilled`, with their messages below the row. Pods being deleted are marked `Terminating`. These are reported statuses, not an automatic root-cause diagnosis. A previous container failure is not displayed as a current failure after the container recovers; the restart count remains visible.

No permissions or dependencies were added. Messages remain HTML-escaped. Tests cover missing status, Running-but-unready Pods, image/crash/memory/init failures, scheduling failures, termination, recovered containers, and escaped messages. CI checks the expanded page on the existing live cluster.

## Part 5: bounded Pod logs

Click **Logs** beside a Pod to view its current `utility` container output. Each snapshot requests at most 200 lines and 65,536 bytes, with timestamps. Empty output and unavailable/replaced Pods have explicit messages. There is no live streaming or previous-container selection yet.

Apply the updated manifests before restarting the dashboard: `kubectl --context kind-kubeops apply -k k8s`. The viewer now has Pod get/list and Pod-log get permissions in the dedicated demo namespace. It still cannot change workloads, execute commands in containers, or read Secrets. Kubernetes RBAC grants namespace-wide Pod-log reads; the application narrows selection to Pods matching `app=kubeops-utility`. Keep this namespace exclusive to the demo.

The handler checks selection against the current demo Pod list before calling kubectl, uses a fixed container and limits, and displays output as escaped HTML. Logs are not saved by the dashboard. Logs can contain application data, so the dashboard remains localhost-only. Tests cover rejected selections, fixed limits, UTF-8 handling, escaped output, and unavailable logs; CI reads actual Pod logs using the viewer identity.

## Part 6: related Kubernetes events

The workload page now shows the latest 50 retained events for the current demo Deployment, Service, and Pods. Events are matched by resource UID, so unrelated objects and old objects with reused names are excluded. Each row includes type, object, reason, occurrence count, last-observed time, and a message capped at 2,000 characters. Messages are HTML-escaped.

Reapply the manifests before restarting the dashboard: `kubectl --context kind-kubeops apply -k k8s`. The viewer gains only namespace-scoped event-list permissions. Kubernetes RBAC does not restrict this list by object UID; filtering happens in the application. No event creation or workload mutation is available through the dashboard.

This is a snapshot of events Kubernetes still retains, not a durable audit history. Events for removed Pods and ReplicaSets are not included in this version. An empty state means no matching events were returned, not that the workload has never had a problem. The display is capped; the namespace event list is still fetched in full for this small demo.

## Part 7: resource requests and limits

The workload page now shows CPU and memory requests and limits per application/init container. Deployment template settings and actual Pod specifications have separate rows, so admission defaults and rollout differences are not hidden. Quantity strings such as `100m`, `0.5`, and `64Mi` are preserved as Kubernetes returns them; missing values show `Not set`, not zero.

These are configured per-container budgets, not measured consumption or aggregate Pod scheduling totals. No Metrics Server, new permissions, dependencies, or additional API reads are needed. All displayed values are HTML-escaped. Tests cover missing settings, multiple containers, init containers, quantity preservation, template/Pod differences, and escaped output. CI verifies the deployed demo's budgets in the rendered page.

## Next stage

Show Kubernetes-reported Pod quality-of-service classes alongside the resource settings.
