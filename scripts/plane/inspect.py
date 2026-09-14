#!/usr/bin/env python3
"""Inspect Plane metadata and pending migrations; never apply migrations."""
import json
import re
import socket
import subprocess


def kubectl(*args):
    result = subprocess.run(
        ["k3s", "kubectl", "--request-timeout=20s", *args],
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode:
        # Do not echo arbitrary command output, environment or connection URLs.
        raise RuntimeError(f"kubectl {args[0]} failed with exit {result.returncode}")
    return result.stdout


def get(kind, namespace="plane", name=None):
    args = ["get", kind, "-n", namespace]
    if name:
        args.append(name)
    return json.loads(kubectl(*args, "-o", "json"))


def main():
    if socket.gethostname().split(".")[0] != "monolith":
        raise RuntimeError("Inspection requires Monolith")
    pods = get("pods")["items"]
    summary = []
    for pod in pods:
        statuses = {s["name"]: s for s in pod["status"].get("containerStatuses", [])}
        summary.append({
            "name": pod["metadata"]["name"],
            "created": pod["metadata"].get("creationTimestamp"),
            "phase": pod["status"].get("phase"),
            "containers": [{
                "name": c["name"], "image": c["image"],
                "imageID": statuses.get(c["name"], {}).get("imageID"),
                "ready": statuses.get(c["name"], {}).get("ready"),
                "restarts": statuses.get(c["name"], {}).get("restartCount"),
                "resources": c.get("resources", {}),
            } for c in pod["spec"]["containers"]],
        })
    print(json.dumps({"pods": summary}), flush=True)
    application = get("application", "argocd", "plane")
    status = application.get("status", {})
    print(json.dumps({"argocd": {
        "health": status.get("health", {}).get("status"),
        "sync": status.get("sync", {}).get("status"),
        "revision": status.get("sync", {}).get("revision"),
        "operation_phase": status.get("operationState", {}).get("phase"),
        "condition_types": [c.get("type") for c in status.get("conditions", [])],
        "resources": [{k: r.get(k) for k in ("kind", "name", "status", "health")}
                      for r in status.get("resources", [])],
    }}), flush=True)
    candidates = sorted(
        [p for p in pods if p["metadata"]["name"].startswith("plane-api-wl-")
         and any(c["name"] == "plane-api" and c.get("state", {}).get("running")
                 for c in p["status"].get("containerStatuses", []))],
        key=lambda p: p["metadata"]["creationTimestamp"], reverse=True,
    )
    if not candidates:
        raise RuntimeError("No running Plane API container available for read-only migration plan")
    pod_name = candidates[0]["metadata"]["name"]
    # PostgreSQL rejects writes for this process; showmigrations only builds a plan.
    output = kubectl("exec", "-n", "plane", pod_name, "-c", "plane-api", "--",
                     "env", "PGOPTIONS=-c default_transaction_read_only=on",
                     "python", "manage.py", "showmigrations", "--plan", "--no-color")
    rows = [line.strip() for line in output.splitlines()
            if re.fullmatch(r"\s*\[(?:X| )\]  [A-Za-z0-9_]+\.[A-Za-z0-9_]+\s*", line)]
    if not rows:
        raise RuntimeError("No recognizable migration plan; raw output withheld")
    print(json.dumps({"migration_plan_pod": pod_name, "migrations": rows,
                      "pending_count": sum(row.startswith("[ ]") for row in rows)}))


if __name__ == "__main__":
    main()
