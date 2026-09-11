# LWA Infra
|> Last updated: 2026-08-04

## Hardware

| Node | Hostname | Specs | Role |
|---|---|---|---|
| MacBook Air M4 (2025) | `apex` | 16GB unified, 256GB | Primary workstation, control plane, all authoring originates here |
| AMD Ryzen 7 5700G | `monolith` | 8c/16t, 64GB DDR4-3200, 512GB NVMe + 500GB SSD + 256GB SSD + 3.6TB HDD + 1.8TB HDD | k3s single-node cluster, household services, Obelisk & Construct QEMU host |
| Asus VM40B | `watchtower` | Celeron 1007U, 8GB DDR3-1600, 1TB Crucial MX500 | DNS and monitoring, never runs workloads |
| Dell Precision 5560 | `studio` | i9-11950H, 32GB DDR4, 512GB NVMe | Personal DAW: Reaper + M-Audio Air 192\|14 |

## Network

TP-Link Omada ecosystem, fully managed, SNMP-monitored.

| Device | Role |
|---|---|
| ER605 v2 | Multi-WAN VPN router, MAC-bound DHCP |
| OC200 | Omada network controller |
| SG2218P | Managed PoE+ switch |
| 2x EAP245 | Wireless access points |
| EAP225-Outdoor | Outdoor wireless access point |

**WAN:** T-Mobile FAST 5688W and AT&T CGW450, equal-weight load balanced across two independent cellular carriers.

**VLANs:** Mgmt (10), Users (20), and Infra (30) are live and stable. IoT (40) is partial -- the NVR is on it, no WiFi SSID yet. Guest (50) and a blackhole/native VLAN (999) are not yet built. Full detail: `docs/homelab-state.md`.

DNS chain: **AdGuard Home -> Unbound -> root**, recursive, no upstream forwarder dependency.
Public DNS: **Cloudflare**, authoritative for `littlewolfacres.com`.
Local domain: `littlewolfacres.com`, all hosts resolve as `hostname.littlewolfacres.com`.

## Stack

- **Kubernetes** - k3s (single-node, expandable)
- **GitOps** - ArgoCD v3.3.0, manages all k3s workloads declaratively against this repo
- **Project Management** - Plane (self-hosted), tracks operational work items, client obligations, and incidents
- **TLS** - cert-manager v1.20.2, automatic Let's Encrypt certificates via Cloudflare DNS-01
- **Ingress** - Traefik (k3s default), terminates TLS and routes to cluster services
- **IaC** - Ansible (Terraform Cloud used for state isolation only — monolith, watchtower workspaces track Terraform state, no resource declarations)
- **Automation** - GitHub Actions + Ansible (modular role structure)
- **Secrets** - Ansible Vault
- **Monitoring** - Prometheus, Grafana, Alertmanager, Loki, Promtail, Netdata, node_exporter, blackbox_exporter, snmp_exporter, adguard_exporter, tmobile_exporter (custom), reolink_exporter (custom), NUT (planned)
- **OS** - Ubuntu Server 24.04 LTS (monolith + watchtower), macOS Sequoia (apex)

## CI/CD

GitHub Actions pipelines on self-hosted runners (monolith, watchtower). All changes go through **branch -> PR -> merge**. Direct pushes to `master` are disabled. Claude handles the full git workflow via **Scribe**.

ArgoCD is not a GitHub Actions workflow. It is a continuously-running GitOps controller that manages 11 services on the cluster, reconciling their live state against this repo on every push to master. It lives in the Stack section above.

Construct access is moving to LAN SSH through `monolith:2222`. After merging the access changes and verifying workstation SSH, the manual `retire-remote-access.yml` workflow removes Tailscale from Monolith/Construct and wmux from Construct. See `docs/construct-runbook.md`. `deploy-synapse.yml` deploys the Kubernetes MCP service; Scribe/Zombatron deployment code remains under `services/apex/`.

| Workflow | Trigger | What it does |
|---|---|---|
| `deploy-watchtower.yml` | Push to master | DNS, monitoring, exporters, Loki/Promtail |
| `deploy-monolith.yml` | Push to master | Firewall, monitoring agents |
| `deploy-synapse.yml` | Push to master | Build + push image, deploy to k3s |
| `deploy-fileserver.yml` | Manual | Samba config |
| `deploy-navidrome.yml` | Manual | Storage config + k8s manifests (also via ArgoCD) |
| `deploy-jellyfin.yml` | Manual | Storage config + k8s manifests (also via ArgoCD) |
| `deploy-kavita.yml` | Manual | Storage config + k8s manifests (also via ArgoCD) |
| `deploy-k3s-manifests.yml` | Push to master | kube-state-metrics (direct kubectl, not ArgoCD) |
| `deploy-mirror.yml` | Push to master | hdd-c -> hdd-d nightly rsync |
| `deploy-omada.yml` | PR + manual | Omada controller state export (read-only introspection) |
| `deploy-firecrawl.yml` | Push to services/firecrawl/** | Firecrawl web scraping API manifests |
| `deploy-reolink-exporter.yml` | Push to master | Reolink NVR exporter |
| `deploy-tmobile-exporter.yml` | Push to master | T-Mobile gateway exporter |
| `rotate-argocd-credentials.yml` | Manual + quarterly | PAT rotation |
| `import-minecraft-world.yml` | Manual | Stage world via Ansible and bounce pod |
| `slack-minecraft-import.yml` | Zombatron Importer bot | Clear import marker and bounce pod |
| `bootstrap-argocd.yml` | Manual (once) | cert-manager + ArgoCD install |
| `retire-remote-access.yml` | Manual after LAN SSH verification | Remove Tailscale from both hosts and wmux from Construct; preserve VM disk |
| `bootstrap-construct.yml` | Manual (once) | Debian 12 dev VM provisioning |
| `bootstrap-kubevirt.yml` | Manual (once) | KubeVirt + Obelisk VM bootstrap (archived) |
| `bootstrap-plane.yml` | Push + manual | Plane secrets + TLS certificate |
| `provision-k3s.yml` | Manual | k3s cluster init |

## Services

| Service | Host | Description |
|---|---|---|
| ArgoCD | monolith | GitOps controller, manages all k3s workloads |
| Navidrome | monolith | Music streaming |
| Jellyfin | monolith | Media streaming |
| Kavita | monolith | eBook/comic library |
| Minecraft Bedrock | monolith | Family Minecraft server |
| Samba | monolith | Network file shares |
| Obelisk (Win11 VM) | monolith | Client-facing Windows environment, RDP |
| Construct (Debian 12 VM) | monolith | Persistent development environment via SSH on monolith:2222 |
| Plane | monolith | Project management and incident tracking |
| Firecrawl | monolith | Web scraping and extraction API |
| AdGuard Home + Unbound | watchtower | Recursive DNS with ad and tracker blocking |
| Prometheus | watchtower | Metrics collection |
| Grafana | watchtower | Metrics dashboards |
| Alertmanager | watchtower | Alert routing and notification |
| Loki | watchtower | Log aggregation |
| Promtail | watchtower | Log shipping agent |
| Netdata | watchtower | Real-time system monitoring |
| NUT | watchtower | UPS monitoring (CyberPower CP1000PFCLCD) |
| Synapse MCP | monolith | Claude infrastructure read access |
| Scribe MCP | monolith (Construct VM) | Claude git control plane |
| Argus MCP | watchtower | Claude monitoring read access |
| Zombatron Importer | monolith (Construct VM) | Slack bot for Minecraft world imports |

## AI Tooling

Four MCP servers give Claude structured, safe access to the infrastructure:

**Synapse** (`monolith:30800`) - read-only k3s pod state, Prometheus metrics, Alertmanager alerts, and monolith filesystem.

**Scribe** (`construct:8765`, forwarded via `monolith:2222:8765`) - git control plane. Branch, commit, push, open PRs. Branch-protected, path-allowlisted, merged-PR guard built in.

**Argus** (`watchtower:9800`) - read-only live Alertmanager and Prometheus configs, systemd state, journald logs, and monitoring HTTP APIs.

**Atlas** (apex, local stdio subprocess) - Plane project management: work items, modules, cycles. Official upstream `makeplane/plane-mcp-server`. Unscoped, full account permissions, no branch-protection equivalent unlike the other three.

Plane itself (`plane.littlewolfacres.com`) is the accountability layer underneath all of this. Every client obligation, upgrade, and piece of operational debt is a tracked ticket there. This repo describes what is running; Plane is the record of what is owed.

**B-4** - local LLM inference via Ollama on apex (Metal backend).
