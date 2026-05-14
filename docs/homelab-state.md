# Little Wolf Acres — Homelab Current State
> Last updated: 2026-05-14 · Authored on apex · All IaC in `speddling/homelab` repo

---

## Network

### Hardware

| Device | IP | Role | Status |
|---|---|---|---|
| ER605 v2.0 | 192.168.0.1 | Gigabit Multi-WAN VPN Router | ✅ Online |
| OC200 | 192.168.0.7 | Omada Network Controller | ✅ Online |
| TL-SG1210P | — | Unmanaged PoE Switch | ✅ Online (no SNMP) |
| EAP245 — Foyer | 192.168.0.2 | Access Point | ✅ Online |
| EAP245 — Yarn Studio | 192.168.0.5 | Access Point | ✅ Online |

### Static DHCP Reservations (MAC-bound in ER605)

| IP | Hostname | Role |
|---|---|---|
| 192.168.0.4 | Big Brother | Reolink NVR / Camera Controller |
| 192.168.0.7 | OC200 | Omada Network Controller |
| 192.168.0.19 | apex | MacBook Air M4 — Primary Workstation |
| 192.168.0.20 | monolith | k3s Node — Primary Server |
| 192.168.0.21 | watchtower | DNS / Monitoring Stack |
| 192.168.0.109 | studio | Ubuntu Studio — DAW / KDE Workstation |

> All other devices use dynamic DHCP leases. Do not set static IPs at the OS level.

### DNS

- **Primary DNS:** Watchtower (`192.168.0.21`) — AdGuard Home → Unbound → Root
- **Fallback DNS:** `1.1.1.1`
- **DHCP DNS option:** ER605 pushes `192.168.0.21` to all LAN clients
- **Local domain:** `littlewolfacres.com` — all hosts resolve as `hostname.littlewolfacres.com`
- **Short hostname resolution:** AdGuard Home search domain set to `littlewolfacres.com` — allows bare hostnames (`monolith`, `watchtower`, `grafana`) to resolve without suffix
- **Local rewrites managed in AdGuard Home:**

| Domain | Resolves To |
|---|---|
| `watchtower.littlewolfacres.com` | 192.168.0.21 |
| `grafana.littlewolfacres.com` | 192.168.0.21 |
| `monolith.littlewolfacres.com` | 192.168.0.20 |
| `navidrome.littlewolfacres.com` | 192.168.0.20 |
| `studio.littlewolfacres.com` | 192.168.0.109 |
| `apex.littlewolfacres.com` | 192.168.0.19 |

### SNMP

- Enabled at site level in Omada Controller
- Community string: `littlewolfacres` (stored in Ansible vault)
- SNMPv3 user: `prometheus` (stored in Ansible vault)
- Monitored devices: ER605, EAP245 Foyer, EAP245 Yarn Studio
- **Note:** TL-SG1210P is unmanaged — no SNMP support. Upgrade to JetStream switch planned.

---

## Watchtower

### Hardware

| Spec     | Detail                        |
| -------- | ----------------------------- |
| Machine  | Asus VM40B Mini-PC            |
| RAM      | 8GB                           |
| Storage  | 1TB SSD                       |
| OS       | Ubuntu Server 24.04 LTS       |
| Hostname | `watchtower`                  |
| IP       | 192.168.0.21 (DHCP MAC-bound) |

### Role

Always-on DNS resolver and full-stack monitoring node. Never runs workloads. Sees everything, never sleeps.

### Services

| Service | Role | Port | Status |
|---|---|---|---|
| Alertmanager | Alert routing → Slack #sentinel | 9093 | ✅ Running |
| Unbound | Recursive DNS resolver (upstream) | 5335 | ✅ Running |
| AdGuard Home | DNS frontend, ad/tracker filtering | 53, 3000 | ✅ Running |
| Prometheus | Metrics scraping + alert evaluation | 9090 | ✅ Running |
| node_exporter | Watchtower host metrics | 9100 | ✅ Running |
| blackbox_exporter | Endpoint / ICMP probing | 9115 | ✅ Running |
| snmp_exporter | Omada network gear metrics | 9116 | ✅ Running |
| adguard_exporter | AGH metrics → Prometheus | 9618 | ✅ Running |
| Netdata | Real-time host observability | 19999 | ✅ Running |
| Grafana | Dashboards (display only) | 3001 | ✅ Running |

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
| blackbox | localhost:9115 | ✅ Up |
| adguard | localhost:9618 | ✅ Up |
| monolith | monolith:9100 | ✅ Up |
| snmp-er605 | 192.168.0.1 | ✅ Up |
| snmp-eap-yarn-studio | 192.168.0.5 | ✅ Up |
| snmp-eap-foyer | 192.168.0.2 | ✅ Up |
| tmobile | localhost:9719 | ✅ Up |
| reolink_nvr | localhost:9720 | ✅ Up |

### Grafana Dashboards

| Dashboard | Grafana ID |
|---|---|
| Node Exporter Full | 1860 |
| AdGuard Home | 20799 |
| Blackbox Exporter | 7587 |
| SNMP Interface Stats | 11169 |
| k3s Cluster | 15661 (pending) |

### Alerting

Alerting is owned by **Prometheus + Alertmanager**. Grafana is display-only.

- **Pipeline:** Prometheus evaluates rules → fires to Alertmanager → routes to `#sentinel` in Slack
- **Contact point:** Sentinel → `#sentinel` in Little Wolf Acres Slack

| Alert | Condition | Scope |
|---|---|---|
| MonolithDown | Scrape fails > 1m | monolith |
| MonolithHighCPU | > 85% sustained 5m | monolith |
| MonolithHighMemory | > 85% sustained 5m | monolith |
| MonolithLowDisk | > 80% used on / | monolith |
| WatchtowerHighCPU | > 85% sustained 5m | watchtower |
| WatchtowerHighMemory | > 85% sustained 5m | watchtower |
| WatchtowerLowDisk | > 80% used | watchtower |
| WatchtowerNodeExporterDown | Scrape fails > 1m | watchtower |
| AdGuardHomeDown | Scrape fails > 1m | watchtower |
| DailySummary | Always firing — canary for pipeline health | all |

### UFW Rules

| Port  | Protocol | Service          | Allowed From  |
| ----- | -------- | ---------------- | ------------- |
| 22    | TCP      | SSH              | apex only |
| 53    | TCP+UDP  | AdGuard Home DNS | LAN           |
| 3000  | TCP      | AdGuard Home UI  | LAN           |
| 3001  | TCP      | Grafana          | LAN           |
| 9090  | TCP      | Prometheus       | LAN           |
| 9093  | TCP      | Alertmanager     | LAN           |
| 9116  | TCP      | snmp_exporter    | LAN           |
| 9618  | TCP      | adguard_exporter | LAN           |
| 19999 | TCP      | Netdata          | LAN           |

### IaC

| Layer | Tool | Location |
|---|---|---|
| State | Terraform Cloud (`littlewolfacres` org, `watchtower` workspace) | app.terraform.io |
| Config | Ansible | `services/watchtower/ansible/` |
| Pipeline | GitHub Actions | `.github/workflows/deploy-watchtower.yml` |
| Runner | Self-hosted, label: `watchtower` | Installed on Watchtower as systemd service |

### Pending

- **NUT (UPS monitoring)** — role is written and ready, waiting for CyberPower CP1500PFCLCD hardware

---

## Monolith

### Hardware

| Spec     | Detail                        |
| -------- | ----------------------------- |
| Machine  | AMD Tower (Fractal Design Define R4) |
| CPU      | AMD Ryzen 7 5700G             |
| RAM      | 32GB DDR4-3200 (2×16GB Corsair Vengeance LPX) |
| OS       | Ubuntu Server 24.04 LTS       |
| Hostname | `monolith`                    |
| IP       | 192.168.0.20 (DHCP MAC-bound) |
| Storage  | 512GB NVMe — `/` (150G LVM, unallocated headroom) |
|          | 512GB SSD — `/mnt/ssd-a` — k8s local-path provisioner |
|          | 256GB SSD — `/mnt/ssd-b` — isolated workspace / client jumpbox |
|          | 4TB HDD — `/mnt/hdd-c` — music library / fileserver / bulk storage |
|          | 2TB HDD — `/mnt/hdd-d` — mirror of music-library and Samba share from hdd-c |

### Role

Primary k3s worker node and household services platform. Hosts all Kubernetes workloads including Navidrome, Minecraft, and family fileshares. Named for its role as the single monolithic compute node — a deliberate single-node architecture expandable to a multi-node cluster if needed.

**Workspaces**
- [x] Synapse — MCP/AI tooling namespace. Claude's interface to the homelab and coursework. (see `docs/synapse.md`)
- [ ] Obelisk — client workspace on `/mnt/ssd-b` (reserved name, future)

### Services

| Service | Role | Status |
|---|---|---|
| k3s | Kubernetes (single-node cluster) | ✅ Running |
| Navidrome | Music streaming server | ✅ Running |
| Samba | File share (family backups, media) | ✅ Running |
| node_exporter | Host metrics → Prometheus on Watchtower | ✅ Running |
| Synapse | MCP server — AI tooling namespace | ✅ Running |

### SSH Access

| Host | Access | Notes |
|---|---|---|
| apex | ✅ Permanent | Primary control plane |
| studio | ✅ Permanent | Secondary access for lab-adjacent work |

### IaC

| Layer | Tool | Location |
|---|---|---|
| State | Terraform Cloud (`littlewolfacres` org, `monolith` workspace) | app.terraform.io |
| Config | Ansible | `services/monolith/ansible/` |
| Pipeline | GitHub Actions | `.github/workflows/` |
| Runner | Self-hosted, label: `monolith` | Installed on Monolith as systemd service |

### UFW Rules

| Port | Protocol | Service | Allowed From |
|---|---|---|---|
| 22 | TCP | SSH | apex, studio |
| 9100 | TCP | node_exporter | watchtower |
| 30800 | TCP | Synapse MCP server | apex only |
| 445 | TCP | Samba | LAN |
| 139 | TCP | Samba (NetBIOS) | LAN |

---

## Apex

| Spec     | Detail                                                                 |
| -------- | ---------------------------------------------------------------------- |
| Machine  | MacBook Air M4 (2025) 16GB                                             |
| Hostname | `apex`                                                                 |
| IP       | 192.168.0.19 (DHCP MAC-bound)                                          |
| Role     | Primary workstation — all authoring, config, remote ops originate here |

---

## Studio

| Spec     | Detail                                                       |
| -------- | ------------------------------------------------------------ |
| Machine  | Dell Precision                                               |
| Hostname | `studio`                                                     |
| IP       | 192.168.0.109 (DHCP MAC-bound)                               |
| Role     | Personal DAW — Reaper with M-Audio Air 192\|14. Secondary SSH access to monolith. |

---

## Git Workflow

All changes go through a branch → PR → merge to master flow.
Direct pushes to master are disabled via branch protection (Branches rule).

```bash
# Start new work
cd ~/homelab
git checkout -b feature/description-of-change

# Commit and push branch
git add .
git commit -m "feat: description of change"
git push -u origin feature/description-of-change

# Open PR via GitHub CLI
gh pr create --title "feat: description" --body "What and why"

# PR triggers validate job (Ansible syntax-check + Terraform validate)
# Merge PR to master triggers deploy job

# Trigger a workflow manually
gh workflow run deploy-watchtower.yml
```

### Branch naming conventions

| Prefix | Use |
|---|---|
| `feature/*` | New capabilities or services |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation only — does not trigger deploy |
| `chore/*` | Maintenance, dependency updates |

---

## Pending Work

| Item | Priority | Notes |
| ---- | -------- | ----- |
| Daily summary scheduled time | Medium | Currently always firing — should fire once daily at set time |
| Disk alerts for `/mnt/hdd-c` and `/mnt/hdd-d` | Medium | Add mount-specific disk rules to Prometheus |
| k3s dashboard in Grafana | Medium | Import dashboard ID 15661 |
| Vault Samba plaintext passwords | Medium | `bubbie` and `junia` in fileserver vars — low risk LAN-only but should be done |
| hdd-d mirror — Ansible rsync role + systemd timer | Medium | Nightly mirror of music-library and Samba share from hdd-c to hdd-d |
| Switch .local to littlewolfacres.com rewrites | Medium | Update AdGuard Home rewrites and all references in repo |
| ArgoCD — GitOps for k3s | Medium | Migrate from kubectl apply chains to GitOps |
| Synapse — Claude Desktop config on apex | Low | Add `http://monolith.littlewolfacres.com:30800/sse` to `claude_desktop_config.json` after first deploy |
| Loki — log aggregation | Low | Add to Watchtower stack |
| Obelisk — client workspace on `/mnt/ssd-b` | Low | Isolated client environment, reserved name |
| JetStream managed switch | Low | Replaces unmanaged TL-SG1210P, enables SNMP per-port stats |
| UPS — CyberPower CP1500PFCLCD | Low | NUT role ready, waiting on hardware budget |

---

## Post-Watchtower Cleanup
- Remove UFW from fileserver Ansible playbook — firewall policy managed at network layer via ER605
