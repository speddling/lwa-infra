# Monitoring Runbook — Little Wolf Acres
> Reference for the full observability stack: Prometheus, Grafana, Alertmanager, exporters, and the daily Slack summary.
> Last updated: 2026-05-16

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
└── node_exporter       :9100   — Monolith host metrics (scraped remotely)
```

---

## Prometheus Scrape Jobs

| Job | Target | Metrics |
|-----|--------|---------|
| `watchtower` | `localhost:9100` → relabeled `instance=watchtower` | Host CPU, memory, disk, network |
| `blackbox` | `localhost:9115` | HTTP/ICMP probe results |
| `adguard` | `localhost:9618` | DNS query counts, block rates |
| `monolith` | `monolith.littlewolfacres.com:9100` → labelled `instance=monolith` | Host CPU, memory, disk, network |
| `snmp-er605` | `192.168.0.1` via SNMP exporter | Router interface stats |
| `snmp-eap-yarn-studio` | `192.168.0.5` via SNMP exporter | AP interface stats |
| `snmp-eap-foyer` | `192.168.0.2` via SNMP exporter | AP interface stats |
| `tmobile` | `localhost:9719` | Gateway signal, band, uptime |
| `reolink_nvr` | `localhost:9720` | Camera online/recording status |

> **Instance label convention:** Prometheus relabels both node_exporter scrapes so
> `instance` is a clean hostname (`watchtower` / `monolith`) rather than `localhost:9100`
> or the remote FQDN. All alert rules, dashboard queries, and the daily summary script
> use these relabeled values. Do not revert this without updating all three places.

---

## Grafana Dashboards

Grafana runs on port `3001`. Access via `http://grafana.littlewolfacres.com:3001`
or directly at `http://192.168.0.21:3001`.

Dashboards are **provisioned from disk** — JSON files downloaded by Ansible into
`/var/lib/grafana/dashboards/`. They survive Grafana restarts and re-deploys without
needing manual re-import. Do not rely on dashboards imported manually through the UI;
add them to the Grafana Ansible role instead.

| Dashboard | File | Grafana ID | Purpose |
|-----------|------|-----------|---------|
| Node Exporter Full | `node-exporter-full.json` | 1860 | Full host metrics for Watchtower and Monolith |
| k3s Cluster | `k3s-cluster.json` | 15661 | Kubernetes cluster overview |

### Using Node Exporter Full

The dashboard has two template variables at the top:

- **Job** — select `watchtower` or `monolith`
- **Node** — auto-populates to `watchtower` or `monolith` once a job is selected

If the dashboard shows no data after a restart, the variable selection has reset. Select
a job from the dropdown and data will return immediately. This is also why the dashboard
is now provisioned via Ansible — variable defaults are persisted in the JSON, so on
first load after a restart the dashboard defaults to showing `watchtower`.

### Adding a new dashboard

1. Find the Grafana Labs dashboard ID at `https://grafana.com/grafana/dashboards/`
2. Add a `get_url` task to `roles/grafana/tasks/main.yml` following the pattern for ID 1860
3. Commit, push, and let the deploy workflow apply it — no manual import needed

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

# Check storage size
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

# Deploy only exporters
ansible-playbook -i inventory.ini playbooks/exporters.yml \
  --vault-password-file=~/homelab/.vault_pass
```

The `monitoring.yml` playbook applies roles in order:
`prometheus → alertmanager → netdata → grafana → daily_summary → argus → nut`

Changes to any of these role templates require a `monitoring.yml` run to take effect.
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

2. **Check dashboard variable selection:**
   Open the dashboard → check the Job and Node dropdowns at the top. If blank or
   showing `node-exporter` (old convention), select `watchtower` or `monolith`.

3. **Check Grafana data source:**
   Grafana → Configuration → Data Sources → Prometheus → Test. Should succeed.

4. **Check if the daily summary fired correctly:**
   If the `#sentinel` morning report had real numbers, Prometheus is healthy — the
   issue is in Grafana only (data source, variable, or provisioning).

5. **Check Grafana logs:**
   ```bash
   journalctl -fu grafana-server
   ```

### Prometheus alert not firing when expected

```bash
# Check the rule is loaded
curl -s http://192.168.0.21:9090/api/v1/rules | python3 -m json.tool | grep -A5 'AlertName'

# Manually evaluate the expression in Prometheus UI
# http://192.168.0.21:9090/graph — paste the expr from alert_rules.yml

# Validate config is syntactically correct
promtool check rules /etc/prometheus/alert_rules.yml
```

### Alert firing but no Slack message

```bash
# Check Alertmanager received the alert
curl -s http://192.168.0.21:9093/api/v2/alerts | python3 -m json.tool

# Check Alertmanager routing config is live
curl -s http://192.168.0.21:9093/api/v2/status | python3 -m json.tool

# Check Alertmanager logs for Slack delivery errors
journalctl -fu alertmanager -n 100
```

### Daily summary not posting to Slack

```bash
# Check timer is active
systemctl status daily-summary.timer

# Check last service run result
systemctl status daily-summary.service

# Run manually and watch output
sudo systemctl start daily-summary.service
journalctl -u daily-summary.service -n 50

# Common causes:
# - Slack webhook URL rotated (update vault.yml, re-run monitoring.yml)
# - Prometheus unreachable (check prometheus service)
# - Script has Python syntax error (check journald output)
```

### Scrape target is down

```bash
# Identify which target
curl -s http://192.168.0.21:9090/api/v1/targets | python3 -m json.tool | grep -B5 '"health":"down"'

# For node_exporter targets — check the exporter service on the host
systemctl status node_exporter        # on watchtower
# On monolith:
ssh gh-runner@monolith.littlewolfacres.com "systemctl status node_exporter"

# For SNMP targets — verify device is reachable
snmpwalk -v2c -c littlewolfacres 192.168.0.1 1.3.6.1.2.1.1.1.0
```

---

## Label Conventions

Consistent labels across the stack — changing these requires updating Prometheus config,
alert rules, and the daily summary script simultaneously.

| Label | Values | Notes |
|-------|--------|-------|
| `job` | `watchtower`, `monolith`, `adguard`, `blackbox`, `snmp-*`, `tmobile`, `reolink_nvr` | Identifies the scrape job / service type |
| `instance` | `watchtower`, `monolith` | Relabeled from raw address — clean hostnames only |
| `severity` | `warning`, `critical` | Used in Alertmanager routing and Slack formatting |
| `host` | `watchtower`, `monolith` | Custom label on alert rules for quick identification |

> The `instance` relabeling was introduced in May 2026 to fix Grafana's Node Exporter Full
> dashboard losing variable selections on restart. Previously `instance` was `localhost:9100`
> for Watchtower, which didn't match dashboard variable defaults.
