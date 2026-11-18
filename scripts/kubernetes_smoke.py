"""Check the deployed Service, Pod identity, and scaling in kind-kubeops."""

import json
import subprocess

KUBECTL = [
    "kubectl",
    "--context",
    "kind-kubeops",
    "--namespace",
    "kubeops-demo",
    "--request-timeout=15s",
]


def kubectl(*args, body=None, timeout=90):
    return subprocess.run(
        [*KUBECTL, *args],
        input=body,
        text=True,
        capture_output=True,
        check=True,
        timeout=timeout,
    ).stdout


def main():
    # Run inside the cluster so this checks Service DNS/routing, not just port-forwarding.
    probe = """import json, urllib.request
base = 'http://kubeops-utility:8080'
with urllib.request.urlopen(base + '/', timeout=10) as r:
    data = json.load(r)
assert data['pod'].startswith('kubeops-utility-'), data
assert data['node'] and data['version'] == 'v1', data
assert data['message'] == 'hello from Kubernetes', data
for path in ('/health/live', '/health/ready'):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        assert r.status == 200 and json.load(r) == {'status': 'ok'}
print(json.dumps(data))
"""
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "kubeops-smoke"},
        "spec": {
            "restartPolicy": "Never",
            "activeDeadlineSeconds": 60,
            "automountServiceAccountToken": False,
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 10001,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [
                {
                    "name": "probe",
                    "image": "kubeops-utility:v1",
                    "imagePullPolicy": "Never",
                    "command": ["python", "-c", probe],
                    "resources": {
                        "requests": {"cpu": "50m", "memory": "32Mi"},
                        "limits": {"cpu": "250m", "memory": "64Mi"},
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                }
            ],
        },
    }
    created = False
    try:
        kubectl("create", "-f", "-", body=json.dumps(pod))
        created = True
        kubectl(
            "wait",
            "--for=jsonpath={.status.phase}=Succeeded",
            "pod/kubeops-smoke",
            "--timeout=75s",
        )
        print(kubectl("logs", "kubeops-smoke"))
        kubectl("scale", "deployment/kubeops-utility", "--replicas=2")
        kubectl(
            "wait",
            "--for=jsonpath={.status.readyReplicas}=2",
            "deployment/kubeops-utility",
            "--timeout=75s",
        )
        print(
            "Service, health endpoints, Pod identity, and two ready replicas verified."
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stdout, exc.stderr)
        raise
    finally:
        # Restore the documented replica count and remove only this script's probe Pod.
        if created:
            subprocess.run([*KUBECTL, "logs", "kubeops-smoke"], check=False, timeout=30)
            kubectl("delete", "pod/kubeops-smoke", "--ignore-not-found", "--wait=false")
            kubectl("scale", "deployment/kubeops-utility", "--replicas=1")


if __name__ == "__main__":
    main()
