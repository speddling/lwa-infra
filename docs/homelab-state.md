# LWA Infra -- Current State
> Last updated: 2026-06-22

---

## Network

### Hardware

| Device | IP | Role | Status |
|---|---|---|---|
| T-Mobile FAST 5688W | -- | 5G WAN1 | Online |
| AT&T CGW450 | -- | 5G WAN2 | Online |
| ER605 v2.0 | 192.168.0.1 | Multi-WAN VPN Router | Online |
| OC200 | 192.168.0.7 | Network Controller | Online |
| SG2218P | -- | Managed PoE+ Switch | Online |
| CyberPower CP1000PFCLCD | -- | UPS | Online |
| EAP245 | 192.168.0.2 | Access Point | Online |
| EAP245 | 192.168.0.5 | Access Point | Online |

### Static DHCP Reservations (MAC-bound in ER605)

| IP | Hostname | Role |
|---|---|---|
| 192.168.0.4 | Big Brother | NVR |
| 192.168.0.7 | OC200 | Network Controller |
| 192.168.0.19 | apex | Primary Workstation |
| 192.168.0.20 | monolith | k3s Node |
| 192.168.0.21 | watchtower | DNS / Monitoring |
| 192.168.0.109 | studio | DAW / KDE Workstation |

> All other devices use dynamic DHCP leases. Do not set static IPs at the OS level.

### DNS

- **Primary DNS:** Watchtower (`192.168.0.21`) -- AdGuard Home -> Unbound -> Root
- **Fallback DNS:** `1.1.1.1`
- **DHCP DNS option:** ER605 pushes `192.168.0.21` to all LAN clients
- **Local domain:** `littlewolfacres.com` -- all hosts resolve as `hostname.littlewolfacres.com`
- **Short hostname resolution:** AdGuard Home search domain set to `littlewolfacres.com`
- **Local rewrites managed in AdGuard Home:**

| Domain | Resolves To |
|---|---|
| `watchtower.littlewolfacres.com` | 192.168.0.21 |
| `grafana.littlewolfacres.com` | 192.168.0.21 |
| `monolith.littlewolfacres.com` | 192.168.0.20 |
| `navidrome.littlewolfacres.com` | 192.168.0.20 |
| `argocd.littlewolfacres.com` | 192.168.0.20 |
| `plane.littlewolfacres.com` | 192.168.0.20 |
| `zombatron.littlewolfacres.com` | 192.168.0.20 |
| `studio.littlewolfacres.com` | 192.168.0.109 |
| `apex.littlewolfacres.com` | 192.168.0.19 |

### SNMP

- Enabled at site level in Omada Controller
- Community string: `littlewolfacres` (stored in Ansible vault)
- SNMPv3 user: `prometheus` (stored in Ansible vault)
- Monitored devices: ER605, 2x EAP245

---

## Watchtower

### Hardware

| Spec | Detail |
|---|---|
| Machine | Asus VM40B Mini-PC |
| CPU | Intel Celeron 1007U @ 1.50GHz -- 2 cores / 2 threads |
| RAM | 8 GB DDR3-1600 (2x4 GB Micron 8KTF51264HZ-1G6E1) |
| Storage | 1 TB SSD -- Crucial CT1000MX500SSD1 |
| OS | Ubuntu Server 24.04.4 LTS |
| Kernel | 6.8.0-111-generic |
| Hostname | `watchtower` |
| IP | 192.168.0.21 (DHCP MAC-bound) |

### Role

DNS resolution and infrastructure monitoring.

### Services

| Service | Role | Port | Status |
|---|---|---|---|
| Alertmanager | Alert routing | 9093 | ✅ Running |
| Loki | Log aggregation | 3100 | ✅ Running |
| Promtail | Log shipper | 9080 | ✅ Running |
| Unbound | Recursive DNS resolver | 5335 | ✅ Running |
| AdGuard Home | DNS with ad/tracker filtering | 53, 3000 | ✅ Running |
| Prometheus | Metrics and alerting | 9090 | ✅ Running |
| node_exporter | Host metrics | 9100 | ✅ Running |
| blackbox_exporter | Endpoint probing | 9115 | ✅ Running |
| snmp_exporter | SNMP metrics | 9116 | ✅ Running |
| adguard_exporter | AdGuard metrics | 9618 | ✅ Running |
| Netdata | Real-time monitoring | 19999 | ✅ Running |
| Grafana | Dashboards | 3001 | ✅ Running |

> **AdGuard Home auto-update is disabled** (`disable_updates: true` in `AdGuardHome.yaml`). Version upgrades go through the Ansible role.

### Web UIs

| Service | URL |
|---|---|
| AdGuard Home | http://watchtower:3000 |
| Grafana | http://grafana.littlewolfacres.com:3001 |
| Prometheus | http://watchtower:9090 |
| Alertmanager | http://watchtower:9093 |
| Netdata | http://watchtower:19999 |

### Prometheus Targets

| Job | Target | Status |
|---|---|---|
| watchtower | localhost:9100 | ✅ Up |
| prometheus | localhost:9090 | ✅ Up |
| loki | localhost:3100 | ✅ Up |
| promtail | localhost:9080 | ✅ Up |
| blackbox | localhost:9115 | ✅ Up |
| adguard | localhost:9618 | ✅ Up |
| monolith | monolith:9100 | ✅ Up |
| snmp-er605 | 192.168.0.1 | ✅ Up |
| snmp-eap-yarn-studio | 192.168.0.5 | ✅ Up |
| snmp-eap-foyer | 192.168.0.2 | ✅ Up |
| tmobile | localhost:9719 | ✅ Up |
| reolink_nvr | localhost:9720 | ✅ Up |

### Grafana Dashboards

| Dashboard | UID | Source |
|---|---|---|
| Node Exporter Full | `rYdddlPWk` | Community ID 1860 |
| Blackbox Probes | `lwa-blackbox-probes` | Custom |
| k3s Cluster | `lwa-k3s-cluster` | Custom |
| SNMP Interfaces | `lwa-snmp-interfaces` | Custom |
| T-Mobile 5G Gateway | `lwa-tmobile-gateway` | Custom |
| Reolink NVR | `lwa-reolink-nvr` | Custom |

### Alerting

| Alert | Condition | Scope |
|---|---|---|
| MonolithDown | Scrape fails > 1m | monolith |
| MonolithHighCPU | > 85% sustained 5m | monolith |
| MonolithHighMemory | > 85% sustained 5m | monolith |
| MonolithLowDisk | > 80% used on / | monolith |
| MonolithLowDiskHddC | > 80% used on /mnt/hdd-c | monolith |
| MonolithLowDiskHddD | > 80% used on /mnt/hdd-d | monolith |
| WatchtowerHighCPU | > 85% sustained 5m | watchtower |
| WatchtowerHighMemory | > 85% sustained 5m | watchtower |
| WatchtowerLowDisk | > 80% used, 10m | watchtower |
| WatchtowerCriticalDisk | > 90% used, 5m | watchtower |
| WatchtowerPrometheusDown | Scrape fails > 2m | watchtower |
| WatchtowerPrometheusTSDB | TSDB blocks > 8 GB | watchtower |
| WatchtowerNodeExporterDown | Scrape fails > 1m | watchtower |
| AdGuardHomeDown | Scrape fails > 1m | watchtower |
| WANDown | ICMP probe to 1.1.1.1 fails > 3m | watchtower |
| TMobileExporterDown | Scrape fails > 2m | watchtower |
| TMobile4GSignalWeak | 4G RSRP < -110 dBm, 10m | watchtower |
| TMobile5GSignalWeak | 5G RSRP < -110 dBm, 10m | watchtower |
| DeadManSwitch | Always firing -- watchdog confirmation | all |

### UFW Rules

| Port | Protocol | Service | Allowed From |
|---|---|---|---|
| 22 | TCP | SSH | apex only |
| 53 | TCP+UDP | AdGuard Home DNS | LAN |
| 3000 | TCP | AdGuard Home UI | LAN |
| 3001 | TCP | Grafana | LAN |
| 9090 | TCP | Prometheus | LAN |
| 9093 | TCP | Alertmanager | LAN |
| 9116 | TCP | snmp_exporter | LAN |
| 9618 | TCP | adguard_exporter | LAN |
| 19999 | TCP | Netdata | LAN |

### IaC

| Layer | Tool | Location |
|---|---|---|
| State | Terraform Cloud (`littlewolfacres` org, `watchtower` workspace) | app.terraform.io |
| Config | Ansible | `services/watchtower/ansible/` |
| Pipeline | GitHub Actions | `.github/workflows/deploy-watchtower.yml` |
| Runner | Self-hosted, label: `watchtower` | Installed as systemd service |

---

## Monolith

### Hardware

| Spec | Detail |
|---|---|
| Machine | AMD Tower (Fractal Design Define R4) |
| CPU | AMD Ryzen 7 5700G -- 8 cores / 16 threads |
| GPU | AMD Radeon Vega (integrated, Cezanne) |
| RAM | 64 GB DDR4-3200 |
| OS | Ubuntu Server 24.04.4 LTS |
| Kernel | 6.8.0-111-generic |
| Hostname | `monolith` |
| IP | 192.168.0.20 (DHCP MAC-bound) |
| Storage | 512 GB NVMe -- Samsung PM9A1 -- `/` (150G LVM) |
| | 500 GB SSD -- Crucial CT500MX500SSD1 -- `/mnt/ssd-a` -- k8s local-path provisioner |
| | 256 GB SSD -- Crucial CT256M55 -- `/mnt/ssd-b` -- isolated workspace / client jumpbox |
| | 3.6 TB HDD -- Seagate ST4000DM004 -- `/mnt/hdd-c` -- music library / fileserver / bulk storage |
| | 1.8 TB HDD -- Hitachi HUA72202 -- `/mnt/hdd-d` -- mirror of hdd-c |

### Storage

All mounts are UUID-based in `/etc/fstab` to survive drive reordering on reboot.

```bash
UUID=2903b345-9ec9-4524-9a59-c065f1a7c67c  /mnt/ssd-a  ext4  defaults  0  2  # 500GB SSD - k8s local-path provisioner
UUID=6ec61651-6596-4f29-82e5-ca6c43b6f552  /mnt/ssd-b  ext4  defaults  0  2  # 256GB SSD - isolated workspace / client jumpbox
UUID=5d036336-cc84-48ba-9f36-d403d4c75145  /mnt/hdd-c  ext4  defaults  0  2  # 3.6TB HDD - music library / fileserver / bulk storage
UUID=725e0389-8e5b-431f-bdb4-1c59ab79ddf6  /mnt/hdd-d  ext4  defaults  0  2  # 1.8TB HDD - mirror of hdd-c
```

### Role

k3s single-node cluster host. Runs all household and client services.

### Workspaces

| Name | Status | Description |
|---|---|---|
| Synapse | ✅ Active | MCP/AI tooling namespace |
| Obelisk | ✅ Active | Windows 11 VM on `/mnt/ssd-b` -- QEMU/KVM. RDP: `192.168.0.20:33389` |

### Services

| Service | Role | Status |
|---|---|---|
| k3s | Kubernetes single-node cluster | ✅ Running |
| Navidrome | Music streaming -- `navidrome.littlewolfacres.com` | ✅ Running |
| Minecraft Bedrock | Family game server -- `zombatron.littlewolfacres.com:30132` | ✅ Running |
| Samba | File shares (vault, studio-archive, music-library) | ✅ Running |
| node_exporter | Host metrics | ✅ Running |
| Synapse | MCP server | ✅ Running |
| hdd-d mirror | Nightly rsync hdd-c -> hdd-d via systemd timer at 02:00 | ✅ Running |
| Obelisk | QEMU/KVM Win11 VM -- RDP `192.168.0.20:33389` | ✅ Running |

### Samba Shares

| Share | Path | User |
|---|---|---|
| `vault` | `/mnt/ssd-b/vault` | `vault` |
| `studio-archive` | `/mnt/hdd-c/studio-archive` | `james` |
| `music-library` | `/mnt/hdd-c/music-library` | `james` |

### IaC

| Layer | Tool | Location |
|---|---|---|
| State | Terraform Cloud (`littlewolfacres` org, `monolith` workspace) | app.terraform.io |
| Config | Ansible | `services/monolith/ansible/` |
| Pipeline | GitHub Actions | `.github/workflows/deploy-monolith.yml` |
| Runner | Self-hosted, label: `monolith` | Installed as systemd service |

### UFW Rules

| Port | Protocol | Service | Allowed From |
|---|---|---|---|
| 22 | TCP | SSH | apex, studio |
| 80 | TCP | Traefik HTTP | LAN |
| 443 | TCP | Traefik HTTPS | LAN |
| 139 | TCP | Samba (NetBIOS) | LAN |
| 445 | TCP | Samba | LAN |
| 9100 | TCP | node_exporter | watchtower |
| 30132 | UDP | Minecraft Bedrock (NodePort) | LAN |
| 30800 | TCP | Synapse MCP server | apex only |
| 30880 | TCP | ArgoCD NodePort fallback | LAN |
| 30885 | TCP | ArgoCD app-controller metrics | watchtower |
| 30883 | TCP | ArgoCD server metrics | watchtower |
| 30900 | TCP | kube-state-metrics | watchtower |
| 33389 | TCP | Obelisk RDP (NodePort) | LAN |
| 39182 | TCP | Obelisk windows_exporter | watchtower |

---

## ArgoCD

GitOps controller for k3s. Watches `speddling/lwa-infra` on `master` and reconciles all k8s workloads.

### Access

| Method | URL |
|---|---|
| Primary (HTTPS) | https://argocd.littlewolfacres.com |
| Fallback (NodePort) | http://monolith.littlewolfacres.com:30880 |

### Services (NodePort)

| Port | Service | Purpose |
|---|---|---|
| 30880 | argocd-server | UI/API fallback |
| 30885 | argocd-application-controller | Prometheus metrics |
| 30883 | argocd-server metrics | Prometheus metrics |

### Applications Under Management

| App | Source Path | Namespace |
|---|---|---|
| navidrome | `services/navidrome/kubernetes/` | navidrome |
| minecraft | `services/minecraft/kubernetes/` | minecraft |
| synapse | `services/synapse/kubernetes/` | synapse |
| kube-state-metrics | `kubernetes/manifests/` | kube-system |
| cert-manager | `kubernetes/cluster/cert-manager/` | cert-manager |

### Prometheus Targets

| Job | Target |
|---|---|
| argocd-app-controller | monolith.littlewolfacres.com:30885 |
| argocd-server | monolith.littlewolfacres.com:30883 |

### Alert Rules

| Alert | Condition | Severity |
|---|---|---|
| ArgoCDAppOutOfSync | App OutOfSync > 5m | warning |
| ArgoCDAppDegraded | App health Degraded > 5m | critical |
| ArgoCDAppMissing | App health Missing > 2m | critical |
| ArgoCDControllerDown | Controller scrape fails > 1m | critical |
| ArgoCDServerDown | Server scrape fails > 1m | critical |

### Credential Management

| Aspect | Detail |
|---|---|
| Secret name | `homelab-repo` in `argocd` namespace |
| Vault variable | `vault_argocd_github_token` in `ansible/vars/vault.yml` |
| PAT type | Fine-grained, single-repo scope, Contents: Read, no expiration |
| Initial creation | `bootstrap-argocd.yml` (manual, runs once) |
| Ongoing rotation | `rotate-argocd-credentials.yml` (manual trigger + quarterly schedule) |

### IaC

| Layer | Location |
|---|---|
| Cluster config | `kubernetes/cluster/argocd/` |
| Bootstrap | `kubernetes/bootstrap/apps-of-apps.yaml` |
| App manifests | `kubernetes/apps/` |
| Bootstrap workflow | `.github/workflows/bootstrap-argocd.yml` |
| Rotation workflow | `.github/workflows/rotate-argocd-credentials.yml` |
| Rotation playbook | `services/monolith/ansible/playbooks/argocd-credentials.yml` |

---

## cert-manager

Automatic TLS via Cloudflare DNS-01. Issues and renews Let's Encrypt certificates, no inbound port required.

### ClusterIssuers

| Name | Use |
|---|---|
| `letsencrypt-prod` | All production ingress resources |
| `letsencrypt-staging` | Testing only |

### IaC

| Layer | Location |
|---|---|
| Cluster config | `kubernetes/cluster/cert-manager/` |
| Managed by | ArgoCD (`cert-manager` Application) |

---

## AI Nodes

### B-4 (apex)

| Detail | Value |
|---|---|
| Host | `apex` |
| Software | Ollama |
| Status | Active |

| Model | Size | Use |
|---|---|---|
| `gemma4` | ~12 GB | Claude Code integration |
| `llama3.2:3b` | ~2 GB | Direct chat |

---

## Apex

| Detail | Value |
|---|---|
| Hostname | `apex` |
| IP | 192.168.0.19 (DHCP MAC-bound) |

| Service | Port | Status |
|---|---|---|
| Scribe MCP | 8765 | ✅ Running |
| Zombatron Importer | Socket Mode | ✅ Running |

---

## Studio

| Detail | Value |
|---|---|
| Hostname | `studio` |
| IP | 192.168.0.109 (DHCP MAC-bound) |

| Mount | Source |
|---|---|
| `/music-library` | `//monolith/music-library` (CIFS) |
