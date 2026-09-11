# LWA Infra -- Current State
> Last updated: 2026-08-04

---

## Network

### VLAN Status

| VLAN | Name | Subnet | Gateway | Status |
|---|---|---|---|---|
| 10 | Mgmt | 192.168.10.0/24 | .10.1 | ✅ Live |
| 20 | Users | 192.168.20.0/24 | .20.1 | ✅ Live |
| 30 | Infra | 192.168.30.0/24 | .30.1 | ✅ Live |
| 40 | IoT | 192.168.40.0/24 | .40.1 | 🟡 Partial -- NVR only, no WiFi SSID yet |
| 50 | Guest | 192.168.50.0/24 | .50.1 | ❌ Not built |
| 999 | Pit (blackhole) | none | none | ❌ Not built |

The original plan was a single 60-minute cutover across all 5 VLANs at once. Three attempts at that failed (see `cluster-runbook.md` postmortem references in Plane) and were replaced with the current approach: build and stabilize one VLAN at a time, by hand, verified against a live Omada export before trusting any IP in this doc. Mgmt/Users/Infra have held stable since; IoT/Guest/blackhole are the remaining scope.

**Do not trust static IPs in this file (or any doc) without cross-checking a live Omada DeviceList/OnlineClient export first.** Several IPs drifted silently during the manual rebuild and went undetected for days -- see the 2026-07-03 incident log in Plane.

### Hardware -- Confirmed Current Addresses (2026-07-05 Omada export)

| Device | IP | VLAN | Role |
|---|---|---|---|
| T-Mobile FAST 5688W | -- (WAN1, no LAN IP) | -- | 5G WAN1 |
| AT&T CGW450 | -- (WAN2, no LAN IP) | -- | 5G WAN2, direct to ER605 WAN2 port |
| ER605 v2.0 | 192.168.10.1 | Mgmt (10) | Multi-WAN VPN Router |
| SG2218P | 192.168.10.102 | Mgmt (10) | Managed PoE+ Switch |
| OC200 | 192.168.10.3 | Mgmt (10) | Network Controller |
| EAP245 -- Upstairs Hall | 192.168.10.100 | Mgmt (10) | Wireless AP |
| EAP245 -- Downstairs Hall | 192.168.10.101 | Mgmt (10) | Wireless AP |
| apex | 192.168.20.2 | Users (20) | Primary Workstation, WiFi |
| studio | 192.168.20.3 | Users (20) | DAW / KDE Workstation, WiFi |
| studio (wired dock) | 192.168.10.7 | Mgmt (10) | Out-of-band emergency access -- occasional/physical, not always-on |
| monolith | 192.168.30.10 | Infra (30) | k3s Node |
| watchtower | 192.168.30.11 | Infra (30) | DNS / Monitoring |
| Big Brother NVR | 192.168.40.10 | IoT (40) | NVR, wired to SG2218P port 7 |
| Brother HL-L3290CWD printer | 192.168.20.103 | Users (20), temporary | Will move to IoT once its WiFi SSID exists |
| CyberPower CP1000PFCLCD | -- | -- | UPS |

> Note the final Mgmt addressing (.10.100-.102 for switch/APs) differs from the original migration plan (.10.2, .10.4, .10.5) -- it settled differently during the manual rebuild. Functionally equivalent, just don't cross-reference the old plan's specific numbers.

### Remaining Network Migration Work

Design reference for the parts of the original migration plan not yet built. Kept here (not a separate runbook) since this is now the only place tracking current + pending network state together.

**IoT (40) -- remaining:**
| Planned IP | Device | Status |
|---|---|---|
| .40.11 | Reolink camera #1 (porch) | Not yet installed |
| .40.12 | Reolink camera #2 (driveway PTZ) | Not yet installed |
| .40.20 | Brother printer (once IoT SSID exists) | Currently on Users (20) temporarily |

**Guest (50) -- not started.** Pure DHCP, `.50-.200` pool (wider than other VLANs, fewer statics needed). No DNS allow to Infra -- Guest gets `1.1.1.1` / `9.9.9.9` via DHCP directly, bypassing AdGuard entirely (no internal hostname resolution, no AdGuard log noise -- this is intentional split-horizon, not a gap).

**SSID plan (not yet built):**
| SSID | VLAN | Notes |
|---|---|---|
| `LittleWolfAcres-IoT` | 40 | Printer + future IoT WiFi devices |
| `LittleWolfAcres-Guest` | 50 | Visitor devices, daughter's school Chromebook |

All three APs will broadcast all three SSIDs (`LittleWolfAcres` on Users already does). No Infra SSID -- Infra stays wired-only by design.

**Firewall rules still needed once Guest/IoT exist** (ER605 default: inter-VLAN deny, WAN-outbound allow, WAN-inbound deny):
- Guest → IoT printer only (TCP 631, 9100; UDP 5353), else WAN-only
- IoT → WAN only, no allow to any internal VLAN (cameras/NVR intra-VLAN, no rule needed)
- mDNS/Bonjour printer discovery across VLANs needs the ER605's mDNS Repeater (Settings → Services → mDNS) forwarding Users→IoT and Guest→IoT -- opening UDP 5353 alone does not make multicast discovery cross VLAN boundaries. If discovery fails after configuring the repeater, check the ACL isn't independently blocking the forwarded traffic before assuming the repeater config is wrong. Fallback: static IP printer entry per device, works regardless of mDNS Repeater state.

**Blackhole/Pit (999) -- not started.** Native VLAN on the ER605 trunk uplink; untagged frames dropped. Replaces VLAN 1 as the trunk's default once built.

**Final network security sweep (after all of the above):** both watchtower and monolith currently allow SSH from the entire LAN (`192.168.0.0/16`) as a deliberate temporary safety net during this rebuild. Once Guest/IoT/blackhole are all stable, remove that fallback from both hosts' `ufw` roles and confirm every device needing SSH has a narrow, permanent rule first (apex, studio WiFi, studio wired dock already do on monolith).

**Remote access (deferred, not started):** single entry point via WireGuard on the ER605, one inbound UDP port (51820), no per-service port forwards. Clients land in their own subnet with reach into Users/Infra/IoT. Subnet allocation, client keys, and policy all still TBD.

**Also deferred:** EAP225-Outdoor (balcony AP, needs outdoor-rated cable run + inline surge protector), coop/run Ethernet drop (pulled when power-to-coop project happens), VLAN-aware Linux bridge config on monolith (needed before any VM lands on a non-Infra VLAN).

### DNS

- **Primary DNS:** Watchtower (`192.168.30.11`) -- AdGuard Home -> Unbound -> Root
- **Fallback DNS:** `1.1.1.1` (added as a genuine emergency measure the night of the 2026-07-03 outage, not removed since -- harmless now that both Cloudflare public records and AdGuard agree, but only actually needed if watchtower itself is down)
- **DHCP DNS option:** ER605 pushes `192.168.30.11` to Mgmt/Users/Infra/IoT VLAN clients
- **Local domain:** `littlewolfacres.com` -- all hosts resolve as `hostname.littlewolfacres.com`
- **Local rewrites managed in AdGuard Home** (`services/watchtower/ansible/roles/adguard/templates/AdGuardHome.yaml.j2` -- never edit via the AdGuard UI directly, it gets overwritten on next deploy):

| Domain | Resolves To |
|---|---|
| `watchtower.littlewolfacres.com` | 192.168.30.11 |
| `grafana.littlewolfacres.com` | 192.168.30.11 |
| `monolith.littlewolfacres.com` | 192.168.30.10 |
| `navidrome.littlewolfacres.com` | 192.168.30.10 |
| `argocd.littlewolfacres.com` | 192.168.30.10 |
| `plane.littlewolfacres.com` | 192.168.30.10 |
| `firecrawl.littlewolfacres.com` | 192.168.30.10 |
| `zombatron.littlewolfacres.com` | 192.168.30.10 |
| `studio.littlewolfacres.com` | 192.168.20.3 |
| `apex.littlewolfacres.com` | 192.168.20.2 |

Some hostnames (`plane`, `apex` itself) also have public Cloudflare A records pointing directly at the LAN IP -- needed because apex doesn't reliably use AdGuard as its resolver (see Atlas section in `Claude MCPs.md` for why), and any long-running local process there needs the hostname to resolve at the OS level with no per-call override.

### SNMP

- Enabled at site level in Omada Controller (moved from a global-config location in older Omada UI versions -- now under **Site → Network Config → SNMP**)
- Version: v2c
- Community string: stored in Ansible vault as `vault_snmp_community` (rotated 2026-07-07 after Omada's complexity policy rejected the old value -- must contain letters, numbers, and symbols, 10-64 chars, no repeated characters back-to-back)
- SNMPv3 user: `prometheus` (stored in vault)
- Monitored devices: ER605, SG2218P, both EAP245s -- `snmp_exporter` fully in IaC now (`services/watchtower/ansible/roles/snmp_exporter/`), previously ran unmanaged on watchtower's disk with no role at all

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
| IP | 192.168.30.11 (Infra VLAN) |

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
| snmp_exporter | SNMP metrics | 9116 | ✅ Running -- now in IaC |
| adguard_exporter | AdGuard metrics | 9618 | ✅ Running |
| tmobile_exporter | T-Mobile gateway metrics | 9719 | ✅ Running |
| reolink_exporter | NVR metrics | 9720 | ✅ Running -- pointed at IoT `.40.10` (was pointed at a dead Mgmt-range IP for days before catching it) |
| Netdata | Real-time monitoring | 19999 | ✅ Running |
| Grafana | Dashboards | 3001 | ✅ Running |
| Scribe MCP | Claude git control plane (runs on apex, not watchtower -- see `Claude MCPs.md`) | -- | -- |

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
| snmp-er605 | 192.168.10.1 | ✅ Up |
| snmp-sg2218p | 192.168.10.102 | ✅ Up |
| snmp-eap-up | 192.168.10.100 | ✅ Up |
| snmp-eap-down | 192.168.10.101 | ✅ Up |
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
| Homelab Overview | `lwa-homelab-overview` | Custom -- single-page at-a-glance: WAN status/traffic (both links), server CPU/RAM/disk, live camera snapshot |

### UFW Rules

| Port | Protocol | Service | Allowed From |
|---|---|---|---|
| 22 | TCP | SSH | LAN-wide (`192.168.0.0/16`) -- **deliberate temporary safety net during the VLAN rebuild, not an oversight.** Remove at the final network security sweep (see Network section above) once Guest/IoT/blackhole are stable. |
| 53 | TCP+UDP | AdGuard Home DNS | LAN |
| 3000 | TCP | AdGuard Home UI | LAN |
| 3001 | TCP | Grafana | LAN |
| 9090 | TCP | Prometheus | LAN |
| 9093 | TCP | Alertmanager | LAN |
| 9116 | TCP | snmp_exporter | LAN |
| 9618 | TCP | adguard_exporter | LAN |
| 19999 | TCP | Netdata | LAN |
| 9800 | TCP | Argus MCP server | apex only |

### IaC

| Layer | Tool | Location |
|---|---|---|
| State | Terraform Cloud (`littlewolfacres` org, `watchtower` workspace) | app.terraform.io |
| Config | Ansible | `services/watchtower/ansible/` |
| Pipeline | GitHub Actions | `.github/workflows/deploy-watchtower.yml` |
| Runner | Self-hosted, label: `watchtower` | Installed as systemd service. Runs as `speddling` currently -- should be `gh-runner` for consistency with monolith, tracked in Plane. |

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
| IP | 192.168.30.10 (Infra VLAN) |
| Storage | 512 GB NVMe -- Samsung PM9A1 -- `/` (150G LVM) + `/vm/construct` (80G LVM) |
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
|| Obelisk | ⚠️ Deprecated (Windows 11 VM on `/mnt/ssd-b` -- QEMU/KVM. RDP: `192.168.30.10:33389`. Scheduled for decommission at end-of-month upgrades) |
| Construct | ✅ Active | Debian 12 dev VM on NVMe `/vm/construct` -- QEMU/KVM. SSH: `monolith:2222` (client alias `construct`) |

### Services

| Service | Role | Status |
|---|---|---|
| k3s | Kubernetes single-node cluster | ✅ Running |
| Firecrawl | Web scraping API -- `firecrawl.littlewolfacres.com` | ✅ Running (via ArgoCD) |
| Navidrome | Music streaming -- `navidrome.littlewolfacres.com` | ✅ Running |
| Minecraft Bedrock | Family game server -- `zombatron.littlewolfacres.com:30132` | ✅ Running |
| Samba | File shares (vault, studio-archive, music-library) | ✅ Running |
| node_exporter | Host metrics | ✅ Running |
| Synapse | MCP server | ✅ Running |
| hdd-d mirror | Nightly rsync hdd-c -> hdd-d via systemd timer at 02:00 | ✅ Running |
|| Obelisk | QEMU/KVM Win11 VM -- RDP `192.168.30.10:33389` | ⚠️ Deprecated (scheduled for decommission at end-of-month upgrades) |
| Construct | QEMU/KVM Debian 12 dev VM -- SSH `monolith:2222` | ✅ Running |
| Plane | Project management -- `plane.littlewolfacres.com` | ✅ Running (via ArgoCD) |

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
| Runner | Self-hosted, label: `monolith`, runs as `gh-runner` | Installed as systemd service. Registration was auto-deleted by GitHub after the 2026-07-03 outage (offline too long) and had to be manually re-registered; also found missing its required `monolith` custom label after re-registration, which silently blocked job dispatch even with the runner showing "online." Check both registration validity and labels (`gh api repos/speddling/lwa-infra/actions/runners`) if jobs sit queued despite the runner looking healthy. |

### UFW Rules

| Port | Protocol | Service | Allowed From |
|---|---|---|---|
| 22 | TCP | SSH | apex (192.168.20.2), studio WiFi (192.168.20.3), studio wired dock (192.168.10.7) -- **plus LAN-wide (192.168.0.0/16) temporarily, same deliberate safety net as watchtower.** Remove at the final network security sweep. |
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
| 2222 | TCP | Construct SSH (port forward) | Apex + Studio (WiFi); verify live rules after deploy |
| 33389 | TCP | Obelisk RDP (NodePort) | LAN |
| 39182 | TCP | Obelisk windows_exporter | watchtower |

**Do not add UFW rules manually on Monolith** -- all rules are managed by the `ufw` Ansible role in `services/monolith/ansible/roles/ufw/`. Add rules there and run the **Deploy Monolith Config** workflow.

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
| firecrawl | `services/firecrawl/kubernetes/` | firecrawl |
| minecraft | `services/minecraft/kubernetes/` | minecraft |
| synapse | `services/synapse/kubernetes/` | synapse |
| plane | Helm chart, `helm.plane.so` | plane |
| kube-state-metrics | `kubernetes/manifests/` | kube-system |
| cert-manager | `kubernetes/cluster/cert-manager/` | cert-manager |
| apps | `kubernetes/apps/` | -- (apps-of-apps) |
| argocd-cluster-config | `kubernetes/cluster/argocd/` | argocd |

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

### Known Gotcha -- `copyutil` Init Container Crash-Loop

`argocd-repo-server`'s `copyutil` init container (copies the ArgoCD binary into a shared `emptyDir` for the other containers) can get stuck crash-looping with a `file exists` error if it's interrupted mid-copy -- e.g. by a power outage. The `emptyDir` survives container restarts within the same pod, so a retry collides with its own leftover file from the interrupted first attempt. Fix: delete the pod (`kubectl delete pod -n argocd <repo-server-pod>`), the Deployment recreates it with a fresh empty volume. Hit this after the 2026-07-03 outage; repo-server sat at `0/1` ready for days undetected since `argocd-application-controller` itself still showed `Running 1/1`.

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

## Apex (Workstation)

| Detail | Value |
|---|---|
| Hostname | `apex` |
| IP | 192.168.20.2 (Users VLAN, WiFi) |

Apex has transitioned to a pure workstation role — no longer runs self-hosted services. Scribe MCP and Zombatron Importer have migrated to the **Construct VM** under `services/construct/ansible/roles/`.

| Service | Port | Status |
|---|---|---|
| None | -- | Pure workstation (DAW, AI development) |

---

## Construct (VM on Monolith)

| Detail | Value |
|---|---|
| Hostname | `construct` |
| Type | Debian 12 VM, QEMU/KVM on Monolith (NVMe `/vm/construct`) |
| SSH | `monolith:2222` (port-forward), client alias `construct` |
| Access transition | Tailscale and wmux retirement pending manual workflow; see `construct-runbook.md` |

| Service | Port | Status |
|---|---|---|
| Scribe MCP | 8765 | ✅ Running |
| Zombatron Importer | Socket Mode | ✅ Running |

Scribe MCP and Zombatron Importer migrated here from Apex when Apex became a pure workstation.

---

## Studio

| Detail | Value |
|---|---|
| Hostname | `studio` |
| IP (WiFi, primary) | 192.168.20.3 (Users VLAN) |
| IP (wired dock) | 192.168.10.7 (Mgmt VLAN) -- deliberately Mgmt, not Users: out-of-band emergency access to OC200/ER605/switch when the network itself is degraded, so it doesn't depend on Users VLAN being healthy. Occasional/physical use, not always-on. |

| Mount | Source |
|---|---|
| `/music-library` | `//monolith/music-library` (CIFS) |
