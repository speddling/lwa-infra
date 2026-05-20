# Little Wolf Acres — Homelab

Personal homelab built with production-grade IaC discipline. Everything is code, nothing is clicked.

## Hardware

| Node | Hostname | Specs | Role |
|---|---|---|---|
| MacBook Air M4 (2025) | `apex` | 16GB · 256GB | Primary workstation · control plane · all authoring originates here |
| AMD Ryzen 7 5700G | `monolith` | 32GB DDR4 · 512GB NVMe + SSD + 6TB HDD | k3s single-node cluster · household services |
| Asus VM40B | `watchtower` | 8GB · 1TB SSD | Always-on DNS + monitoring — never runs workloads |
| Dell Precision | `studio` | — | Personal DAW — Reaper + M-Audio Air 192\|14 |

## Network

TP-Link Omada ecosystem — fully managed, SNMP-monitored.

| Device | Role |
|---|---|
| ER605 v2 | Multi-WAN VPN router |
| OC200 | Omada network controller |
| TL-SG1210P | Unmanaged PoE switch (replacement planned) |
| 2× EAP245 | Access points — Foyer + Yarn Studio |

DNS chain: **AdGuard Home → Unbound → root** — recursive, no upstream forwarder dependency.
Public DNS: **Cloudflare** — authoritative for `littlewolfacres.com`, provides LAN fallback resolution for all internal hostnames if AdGuard is unreachable.

Local domain: `littlewolfacres.com` — all hosts resolve as `hostname.littlewolfacres.com`

## Stack

- **Kubernetes** — k3s (single-node, expandable)
- **GitOps** — ArgoCD v3.3.0 — all k3s workloads managed declaratively from this repo
- **TLS** — cert-manager v1.20.2 — automatic Let's Encrypt certificates via Cloudflare DNS-01
- **Ingress** — Traefik (k3s default) — terminates TLS, routes to cluster services
- **IaC** — Terraform Cloud
- **Automation** — GitHub Actions + Ansible (modular role structure)
- **Secrets** — Ansible Vault · consolidated at `ansible/vars/vault.yml`
- **Variables** — Single source of truth at `ansible/vars/main.yml` — all IPs, ports, paths, and service config
- **Monitoring** — Prometheus · Grafana · Alertmanager · Netdata · node_exporter · blackbox_exporter · snmp_exporter · adguard_exporter
- **OS** — Ubuntu Server 24.04 LTS (monolith + watchtower) · macOS Sequoia (apex)

## CI/CD

GitHub Actions pipelines on self-hosted runners (monolith, watchtower) and SSH-driven runners (apex). All changes go through **branch → PR → merge**. Direct pushes to `master` are disabled.

Claude handles the full git workflow via **Scribe** — branch, commit, push, and open PRs automatically. Human approval at PR review is the only required gate.

```
feat/*    New capabilities or services
fix/*     Bug fixes
docs/*    Documentation only — does not trigger deploy
chore/*   Maintenance, dependency updates
```

| Workflow | Trigger | What it does |
|---|---|---|
| `deploy-watchtower.yml` | Push to master | DNS, monitoring, exporters |
| `deploy-monolith.yml` | Push to master | Firewall, monitoring agents |
| `deploy-fileserver.yml` | Manual | Samba config |
| `bootstrap-argocd.yml` | Manual (once) | cert-manager + ArgoCD install |
| `provision-k3s.yml` | Manual | k3s cluster init |

## Services

| Service | Host | URL | Status |
|---|---|---|---|
| ArgoCD | monolith | https://argocd.littlewolfacres.com | ✅ Online |
| Navidrome | monolith | https://navidrome.littlewolfacres.com (HTTP for now) | ✅ Online |
| Minecraft server | monolith | UDP 19132 | ✅ Online |
| Samba file share | monolith | — | ✅ Online |
| hdd-d mirror | monolith | — nightly 02:00 | ✅ Online |
| AdGuard Home + Unbound | watchtower | http://watchtower:3000 | ✅ Online |
| Prometheus | watchtower | http://watchtower:9090 | ✅ Online |
| Grafana | watchtower | http://grafana.littlewolfacres.com:3001 | ✅ Online |
| Alertmanager | watchtower | http://watchtower:9093 | ✅ Online |
| Netdata | watchtower | http://watchtower:19999 | ✅ Online |
| Synapse MCP | monolith | monolith:30800 | ✅ Online |
| Scribe MCP | apex | apex:8765 | ✅ Online |
| Argus MCP | watchtower | watchtower:9800 | ✅ Online |

## AI Tooling

Three MCP servers give Claude structured, safe access to the homelab:

**Synapse** (`monolith:30800`) — Claude's eyes on the cluster. Read-only access to k3s pod state, Prometheus metrics, Alertmanager alerts, and the monolith filesystem.

**Scribe** (`apex:8765`) — Claude's git control plane. Branch, stage, commit, push, and open PRs against this repo — with branch protection and path allowlisting baked in at the server level.

**Argus** (`watchtower:9800`) — Claude's eyes on the monitoring layer. Read-only access to live Alertmanager and Prometheus configs, systemd service state, journald logs, and monitoring HTTP APIs.

See `docs/Claude MCPs.md` for full reference.

## Custom Exporters

**T-Mobile Home Internet Exporter** — custom Python Prometheus exporter for T-Mobile FAST 5688W gateway metrics.

**Reolink NVR Exporter** — custom Python Prometheus exporter for Reolink camera system availability and status.

## Planned

- **Navidrome HTTPS** — upgrade ingress from HTTP to HTTPS now that cert-manager is live
- **Loki** — log aggregation on watchtower
- **Lore** — dedicated AI inference node, Mac Mini M4 Pro 48GB / 10GbE, headless. Added when B-4 on apex is outgrown
- **Data** — aspirational. Maxed Mac Studio, long-term AI platform. Not current plan
- **Obelisk** — isolated client workspace on `/mnt/ssd-b`
- **JetStream switch** — replaces unmanaged TL-SG1210P, enables per-port SNMP stats
- **NUT** — UPS monitoring via CyberPower CP1500PFCLCD (role ready, waiting on hardware)
- **Fileserver idempotency** — fix `smbpasswd -a` in deploy-fileserver so it's safe to re-run
