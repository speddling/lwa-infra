# LWA Infra
> Documentation audit: 2026-09-11. Runtime status is qualified in `docs/homelab-state.md`.

## Hardware

| Node | Hostname | Specs | Role |
|---|---|---|---|
| MacBook Air M4 (2025) | `apex` | 16GB unified, 256GB | Client workstation; former development host, all dev work now on Construct |
| AMD Ryzen 7 5700G | `monolith` | 8c/16t, 64GB DDR4-3200, 512GB NVMe + 500GB SSD + 256GB SSD + 3.6TB HDD + 1.8TB HDD | k3s single-node cluster, household services, Obelisk & Construct QEMU host |
| Asus VM40B | `watchtower` | Celeron 1007U, 8GB DDR3-1600, 1TB Crucial MX500 | DNS, monitoring and self-hosted CI runner; separate from k3s workloads |
| Dell Precision 5560 | `studio` | i9-11950H, 32GB DDR4, 512GB NVMe | Personal DAW: Reaper + M-Audio Air 192\|14 |

## Network

TP-Link Omada ecosystem, fully managed, SNMP-monitored.

| Device | Role |
|---|---|
| ER605 v2 | Multi-WAN VPN router, MAC-bound DHCP |
| OC200 | Omada network controller |
| SG2218P | Managed PoE+ switch |
| 2x EAP245 | Master Bedroom (192.168.10.100), Downstairs Hall (192.168.10.101) |
| EAP225-Outdoor | Installed in Foyer, owner reports 192.168.10.102; monitoring unverified |

**WAN:** T-Mobile FAST 5688W and AT&T CGW450, equal-weight load balanced across two independent cellular carriers.

**VLANs:** Mgmt (10), Users (20), and Infra (30) are live and stable. IoT (40) is partial -- the NVR is on it, no WiFi SSID yet. Guest (50) and a blackhole/native VLAN (999) are not yet built. Full detail: `docs/homelab-state.md`.

DNS chain: **AdGuard Home -> Unbound -> root**, recursive, no upstream forwarder dependency.
Public DNS: **Cloudflare**, authoritative for `littlewolfacres.com`.
Local domain: `littlewolfacres.com`, all hosts resolve as `hostname.littlewolfacres.com`.

## Stack

- **Kubernetes** - k3s (single-node, expandable)
- **GitOps** - ArgoCD v3.3.0 bootstrap pin; reconciles declared Applications, with some direct workflow applies still present
- **Project Management** - Plane (self-hosted), tracks operational work items, client obligations, and incidents
- **TLS** - cert-manager v1.20.2, automatic Let's Encrypt certificates via Cloudflare DNS-01
- **Ingress** - Traefik (k3s default), terminates TLS and routes to cluster services
- **IaC** - Ansible for host configuration; Terraform Cloud workspaces for each server. Monolith declares a k3s bootstrap `null_resource`; Watchtower declares only the backend
- **Automation** - GitHub Actions + Ansible (modular role structure)
- **Secrets** - Ansible Vault, GitHub Actions secrets, generated Kubernetes secrets and workstation-local credentials; see `docs/architecture.md` for ownership exceptions
- **Monitoring** - Prometheus, Grafana, Alertmanager, Loki, Promtail, Netdata, node_exporter, blackbox_exporter, snmp_exporter, adguard_exporter, tmobile_exporter (custom), reolink_exporter (custom), NUT (coordinated shutdown active; physical shutdown and reboot recovery verified)
- **OS** - Ubuntu Server 24.04 LTS (monolith + watchtower), macOS Sequoia (apex)

## CI/CD

Changes follow **branch → PR → human review and merge**. Scribe is one git mechanism;
using it is not a permanent requirement. No separate staging/promotion environment is
declared. Path-filtered push workflows can deploy immediately after merge to `master`.

| Runner host | Runner process user | Ansible SSH target user |
|---|---|---|
| Monolith | `gh-runner` | `speddling` in the main Monolith and retirement inventories |
| Watchtower | `speddling` | `speddling` |

The runner process owns its SSH key and known-hosts file. That identity is distinct
from the remote login user and from `become`/sudo. Synapse image builds use a
GitHub-hosted runner; deployment uses Monolith.

ArgoCD continuously reconciles the root `apps` Application and ten child Applications.
It is independent of Actions. Several workflows also apply the same Kubernetes
resources directly; controller/CRD installation and secret bootstrap have separate owners.

All development work has moved from Apex to Construct (owner confirmed 2026-09-11). Surviving Apex-hosted tooling still needs migration or retirement; see [the migration inventory](docs/construct-development-migration.md). Construct uses LAN SSH through `monolith:2222`. Retirement run 34625414651 successfully removed Tailscale from Monolith/Construct and wmux from Construct on 2026-09-11, with fresh SSH, DNS and k3s API checks passing. See `docs/construct-runbook.md`. `deploy-synapse.yml` deploys the Kubernetes MCP service; Scribe/Zombatron deployment code remains under `services/apex/`.

| Workflow | Trigger | What it does |
|---|---|---|
| `deploy-watchtower.yml` | Push to master | DNS, monitoring, exporters, Loki/Promtail |
| `deploy-monolith.yml` | Push to master | Firewall, monitoring agents |
| `deploy-synapse.yml` | Push to master | Build + push image, deploy to k3s |
| `deploy-fileserver.yml` | Manual | Samba config |
| `deploy-navidrome.yml` | Manual | Storage config + k8s manifests (also via ArgoCD) |
| `deploy-jellyfin.yml` | Manual | Storage config + k8s manifests (also via ArgoCD) |
| `deploy-kavita.yml` | Manual | Storage config + k8s manifests (also via ArgoCD) |
| `deploy-k3s-manifests.yml` | Push to master | kube-state-metrics direct apply; also managed by ArgoCD |
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
| `bootstrap-kubevirt.yml` | Manual (once) | Legacy, still dispatchable; references removed manifests — do not use |
| `bootstrap-plane.yml` | Push + manual | Plane secrets + TLS certificate |
| `provision-k3s.yml` | Manual | k3s cluster init |

## Services

| Service | Host | Description |
|---|---|---|
| ArgoCD | monolith | GitOps controller for declared Applications |
| Navidrome | monolith | Music streaming |
| Jellyfin | monolith | Media streaming |
| Kavita | monolith | eBook/comic library |
| Minecraft Bedrock | monolith | Family Minecraft server |
| Samba | monolith | Network file shares |
| Obelisk (Win11 VM) | monolith | Unused Windows VM; retain files for possible redeployment, runtime retirement unverified |
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
| NUT | Watchtower primary; Monolith secondary | [Coordinated shutdown active](docs/ups-shutdown-runbook.md); physical shutdown and automatic reboot recovery verified |
| Synapse MCP | monolith | Claude infrastructure read access |
| Scribe MCP | Runtime location awaiting confirmation | Git control plane; deployment code under `services/apex/` |
| Argus MCP | watchtower | Claude monitoring read access |
| Zombatron Importer | Runtime location awaiting confirmation | Slack world-import bot; deployment code under `services/apex/` |

## AI Tooling

The repository describes four MCP integrations with different access boundaries:

**Synapse** (`monolith:30800`) - read-only k3s pod state, Prometheus metrics, Alertmanager alerts, and monolith filesystem.

**Scribe** — git control plane with branch/path guards. Current endpoint and usage need confirmation; the repository only supplies Apex launchd deployment. Monolith port 2222 forwards SSH, not the MCP HTTP port.

**Argus** (`watchtower:9800`) - read-only live Alertmanager and Prometheus configs, systemd state, journald logs, and monitoring HTTP APIs.

**Atlas** (historically Apex-local; Construct client configuration pending) - Plane project management: work items, modules, cycles. Official upstream `makeplane/plane-mcp-server`. Unscoped, full account permissions, no branch-protection equivalent unlike the other three.

Plane itself (`plane.littlewolfacres.com`) is the accountability layer underneath all of this. Every client obligation, upgrade, and piece of operational debt is a tracked ticket there. This repo describes what is running; Plane is the record of what is owed.

**B-4** — historically Ollama on Apex (Metal backend). Retention and access from Construct require a decision; moving development does not move inference automatically.
