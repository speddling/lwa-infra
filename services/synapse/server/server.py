"""
synapse — Local MCP server for Little Wolf Acres

Gives Claude Desktop (on apex) tool access to Monolith's k3s cluster,
Prometheus metrics on Watchtower, and the host filesystem — over SSE,
entirely within the LAN.

Tools:
  k8s_*    read-only kubectl operations via the Python kubernetes client
  prom_*   PromQL queries against Prometheus on Watchtower (192.168.0.21)
  fs_*     read-only filesystem access, path-allowlisted via ALLOWED_READ_PATHS

Transport: Streamable HTTP via FastMCP (supports both legacy SSE and current protocol)
Auth:      None — UFW on Monolith restricts port 30800 to apex only
RBAC:      In-cluster ServiceAccount with a least-privilege ClusterRole
"""

import logging
import os
import pathlib

import httpx
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("synapse")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://192.168.0.21:9090")
ALLOWED_READ_PATHS = [
    p.strip()
    for p in os.environ.get("ALLOWED_READ_PATHS", "/mnt/ssd-a").split(",")
    if p.strip()
]

k8s_config.load_incluster_config()
core_v1 = k8s_client.CoreV1Api()
apps_v1 = k8s_client.AppsV1Api()

mcp = FastMCP("synapse")


# ---------------------------------------------------------------------------
# Kubernetes tools
# ---------------------------------------------------------------------------

@mcp.tool()
def k8s_get_pods(namespace: str) -> str:
    """List pods and their status. Use namespace='all' for cluster-wide."""
    pods = (
        core_v1.list_pod_for_all_namespaces()
        if namespace == "all"
        else core_v1.list_namespaced_pod(namespace)
    )
    rows = [f"{'NAMESPACE':<20} {'NAME':<45} {'STATUS':<12} READY"]
    for pod in pods.items:
        statuses = pod.status.container_statuses or []
        ready = sum(1 for c in statuses if c.ready)
        total = len(pod.spec.containers)
        rows.append(
            f"{pod.metadata.namespace:<20} {pod.metadata.name:<45} "
            f"{pod.status.phase:<12} {ready}/{total}"
        )
    return "\n".join(rows)


@mcp.tool()
def k8s_get_nodes() -> str:
    """Get k3s node status, kubelet version, CPU and memory capacity."""
    nodes = core_v1.list_node()
    rows = [f"{'NAME':<20} {'STATUS':<10} {'VERSION':<20} {'CPU':<6} MEMORY"]
    for node in nodes.items:
        conds = {c.type: c.status for c in node.status.conditions}
        ready = "Ready" if conds.get("Ready") == "True" else "NotReady"
        cap = node.status.capacity
        rows.append(
            f"{node.metadata.name:<20} {ready:<10} "
            f"{node.status.node_info.kubelet_version:<20} "
            f"{cap.get('cpu', '?'):<6} {cap.get('memory', '?')}"
        )
    return "\n".join(rows)


@mcp.tool()
def k8s_get_logs(namespace: str, pod_name: str, tail_lines: int = 50) -> str:
    """Fetch recent log lines from a running pod."""
    logs = core_v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=tail_lines)
    return logs or "(no output)"


@mcp.tool()
def k8s_describe_pod(namespace: str, pod_name: str) -> str:
    """Describe a pod: containers, resource requests/limits, recent events."""
    pod = core_v1.read_namespaced_pod(pod_name, namespace)
    events = core_v1.list_namespaced_event(
        namespace, field_selector=f"involvedObject.name={pod_name}"
    )
    lines = [
        f"Pod:       {pod.metadata.name}",
        f"Namespace: {pod.metadata.namespace}",
        f"Phase:     {pod.status.phase}",
        f"Node:      {pod.spec.node_name}",
        f"IP:        {pod.status.pod_ip}",
        "",
        "Containers:",
    ]
    for c in pod.spec.containers:
        res = c.resources or k8s_client.V1ResourceRequirements()
        req, lim = res.requests or {}, res.limits or {}
        lines.append(
            f"  {c.name}  cpu={req.get('cpu','-')}/{lim.get('cpu','-')}  "
            f"mem={req.get('memory','-')}/{lim.get('memory','-')}"
        )
    lines.append("\nRecent Events:")
    for ev in sorted(events.items, key=lambda e: e.last_timestamp or "", reverse=True)[:10]:
        lines.append(f"  [{ev.type}] {ev.reason}: {ev.message}")
    return "\n".join(lines)


@mcp.tool()
def k8s_get_pvcs(namespace: str) -> str:
    """List PersistentVolumeClaims. Use namespace='all' for cluster-wide."""
    pvcs = (
        core_v1.list_persistent_volume_claim_for_all_namespaces()
        if namespace == "all"
        else core_v1.list_namespaced_persistent_volume_claim(namespace)
    )
    rows = [f"{'NAMESPACE':<20} {'NAME':<35} {'STATUS':<10} {'CAPACITY':<12} STORAGECLASS"]
    for pvc in pvcs.items:
        cap = (pvc.status.capacity or {}).get("storage", "?")
        rows.append(
            f"{pvc.metadata.namespace:<20} {pvc.metadata.name:<35} "
            f"{pvc.status.phase:<10} {cap:<12} {pvc.spec.storage_class_name}"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Prometheus tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def prom_query(query: str) -> str:
    """Run an instant PromQL query against Prometheus on Watchtower."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
        r.raise_for_status()
        data = r.json()
    if data["status"] != "success":
        return f"Prometheus error: {data.get('error')}"
    results = data["data"]["result"]
    if not results:
        return "No data returned."
    lines = [f"Query: {query}", ""]
    for item in results:
        labels = ", ".join(f'{k}="{v}"' for k, v in item["metric"].items())
        lines.append(f"  {{{labels}}} = {item['value'][1]}")
    return "\n".join(lines)


@mcp.tool()
async def prom_active_alerts() -> str:
    """Get all currently firing Prometheus alerts."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{PROMETHEUS_URL}/api/v1/alerts")
        r.raise_for_status()
        data = r.json()
    firing = [a for a in data["data"]["alerts"] if a["state"] == "firing"]
    if not firing:
        return "No alerts currently firing."
    lines = [f"{len(firing)} alert(s) firing:", ""]
    for a in firing:
        lb, an = a.get("labels", {}), a.get("annotations", {})
        lines.append(
            f"  [{lb.get('alertname','?')}] severity={lb.get('severity','?')} "
            f"— {an.get('summary','(no summary)')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Filesystem tools
# ---------------------------------------------------------------------------

def _is_allowed_path(requested: str) -> bool:
    """Resolve symlinks and canonicalize before checking — prevents path traversal."""
    try:
        resolved = pathlib.Path(requested).resolve(strict=False)
        return any(
            str(resolved).startswith(str(pathlib.Path(p).resolve()))
            for p in ALLOWED_READ_PATHS
        )
    except Exception:
        return False


@mcp.tool()
def fs_read_file(path: str) -> str:
    """Read a file from Monolith. Restricted to ALLOWED_READ_PATHS."""
    if not _is_allowed_path(path):
        return f"Access denied: '{path}' is outside allowed paths ({', '.join(ALLOWED_READ_PATHS)})"
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_file():
        return f"Not a file: {path}"
    return resolved.read_text(errors="replace")


@mcp.tool()
def fs_list_dir(path: str) -> str:
    """List a directory on Monolith. Restricted to ALLOWED_READ_PATHS."""
    if not _is_allowed_path(path):
        return f"Access denied: '{path}' is outside allowed paths ({', '.join(ALLOWED_READ_PATHS)})"
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_dir():
        return f"Not a directory: {path}"
    entries = sorted(resolved.iterdir(), key=lambda e: (e.is_file(), e.name))
    return "\n".join(f"[{'FILE' if e.is_file() else 'DIR '}] {e.name}" for e in entries) or "(empty)"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080, path="/mcp")
