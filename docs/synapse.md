# Synapse — MCP/AI Tooling on Monolith

## Overview

Synapse is the MCP (Model Context Protocol) namespace on Monolith. It gives Claude Desktop (on apex) tool access to the k3s cluster, Prometheus metrics on Watchtower, and the host filesystem — entirely within the LAN. No data leaves the network.

It serves as Claude's interface to both the Little Wolf Acres homelab and BS CS / AI coursework.

---

## Stack

| Layer | Detail |
|---|---|
| Namespace | `synapse` on Monolith k3s |
| Transport | HTTP/SSE (`http://monolith.littlewolfacres.com:30800/sse`) |
| Image | `ghcr.io/speddling/synapse:latest` (built in CI) |
| Server | Python — `mcp` SDK, Starlette, uvicorn |
| Auth | None — UFW restricts port 30800 to apex (192.168.0.19) only |
| IaC | GitHub Actions (`deploy-synapse.yml`) |
| Runner | Self-hosted, label: `monolith` |

---

## Tools

| Tool | Description |
|---|---|
| `k8s_get_pods` | List pods in a namespace or cluster-wide |
| `k8s_get_nodes` | Node status, kubelet version, CPU/memory capacity |
| `k8s_get_logs` | Tail pod log output |
| `k8s_describe_pod` | Pod details, resource requests/limits, recent events |
| `k8s_get_pvcs` | PersistentVolumeClaim status |
| `prom_query` | Instant PromQL query against Prometheus on Watchtower |
| `prom_active_alerts` | Currently firing Prometheus alerts |
| `fs_read_file` | Read a file from an allowlisted path on Monolith |
| `fs_list_dir` | List a directory from an allowlisted path |

---

## File Layout

```
services/synapse/
  server/
    server.py           # MCP server — tools, SSE transport
    requirements.txt
    Dockerfile          # Multi-stage, runs as uid 1000
  kubernetes/
    namespace.yaml
    rbac.yaml           # ServiceAccount + least-privilege ClusterRole
    configmap.yaml      # PROMETHEUS_URL, ALLOWED_READ_PATHS
    deployment.yaml
    service.yaml        # NodePort 30800
.github/workflows/
  deploy-synapse.yml    # Build image → push ghcr.io → apply manifests → UFW
```

---

## Security Model

| Control | Detail |
|---|---|
| Network | UFW: port 30800 allowed from 192.168.0.19 (apex) only |
| k8s permissions | Custom ClusterRole: read-only get/list/watch + pods/log. No write, no exec, no secrets. |
| Filesystem | hostPath volumes mounted `readOnly: true`. Path allowlist enforced in server.py. |
| Prometheus | Read-only HTTP queries against Watchtower |
| Container | Runs as uid 1000, non-root, multi-stage build |

---

## Deployment

The `deploy-synapse` workflow is `workflow_dispatch` — trigger it manually after merging to master:

```bash
gh workflow run deploy-synapse.yml
```

On first run it will:
1. Build and push the image to `ghcr.io/speddling/synapse`
2. Create the `synapse` namespace and pull secret
3. Apply RBAC, ConfigMap, Deployment, Service
4. Wait for the rollout
5. Add the UFW rule for apex → port 30800

---

## Claude Desktop Configuration (apex)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "synapse": {
      "command": "/Users/speddling/.nvm/versions/node/v24.15.0/bin/npx",
      "args": ["mcp-remote", "http://monolith.littlewolfacres.com:30800/sse", "--allow-http"]
    }
  }
}
```

Quit and relaunch Claude Desktop. A hammer icon in the chat interface confirms the connection.

---

## Runbook

```bash
# Pod status
kubectl get pods -n synapse

# Logs
kubectl logs -n synapse deployment/synapse --tail=50 -f

# Health check (from apex)
curl http://monolith.littlewolfacres.com:30800/health

# Restart after config change
kubectl rollout restart deployment/synapse -n synapse

# UFW check (on monolith)
sudo ufw status numbered | grep 30800
```

---

## Future

- Add Prometheus scrape target for Synapse health (`job: synapse`, `target: monolith:30800`)
- Add `SynapseDown` alert rule on Watchtower
- When Obelisk is built, add a second MCP server instance in the `obelisk` namespace with its own allowlisted paths and a separate Claude Desktop entry
