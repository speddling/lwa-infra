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

DNS chain: **AdGuard Home → Unbound → root** — recursive, no upstream forwarder dependency

Local domain: `littlewolfacres.com` — all hosts resolve as `hostname.littlewolfacres.com`

## Stack

- **Kubernetes** — k3s (single-node, expandable)
- **IaC** — Terraform Cloud
- **Automation** — GitHub Actions + Ansible (modular role structure)
- **Secrets** — Ansible Vault · consolidated at `ansible/vars/vault.yml`
- **Variables** — Single source of truth at `ansible/vars/main.yml` — all IPs, ports, paths, and service config
- **Monitoring** — Prometheus · Grafana · Alertmanager · Netdata · node_exporter · blackbox_exporter · snmp_exporter · adguard_exporter
- **OS** — Ubuntu Server 24.04 LTS (monolith + watchtower) · macOS Sequoia (apex)

## CI/CD

GitHub Actions pipelines on self-hosted runners (monolith, watchtower) and SSH-driven runners (apex). All changes go through **branch → PR → merge**. Direct pushes to `main` are disabled.

Claude handles the full git workflow via **Scribe** — branch, commit, push, and open PRs automatically. Human approval at PR review is the only required gate.

```
feat/*    New capabilities or services
fix/*     Bug fixes
docs/*    Documentation only — does not trigger deploy
chore/*   Maintenance, dependency updates
```

## Services

| Service | Host | Stack | Status |
|---|---|---|---|
| Navidrome | monolith | Kubernetes · PVC + Ingress | ✅ Online — ~1TB FLAC/MP3 library |
| Samba file share | monolith | Ansible | ✅ Online — family backups + vault share |
| hdd-d mirror | monolith | Ansible · systemd timer (nightly 02:00) | ✅ Online |
| Minecraft server | monolith | Kubernetes · optional world import workflow | ✅ Online |
| AdGuard Home + Unbound | watchtower | Ansible | ✅ Online |
| Prometheus + Grafana + Alertmanager | watchtower | Ansible | ✅ Online |
| Synapse | monolith | FastMCP · Kubernetes | ✅ Online |
| Scribe | apex | FastMCP · launchd · Ansible | ✅ Online |
| Argus | watchtower | FastMCP · systemd · Ansible | ✅ Online |

## AI Tooling

Three MCP servers give Claude structured, safe access to the homelab:

**Synapse** (`monolith:30800`) — Claude's eyes on the cluster. Read-only access to k3s pod state, Prometheus metrics, Alertmanager alerts, and the monolith filesystem. Deployed as a Kubernetes service. See `docs/synapse.md`.

**Scribe** (`apex:8765`) — Claude's git control plane. Branch, stage, commit, push, and open PRs against this repo — with branch protection and path allowlisting baked in at the server level. Deployed as a launchd service on apex. See `docs/scribe.md`.

**Argus** (`watchtower:9800`) — Claude's eyes on the monitoring layer. Read-only access to live Alertmanager and Prometheus configs, systemd service and timer state, journald logs, and the Alertmanager and Prometheus HTTP APIs. Deployed as a systemd service on watchtower. See `docs/argus.md`.

## Custom Exporters

**T-Mobile Home Internet Exporter** — custom Python Prometheus exporter for T-Mobile FAST 5688W gateway metrics. Hardened systemd service on watchtower, scraped by Prometheus.

**Reolink NVR Exporter** — custom Python Prometheus exporter for Reolink camera system availability and status.

## Planned

- **ArgoCD** — GitOps for k3s. Migrate from `kubectl apply` chains to declarative GitOps with automatic cluster reconciliation on merge
- **Loki** — log aggregation on watchtower
- **Rommie** — local LLM workspace on monolith (pending GPU — RTX 3090 24GB)
- **Obelisk** — isolated client workspace on `/mnt/ssd-b`
- **JetStream switch** — replaces unmanaged TL-SG1210P, enables per-port SNMP stats
- **NUT** — UPS monitoring via CyberPower CP1500PFCLCD (role ready, waiting on hardware)
