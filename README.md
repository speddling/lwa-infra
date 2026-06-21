# LWA Infra

Self-managed infrastructure built with production-grade IaC discipline. Everything is code, nothing is clicked.

## Hardware

| Node | Hostname | Specs | Role |
|---|---|---|---|
| MacBook Air M4 (2025) | `apex` | 16GB unified · 256GB | Primary workstation · control plane · all authoring originates here |
| AMD Ryzen 7 5700G | `monolith` | 8c/16t · 64GB DDR4-3200 · 512GB NVMe + 500GB SSD + 256GB SSD + 3.6TB HDD + 1.8TB HDD | k3s single-node cluster · household services · Obelisk QEMU host |
| Asus VM40B | `watchtower` | Celeron 1007U · 8GB DDR3-1600 · 1TB Crucial MX500 | Always-on DNS + monitoring — never runs workloads |
| Dell Precision 5560 | `studio` | i9-11950H · 32GB DDR4 · 512GB NVMe | Personal DAW — Reaper + M-Audio Air 192\|14 |

## Network

TP-Link Omada ecosystem — fully managed, SNMP-monitored. A 5-VLAN segmented redesign is underway (hardware swap and pre-cutover prep in progress) — design in `docs/network-rebuild-plan.md`, cutover procedure in `docs/network-migration-runbook.md`, live status in Plane.

| Device | Role |
|---|---|
| ER605 v2 | Multi-WAN VPN router · MAC-bound DHCP |
| OC200 | Omada network controller |
| SG2218P | Managed PoE+ switch — installed, OC200 config in progress |
| 2× EAP245 | Access points — Foyer + Yarn Studio |

> TL-SG1210P (old unmanaged switch) is decommissioned, in the spare-parts pile.

**WAN:** T-Mobile Home Internet (Rely) — primary. AT&T Internet Air (CGW450) is installed and running as WAN2 on a separate cellular network; final ER605 tuning and SNMP monitoring are deferred until after the VLAN cutover.

DNS chain: **AdGuard Home → Unbound → root** — recursive, no upstream forwarder dependency.
Public DNS: **Cloudflare** — authoritative for `littlewolfacres.com`.
Local domain: `littlewolfacres.com` — all hosts resolve as `hostname.littlewolfacres.com`.

## Stack

- **Kubernetes** — k3s (single-node, expandable)
- **GitOps** — ArgoCD v3.3.0 — all k3s workloads managed declaratively from this repo
- **TLS** — cert-manager v1.20.2 — automatic Let's Encrypt certificates via Cloudflare DNS-01
- **Ingress** — Traefik (k3s default) — terminates TLS, routes to cluster services
- **IaC** — Terraform Cloud (multi-workspace: monolith, watchtower)
- **Automation** — GitHub Actions + Ansible (modular role structure)
- **Secrets** — Ansible Vault · consolidated at `ansible/vars/vault.yml`
- **Variables** — Single source of truth at `ansible/vars/main.yml`
- **Monitoring** — Prometheus · Grafana · Alertmanager · Loki · Promtail · Netdata · node_exporter · blackbox_exporter · snmp_exporter · adguard_exporter · tmobile_exporter (custom) · reolink_exporter (custom)
- **OS** — Ubuntu Server 24.04 LTS (monolith + watchtower) · macOS Sequoia (apex)

## CI/CD

GitHub Actions pipelines on self-hosted runners (monolith, watchtower). All changes go through **branch → PR → merge**. Direct pushes to `master` are disabled. Claude handles the full git workflow via **Scribe**.

Most-used pipelines below — full list with exact triggers in `docs/architecture.md`.

| Workflow | Trigger | What it does |
|---|---|---|
| `deploy-watchtower.yml` | Push to master (`services/watchtower/**`) | DNS, monitoring, exporters, Loki/Promtail |
| `deploy-monolith.yml` | Push to master | Firewall, monitoring agents |
| `deploy-synapse.yml` | Push to master | Synapse MCP server |
| `deploy-fileserver.yml` | Manual | Samba config |
| `rotate-argocd-credentials.yml` | Manual + quarterly | PAT rotation |
| `import-minecraft-world.yml` | Manual | Stage world via Ansible + bounce pod |
| `slack-minecraft-import.yml` | Zombatron Importer bot | Clear import marker + bounce pod |
| `bootstrap-argocd.yml` | Manual (once) | cert-manager + ArgoCD install |
| `provision-k3s.yml` | Manual | k3s cluster init |

> Apex services (Scribe, Zombatron Importer) deploy manually from apex — no inbound SSH.

## Services

| Service | Host | URL / Endpoint | Status |
|---|---|---|---|
| ArgoCD | monolith | https://argocd.littlewolfacres.com | ✅ Online |
| Navidrome | monolith | https://navidrome.littlewolfacres.com | ✅ Online |
| Minecraft Bedrock | monolith | `zombatron.littlewolfacres.com:30132` (UDP) | ✅ Online |
| Samba | monolith | — | ✅ Online |
| Obelisk (Win11 VM) | monolith | `192.168.0.20:33389` (RDP) | ✅ Running |
| Plane | monolith | https://plane.littlewolfacres.com | ✅ Online |
| AdGuard Home + Unbound | watchtower | http://watchtower:3000 | ✅ Online |
| Prometheus | watchtower | http://watchtower:9090 | ✅ Online |
| Grafana | watchtower | http://grafana.littlewolfacres.com:3001 | ✅ Online |
| Alertmanager | watchtower | http://watchtower:9093 | ✅ Online |
| Loki | watchtower | http://watchtower:3100 | ✅ Online |
| Promtail | watchtower | http://watchtower:9080 | ✅ Online |
| Netdata | watchtower | http://watchtower:19999 | ✅ Online |
| Synapse MCP | monolith | monolith:30800 | ✅ Online |
| Scribe MCP | apex | apex:8765 | ✅ Online |
| Argus MCP | watchtower | watchtower:9800 | ✅ Online |
| Zombatron Importer | apex | Slack Socket Mode | ✅ Online |

## AI Tooling

Three MCP servers give Claude structured, safe access to the infrastructure:

**Synapse** (`monolith:30800`) — read-only k3s pod state, Prometheus metrics, Alertmanager alerts, and monolith filesystem.

**Scribe** (`apex:8765`) — git control plane. Branch, commit, push, open PRs against `speddling/lwa-homelab` and `speddling/lwa-web`. Branch-protected, path-allowlisted, merged-PR guard built in.

**Argus** (`watchtower:9800`) — read-only live Alertmanager and Prometheus configs, systemd state, journald logs, monitoring HTTP APIs.

See `docs/Claude MCPs.md` for full reference.

**B-4** — local LLM inference via Ollama on apex (Metal backend). Two future LLM environments (Lore, a Mac dev/inference setup; Data, a Linux dev/inference setup) are tracked in Plane, not here.

## Active Work

In-flight upgrades, roadmap, and operational debt are tracked in Plane (`LWA Infra` project), not in this repo.
