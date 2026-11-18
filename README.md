# KubeOps Console

A Kubernetes operations dashboard project, being developed in small working stages.

## Part 1: HTTP workload service

This first release contains the small application the dashboard will eventually deploy and inspect. It reports its version, hostname, optional Pod/node identity, and a configurable message. It also exposes health endpoints.

Part 2 adds a local Kubernetes deployment for this service. The dashboard itself is not included yet.

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

## Next stage

Add the first read-only dashboard view for inspecting this workload. Further operations will follow in small stages.
