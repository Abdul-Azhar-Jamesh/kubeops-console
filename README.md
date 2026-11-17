# KubeOps Console

A Kubernetes operations dashboard project, being developed in small working stages.

## Part 1: HTTP workload service

This first release contains the small application the dashboard will eventually deploy and inspect. It reports its version, hostname, optional Pod/node identity, and a configurable message. It also exposes health endpoints.

The dashboard and Kubernetes deployment features are not included in this release.

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

Optional environment variables: `APP_VERSION`, `MESSAGE`, `POD_NAME`, and `NODE_NAME`. Pod/node values remain null unless supplied; a future Kubernetes manifest will populate them through the Downward API.

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

## Next stage

Add a Kubernetes Deployment and ClusterIP Service for this workload, with resource budgets and health probes. Dashboard development will follow in later stages.
