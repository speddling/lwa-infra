# Little Wolf Acres — Homelab Current State
> Last updated: 2026-05-23 · Authored on apex · All IaC in `speddling/homelab` repo

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
| `argocd.littlewolfacres.com` | 192.168.0.20 |
| `zombatron.littlewolfacres.com` | 192.168.0.20 |
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
| CPU      | Intel Celeron 1007U @ 1.50GHz — 2 cores / 2 threads |
| RAM      | 8GB DDR3-1600 (2×4GB Micron 8KTF51264HZ-1G6E1) |
| Storage  | 1TB SSD — Crucial CT1000MX500SSD1 |
| OS       | Ubuntu Server 24.04.4 LTS       |
| Kernel   | 6.8.0-111-generic              |
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

> **AdGuard Home auto-update is disabled** (`disable_updates: true` in `AdGuardHome.yaml`). Version upgrades go through the Ansible role — prevents unscheduled restarts that cause ~10s DNS outages across the LAN.

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
| Node Exporter Full | `rYdddlPWk` | Community ID 1860 — downloaded by Ansible |
| Blackbox Probes | `lwa-blackbox-probes` | Custom — `roles/grafana/files/blackbox-probes.json` |
| k3s Cluster | `lwa-k3s-cluster` | Custom — `roles/grafana/files/k3s-cluster.json` |
| SNMP Interfaces | `lwa-snmp-interfaces` | Custom — `roles/grafana/files/snmp-interfaces.json` |
| T-Mobile 5G Gateway | `lwa-tmobile-gateway` | Custom — `roles/grafana/files/tmobile-gateway.json` |
| Reolink NVR | `lwa-reolink-nvr` | Custom — `roles/grafana/files/reolink-nvr.json` |

All dashboards are provisioned from disk by Ansible. Do not import community dashboards via the Grafana UI — add them to the Ansible role instead. The monitoring playbook automatically purges any dashboard not in the managed UID set.

### Alerting

Alerting is owned by **Prometheus + Alertmanager**. Grafana is display-only.

- **Pipeline:** Prometheus evaluates rules → fires to Alertmanager → routes to `#sentinel` in Slack
- **Contact point:** Sentinel → `#sentinel` in Little Wolf Acres Slack
- **Daily summary:** Alertmanager child route with `repeat_interval: 24h` — always-firing canary that confirms pipeline health

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
| WatchtowerLowDisk | > 80% used | watchtower |
| WatchtowerPrometheusTSDB | TSDB blocks > 8GB (80% of 10GB retention limit) | watchtower |
| WatchtowerNodeExporterDown | Scrape fails > 1m | watchtower |
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
| CPU      | AMD Ryzen 7 5700G with Radeon Graphics — 8 cores / 16 threads |
| GPU      | AMD Radeon Vega (integrated, Cezanne) |
| RAM      | 32GB DDR4-3200 (2×16GB Corsair Vengeance LPX CMK32GX4M2E3200C16) |
| OS       | Ubuntu Server 24.04.4 LTS       |
| Kernel   | 6.8.0-111-generic              |
| Hostname | `monolith`                    |
| IP       | 192.168.0.20 (DHCP MAC-bound) |
| Storage  | 512GB NVMe — Samsung PM9A1 — `/` (150G LVM, unallocated headroom) |
|          | 500GB SSD — Crucial CT500MX500SSD1 — `/mnt/ssd-a` — k8s local-path provisioner |
|          | 256GB SSD — Crucial CT256M55 — `/mnt/ssd-b` — isolated workspace / client jumpbox |
|          | 3.6TB HDD — Seagate ST4000DM004 — `/mnt/hdd-c` — music library / fileserver / bulk storage |
|          | 1.8TB HDD — Hitachi HUA72202 — `/mnt/hdd-d` — mirror of hdd-c |

### Upgrade Roadmap

| Order | Item | Notes |
|---|---|---|
| 1 | RAM — 2×16GB DDR4-3200 | Bring to 64GB. Cheap now, immediate headroom for k3s and CPU inference |

> **Hardware freeze after RAM.** No GPU, no PSU replacement, no case fans. Monolith is stable and sufficient for its current role. AI workloads are handled by B-4 on apex and eventually Lore.

### Role

Primary k3s worker node and household services platform. Hosts all Kubernetes workloads including Navidrome, Minecraft, and family fileshares. Named for its role as the single monolithic compute node — a deliberate single-node architecture expandable to a multi-node cluster if needed.

### Workspaces

| Name | Status | Description |
|---|---|---|
| Synapse | ✅ Active | MCP/AI tooling namespace. Claude's interface to the homelab. See `docs/Claude MCPs.md` |
| Obelisk | Reserved | Client workspace on `/mnt/ssd-b` — isolated environment, future build |

### Services

| Service | Role | Status |
|---|---|---|
| k3s | Kubernetes (single-node cluster) | ✅ Running |
| Navidrome | Music streaming — `navidrome.littlewolfacres.com` | ✅ Running |
| Minecraft Bedrock | Family game server — `zombatron.littlewolfacres.com:30132` | ✅ Running |
| Samba | File shares (vault, studio-archive, music-library) — passwords vaulted | ✅ Running |
| node_exporter | Host metrics → Prometheus on Watchtower | ✅ Running |
| Synapse | MCP server — AI tooling namespace | ✅ Running |
| hdd-d mirror | Nightly rsync from hdd-c → hdd-d via systemd timer at 02:00 | ✅ Running |

### Samba Shares

| Share | Path | User | Access |
|---|---|---|---|
| `vault` | `/mnt/ssd-b/vault` | `vault` | Family backup share |
| `studio-archive` | `/mnt/lab-backups/studio-archive` | `james` | DAW project storage |
| `music-library` | `/mnt/hdd-c/music-library` | `james` | Navidrome source — metadata editing from Studio |

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
| Pipeline | GitHub Actions | `.github/workflows/deploy-monolith.yml` |
| Runner | Self-hosted, label: `monolith` | Installed on Monolith as systemd service |

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

---

## ArgoCD

GitOps controller for k3s. Watches `speddling/homelab` on `master` and reconciles
all k8s workloads. Replaces the per-app `kubectl apply` GitHub Actions workflows.

### Access

| Method | URL | Notes |
|---|---|---|
| Primary (HTTPS) | https://argocd.littlewolfacres.com | Traefik ingress, Let's Encrypt cert |
| Fallback (NodePort) | http://monolith.littlewolfacres.com:30880 | Use when DNS is unstable |

### Services (NodePort)

| Port | Service | Purpose |
|---|---|---|
| 30880 | argocd-server | UI/API fallback (primary: Traefik ingress) |
| 30885 | argocd-application-controller | Prometheus metrics scrape |
| 30883 | argocd-server metrics | Prometheus metrics scrape |

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

ArgoCD authenticates to `speddling/homelab` via a GitHub fine-grained PAT.

| Aspect | Detail |
|---|---|
| Secret name | `homelab-repo` in `argocd` namespace |
| Vault variable | `vault_argocd_github_token` in `ansible/vars/vault.yml` |
| PAT type | Fine-grained, single-repo scope, Contents: Read, no expiration |
| Initial creation | `bootstrap-argocd.yml` (manual, runs once) |
| Ongoing rotation | `rotate-argocd-credentials.yml` (manual trigger + quarterly schedule) |
| Rotation runbook | See `docs/runbook.md` → ArgoCD → Rotating Repository Credentials |

> The secret is managed out-of-band — never via ArgoCD sync (circular dependency).
> The Ansible playbook writes a 0600 temp file, applies it, then shreds it.
> The token never appears in Ansible output or CI logs (`no_log: true`).

### IaC

| Layer | Location |
|---|---|
| Cluster config | `kubernetes/cluster/argocd/` |
| Bootstrap | `kubernetes/bootstrap/apps-of-apps.yaml` |
| App manifests | `kubernetes/apps/` |
| Bootstrap workflow | `.github/workflows/bootstrap-argocd.yml` (manual, runs once) |
| Rotation workflow | `.github/workflows/rotate-argocd-credentials.yml` |
| Rotation playbook | `services/monolith/ansible/playbooks/argocd-credentials.yml` |

---

## cert-manager

Automatic TLS certificate management for k3s. Issues and renews Let's Encrypt
certificates via Cloudflare DNS-01 challenge (no inbound port required).

### ClusterIssuers

| Name | Endpoint | Use |
|---|---|---|
| `letsencrypt-prod` | acme-v02.api.letsencrypt.org | All production ingress resources |
| `letsencrypt-staging` | acme-staging-v02.api.letsencrypt.org | Testing only — certs not browser-trusted |

### How to add TLS to an ingress

Add these two annotations to any Ingress manifest:
```yaml
traefik.ingress.kubernetes.io/router.entrypoints: websecure
traefik.ingress.kubernetes.io/router.tls: "true"
cert-manager.io/cluster-issuer: letsencrypt-prod
```
And add a `spec.tls` block referencing a `secretName`. cert-manager handles the rest.

### IaC

| Layer | Location |
|---|---|
| Cluster config | `kubernetes/cluster/cert-manager/` |
| Managed by | ArgoCD (`cert-manager` Application) |

---

## AI Nodes

### B-4 — apex (Active)

Local LLM workspace running Ollama on the MacBook Air M4. Entry-point for AI/ML development and MLOps workflow experimentation. All 16GB unified memory available for inference via Metal backend.

| Spec | Detail |
|---|---|
| Host | `apex` (MacBook Air M4, 16GB unified memory) |
| Install path | `~/B-4/` |
| Software | Ollama |
| API | `http://localhost:11434` |
| Status | Active |

### Models

| Model | Size | Command | Use |
|---|---|---|---|
| `gemma4` | ~12GB | `ollama launch claude` then select `gemma4` | Claude Code integration via Ollama — agentic coding workflows |
| `llama3.2:3b` | ~2GB | `ollama run llama3.2:3b` | Direct chat — fast, low footprint, good for quick queries and learning |

### Quick Reference

```bash
# Claude Code via Ollama (gemma4)
ollama launch claude
# select gemma4 from the model picker

# Direct chat (llama3.2:3b)
ollama run llama3.2:3b

# List all downloaded models
ollama list

# Pull a new model
ollama pull <model-name>

# Check Ollama API is running
curl http://localhost:11434
```

### Next Model (when ready to step up)
`llama3.1:8b` — fits comfortably in 16GB, noticeably more capable than 3b, good daily driver until Lore arrives.
```bash
ollama pull llama3.1:8b
ollama run llama3.1:8b
```

### Lore — Mac Mini (Planned)

Dedicated AI inference node. Headless in closet. Added when B-4 on apex is outgrown.

| Spec | Detail |
|---|---|
| Hardware | Mac Mini M4 Pro — 14-core CPU, 20-core GPU |
| Memory | 48GB unified memory |
| Network | 10 Gigabit Ethernet |
| Storage | 512GB SSD base — Thunderbolt 5 for expansion |
| Hostname | `lore` (reserved) |
| IP | TBD — DHCP MAC-bound on arrival |
| Software | Ollama headless — API served to LAN |
| Status | Planned — budget pending |

> Edu pricing applies via `.edu` email. 10GbE port future-proofs beyond current gigabit infrastructure.

### Data — Mac Studio (Aspirational)

Long-term AI platform. Not current plan — placeholder if the AI path continues and warrants the investment.

| Spec | Detail |
|---|---|
| Hardware | Mac Studio (maxed chipset and RAM) |
| Hostname | `data` (reserved) |
| Status | Aspirational — not on current roadmap |

---

## Apex

| Spec     | Detail                                                                 |
| -------- | ---------------------------------------------------------------------- |
| Machine  | MacBook Air M4 (2025) 16GB                                             |
| Hostname | `apex`                                                                 |
| IP       | 192.168.0.19 (DHCP MAC-bound)                                          |
| Role     | Primary workstation — all authoring, config, and remote ops originate here |

### Services

| Service | Role | Port | Status |
|---|---|---|---|
| Scribe | MCP server — Claude's git control plane | 8765 | ✅ Running |
| Zombatron Importer | Slack bot — Minecraft world import via `#zombatron` | Socket Mode (outbound) | ✅ Running |

### IaC

| Layer | Tool | Location |
|---|---|---|
| Config | Ansible | `services/apex/ansible/` |
| Deploy | Manual from apex | No inbound SSH — GitHub Actions cannot reach apex |

```bash
# Deploy Scribe
ansible-playbook --vault-password-file ~/homelab/.vault_pass \
  -i services/apex/ansible/inventory.ini \
  services/apex/ansible/playbooks/scribe.yml

# Deploy Zombatron Importer
ansible-playbook --vault-password-file ~/homelab/.vault_pass \
  -i services/apex/ansible/inventory.ini \
  services/apex/ansible/playbooks/deploy-zombatron-importer.yml
```

---

## Studio

| Spec | Detail |
| ---- | ------ |
| Machine | Dell Precision 5560 |
| CPU | Intel Core i9-11950H @ 2.60GHz — 8 cores / 16 threads |
| RAM | 32GB DDR4-3200 (2×16GB Samsung M471A2G43BB2-CWE) |
| Storage | 512GB NVMe — Samsung PM9A1 |
| GPU | Intel UHD Graphics (Tiger Lake-H, integrated) |
| OS | Ubuntu Studio 24.04 LTS (KDE Plasma 5.27.12 · Wayland) |
| Kernel | 6.8.0-111-lowlatency |
| Hostname | `studio` |
| IP | 192.168.0.109 (DHCP MAC-bound) |
| Role | Personal DAW — Reaper with M-Audio Air 192\|14. Secondary SSH access to monolith. |

### Mounts

| Mount | Source | Type | Notes |
|---|---|---|---|
| `/music-library` | `//monolith/music-library` | CIFS (Samba) | Manual setup — not managed by Ansible. See runbook. |

### Notes

- Studio is **not IaC-managed** — no Ansible runner, no GitHub Actions pipeline
- SSH access to Monolith only; Monolith cannot reach Studio
- `/music-library` automounts on first access via `x-systemd.automount` — persists across reboots via `/etc/fstab`

---

## Git Workflow

All changes go through a branch → PR → merge to main flow.
Direct pushes to main are disabled via branch protection.

Claude handles the full workflow via Scribe (see `docs/Claude MCPs.md`). Human action required only at PR review and merge.

```bash
# Start new work
git checkout -b feat/description-of-change

# Commit and push branch
git add <explicit paths>
git commit -m "feat: description of change"
git push -u origin feat/description-of-change

# Open PR via GitHub CLI
gh pr create --title "feat: description" --body "What and why"

# After merge — sync local repo back to main
git checkout main && git pull

# Trigger a workflow manually
gh workflow run deploy-watchtower.yml
```

### Branch naming conventions

| Prefix | Use |
|---|---|
| `feat/*` | New capabilities or services |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation only — does not trigger deploy |
| `chore/*` | Maintenance, dependency updates |

---

## Pending Work

### Hardware

| Item | Priority | Notes |
| ---- | -------- | ----- |
| RAM — 2×16GB DDR4-3200 | High | Bring Monolith to 64GB |
| Lore — Mac Mini M4 Pro 48GB / 10GbE | Medium | Dedicated AI inference node. Headless. Edu pricing. Budget pending |
| UPS — CyberPower CP1500PFCLCD | Low | NUT role ready, waiting on hardware budget |
| JetStream managed switch | Low | Replaces unmanaged TL-SG1210P, enables SNMP per-port stats |

### Software

| Item | Priority | Notes |
| ---- | -------- | ----- |
| ArgoCD + cert-manager | ✅ Done | GitOps live, HTTPS working |
| Navidrome ingress — upgrade to HTTPS | ✅ Done | websecure entrypoint + cert-manager annotation |
| Minecraft Bedrock server | ✅ Done | NodePort 30132, ArgoCD-managed, Slack import via Zombatron Importer |
| Minecraft — realm world import | Pending | Export from Realm → drop in `#zombatron` → cancel $8/month subscription |
| Minecraft — automated PVC backups | Low | k8s CronJob to tarball `/data` nightly to `/mnt/hdd-c` |
| Fileserver idempotency | Low | Fix `smbpasswd -a` in fileserver playbook — fails on re-run when user exists |
| Loki — log aggregation | Low | Add to Watchtower stack |
| Obelisk — client workspace on `/mnt/ssd-b` | Low | Isolated client environment, reserved name |
| Synapse — health endpoint | Low | Add /health route to FastMCP app for proper k8s probes |

---

## Post-Watchtower Cleanup
- Remove UFW install task from fileserver Ansible playbook — UFW is now managed by `deploy-monolith.yml` via the `ufw` role
- Fix `smbpasswd -a` idempotency in fileserver playbook (use `pdbedit -L` to check before adding)
