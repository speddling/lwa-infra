# Little Wolf Acres — Homelab Current State
> Last updated: May 2026 · Authored on apex · All IaC in `speddling/homelab` repo

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
| 192.168.0.19 | Apex | MacBook Pro — Primary Workstation |
| 192.168.0.20 | Monolith | k3s Node — Primary Server |
| 192.168.0.21 | Watchtower | DNS / Monitoring Stack |
| 192.168.0.109 | Studio | Ubuntu Studio — DAW / KDE Workstation |

> All other devices use dynamic DHCP leases. Do not set static IPs at the OS level.

### DNS

- **Primary DNS:** Watchtower (`192.168.0.21`) — AdGuard Home → Unbound → Root
- **Fallback DNS:** `1.1.1.1`
- **Local rewrites managed in AdGuard Home:**

| Domain | Resolves To |
|---|---|
| `watchtower.local` | 192.168.0.21 |
| `grafana.local` | 192.168.0.21 |
| `monolith.local` | 192.168.0.20 |
| `navidrome.local` | 192.168.0.20 |

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
| Unbound | Recursive DNS resolver (upstream) | 5335 | ✅ Running |
| AdGuard Home | DNS frontend, ad/tracker filtering | 53, 3000 | ✅ Running |
| Prometheus | Metrics scraping + TSDB | 9090 | ✅ Running |
| node_exporter | Watchtower host metrics | 9100 | ✅ Running |
| blackbox_exporter | Endpoint / ICMP probing | 9115 | ✅ Running |
| snmp_exporter | Omada network gear metrics | 9116 | ✅ Running |
| adguard_exporter | AGH metrics → Prometheus | 9618 | ✅ Running |
| Netdata | Real-time host observability | 19999 | ✅ Running |
| Grafana | Dashboards + alerting → Slack | 3001 | ✅ Running |

### Web UIs

| Service | URL |
|---|---|
| AdGuard Home | http://192.168.0.21:3000 |
| Grafana | http://192.168.0.21:3001 |
| Prometheus | http://192.168.0.21:9090 |
| Netdata | http://192.168.0.21:19999 |

### Prometheus Targets

| Job | Target | Status |
|---|---|---|
| watchtower | localhost:9100 | ✅ Up |
| blackbox | localhost:9115 | ✅ Up |
| adguard | localhost:9618 | ✅ Up |
| monolith | monolith.local:9100 | ✅ Up |
| snmp-er605 | 192.168.0.1 | ✅ Up |
| snmp-eap-yarn-studio | 192.168.0.5 | ✅ Up |
| snmp-eap-foyer | 192.168.0.2 | ✅ Up |

### Grafana Dashboards

| Dashboard | Grafana ID |
|---|---|
| Node Exporter Full | 1860 |
| AdGuard Home | 20799 |
| Blackbox Exporter | 7587 |
| SNMP Interface Stats | 11169 |

### Alerting

- **Contact point:** Sentinel → `#sentinel` in Little Wolf Acres Slack
- **Alert rules (all in `watchtower` group, Homelab folder):**

| Alert | Condition |
|---|---|
| High CPU Usage | > 85% sustained 5m |
| High Memory Usage | > 85% sustained 5m |
| Low Disk Space | > 80% used |
| Node Exporter Down | Scrape fails > 1m |
| AdGuard Home Down | Scrape fails > 1m |

### UFW Rules

| Port  | Protocol | Service          | Allowed From  |
| ----- | -------- | ---------------- | ------------- |
| 22    | TCP      | SSH              | apex & studio |
| 53    | TCP+UDP  | AdGuard Home DNS | LAN           |
| 3000  | TCP      | AdGuard Home UI  | LAN           |
| 3001  | TCP      | Grafana          | LAN           |
| 9090  | TCP      | Prometheus       | LAN           |
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
| Machine  | AMD Tower                     |
| OS       | Ubuntu Server 24.04 LTS       |
| Hostname | `monolith`                    |
| IP       | 192.168.0.20 (DHCP MAC-bound) |
| Storage  | Boot 512GB NVMe               |
|          | 256GB SSD                     |
|          | 512GB SSD                     |
|          | 4TB HDD                       |
|          | 2TB HDD                       |

### Role

Primary k3s node. Runs all workloads. Named for its role as the single heavy node.

### Services

| Service | Role | Status |
|---|---|---|
| k3s | Kubernetes (single-node cluster) | ✅ Running |
| Navidrome | Music streaming server | ✅ Running |
| Samba | File share (family backups, media) | ✅ Running |
| node_exporter | Host metrics → Prometheus on Watchtower | ✅ Running |

### IaC

| Layer | Tool | Location |
|---|---|---|
| State | Terraform Cloud (`littlewolfacres` org, `monolith` workspace) | app.terraform.io |
| Config | Ansible | `services/monolith/ansible/` |
| Pipeline | GitHub Actions | `.github/workflows/` (existing k3s workflows) |
| Runner | Self-hosted, label: `monolith` | Installed on Monolith as systemd service |

### DNS

- Points to Watchtower (`192.168.0.21`) as primary DNS
- Fallback: `1.1.1.1`
- Configured via `/etc/systemd/resolved.conf`


---

## Apex

| Spec     | Detail                                                                 |
| -------- | ---------------------------------------------------------------------- |
| Machine  | MacBook Air M4                                                         |
| Hostname | `apex`                                                                 |
| IP       | 192.168.0.19 (DHCP MAC-bound)                                          |
| Role     | Primary workstation — all authoring, config, remote ops originate here |

## Studio


| Spec     | Detail                                                       |
| -------- | ------------------------------------------------------------ |
| Machine  | Dell Precision                                               |
| Hostname |                                                              |
| IP       | 192.168.0.                                                   |
| Role     | Personal Laptop & DAW - Reaper with an M-Audio Air 192 \| 14 |


---

## CLI Reference — Little Wolf Acres Homelab

### Service Health Checks (run on Watchtower)

```bash
# Check all core Watchtower services at once
systemctl status prometheus grafana-server netdata AdGuardHome unbound

# Check individual services
systemctl status prometheus
systemctl status grafana-server
systemctl status AdGuardHome
systemctl status unbound
systemctl status node_exporter
systemctl status blackbox_exporter
systemctl status snmp_exporter
systemctl status adguard_exporter
systemctl status netdata
```

### Live Log Tailing (run on Watchtower)

```bash
journalctl -fu prometheus
journalctl -fu grafana-server
journalctl -fu AdGuardHome
journalctl -fu unbound
journalctl -fu adguard_exporter
journalctl -fu snmp_exporter
```

### DNS Testing

```bash
# Test Unbound directly (recursive resolver)
dig @127.0.0.1 -p 5335 google.com

# Test AdGuard Home (DNS frontend)
dig @127.0.0.1 google.com

# Test a local rewrite
dig monolith.local
dig grafana.local

# Test from a specific DNS server
dig @192.168.0.21 monolith.local
```

### SNMP Testing (run on Watchtower)

```bash
# Test ER605
snmpwalk -v2c -c littlewolfacres 192.168.0.1 1.3.6.1.2.1.1.1.0

# Test EAP245 Yarn Studio
snmpwalk -v2c -c littlewolfacres 192.168.0.5 1.3.6.1.2.1.1.1.0

# Test EAP245 Foyer
snmpwalk -v2c -c littlewolfacres 192.168.0.2 1.3.6.1.2.1.1.1.0

# Test SNMP exporter directly
curl "http://localhost:9116/snmp?module=if_mib&auth=littlewolfacres_v2&target=192.168.0.1"
```

### Prometheus

```bash
# Validate config before restarting
promtool check config /etc/prometheus/prometheus.yml

# Check storage size
du -sh /var/lib/prometheus

# Restart after config change
sudo systemctl restart prometheus
```

### Ansible (run from apex)

```bash
# Run DNS playbook
cd ~/homelab/services/watchtower/ansible
ansible-playbook -i inventory.ini playbooks/dns.yml --ask-become-pass --vault-password-file=~/homelab/.vault_pass

# Run monitoring playbook
ansible-playbook -i inventory.ini playbooks/monitoring.yml --ask-become-pass --vault-password-file=~/homelab/.vault_pass

# Run exporters playbook
ansible-playbook -i inventory.ini playbooks/exporters.yml --ask-become-pass --vault-password-file=~/homelab/.vault_pass

# Dry run (check mode)
ansible-playbook -i inventory.ini playbooks/monitoring.yml --check --ask-become-pass --vault-password-file=~/homelab/.vault_pass

# Edit vault
ansible-vault edit group_vars/all/vault.yml --vault-password-file=~/homelab/.vault_pass

# View vault
ansible-vault view group_vars/all/vault.yml --vault-password-file=~/homelab/.vault_pass
```

### Monolith Ansible (run from apex)

```bash
cd ~/homelab/services/monolith/ansible
ansible-playbook -i inventory.ini playbooks/monitoring.yml --ask-become-pass
```

### Terraform (run from apex)

```bash
# Watchtower
cd ~/homelab/terraform/watchtower
terraform init
terraform plan
terraform apply

# Monolith
cd ~/homelab/terraform/monolith
terraform init
terraform plan
terraform apply
```

### UFW (run on Watchtower)

```bash
# Check rules
sudo ufw status

# Temporarily allow Studio for SSH troubleshooting
sudo ufw allow from 192.168.0.109 to any port 22 proto tcp

# Remove it when done
sudo ufw delete allow from 192.168.0.109 to any port 22 proto tcp
```

### NUT — When UPS Arrives (run on apex)

```bash
# Enable NUT role
# Edit inventory.ini and add:
# nut_enabled=true
# under [watchtower:vars]

# Then redeploy
cd ~/homelab/services/watchtower/ansible
ansible-playbook -i inventory.ini playbooks/monitoring.yml --ask-become-pass --vault-password-file=~/homelab/.vault_pass
```

### Grafana API (run from anywhere on LAN)

```bash
# List all alert rules
curl -s -u 'admin:PASSWORD' 'http://192.168.0.21:3001/api/v1/provisioning/alert-rules' | python3 -m json.tool

# Delete a specific alert rule by UID
curl -X DELETE -u 'admin:PASSWORD' 'http://192.168.0.21:3001/api/v1/provisioning/alert-rules/RULE-UID'
```

### Git Workflow

```bash
# Standard commit and push (triggers GitHub Actions if paths match)
cd ~/homelab
git add .
git commit -m "feat: description of change"
git push

# Trigger workflow manually via GitHub CLI
gh workflow run deploy-watchtower.yml
```

---

## Pending Work

| Item                          | Priority | Notes                                                      |
| ----------------------------- | -------- | ---------------------------------------------------------- |
| Family file server            | Medium   | Structured backup for iPad art, crochet notes              |
| JetStream PoE switch          | Low      | Replaces unmanaged TL-SG1210P, enables SNMP per-port stats |
| UPS — CyberPower CP1500PFCLCD | Low      | NUT role ready, waiting on hardware budget                 |
| SNMP MIB generator            | Low      | Proper TP-Link MIB walk for richer metrics                 |
| Omada DNS integration         | Low      | Point LAN clients at Watchtower via DHCP option            |
