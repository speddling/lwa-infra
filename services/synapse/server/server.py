"""
synapse — Local MCP server for Little Wolf Acres

Gives Claude Desktop (on apex) tool access to Monolith's k3s cluster,
Prometheus metrics on Watchtower, and the host filesystem — over SSE,
entirely within the LAN.

Tools:
  k8s_*    read-only kubectl operations via the Python kubernetes client
  prom_*   PromQL queries against Prometheus on Watchtower (192.168.0.21)
  fs_*     read-only filesystem access, path-allowlisted via ALLOWED_READ_PATHS

Transport: HTTP/SSE (Starlette + uvicorn)
Auth:      None — UFW on Monolith restricts port 30800 to apex only
RBAC:      In-cluster ServiceAccount with a least-privilege ClusterRole
"""

import logging
import os
import pathlib

import httpx
import uvicorn
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from mcp import types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

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

# load_incluster_config() reads the pod's ServiceAccount token from
# /var/run/secrets/kubernetes.io/serviceaccount/ — mounted automatically by k8s.
k8s_config.load_incluster_config()
core_v1 = k8s_client.CoreV1Api()
apps_v1 = k8s_client.AppsV1Api()

server = Server("synapse")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="k8s_get_pods",
            description="List pods and their status. namespace='all' for cluster-wide.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                },
                "required": ["namespace"],
            },
        ),
        types.Tool(
            name="k8s_get_nodes",
            description="Get k3s node status, kubelet version, CPU and memory capacity.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="k8s_get_logs",
            description="Fetch recent log lines from a running pod.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "pod_name": {"type": "string"},
                    "tail_lines": {"type": "integer", "default": 50},
                },
                "required": ["namespace", "pod_name"],
            },
        ),
        types.Tool(
            name="k8s_describe_pod",
            description="Describe a pod: containers, resource requests/limits, recent events.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "pod_name": {"type": "string"},
                },
                "required": ["namespace", "pod_name"],
            },
        ),
        types.Tool(
            name="k8s_get_pvcs",
            description="List PersistentVolumeClaims. namespace='all' for cluster-wide.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                },
                "required": ["namespace"],
            },
        ),
        types.Tool(
            name="prom_query",
            description="Run an instant PromQL query against Prometheus on Watchtower.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="prom_active_alerts",
            description="Get all currently firing Prometheus alerts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="fs_read_file",
            description=(
                f"Read a file from Monolith. "
                f"Allowed paths: {', '.join(ALLOWED_READ_PATHS)}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="fs_list_dir",
            description=(
                f"List a directory on Monolith. "
                f"Allowed paths: {', '.join(ALLOWED_READ_PATHS)}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        ),
    ]


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


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    logger.info("tool=%s args=%s", name, arguments)
    try:
        result = await _dispatch(name, arguments)
        return [types.TextContent(type="text", text=result)]
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return [types.TextContent(type="text", text=f"Error: {exc}")]


async def _dispatch(name: str, args: dict) -> str:  # noqa: C901
    if name == "k8s_get_pods":
        ns = args["namespace"]
        pods = (
            core_v1.list_pod_for_all_namespaces()
            if ns == "all"
            else core_v1.list_namespaced_pod(ns)
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

    elif name == "k8s_get_nodes":
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

    elif name == "k8s_get_logs":
        logs = core_v1.read_namespaced_pod_log(
            args["pod_name"], args["namespace"], tail_lines=int(args.get("tail_lines", 50))
        )
        return logs or "(no output)"

    elif name == "k8s_describe_pod":
        ns, pod_name = args["namespace"], args["pod_name"]
        pod = core_v1.read_namespaced_pod(pod_name, ns)
        events = core_v1.list_namespaced_event(
            ns, field_selector=f"involvedObject.name={pod_name}"
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

    elif name == "k8s_get_pvcs":
        ns = args["namespace"]
        pvcs = (
            core_v1.list_persistent_volume_claim_for_all_namespaces()
            if ns == "all"
            else core_v1.list_namespaced_persistent_volume_claim(ns)
        )
        rows = [f"{'NAMESPACE':<20} {'NAME':<35} {'STATUS':<10} {'CAPACITY':<12} STORAGECLASS"]
        for pvc in pvcs.items:
            cap = (pvc.status.capacity or {}).get("storage", "?")
            rows.append(
                f"{pvc.metadata.namespace:<20} {pvc.metadata.name:<35} "
                f"{pvc.status.phase:<10} {cap:<12} {pvc.spec.storage_class_name}"
            )
        return "\n".join(rows)

    elif name == "prom_query":
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": args["query"]})
            r.raise_for_status()
            data = r.json()
        if data["status"] != "success":
            return f"Prometheus error: {data.get('error')}"
        results = data["data"]["result"]
        if not results:
            return "No data returned."
        lines = [f"Query: {args['query']}", ""]
        for item in results:
            labels = ", ".join(f'{k}="{v}"' for k, v in item["metric"].items())
            lines.append(f"  {{{labels}}} = {item['value'][1]}")
        return "\n".join(lines)

    elif name == "prom_active_alerts":
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

    elif name == "fs_read_file":
        path = args["path"]
        if not _is_allowed_path(path):
            return f"Access denied: '{path}' is outside allowed paths ({', '.join(ALLOWED_READ_PATHS)})"
        resolved = pathlib.Path(path).resolve()
        if not resolved.is_file():
            return f"Not a file: {path}"
        return resolved.read_text(errors="replace")

    elif name == "fs_list_dir":
        path = args["path"]
        if not _is_allowed_path(path):
            return f"Access denied: '{path}' is outside allowed paths ({', '.join(ALLOWED_READ_PATHS)})"
        resolved = pathlib.Path(path).resolve()
        if not resolved.is_dir():
            return f"Not a directory: {path}"
        entries = sorted(resolved.iterdir(), key=lambda e: (e.is_file(), e.name))
        return "\n".join(f"[{'FILE' if e.is_file() else 'DIR '}] {e.name}" for e in entries) or "(empty)"

    return f"Unknown tool: '{name}'"


# SSE wiring
# GET  /sse        Claude connects here and holds the stream open
# POST /messages/  Claude sends tool call requests (SSE protocol framing)
# GET  /health     Kubernetes liveness / readiness probe
sse = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as (r, w):
        await server.run(r, w, server.create_initialization_options())


app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
        Route("/health", endpoint=lambda _: PlainTextResponse("ok")),
    ]
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
