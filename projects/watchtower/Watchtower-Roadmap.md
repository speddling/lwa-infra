# VM40B Homelab — Monitoring & DNS Stack Roadmap

> **Hardware:** Asus VM40B · 8GB RAM · 1TB SSD (repurposed)
> **Role:** Always-on DNS resolver + full-stack monitoring node
> **Dev machine:** MacBook Air M4 — all authoring, config, and remote ops from here
> **IaC:** Terraform + GitHub Actions (shared workflow with K8s lab)

---

## Stack Overview

| Service | Role | Port |
|---|---|---|
| Unbound | Recursive DNS resolver (upstream) | 5335 |
| AdGuard Home | DNS frontend, ad/tracker filtering | 53, 3000 |
| Prometheus | Metrics scraping + TSDB | 9090 |
| node_exporter | VM40B host metrics | 9100 |
| blackbox_exporter | Endpoint / ICMP probing | 9115 |
| snmp_exporter | Omada network gear metrics | 9116 |
| AdGuard exporter | AGH metrics → Prometheus | 9617 |
| Netdata | Real-time host observability | 19999 |
| Grafana | Dashboards + alerting | 3001 |

---

## Workflow Architecture

```
MacBook Air M4 (dev)
  └── VS Code / Obsidian / Terminal
        ├── Terraform (local state or remote backend)
        │     └── Provisions VM40B config, firewall rules
        └── Git push → GitHub
              └── GitHub Actions CI/CD
                    ├── Lint / validate Terraform + Ansible
                    └── SSH deploy → VM40B
                          ├── systemd units
                          ├── Prometheus config
                          └── AdGuard Home config
```

> **Deviation note:** Ansible is recommended here alongside Terraform.
> Terraform owns *infrastructure* (firewall rules, DNS records, future cloud resources).
> Ansible owns *configuration management* on the VM40B itself (packages, systemd units, config files).
> GitHub Actions orchestrates both. This mirrors real-world DevOps practice and maps directly to your BS/CS + AI coursework trajectory.

---

## Phase 0 — Mac Dev Environment Setup

> One-time setup on MacBook Air M4. Skip what you already have.

- [ ] Install Homebrew if not present
- [ ] `brew install terraform ansible git gh`
- [ ] `brew install --cask visual-studio-code`
- [ ] Configure SSH key pair — add public key to VM40B `authorized_keys`
- [ ] Install VS Code extensions: `HashiCorp Terraform`, `Ansible`, `Remote-SSH`
- [ ] Configure `~/.ssh/config` with VM40B host alias
- [ ] Create GitHub repo: `homelab-iac` (or add to existing K8s lab repo under `/vm40b`)
- [ ] Set GitHub Actions secrets: `VM40B_HOST`, `VM40B_USER`, `SSH_PRIVATE_KEY`

---

## Phase 1 — Hardware & OS Prep

> Hands-on — physical access to VM40B required.

- [ ] Physically install 1TB SSD into VM40B (2.5" SATA bay)
- [ ] Download Ubuntu Server 24.04 LTS — flash to USB (`dd` or Balena Etcher)
- [ ] Boot and install — minimal install, no snaps, LVM optional
- [ ] Set static IP via Omada controller DHCP reservation (MAC binding preferred over static `/etc/netplan`)
- [ ] Enable and harden SSH
  - [ ] `PasswordAuthentication no`
  - [ ] `PermitRootLogin no`
  - [ ] Copy public key from Mac
- [ ] Set hostname: `monitoring` or similar
- [ ] `sudo apt update && sudo apt upgrade -y`
- [ ] Install baseline packages: `curl wget git htop ufw`
- [ ] Configure UFW — allow SSH, DNS (53/udp+tcp), and monitoring ports from LAN only
- [ ] Enable `unattended-upgrades` for security patches
- [ ] Verify connectivity from MacBook Air via SSH alias

---

## Phase 2 — IaC Scaffold (Terraform + GitHub Actions)

> Authored on MacBook Air · executed via GitHub Actions

### Repo Structure

```
homelab-iac/
├── vm40b/
│   ├── main.tf               # Provider config, SSH provisioner
│   ├── variables.tf
│   ├── outputs.tf
│   └── ansible/
│       ├── inventory.ini
│       ├── playbooks/
│       │   ├── dns.yml
│       │   ├── monitoring.yml
│       │   └── exporters.yml
│       └── roles/
│           ├── unbound/
│           ├── adguard/
│           ├── prometheus/
│           ├── exporters/
│           ├── netdata/
│           └── grafana/
├── k8s-lab/                  # Existing or future K8s Terraform
└── .github/
    └── workflows/
        ├── vm40b-deploy.yml
        └── k8s-deploy.yml
```

### GitHub Actions Pipeline — `vm40b-deploy.yml`

```yaml
name: VM40B Deploy
on:
  push:
    paths:
      - 'vm40b/**'
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init & Apply
        working-directory: vm40b
        run: |
          terraform init
          terraform apply -auto-approve
        env:
          TF_VAR_vm40b_host: ${{ secrets.VM40B_HOST }}

      - name: Run Ansible Playbooks
        uses: dawidd6/action-ansible-playbook@v2
        with:
          playbook: vm40b/ansible/playbooks/dns.yml
          inventory: vm40b/ansible/inventory.ini
          key: ${{ secrets.SSH_PRIVATE_KEY }}
```

- [ ] Scaffold repo structure locally on MacBook Air
- [ ] Write `inventory.ini` with VM40B static IP
- [ ] Write stub `main.tf` with SSH null_resource provisioner
- [ ] Commit and push — verify GitHub Actions runner reaches VM40B (VPN/tunnel may be needed if not on LAN)
- [ ] Confirm Terraform state strategy: local (simple) vs Terraform Cloud (recommended for multi-machine lab)

> **Note on remote runners:** GitHub Actions hosted runners are off your LAN. Either use a self-hosted runner on the K8s lab node, or use a Tailscale / WireGuard tunnel to expose VM40B to the runner. Self-hosted runner on the existing K8s node is the cleaner choice — it keeps sensitive SSH keys off GitHub's infrastructure.

---

## Phase 3 — DNS Layer (Unbound + AdGuard Home)

> Ansible role: `unbound`, `adguard` · Deployed via GitHub Actions

### Unbound

- [ ] Install via apt: `sudo apt install unbound`
- [ ] Configure `/etc/unbound/unbound.conf.d/pi-hole.conf`
  - Listen on `127.0.0.1:5335`
  - Root hints enabled
  - DNSSEC validation on
  - Cache tuning (rrset-cache-size, msg-cache-size)
- [ ] Disable and mask `systemd-resolved` stub listener
- [ ] Verify: `dig @127.0.0.1 -p 5335 google.com`

### AdGuard Home

- [ ] Download and run AGH installer script
- [ ] Complete web setup wizard (port 3000 initially → move to 53 post-setup)
- [ ] Set upstream DNS → `127.0.0.1:5335` (Unbound)
- [ ] Configure bootstrap DNS
- [ ] Add blocklists (Hagezi, OISD, Steven Black recommended)
- [ ] Enable DNSSEC
- [ ] Configure local DNS rewrites for homelab hostnames (e.g. `grafana.local`, `k3s.local`)
- [ ] Lock down AGH web UI to LAN CIDR only

### Omada Integration

- [ ] In OC200 controller: set primary DNS to VM40B static IP
- [ ] Set secondary DNS to a fallback (e.g. `1.1.1.1`) in case VM40B is down
- [ ] Verify DNS resolution from a LAN client
- [ ] Verify ad blocking is functioning

---

## Phase 4 — Prometheus

> Ansible role: `prometheus` · Binary install (no Docker — keeps it simple on this hardware)

- [ ] Download Prometheus binary from GitHub releases (arm64 if needed — VM40B is x86_64)
- [ ] Create `prometheus` system user (no login shell)
- [ ] Install to `/usr/local/bin/prometheus`
- [ ] Create `/etc/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'vm40b'
    static_configs:
      - targets: ['localhost:9100']

  - job_name: 'blackbox'
    static_configs:
      - targets: ['localhost:9115']

  - job_name: 'adguard'
    static_configs:
      - targets: ['localhost:9617']

  - job_name: 'k3s-nodes'
    static_configs:
      - targets: ['<k3s-node-ip>:9100']

  - job_name: 'snmp-omada'
    static_configs:
      - targets: ['<omada-ip>']
    metrics_path: /snmp
    params:
      module: [if_mib]
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - target_label: __address__
        replacement: localhost:9116
```

- [ ] Create systemd unit `/etc/systemd/system/prometheus.service`
  - `--storage.tsdb.retention.time=30d`
  - `--storage.tsdb.retention.size=50GB`
  - `--storage.tsdb.path=/var/lib/prometheus`
- [ ] `systemctl enable --now prometheus`
- [ ] Verify UI at `http://vm40b-ip:9090`

---

## Phase 5 — Exporters

> Ansible role: `exporters`

### node_exporter (VM40B host metrics)

- [ ] Install binary, create system user
- [ ] Systemd unit — default collectors are sufficient to start
- [ ] Verify: `curl localhost:9100/metrics`

### node_exporter (K8s lab node)

- [ ] Add to existing K8s lab Ansible playbook or deploy via Terraform
- [ ] Add scrape target to `prometheus.yml`

### blackbox_exporter

- [ ] Install binary + systemd unit
- [ ] Configure modules: `http_2xx`, `icmp`, `tcp_connect`
- [ ] Add probe targets to `prometheus.yml`: router, APs, Navidrome, Grafana, GitHub
- [ ] Verify endpoint probing

### snmp_exporter (Omada gear)

- [ ] Install binary + systemd unit
- [ ] Enable SNMP on ER605 and EAP245s via Omada controller
- [ ] Use `generator.yml` to build MIB-specific config (TP-Link OIDs)
- [ ] Verify interface counters scraping

### AdGuard Home exporter

- [ ] Install `adguard_exporter` (GitHub: ebrianne/adguard-exporter)
- [ ] Configure AGH API credentials
- [ ] Systemd unit on VM40B
- [ ] Verify metrics endpoint

---

## Phase 6 — Netdata

> Ansible role: `netdata` · Real-time complement to Prometheus

- [ ] Install via official script: `bash <(curl -Ss https://my-netdata.io/kickstart.sh) --dont-start-it`
- [ ] Configure `/etc/netdata/netdata.conf`
  - Bind to LAN IP only
  - Disable cloud features if preferred (on-prem only)
- [ ] Enable Prometheus metrics endpoint on Netdata (`exporting.conf`)
  - Optionally scrape Netdata from Prometheus as an additional source
- [ ] `systemctl enable --now netdata`
- [ ] Verify dashboard at `http://vm40b-ip:19999`
- [ ] Add Netdata data source to Grafana (optional — Netdata has its own UI)

---

## Phase 7 — Grafana

> Ansible role: `grafana`

- [ ] Install via apt (Grafana OSS repo)
- [ ] Configure `/etc/grafana/grafana.ini`
  - Bind to LAN IP
  - Disable anonymous access
  - Change default admin password
- [ ] `systemctl enable --now grafana-server`
- [ ] Add Prometheus data source
- [ ] Import community dashboards

| Dashboard | Grafana ID |
|---|---|
| Node Exporter Full | 1860 |
| Blackbox Exporter | 7587 |
| AdGuard Home | 13330 |
| Kubernetes cluster | 15661 |
| SNMP Stats | 11169 |

- [ ] Build custom homelab overview dashboard
  - DNS query rate + block rate (AGH)
  - VM40B CPU / RAM / disk / network
  - K8s node health
  - Uptime probes (blackbox)
  - Omada AP client counts + throughput

---

## Phase 8 — Alerting

> Configured in Grafana (no Alertmanager needed at this scale)

- [ ] Define alert rules in Grafana
  - VM40B CPU > 80% sustained 5m
  - Disk > 85% used
  - DNS resolver down (blackbox probe)
  - K8s node unreachable
  - Any monitored endpoint down > 2m
- [ ] Configure notification channel
  - Recommended: Telegram bot (free, instant, no app required)
  - Alternatives: Slack webhook, email (SMTP), Ntfy (self-hosted)
- [ ] Test alert firing + recovery notifications

---

## Phase 9 — Ongoing Maintenance

- [ ] Verify `unattended-upgrades` is running: `systemctl status unattended-upgrades`
- [ ] Set up log rotation for Prometheus, Grafana, AGH under `/etc/logrotate.d/`
- [ ] Schedule monthly Prometheus storage size check
- [ ] Keep Ansible roles version-pinned — bump intentionally, not automatically
- [ ] Back up configs to GitHub repo on change (Ansible handles this via idempotent playbooks)
- [ ] Document any manual config deviations in this note

---

## Reference

### Useful Commands (from MacBook Air)

```bash
# SSH to VM40B
ssh monitoring

# Check all monitoring services
ssh monitoring "systemctl status prometheus grafana-server netdata adguardhome unbound"

# Tail Prometheus logs
ssh monitoring "journalctl -fu prometheus"

# Run Ansible playbook manually
ansible-playbook -i vm40b/ansible/inventory.ini vm40b/ansible/playbooks/monitoring.yml

# Terraform plan
cd vm40b && terraform plan
```

### Port Reference (UFW rules)

| Port | Protocol | Service | Source |
|---|---|---|---|
| 22 | TCP | SSH | Mac IP only |
| 53 | TCP+UDP | AdGuard Home DNS | LAN |
| 3000 | TCP | AdGuard Home UI | LAN |
| 3001 | TCP | Grafana | LAN |
| 9090 | TCP | Prometheus | LAN |
| 19999 | TCP | Netdata | LAN |
| 9100 | TCP | node_exporter | VM40B only |
| 9115 | TCP | blackbox_exporter | VM40B only |
| 9116 | TCP | snmp_exporter | VM40B only |
| 9617 | TCP | AGH exporter | VM40B only |

### Related Notes

- [[K8s Lab — Terraform Setup]]
- [[Omada Network Config]]
- [[Navidrome — Music Server]]
- [[GitHub Actions — Homelab Pipelines]]
- [[MacBook Air M4 — Dev Environment]]

---

A few decisions worth calling out explicitly:

**Ansible added to the stack** — Terraform alone is awkward for ongoing config management of a single Linux box. Terraform handles infrastructure declarations; Ansible handles what's actually installed and configured on the machine. GitHub Actions drives both. This is the standard real-world pattern and directly relevant to DevOps interviews.

**Self-hosted GitHub Actions runner** — hosted runners are off your LAN and can't SSH into the VM40B without punching a hole in your network. Running a self-hosted runner on your existing K8s lab node solves this cleanly. It also means your runner has direct access to both the VM40B and the K8s cluster from the same pipeline.

**No Docker on the VM40B** — everything is installed as native binaries with systemd units. Docker adds overhead and complexity that isn't justified on 8GB of RAM when all these services run fine as binaries. Keeps it debuggable too.

**Grafana alerting instead of Alertmanager** — at your scale, Alertmanager is overkill. Grafana's built-in alerting covers everything you need with less operational surface area.

The `[[wikilinks]]` at the bottom are Obsidian-native — drop it straight into your vault and they'll be live links once you create the related notes.



*Last updated: {{date}}*
*Status: 🟡 In Progress*
