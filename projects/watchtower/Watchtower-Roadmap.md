# Watchtower — Monitoring & DNS Stack Roadmap

> **Hardware:** Asus VM40B · 8GB RAM · 1TB SSD (repurposed from Monolith)
> **Hostname:** `watchtower` · **Dev machine:** `apex` (MacBook Air M4)
> **Role:** Always-on DNS resolver + full-stack monitoring node
> **IaC:** Terraform (Terraform Cloud state) + Ansible + GitHub Actions
> **Alerts:** Slack → Little Wolf Acres workspace

---

## Stack Overview

| Service | Role | Port |
|---|---|---|
| Unbound | Recursive DNS resolver (upstream) | 5335 |
| AdGuard Home | DNS frontend, ad/tracker filtering | 53, 3000 |
| Prometheus | Metrics scraping + TSDB | 9090 |
| node_exporter | Watchtower host metrics | 9100 |
| blackbox_exporter | Endpoint / ICMP probing | 9115 |
| snmp_exporter | Omada network gear metrics | 9116 |
| AdGuard exporter | AGH metrics → Prometheus | 9617 |
| Netdata | Real-time host observability | 19999 |
| Grafana | Dashboards + alerting → Slack | 3001 |

---

## Background & Key Decisions

### Context

This project grew out of a conversation mapping the full homelab. The Asus VM40B was an idle mini-PC being used as a doorstop. Rather than buy new hardware, the plan repurposes it with a 1TB SSD migrated from Monolith (where Navidrome's audio library was moved to an 8TB HDD upgrade). The 8TB was chosen over 4TB deliberately — the lab is planned to grow into LLM/AI dev work where model weights, datasets, and training checkpoints will consume storage fast.

### Naming

- **monolith** — the AMD tower running k3s. Named for its role as the single heavy node.
- **watchtower** — the VM40B monitoring/DNS node. Named for its role: sees everything, never sleeps.
- **apex** — the MacBook Air M4. All authoring, config, and remote ops originate here.
- **Little Wolf Acres** — the family Slack workspace receiving Grafana alerts.

### Why `services/` not `projects/`

Projects implies temporary work with a completion state. These are permanent running infrastructure services. Navidrome and Watchtower are services. The rename also maps cleanly to how the industry talks about what runs in production.

### Why Ansible alongside Terraform

Terraform alone is awkward for ongoing config management of a bare Linux box — it's designed for infrastructure declaration, not package installs and service configuration. Ansible owns what's installed and running on Watchtower (packages, systemd units, config files). Terraform owns infrastructure facts (state, firewall declarations, future cloud resources). GitHub Actions orchestrates both. This is the standard real-world pattern and directly relevant to DevOps interview conversations.

### Why Terraform Cloud for state

The existing Monolith Terraform setup stores state locally on the runner, meaning a dead Monolith loses the state file. Terraform Cloud free tier hosts state remotely, survives any node failure, supports multiple workspaces (one per node), and lets GitHub Actions reach state without being tied to a specific runner machine. Two workspaces: `monolith` and `watchtower`.

### Why isolated runners per node

A self-hosted runner has network-level access to everything its host can reach. If one runner managed multiple nodes via SSH, a compromised pipeline job could pivot laterally across the lab. Watchtower's runner uses the `watchtower` label and only manages Watchtower. Monolith's runner uses the `monolith` label and only manages Monolith. Blast radius is contained by design. Watchtower is bootstrapped manually once via SSH from apex, then handed off to GitHub Actions permanently.

### Why no Docker on Watchtower

8GB RAM, always-on services, no orchestration layer. Everything runs as native binaries with systemd units — lighter, simpler to debug, no container runtime overhead. Consistent with Monolith using k3s with containerd rather than Docker.

### Why Grafana alerting not Alertmanager

At this scale Alertmanager adds operational surface area without meaningful benefit. Grafana's built-in alerting handles all required rules and routes directly to Slack.

### Where this conversation left off

PSU on the VM40B needs replacing before any hands-on work begins. Phase 0 (repo housekeeping + Terraform Cloud setup) can be done on apex immediately while waiting for hardware. The file server for family backups (daughter's iPad art, wife's crochet notes) is the next Monolith project after Watchtower is stable — noted in the repo README already.

--------------

## Repo Structure (Target State)

`projects/` is being renamed to `services/` — permanent infrastructure belongs there, not projects. Watchtower moves from `projects/watchtower/` to `services/watchtower/`.

```
homelab/
├── nodes/
│   ├── macbook/          ← apex (dev machine)
│   ├── amd-tower/        ← Monolith (k3s worker)
│   └── vm40b/            ← Watchtower (new)
├── kubernetes/           ← k3s cluster config, manifests, storage
├── terraform/
│   ├── monolith/         ← existing
│   ├── cluster/          ← existing
│   └── watchtower/       ← new
│       ├── main.tf
│       └── variables.tf
├── services/             ← renamed from projects/
│   ├── navidrome/        ← moved from projects/audio-server/
│   └── watchtower/       ← moved from projects/watchtower/
│       ├── ansible/
│       │   ├── inventory.ini
│       │   ├── playbooks/
│       │   │   ├── dns.yml
│       │   │   ├── monitoring.yml
│       │   │   └── exporters.yml
│       │   └── roles/
│       │       ├── unbound/
│       │       ├── adguard/
│       │       ├── prometheus/
│       │       ├── exporters/
│       │       ├── netdata/
│       │       └── grafana/
│       └── Watchtower-Roadmap.md
├── network/omada/
├── docs/
├── ansible/
│   └── monolith/
│       ├── inventory.ini
│       ├── playbooks/
│       │   ├── bootstrap.yml
│       │   └── node.yml
│       └── roles/
│           ├── common/       ← baseline packages, UFW, unattended-upgrades
│           ├── k3s/          ← replaces curl one-liner in Terraform
│           ├── node_exporter/← so Watchtower can scrape it
│           └── runner/       ← GitHub Actions runner as systemd service
└── .github/
    └── workflows/
        ├── provision-k3s.yml       ← existing (monolith label)
        ├── deploy-k8s-config.yml   ← existing (monolith label)
        └── deploy-watchtower.yml   ← new (watchtower label)
```

---

## Runner Security Model

> Each node manages itself. No runner crosses node boundaries via pipeline.

| Runner Label | Installed On | Manages |
|---|---|---|
| `monolith` | Monolith (AMD tower) | k3s cluster, Navidrome |
| `watchtower` | Watchtower (VM40B) | DNS, monitoring stack |

Watchtower is bootstrapped **manually via SSH from apex** — install OS, harden, install GitHub Actions runner. After that, all config changes go through GitHub Actions using `runs-on: [self-hosted, watchtower]`. Monolith's runner never touches Watchtower and vice versa.

---

## Workflow Architecture

```
apex (MacBook Air M4)
  └── VS Code / Obsidian / Terminal
        ├── Terraform → Terraform Cloud (remote state)
        └── Git push → GitHub
              └── GitHub Actions
                    ├── deploy-watchtower.yml
                    │     runs-on: [self-hosted, watchtower]
                    │     └── Ansible playbooks → configure Watchtower services
                    └── deploy-k8s-config.yml
                          runs-on: [self-hosted, monolith]
                          ├── kubectl apply → k3s cluster
                          └── Ansible playbooks → configure Monolith node
```

---

## Phase 0 — Repo Housekeeping & Dev Environment

> Do this before any Watchtower work begins. Gets the house in order.

### Repo reorganization (on apex)

- [ ] Rename `projects/` → `services/`
- [ ] Move `projects/audio-server/` → `services/navidrome/`
- [ ] Move `projects/watchtower/` → `services/watchtower/`
- [ ] Create `nodes/vm40b/` with `hardware.md`
- [ ] Create `terraform/watchtower/` stub
- [ ] Update `README.md` to reflect new structure and both nodes
- [ ] Update `docs/homelab-overview.md` — replace old drive list with current `df -h` reality
- [ ] Commit and push — verify nothing breaks in existing workflows

### Terraform Cloud setup

- [ ] Create account at [app.terraform.io](https://app.terraform.io) (free tier)
- [ ] Create organization (e.g. `speddling-homelab`)
- [ ] Create two workspaces: `monolith` and `watchtower`
  - Execution mode: **Local** (runner executes, Terraform Cloud stores state)
- [ ] Generate Terraform Cloud API token
- [ ] Add token as GitHub Actions secret: `TF_API_TOKEN`
- [ ] Add backend block to `terraform/monolith/main.tf`:

```hcl
terraform {
  cloud {
    organization = "speddling-homelab"
    workspaces {
      name = "monolith"
    }
  }
}
```

- [ ] Add backend block to new `terraform/watchtower/main.tf`:

```hcl
terraform {
  cloud {
    organization = "speddling-homelab"
    workspaces {
      name = "watchtower"
    }
  }
}
```

- [ ] Run `terraform init` in both directories — verify state migrates cleanly
- [ ] Confirm Terraform Cloud UI shows both workspaces with state

### GitHub Actions secrets audit

- [ ] Confirm existing secrets still valid: `SSH_PRIVATE_KEY`, `VM40B_HOST`, `VM40B_USER`
- [ ] Add `TF_API_TOKEN` (Terraform Cloud)
- [ ] Add `SLACK_WEBHOOK_URL` (Grafana alert channel — see Phase 8)
- [ ] **Do not commit Slack URLs, webhook URLs, or IPs to the repo**

### apex dev environment

- [ ] Verify: `terraform`, `ansible`, `git`, `gh`, `k9s` installed via MacPorts
- [ ] Verify SSH config has both `monolith` and `watchtower` host aliases
- [ ] Install VS Code extensions: `HashiCorp Terraform`, `Ansible`, `Remote-SSH`

---

## Phase 1 — Hardware & OS Prep

> Physical access to VM40B required. Done manually from apex via SSH after install.

- [ ] Install 1TB SSD into VM40B (2.5" SATA bay) — confirm BIOS detects it
- [ ] Download Ubuntu Server 24.04 LTS — flash to USB (Balena Etcher or `dd`)
- [ ] Boot and install — minimal install, OpenSSH server checked, no snaps
- [ ] Set hostname during install: `watchtower`
- [ ] Set static DHCP reservation in Omada controller by MAC address (do this before first boot if possible)
- [ ] Harden SSH immediately after first login:
  - [ ] `PasswordAuthentication no`
  - [ ] `PermitRootLogin no`
  - [ ] `AllowUsers <your-user>`
  - [ ] Copy public key from apex: `ssh-copy-id watchtower`
- [ ] `sudo apt update && sudo apt upgrade -y`
- [ ] Install baseline packages: `curl wget git htop ufw`
- [ ] Configure UFW — LAN only, no public exposure

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from 192.168.x.0/24 to any port 22 proto tcp
sudo ufw allow from 192.168.x.0/24 to any port 53
sudo ufw allow from 192.168.x.0/24 to any port 3000 proto tcp
sudo ufw allow from 192.168.x.0/24 to any port 3001 proto tcp
sudo ufw allow from 192.168.x.0/24 to any port 9090 proto tcp
sudo ufw allow from 192.168.x.0/24 to any port 19999 proto tcp
sudo ufw enable
```

- [ ] Enable `unattended-upgrades`: `sudo apt install unattended-upgrades -y`
- [ ] Verify SSH from apex: `ssh watchtower`
- [ ] Add `nodes/vm40b/hardware.md` to repo with confirmed specs and `df -h` output

---

## Phase 2 — GitHub Actions Runner (Watchtower)

> Bootstrap manually. After this, GitHub Actions takes over.

- [ ] SSH into Watchtower from apex
- [ ] In GitHub repo → Settings → Actions → Runners → New self-hosted runner
- [ ] Select Linux x64 — follow the generated install commands
- [ ] When prompted for labels, add: `self-hosted,watchtower`
- [ ] Install runner as a systemd service:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
systemctl status actions.runner.*
```

- [ ] Verify runner shows as **Idle** in GitHub → Settings → Actions → Runners
- [ ] Write `.github/workflows/deploy-watchtower.yml` on apex:

```yaml
name: Deploy Watchtower Config

on:
  push:
    branches: [master]
    paths:
      - 'services/watchtower/**'
      - 'terraform/watchtower/**'
  workflow_dispatch:

jobs:
  deploy:
    runs-on: [self-hosted, watchtower]
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          cli_config_credentials_token: ${{ secrets.TF_API_TOKEN }}

      - name: Terraform Init & Apply
        working-directory: terraform/watchtower
        run: |
          terraform init
          terraform apply -auto-approve

      - name: Run Ansible — DNS
        run: |
          ansible-playbook \
            -i services/watchtower/ansible/inventory.ini \
            services/watchtower/ansible/playbooks/dns.yml

      - name: Run Ansible — Monitoring
        run: |
          ansible-playbook \
            -i services/watchtower/ansible/inventory.ini \
            services/watchtower/ansible/playbooks/monitoring.yml

      - name: Run Ansible — Exporters
        run: |
          ansible-playbook \
            -i services/watchtower/ansible/inventory.ini \
            services/watchtower/ansible/playbooks/exporters.yml
```

- [ ] Push workflow — verify it appears in GitHub Actions tab
- [ ] Run manually via `workflow_dispatch` with a no-op playbook to confirm runner picks it up

---

## Phase 3 — Ansible Scaffold

> Authored on apex · roles deployed to Watchtower via GitHub Actions

- [ ] Install Ansible on apex: `sudo port install ansible`
- [ ] Create `services/watchtower/ansible/inventory.ini`:

```ini
[watchtower]
watchtower ansible_host=192.168.x.x ansible_user=<your-user> ansible_ssh_private_key_file=~/.ssh/id_ed25519

[watchtower:vars]
ansible_python_interpreter=/usr/bin/python3
```

- [ ] Create role scaffolds using `ansible-galaxy role init`:

```bash
cd services/watchtower/ansible/roles
ansible-galaxy role init unbound
ansible-galaxy role init adguard
ansible-galaxy role init prometheus
ansible-galaxy role init exporters
ansible-galaxy role init netdata
ansible-galaxy role init grafana
```

- [ ] Write `playbooks/dns.yml` — applies `unbound` and `adguard` roles
- [ ] Write `playbooks/monitoring.yml` — applies `prometheus`, `netdata`, `grafana` roles
- [ ] Write `playbooks/exporters.yml` — applies `exporters` role
- [ ] Test locally from apex before committing: `ansible-playbook -i inventory.ini playbooks/dns.yml --check`

---

## Phase 4 — DNS Layer (Unbound + AdGuard Home)

> Ansible roles: `unbound`, `adguard`

### Unbound role

- [ ] Task: install via apt (`unbound`)
- [ ] Template: `/etc/unbound/unbound.conf.d/watchtower.conf`
  - Listen on `127.0.0.1:5335`
  - Root hints enabled
  - DNSSEC validation on
  - Cache tuning: `rrset-cache-size: 256m`, `msg-cache-size: 128m`
- [ ] Task: disable and mask `systemd-resolved` stub listener
- [ ] Handler: restart unbound on config change
- [ ] Verify: `dig @127.0.0.1 -p 5335 google.com`

### AdGuard Home role

- [ ] Task: download and run AGH installer script
- [ ] Task: complete initial setup via AGH API (automate wizard)
- [ ] Template: AGH config — upstream DNS `127.0.0.1:5335`
- [ ] Blocklists to configure: Hagezi Multi Normal, OISD Big, Steven Black
- [ ] Enable DNSSEC
- [ ] Local DNS rewrites for homelab:
  - `watchtower.local` → Watchtower IP
  - `grafana.local` → Watchtower IP
  - `navidrome.local` → Monolith IP
  - `monolith.local` → Monolith IP
- [ ] Lock AGH web UI to LAN CIDR only

### Omada integration

- [ ] In OC200: set primary DNS to Watchtower static IP
- [ ] Set secondary DNS to `1.1.1.1` (fallback if Watchtower is down)
- [ ] Verify DNS resolution from a LAN client
- [ ] Verify ad blocking is active

---

## Phase 5 — Prometheus

> Ansible role: `prometheus` · Native binary, no Docker

- [ ] Task: create `prometheus` system user (no login shell, no home)
- [ ] Task: download Prometheus binary (x86_64) from GitHub releases
- [ ] Task: install to `/usr/local/bin/prometheus`
- [ ] Template: `/etc/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'watchtower'
    static_configs:
      - targets: ['localhost:9100']

  - job_name: 'blackbox'
    static_configs:
      - targets: ['localhost:9115']

  - job_name: 'adguard'
    static_configs:
      - targets: ['localhost:9617']

  - job_name: 'monolith'
    static_configs:
      - targets: ['monolith.local:9100']

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

- [ ] Template: `/etc/systemd/system/prometheus.service`
  - `--storage.tsdb.retention.time=30d`
  - `--storage.tsdb.retention.size=50GB`
  - `--storage.tsdb.path=/var/lib/prometheus`
- [ ] Handler: daemon-reload and restart on config change
- [ ] Verify UI at `http://watchtower.local:9090`

---

## Phase 6 — Exporters

> Ansible role: `exporters`

### node_exporter — Watchtower

- [ ] Task: install binary, create system user
- [ ] Template: systemd unit
- [ ] Verify: `curl localhost:9100/metrics`

### node_exporter — Monolith

- [ ] Add to Monolith via existing Terraform/pipeline or manual install
- [ ] Confirm `monolith.local:9100` is reachable from Watchtower
- [ ] Add scrape target already in `prometheus.yml` above

### blackbox_exporter

- [ ] Task: install binary + systemd unit
- [ ] Configure probe modules: `http_2xx`, `icmp`, `tcp_connect`
- [ ] Probe targets: ER605, EAP245s, Navidrome, Grafana, GitHub, apex
- [ ] Verify endpoint probing in Prometheus

### snmp_exporter

- [ ] Task: install binary + systemd unit
- [ ] Enable SNMP v2c on ER605 and EAP245s via Omada controller
- [ ] Build MIB config with `generator.yml` for TP-Link OIDs
- [ ] Verify interface counter scraping

### AdGuard Home exporter

- [ ] Install `adguard_exporter` (ebrianne/adguard-exporter)
- [ ] Configure AGH API credentials — store as Ansible vault variable, not plaintext
- [ ] Systemd unit
- [ ] Verify metrics endpoint: `curl localhost:9617/metrics`

---

## Phase 7 — Netdata

> Ansible role: `netdata` · Real-time host metrics complement to Prometheus

- [ ] Task: install via official kickstart script (`--dont-start-it` flag)
- [ ] Template: `/etc/netdata/netdata.conf`
  - Bind to LAN IP only
  - Disable Netdata Cloud (on-prem only)
- [ ] Task: `systemctl enable --now netdata`
- [ ] Verify dashboard: `http://watchtower.local:19999`
- [ ] Optional: enable Prometheus exporting endpoint in `exporting.conf`

---

## Phase 8 — Grafana

> Ansible role: `grafana`

- [ ] Task: add Grafana OSS apt repo, install `grafana`
- [ ] Template: `/etc/grafana/grafana.ini`
  - Bind to LAN IP
  - `disable_gravatar = true`
  - `allow_sign_up = false`
  - Change default admin password (store in Ansible vault)
- [ ] Task: `systemctl enable --now grafana-server`
- [ ] Add Prometheus data source (can be automated via Grafana API in Ansible)
- [ ] Import community dashboards

| Dashboard | Grafana ID |
|---|---|
| Node Exporter Full | 1860 |
| Blackbox Exporter | 7587 |
| AdGuard Home | 13330 |
| Kubernetes / k3s cluster | 15661 |
| SNMP Interface Stats | 11169 |

- [ ] Build custom homelab overview dashboard:
  - DNS query rate + block rate (AGH)
  - Watchtower CPU / RAM / disk / network
  - Monolith node health
  - Uptime probes — ER605, APs, Navidrome, GitHub
  - Omada AP client counts + throughput

---

## Phase 9 — Alerting (Grafana → Slack)

> Slack workspace: Little Wolf Acres
> Webhook URL stored as GitHub secret `SLACK_WEBHOOK_URL` — never committed to repo

- [ ] In Slack: create `#homelab-alerts` channel
- [ ] Create Incoming Webhook for that channel (Slack App Directory → Incoming Webhooks)
- [ ] In Grafana → Alerting → Contact Points: add Slack contact point
  - Webhook URL: paste from secret (entered manually in Grafana UI, not in repo)
  - Channel: `#homelab-alerts`
- [ ] Create notification policy — route all alerts to Slack contact point
- [ ] Define alert rules:

| Alert | Condition |
|---|---|
| Watchtower CPU high | > 80% sustained 5m |
| Watchtower disk high | > 85% used |
| DNS resolver down | blackbox probe fails > 2m |
| Monolith unreachable | node_exporter scrape fails > 2m |
| Any endpoint down | blackbox probe fails > 2m |
| Prometheus scrape gap | any target missing > 5m |

- [ ] Test alert: temporarily set a threshold to trigger, confirm Slack message arrives in `#homelab-alerts`
- [ ] Test recovery: confirm Slack sends resolved notification

---

## Phase 10 — Ongoing Maintenance

- [ ] Verify `unattended-upgrades` active: `systemctl status unattended-upgrades`
- [ ] Set up logrotate for Prometheus, Grafana, AGH: `/etc/logrotate.d/`
- [ ] Monthly: check Prometheus storage size — `du -sh /var/lib/prometheus`
- [ ] Keep Ansible role package versions pinned — bump intentionally via PR, not automatically
- [ ] All config changes go through GitHub Actions — no manual edits on Watchtower directly
- [ ] Any manual deviation gets documented immediately in this file

---

## Reference

### Useful commands from apex

```bash
# SSH to nodes
ssh watchtower
ssh monolith

# Check all Watchtower services
ssh watchtower "systemctl status prometheus grafana-server netdata adguardhome unbound"

# Tail a service log
ssh watchtower "journalctl -fu prometheus"
ssh watchtower "journalctl -fu adguardhome"

# Run a single Ansible playbook manually
ansible-playbook -i services/watchtower/ansible/inventory.ini \
  services/watchtower/ansible/playbooks/dns.yml

# Ansible dry run (check mode)
ansible-playbook -i services/watchtower/ansible/inventory.ini \
  services/watchtower/ansible/playbooks/monitoring.yml --check

# Terraform plan for Watchtower
cd terraform/watchtower && terraform plan
```

### Port reference — UFW rules on Watchtower

| Port | Protocol | Service | Allowed from |
|---|---|---|---|
| 22 | TCP | SSH | apex IP only |
| 53 | TCP+UDP | AdGuard Home DNS | LAN |
| 3000 | TCP | AdGuard Home UI | LAN |
| 3001 | TCP | Grafana | LAN |
| 9090 | TCP | Prometheus | LAN |
| 19999 | TCP | Netdata | LAN |
| 9100 | TCP | node_exporter | Watchtower only |
| 9115 | TCP | blackbox_exporter | Watchtower only |
| 9116 | TCP | snmp_exporter | Watchtower only |
| 9617 | TCP | AGH exporter | Watchtower only |

### Ansible vault note

Sensitive values (AGH API credentials, Grafana admin password) go in an encrypted Ansible vault file, not plaintext in vars. To edit:

```bash
ansible-vault edit services/watchtower/ansible/group_vars/all/vault.yml
```

Store the vault password in macOS Keychain or a local `.vault_pass` file excluded via `.gitignore`.

---

## Related Notes

- [[Monolith — K3s Cluster]]
- [[Omada Network Config]]
- [[Navidrome — Audio Server]]
- [[GitHub Actions — Homelab Pipelines]]
- [[apex — MacBook Air M4 Dev Environment]]
- [[Terraform Cloud — State Management]]

---

*Last updated: 2026-04-21*
*Status: 🟡 In Progress — awaiting hardware (PSU replacement)*
