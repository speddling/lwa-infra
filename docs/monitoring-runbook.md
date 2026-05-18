# Monitoring Runbook — Little Wolf Acres
> Reference for the full observability stack: Prometheus, Grafana, Alertmanager, exporters, and the daily Slack summary.
> Last updated: 2026-05-18

---

## Architecture Overview

All monitoring services run as **systemd units on Watchtower** (`192.168.0.21`).
There are no monitoring pods in k3s — Prometheus scrapes Monolith's node_exporter remotely over the LAN.

```
Watchtower (192.168.0.21)
├── prometheus          :9090   — metrics store & alert evaluation
├── alertmanager        :9093   — alert routing → Slack #sentinel
├── grafana-server      :3001   — dashboards (grafana.littlewolfacres.com)
├── node_exporter       :9100   — Watchtower host metrics
├── blackbox_exporter   :9115   — HTTP/ICMP probing
├── snmp_exporter       :9116   — network device metrics (ER605, 2× EAP245)
├── adguard_exporter    :9618   — AdGuard Home DNS stats
├── tmobile_exporter    :9719   — T-Mobile gateway signal/status
├── reolink_exporter    :9720   — NVR camera status
└── daily-summary       timer   — 8 AM + 8 PM Slack digest

Monolith (192.168.0.20 / monolith.littlewolfacres.com)
├── node_exporter       :9100   — Monolith host metrics (scraped remotely)
└── kube-state-metrics  :30900  — k3s object state metrics (NodePort)
```

---

## Prometheus Scrape Jobs

| Job | Target | Metrics |
|-----|--------|---------|
| `watchtower` | `localhost:9100` → relabeled `instance=watchtower` | Host CPU, memory, disk, network |
| `prometheus` | `localhost:9090` → relabeled `instance=watchtower` | Prometheus TSDB, WAL, scrape, rule stats |
| `blackbox` | `localhost:9115` | Exporter health only — not probe results |
| `blackbox-http` | Probes via `localhost:9115` | `probe_success`, `probe_duration_seconds` for HTTP targets |
| `blackbox-icmp` | Probes via `localhost:9115` | `probe_success`, `probe_duration_seconds` for ICMP targets |
| `adguard` | `localhost:9618` | DNS query counts, block rates |
| `monolith` | `monolith.littlewolfacres.com:9100` → labelled `instance=monolith` | Host CPU, memory, disk, network |
| `snmp-er605` | `192.168.0.1` via SNMP exporter | Router interface stats (ifHCInOctets, ifOperStatus, etc.) |
| `snmp-eap-yarn-studio` | `192.168.0.5` via SNMP exporter | AP interface stats |
| `snmp-eap-foyer` | `192.168.0.2` via SNMP exporter | AP interface stats |
| `tmobile` | `localhost:9719` | Gateway signal, band, uptime |
| `reolink_nvr` | `localhost:9720` | NVR up, device info, channel online, HDD usage |
| `kube-state-metrics` | `monolith.littlewolfacres.com:30900` | k3s pod, deployment, PVC, namespace state |

> **Instance label convention:** Prometheus relabels both node_exporter scrapes so
> `instance` is a clean hostname (`watchtower` / `monolith`) rather than `localhost:9100`
> or the remote FQDN. All alert rules, dashboard queries, and the daily summary script
> use these relabeled values. Do not revert this without updating all three places.

### Blackbox probe targets

Probes run via the `blackbox-http` and `blackbox-icmp` jobs. Add or remove targets
in `roles/prometheus/templates/prometheus.yml.j2` under those jobs, then re-deploy.

| Target | Module | What it checks |
|--------|--------|---------------|
| `http://grafana.littlewolfacres.com:3001` | http_2xx | Grafana UI reachable |
| `http://navidrome.littlewolfacres.com` | http_2xx | Navidrome reachable |
| `192.168.0.20` | icmp | Monolith host pingable |
| `192.168.0.21` | icmp | Watchtower self-check |
| `1.1.1.1` | icmp | WAN/internet connectivity |

---

## Grafana Dashboards

Grafana runs on port `3001`. Access via `http://grafana.littlewolfacres.com:3001`
or directly at `http://192.168.0.21:3001`.

Dashboards are **provisioned from disk** — JSON files placed by Ansible into
`/var/lib/grafana/dashboards/`. They survive Grafana restarts and re-deploys.
Do not rely on dashboards imported manually through the UI; add them to the Grafana
Ansible role instead (`roles/grafana/tasks/main.yml` + `roles/grafana/files/`). The
monitoring playbook automatically purges any dashboard not in the managed UID set on
every deploy — community dashboards imported via the UI will be removed.

| Dashboard | File | Source | Purpose |
|-----------|------|--------|---------|
| Node Exporter Full | `node-exporter-full.json` | Community ID 1860 | Full host metrics for Watchtower and Monolith |
| Blackbox Probes | `blackbox-exporter.json` | Custom (`lwa-blackbox-probes`) | HTTP/ICMP probe status and duration |
| k3s Cluster | `k3s-cluster.json` | Custom (`lwa-k3s-cluster`) | Kubernetes cluster overview (needs kube-state-metrics) |
| SNMP Interfaces | `snmp-interfaces.json` | Custom (`lwa-snmp-interfaces`) | Network interface traffic, errors, status |
| T-Mobile 5G Gateway | `tmobile-gateway.json` | Custom (`lwa-tmobile-gateway`) | Gateway signal, band, uptime |
| Reolink NVR | `reolink-nvr.json` | Custom (`lwa-reolink-nvr`) | NVR/camera status and HDD usage |

### Using Node Exporter Full

The dashboard has two template variables at the top:

- **Job** — select `watchtower` or `monolith`
- **Node** — auto-populates to `watchtower` or `monolith` once a job is selected

If panels show N/A after a restart, the variable selection reset. Open the Job
dropdown and select the host — data returns immediately.

### Adding a new community dashboard

1. Find the ID at `https://grafana.com/grafana/dashboards/`
2. Add a `get_url` task to `roles/grafana/tasks/main.yml` following the ID 1860 pattern
3. Commit and push — the deploy workflow applies it on merge to master

### Adding a custom dashboard

1. Build the dashboard in Grafana UI
2. Dashboard settings → JSON Model → copy
3. Save to `roles/grafana/files/<name>.json`
4. Add an `ansible.builtin.copy` task to `roles/grafana/tasks/main.yml`
5. Commit and push

---

## Alert Rules

Alert rules live in two places, evaluated independently:

| Location | File | Evaluated by |
|----------|------|-------------|
| Prometheus | `/etc/prometheus/alert_rules.yml` | Prometheus → fires to Alertmanager |
| Grafana | `/etc/grafana/provisioning/alerting/alert_rules.yml` | Grafana unified alerting |

Source templates in the repo:

```
services/watchtower/ansible/roles/prometheus/templates/alert_rules.yml.j2
services/watchtower/ansible/roles/grafana/templates/alert_rules.yml.j2
```

### Active Prometheus alert rules

| Alert | Condition | Severity | Host |
|-------|-----------|----------|------|
| `WatchtowerHighCPU` | CPU > 85% for 5 min | warning | watchtower |
| `WatchtowerHighMemory` | Memory > 85% for 5 min | warning | watchtower |
| `WatchtowerLowDisk` | Disk `/` > 80% | critical | watchtower |
| `WatchtowerPrometheusTSDB` | TSDB blocks > 8GB (80% of 10GB retention limit) | warning | watchtower |
| `WatchtowerNodeExporterDown` | `up{job="watchtower"} == 0` for 1 min | critical | watchtower |
| `AdGuardHomeDown` | `up{job="adguard"} == 0` for 1 min | critical | watchtower |
| `MonolithDown` | `up{job="monolith"} == 0` for 1 min | critical | monolith |
| `MonolithHighCPU` | CPU > 85% for 5 min | warning | monolith |
| `MonolithHighMemory` | Memory > 85% for 5 min | warning | monolith |
| `MonolithLowDisk` | Disk `/` > 80% | critical | monolith |
| `MonolithLowDiskHddC` | Disk `/mnt/hdd-c` > 80% | critical | monolith |
| `MonolithLowDiskHddD` | Disk `/mnt/hdd-d` > 80% | warning | monolith |

All alerts route to Alertmanager → `#sentinel` Slack channel.

---

## Alertmanager

Routes all alerts to the `Sentinel` contact point (Slack `#sentinel`).
Webhook URL is stored in Ansible Vault (`vault_slack_webhook_url`).

```bash
# Check health
curl -s http://192.168.0.21:9093/-/healthy

# Check active alerts via API
curl -s http://192.168.0.21:9093/api/v2/alerts | python3 -m json.tool

# Restart
sudo systemctl restart alertmanager

# Logs
journalctl -fu alertmanager
```

---

## Daily Summary

A Python script (`/usr/local/bin/daily-summary.py`) runs via systemd timer at
**8 AM and 8 PM America/New_York**, posting a health digest to `#sentinel`.

It queries Prometheus directly over HTTP and is completely independent of Alertmanager.
If the morning report populates correctly but Grafana shows no data, the issue is in
Grafana (dashboard variables, provisioning, data source) — not in Prometheus.

```bash
# Check timer schedule and last run
systemctl status daily-summary.timer
systemctl status daily-summary.service

# Trigger a manual test run
sudo systemctl start daily-summary.service

# Tail logs from the last run
journalctl -u daily-summary.service -n 50
```

Deployment template: `roles/daily_summary/templates/daily-summary.py.j2`
Enhancement roadmap: `docs/daily-summary.md`

---

## SNMP

### Configuration

SNMP is configured in `/etc/prometheus/snmp.yml` (template: `roles/exporters/templates/snmp.yml.j2`).
The `if_mib` module walks the standard `ifTable` and `ifXTable` OID trees and translates them
into named Prometheus metrics via the `metrics:` section. Without the `metrics:` section the
walk succeeds (PDUs are returned) but nothing is exposed — this was the original bug.

Key metrics produced:

| Metric | Type | Description |
|--------|------|-------------|
| `ifHCInOctets` | counter | Inbound octets (64-bit, for high-speed links) |
| `ifHCOutOctets` | counter | Outbound octets (64-bit) |
| `ifInOctets` / `ifOutOctets` | counter | Inbound/outbound octets (32-bit fallback) |
| `ifOperStatus` | gauge | 1=up 2=down (also string label via enum_values) |
| `ifAdminStatus` | gauge | 1=up 2=down (desired state) |
| `ifInErrors` / `ifOutErrors` | counter | Interface errors |
| `ifInDiscards` / `ifOutDiscards` | counter | Discarded packets |
| `ifDescr` / `ifName` / `ifAlias` | info label | Human-readable interface names (via lookup) |

### Testing SNMP manually

```bash
# Verify SNMP reachability (run on watchtower)
snmpwalk -v2c -c littlewolfacres 192.168.0.1 1.3.6.1.2.1.1.1.0   # ER605
snmpwalk -v2c -c littlewolfacres 192.168.0.5 1.3.6.1.2.1.1.1.0   # EAP Yarn Studio
snmpwalk -v2c -c littlewolfacres 192.168.0.2 1.3.6.1.2.1.1.1.0   # EAP Foyer

# Query SNMP exporter directly for ER605
curl "http://localhost:9116/snmp?module=if_mib&auth=littlewolfacres_v2&target=192.168.0.1"

# Verify metrics land in Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=ifHCInOctets{job="snmp-er605"}' | python3 -m json.tool
```

---

## Blackbox Exporter

The blackbox exporter probes external targets on demand. There are two probe jobs:

- **`blackbox-http`** — sends an HTTP GET and checks for HTTP 2xx response
- **`blackbox-icmp`** — sends an ICMP ping

Key metric: `probe_success{instance="<target>"}` — `1` means the probe succeeded, `0` means failure.

```bash
# Probe a target manually (run on watchtower)
curl "http://localhost:9115/probe?module=http_2xx&target=http://grafana.littlewolfacres.com:3001"
curl "http://localhost:9115/probe?module=icmp&target=1.1.1.1"

# Check probe results in Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=probe_success' | python3 -m json.tool
```

### Adding a new probe target

Edit `roles/prometheus/templates/prometheus.yml.j2`, add the target to the appropriate
`blackbox-http` or `blackbox-icmp` job, then re-run the monitoring playbook. No exporter
restart needed — Prometheus will start scraping the new target on the next interval.

---

## Reolink NVR Exporter

The exporter polls the NVR's HTTP CGI API every 30 seconds from Watchtower.

### Metrics

| Metric | Description |
|--------|-------------|
| `reolink_nvr_up` | 1 if the NVR API responds, 0 otherwise |
| `reolink_nvr_info` | Info metric with labels: model, firmware, hardware, name |
| `reolink_nvr_channel_online{channel="N"}` | 1 if camera channel N is online |
| `reolink_nvr_hdd_capacity_mb{id="N"}` | HDD total capacity in MB |
| `reolink_nvr_hdd_used_mb{id="N"}` | HDD used space in MB |
| `reolink_nvr_hdd_mounted{id="N"}` | 1 if HDD is mounted |

### Debugging

If channel or HDD metrics are missing (only `reolink_nvr_up` and `reolink_nvr_info` show),
the exporter's API calls for `GetChannelstatus` or `GetHddInfo` are failing. Check the logs:

```bash
journalctl -u reolink_exporter -n 50
```

The exporter logs the raw API response when parsing fails, which shows the actual response
structure from the NVR. Common causes:

- **Command name mismatch** — some Reolink firmware uses `GetChannelStatus` (capital S)
  vs `GetChannelstatus`. The exporter tries both.
- **Response structure differs** — log the raw JSON and compare to `reolink_exporter.py`
  parsing code. Update the key names if needed.
- **NVR firmware update** — Reolink occasionally changes the CGI API between versions.

```bash
# Test the API directly from watchtower
curl "http://192.168.0.4/api.cgi?cmd=GetChannelstatus&user=admin&password=PASSWORD"
curl "http://192.168.0.4/api.cgi?cmd=GetHddInfo&user=admin&password=PASSWORD"
```

---

## kube-state-metrics

kube-state-metrics exposes Kubernetes object state as Prometheus metrics, enabling
the k3s cluster dashboard (Grafana ID 15661) to show pod status, deployment health, PVCs, etc.

### Deployment

```bash
# Deploy (run on monolith or from apex with kubeconfig)
sudo k3s kubectl apply -f ~/homelab/kubernetes/manifests/kube-state-metrics.yml

# Verify pod is running
sudo k3s kubectl get pods -n kube-system | grep kube-state-metrics

# Check the metrics endpoint is reachable from watchtower
curl http://monolith.littlewolfacres.com:30900/metrics | head -20

# Verify Prometheus picks it up
curl -s 'http://192.168.0.21:9090/api/v1/query?query=kube_pod_info' | python3 -m json.tool
```

The service uses NodePort `30900` (port `30800` is reserved for synapse-mcp).
Prometheus on Watchtower scrapes `monolith.littlewolfacres.com:30900`.

---

## Service Health Checks

```bash
# All monitoring services at once
systemctl status prometheus alertmanager grafana-server node_exporter \
  blackbox_exporter snmp_exporter adguard_exporter tmobile_exporter \
  reolink_exporter daily-summary.timer

# Live log tailing
journalctl -fu prometheus
journalctl -fu alertmanager
journalctl -fu grafana-server
journalctl -fu adguard_exporter
journalctl -fu reolink_exporter
journalctl -fu snmp_exporter
```

---

## Prometheus Operations

```bash
# Validate config (run on watchtower)
promtool check config /etc/prometheus/prometheus.yml

# Validate alert rules
promtool check rules /etc/prometheus/alert_rules.yml

# Check all scrape targets and their health
curl -s http://192.168.0.21:9090/api/v1/targets | python3 -m json.tool | grep -E '"job"|"health"|"instance"'

# Check which jobs are currently UP
curl -s 'http://192.168.0.21:9090/api/v1/query?query=up' | python3 -m json.tool

# Check active alerts
curl -s http://192.168.0.21:9090/api/v1/alerts | python3 -m json.tool

# Check storage size (retention limit: 10GB)
du -sh /var/lib/prometheus

# Reload config without restart (preferred — avoids data gap)
sudo systemctl reload prometheus

# Full restart (if reload doesn't pick up changes)
sudo systemctl restart prometheus
```

---

## Ansible Deployment

All monitoring config is managed by Ansible, run from **Apex** (`192.168.0.19`).

```bash
cd ~/homelab/services/watchtower/ansible

# Deploy full monitoring stack (Prometheus, Alertmanager, Grafana, daily summary, Argus)
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --vault-password-file=~/homelab/.vault_pass

# Dry run first
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --check --vault-password-file=~/homelab/.vault_pass

# Deploy only exporters (node_exporter, blackbox, snmp, adguard, reolink, tmobile)
ansible-playbook -i inventory.ini playbooks/exporters.yml \
  --vault-password-file=~/homelab/.vault_pass
```

The `monitoring.yml` playbook applies roles in order:
`prometheus → alertmanager → netdata → grafana → daily_summary → argus → nut`

The GitHub Actions deploy workflow triggers automatically on push to `master` for paths
under `services/watchtower/**` or `ansible/vars/**`.

---

## Troubleshooting

### Grafana dashboard shows no data

1. **Check Prometheus is up and scraping:**
   ```bash
   curl -s 'http://192.168.0.21:9090/api/v1/query?query=up' | python3 -m json.tool
   ```
   All expected jobs should show `value: 1`.

2. **Node Exporter Full — variable selection reset:**
   Open the dashboard → check the Job and Node dropdowns. Select `watchtower` or `monolith`.
   The `$node` variable is populated from `label_values(node_uname_info{job="$job"}, instance)`
   and should auto-fill once a job is selected.

3. **Check Grafana data source:**
   Grafana → Configuration → Data Sources → Prometheus → Test. Should succeed.

4. **If morning Slack report has real numbers, Prometheus is healthy** — the issue is Grafana
   only (data source, variable, provisioning).

5. **Check Grafana logs:**
   ```bash
   journalctl -fu grafana-server
   ```

### SNMP dashboard shows N/A

Verify the `metrics:` section is deployed:
```bash
# Should return named metrics, not just scrape metadata
curl -s 'http://localhost:9090/api/v1/query?query=ifHCInOctets{job="snmp-er605"}' | python3 -m json.tool

# If empty, the snmp.yml may not have been redeployed — check live config
sudo cat /etc/prometheus/snmp.yml | grep -A5 'metrics:'

# Restart exporter to reload config
sudo systemctl restart snmp_exporter
```

### Blackbox dashboard shows no probes

Verify the probe jobs exist in the live prometheus.yml:
```bash
grep -A5 'blackbox-http\|blackbox-icmp' /etc/prometheus/prometheus.yml

# Test a probe directly
curl "http://localhost:9115/probe?module=icmp&target=1.1.1.1"

# Check probe_success in Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=probe_success' | python3 -m json.tool
```

### k3s dashboard still showing No Data after kube-state-metrics deployed

```bash
# Check pod is running
sudo k3s kubectl get pods -n kube-system | grep kube-state

# Check NodePort is reachable from watchtower (run on watchtower)
curl http://monolith.littlewolfacres.com:30900/metrics | grep kube_pod_info | head -5

# Check Prometheus target health
curl -s http://192.168.0.21:9090/api/v1/targets | python3 -m json.tool | grep -A10 kube-state
```

### Reolink channel/HDD metrics missing

```bash
# Check exporter logs for API errors
journalctl -u reolink_exporter -n 100

# Test the NVR API directly
NVR_PW=$(sudo systemctl show reolink_exporter | grep NVR_PASSWORD | cut -d= -f2)
curl "http://192.168.0.4/api.cgi?cmd=GetChannelstatus&user=admin&password=$NVR_PW"
curl "http://192.168.0.4/api.cgi?cmd=GetHddInfo&user=admin&password=$NVR_PW"
```

### Prometheus alert not firing when expected

```bash
# Manually evaluate the expression in Prometheus UI
# http://192.168.0.21:9090/graph — paste the expr from alert_rules.yml

# Validate alert rules syntax
promtool check rules /etc/prometheus/alert_rules.yml
```

### Alert firing but no Slack message

```bash
curl -s http://192.168.0.21:9093/api/v2/alerts | python3 -m json.tool
curl -s http://192.168.0.21:9093/api/v2/status | python3 -m json.tool
journalctl -fu alertmanager -n 100
```

---

## Label Conventions

Consistent labels across the stack — changing these requires updating Prometheus config,
alert rules, and the daily summary script simultaneously.

| Label | Values | Notes |
|-------|--------|-------|
| `job` | `watchtower`, `monolith`, `adguard`, `blackbox`, `blackbox-http`, `blackbox-icmp`, `snmp-*`, `tmobile`, `reolink_nvr`, `kube-state-metrics` | Identifies the scrape job / service type |
| `instance` | `watchtower`, `monolith` (node exporters); raw address for others | Relabeled to clean hostnames for node_exporter only |
| `severity` | `warning`, `critical` | Used in Alertmanager routing and Slack formatting |
| `host` | `watchtower`, `monolith` | Custom label on Prometheus alert rules |

> The `instance` relabeling for node exporters was introduced in May 2026 to fix the Grafana
> Node Exporter Full dashboard losing variable selections on Grafana restart.
