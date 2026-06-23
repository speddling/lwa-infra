# LWA Infra -- Monitoring Runbook
> Last updated: 2026-06-16

---

## Architecture Overview

All monitoring services run as **systemd units on Watchtower** (`192.168.0.21`).
There are no monitoring pods in k3s — Prometheus scrapes Monolith's node_exporter remotely over the LAN.

```
Watchtower (192.168.0.21)
├── prometheus          :9090   — metrics store & alert evaluation
├── alertmanager        :9093   — alert routing → Slack #sentinel + healthchecks.io watchdog
├── loki                :3100   — log aggregation, 60d retention, filesystem storage
├── promtail            :9080   — log shipper: Watchtower journal + ER605 syslog (:1514)
├── grafana-server      :3001   — dashboards (grafana.littlewolfacres.com)
├── node_exporter       :9100   — Watchtower host metrics
├── blackbox_exporter   :9115   — HTTP/ICMP probing
├── snmp_exporter       :9116   — network device metrics (ER605, 2× EAP245)
├── adguard_exporter    :9618   — AdGuard Home DNS stats
├── tmobile_exporter    :9719   — T-Mobile gateway signal/status
├── reolink_exporter    :9720   — NVR camera status
└── daily-summary       timer   — 8 AM + 8 PM Slack digest

Monolith (192.168.0.20 / monolith.littlewolfacres.com)
├── node_exporter             :9100   — Monolith host metrics (scraped remotely)
├── kube-state-metrics        :30900  — k3s object state metrics (NodePort)
├── argocd-application-controller :30885 — ArgoCD reconciliation metrics (NodePort)
├── argocd-server              :30883 — ArgoCD API/UI metrics (NodePort)
└── windows_exporter (Obelisk) :39182 — Win11 VM host metrics (NodePort, only up while VM is running)
```

> **Promtail depends on a healthy journal.** It reads Watchtower's systemd journal directly
> (`journalctl`-equivalent access via the `journal` scrape config). If the active journal is
> corrupted — most commonly after a dirty power loss — Promtail's reads can fail or skip
> entries from before the corruption point. See **Journald Health** below.

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
| `argocd-app-controller` | `monolith.littlewolfacres.com:30885` → labelled `instance=argocd` | ArgoCD reconciliation, sync status, app health |
| `argocd-server` | `monolith.littlewolfacres.com:30883` → labelled `instance=argocd` | ArgoCD API/UI availability and latency |
| `obelisk` | `monolith.littlewolfacres.com:39182` → labelled `instance=obelisk` | Win11 VM host metrics — scrape failures expected when the VM is off |
| `loki` | `localhost:3100` → relabeled `instance=watchtower` | Loki ingestion rate, chunk store size, query performance |
| `promtail` | `localhost:9080` → relabeled `instance=watchtower` | Promtail scrape lag, log line throughput |

> **WAN2 placeholder:** a commented `snmp-att-cgw450` job exists in `prometheus.yml.j2` for when
> AT&T Internet Air is installed. The CGW450 gateway has no unauthenticated local API like the
> T-Mobile FAST 5688W does — SNMP via the ER605-side interface is the only practical option.
> Uncomment and set `ip_att_gateway` in `ansible/vars/main.yml` when that WAN lands.

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
| `1.1.1.1` | icmp | WAN/internet connectivity — also the basis for the `WANDown` alert |

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

> **The Loki datasource is not provisioned by Ansible** — it was added manually through
> the Grafana UI (Connections → Data sources → Loki → `http://localhost:3100`). If Watchtower
> is ever rebuilt from scratch, that step needs to be repeated manually, or migrated into the
> Grafana role as a provisioned datasource file under `/etc/grafana/provisioning/datasources/`.

### Using Node Exporter Full

The dashboard has two template variables at the top:

- **Job** — select `watchtower` or `monolith`
- **Node** — auto-populates to `watchtower` or `monolith` once a job is selected

If panels show N/A after a restart, the variable selection reset. Open the Job
dropdown and select the host — data returns immediately.

### Querying logs in Grafana (Loki)

Use **Explore**, select the **Loki** datasource, and query with LogQL:

```logql
# All Watchtower systemd journal logs
{job="watchtower-journal"}

# Logs from a specific unit
{job="watchtower-journal", unit="tmobile_exporter.service"}

# Filter by journal priority level
{job="watchtower-journal", level="err"}

# ER605 syslog (empty until the ER605 is configured to send syslog — see WAN2 / ER605 Syslog below)
{job="er605-syslog"}
```

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

> **Jinja2 vs Go templates — escaping gotcha.** This file is rendered through Ansible's
> Jinja2 engine before Prometheus ever sees it. Annotation text that needs Prometheus's
> own Go-template variables (`$value`, `$labels.foo`) must be escaped so Ansible passes
> it through literally instead of trying to parse it: use `{{ "{{" }} $value {{ "}}" }}`,
> never raw `{{ $value }}`. Getting this wrong throws a Jinja2 syntax error on the
> `Deploy Prometheus alert rules` task — and because Ansible halts a play on task failure,
> every role *after* `prometheus` in `monitoring.yml` (`alertmanager`, `loki`, `promtail`,
> etc.) silently never runs. If a deploy appears to partially succeed — some roles clearly
> updated, others inexplicably untouched for days — check this file for an unescaped `$`
> before looking anywhere else.

### Active Prometheus alert rules

| Alert | Condition | Severity | Host |
|-------|-----------|----------|------|
| `WatchtowerHighCPU` | CPU > 85% for 5 min | warning | watchtower |
| `WatchtowerHighMemory` | Memory > 85% for 5 min | warning | watchtower |
| `WatchtowerLowDisk` | Disk `/` > 80% for 10 min | warning | watchtower |
| `WatchtowerCriticalDisk` | Disk `/` > 90% for 5 min | critical | watchtower |
| `WatchtowerPrometheusDown` | `up{job="prometheus"} == 0` for 2 min | critical | watchtower |
| `WatchtowerPrometheusTSDB` | TSDB blocks > 8GB (80% of 10GB retention limit) for 15 min | warning | watchtower |
| `WatchtowerNodeExporterDown` | `up{job="watchtower"} == 0` for 1 min | critical | watchtower |
| `AdGuardHomeDown` | `up{job="adguard"} == 0` for 1 min | critical | watchtower |
| `MonolithDown` | `up{job="monolith"} == 0` for 1 min | critical | monolith |
| `MonolithHighCPU` | CPU > 85% for 5 min | warning | monolith |
| `MonolithHighMemory` | Memory > 85% for 5 min | warning | monolith |
| `MonolithLowDisk` | Disk `/` > 80% for 5 min | critical | monolith |
| `MonolithLowDiskHddC` | Disk `/mnt/hdd-c` > 80% for 5 min | critical | monolith |
| `MonolithLowDiskHddD` | Disk `/mnt/hdd-d` > 80% for 5 min | warning | monolith |
| `ArgoCDAppOutOfSync` | App OutOfSync for 5 min | warning | monolith |
| `ArgoCDAppDegraded` | App health Degraded for 5 min | critical | monolith |
| `ArgoCDAppMissing` | App health Missing for 2 min | critical | monolith |
| `ArgoCDControllerDown` | `up{job="argocd-app-controller"} == 0` for 1 min | critical | monolith |
| `ArgoCDServerDown` | `up{job="argocd-server"} == 0` for 1 min | critical | monolith |
| `DeadManSwitch` | `vector(1)` — always firing | none | — |
| `WANDown` | `probe_success{instance="1.1.1.1"} == 0` for 3 min | critical | watchtower |
| `TMobileExporterDown` | `up{job="tmobile"} == 0` for 2 min | warning | watchtower |
| `TMobile4GSignalWeak` | 4G RSRP < -110 dBm for 10 min | warning | watchtower |
| `TMobile5GSignalWeak` | 5G RSRP < -110 dBm for 10 min | warning | watchtower |

All severity-bearing alerts route to Alertmanager → `#sentinel` Slack channel.
`DeadManSwitch` is routed separately — see **Alertmanager → Dead Man's Switch / Watchdog** below.

---

## Alertmanager

Routes all alerts to the `sentinel` contact point (Slack `#sentinel`).
Webhook URL is stored in Ansible Vault (`vault_slack_webhook_url`).

### RESOLVED notification format

FIRING and RESOLVED messages use different bodies so a recovery notice can't be
mistaken for a status report:

- **FIRING:** 🔴 title, includes the description and a `Fired at` timestamp
- **RESOLVED:** 🟢 `RECOVERED — <AlertName>` title, includes `Outage started` and
  `Recovered at` timestamps instead of repeating the firing description alone

This matters because a RESOLVED message is the *only* notification you'll see if an
alert fires and clears faster than Alertmanager's `group_wait` (30s) — which is common
right after a power outage, when Watchtower itself was down for the firing event and
only comes back up in time to send the resolution.

### Dead Man's Switch / Watchdog

Alertmanager going dark (power loss, crash) means it can't send FIRING alerts about its
own absence — Slack notifications depend on Alertmanager being alive to send them. The
`DeadManSwitch` alert (`vector(1)`, always firing) is routed to a dedicated `watchdog`
receiver that pings **healthchecks.io** every 5 minutes via webhook
(`vault_healthchecks_watchdog_url` in vault). If the pings stop, healthchecks.io emails
you independently of Slack, WAN state, or whether Watchtower is reachable at all.

```bash
# Confirm the watchdog route is live in the running config
curl -s http://192.168.0.21:9093/api/v2/status | python3 -m json.tool | grep -A5 watchdog

# Check Alertmanager's live routing tree (should show a child route
# matching alertname="DeadManSwitch" → receiver: watchdog)
curl -s http://192.168.0.21:9093/api/v2/status
```

Separately, `vault_healthchecks_daily_summary_url` is a **different** healthchecks.io
check used by the daily-summary timer (see below) — two independent checks, two
independent vault variables, do not conflate them.

### General operations

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

## Loki & Promtail

Log aggregation, added to give visibility into events that metrics alone don't
capture — WAN failover, exporter fetch failures, systemd unit restarts — and to
provide an event timeline that correlates with the metric graphs in Grafana.

### Architecture

- **Loki** runs monolithic mode (single binary, all components), filesystem storage
  under `/var/lib/loki`, 60-day retention.
- **Promtail** ships logs from two sources:
  - Watchtower's systemd journal (all units — captures `tmobile_exporter` fetch errors,
    `daily-summary` runs, `alertmanager`/`prometheus` events, etc.)
  - A syslog listener on UDP/TCP `1514` for the ER605 — **not yet wired up**. The ER605
    needs to be manually configured (System → Logs → Remote Syslog →
    `192.168.0.21:1514`) before any `{job="er605-syslog"}` data appears. This was
    deferred to land alongside the AT&T Internet Air WAN2 work.

### Service health checks

```bash
systemctl status loki promtail

journalctl -fu loki
journalctl -fu promtail
```

### Verifying ingestion

```bash
# Confirm both are healthy Prometheus scrape targets
curl -s 'http://192.168.0.21:9090/api/v1/query?query=up%7Bjob%3D~%22loki%7Cpromtail%22%7D' | python3 -m json.tool

# Query Loki directly via its HTTP API
curl -s 'http://192.168.0.21:3100/loki/api/v1/query?query={job="watchtower-journal"}' | python3 -m json.tool
```

Or use Grafana Explore with the Loki datasource — see **Grafana Dashboards → Querying
logs in Grafana** above.

### Troubleshooting

**No logs appear in Grafana Explore at all:**
1. Confirm the Loki datasource exists in Grafana (Connections → Data sources). It is
   **not** provisioned by Ansible — see the note under Grafana Dashboards above. If
   missing, add it manually: type Loki, URL `http://localhost:3100`, Save & Test.
2. Confirm `promtail.service` is active: `systemctl status promtail`
3. Confirm the `promtail` user is in the `systemd-journal` group (required to read the
   journal): `groups promtail`

**Promtail logs show journal read errors:**
The active journal may be corrupted — see **Journald Health** below.

**A whole deploy silently skipped Loki/Promtail despite the PR being merged:**
Check whether an earlier role in `monitoring.yml` (almost always `prometheus`, via a
template syntax error) failed and halted the play before reaching `loki`/`promtail` in
the role list. See the Jinja2/Go-template escaping note under **Alert Rules** above.
This exact failure mode happened once already — `prometheus` succeeded, `alertmanager`
failed silently on a bad template, and `loki`/`promtail` never ran for days despite the
merge showing complete on GitHub.

---

## Journald Health

Promtail's journal source makes journal integrity a monitoring-stack concern, not just
a host hygiene one. The most common cause of corruption is a dirty power loss — a torn
write at the tail of the active `system.journal` file, distinct from the rotated/archived
journal files, which are sealed and essentially never corrupt.

```bash
# Verify all journal files — this can take a while on a host with many archived files
sudo journalctl --verify

# A corrupted ACTIVE file shows as e.g.:
#   File corruption detected at /var/log/journal/<machine-id>/system.journal:<offset> (of <size> bytes, NN%).
#   FAIL: /var/log/journal/<machine-id>/system.journal (Bad message)
# Archived files (named system@<boot-id>-<seq>-<hash>.journal) almost never show this —
# if one of those fails, it's a different and more concerning class of problem.
```

**Recovery (safe, low-risk):**

```bash
# Seal the corrupted active file and start a clean one — does not delete anything yet
sudo journalctl --rotate

# Confirm a fresh system.journal was created (size should be the default ~8MB)
ls -la /var/log/journal/*/system.journal

# Re-verify — the corrupted file will now appear under its rotated name
# (no longer "system.journal"), confirming it's sealed and detached from active writes
sudo journalctl --verify

# Once confirmed sealed, the corrupted archived file is safe to remove —
# the lost entries are isolated to the brief window right around the power event
sudo rm /var/log/journal/*/system@<rotated-filename-from-verify-output>.journal
```

No data of practical concern is lost beyond the immediate corruption window — every
other archived journal file covering the rest of host history remains intact and
passes verification.

---

## Daily Summary

A Python script (`/usr/local/bin/daily-summary.py`) runs via systemd timer at
**8 AM and 8 PM America/New_York**, posting a health digest to `#sentinel`.

It queries Prometheus directly over HTTP and is completely independent of Alertmanager.
If the morning report populates correctly but Grafana shows no data, the issue is in
Grafana (dashboard variables, provisioning, data source) — not in Prometheus.

It also pings a **separate** healthchecks.io check (`vault_healthchecks_daily_summary_url`)
on each successful run — do not confuse this with the Alertmanager watchdog check
described above. Two checks, two purposes: this one confirms the digest script itself
ran; the watchdog confirms Alertmanager is alive at all times.

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

### Pending additions

Commented scrape job stubs already exist in `prometheus.yml.j2` for the incoming SG2218P
managed switch and the EAP225-Outdoor AP. Once those devices are installed and assigned
IPs, set `ip_sg2218p` / `ip_eap225_outdoor` in `ansible/vars/main.yml` and uncomment the
corresponding `snmp-sg2218p` / `snmp-eap-outdoor` jobs. See `docs/network-rebuild-plan.md`
for the full VLAN migration this is part of.

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
sudo k3s kubectl apply -f ~/lwa-homelab/kubernetes/manifests/kube-state-metrics.yml

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

## ArgoCD Metrics

ArgoCD's application-controller and server both expose Prometheus metrics via NodePort,
since Prometheus runs external to k3s and can't use in-cluster service discovery.

```bash
# Check both targets are healthy
curl -s http://192.168.0.21:9090/api/v1/targets | python3 -m json.tool | grep -A10 argocd

# Query reconciliation/sync status directly
curl -s 'http://192.168.0.21:9090/api/v1/query?query=argocd_app_info' | python3 -m json.tool
```

See the **Active Prometheus alert rules** table above for the five ArgoCD alerts
(`ArgoCDAppOutOfSync`, `ArgoCDAppDegraded`, `ArgoCDAppMissing`, `ArgoCDControllerDown`,
`ArgoCDServerDown`). For credential rotation and GitOps operations generally, see
`docs/homelab-state.md` → ArgoCD and `docs/runbook.md`.

---

## Service Health Checks

```bash
# All monitoring services at once
systemctl status prometheus alertmanager grafana-server loki promtail node_exporter \
  blackbox_exporter snmp_exporter adguard_exporter tmobile_exporter \
  reolink_exporter daily-summary.timer

# Live log tailing
journalctl -fu prometheus
journalctl -fu alertmanager
journalctl -fu grafana-server
journalctl -fu loki
journalctl -fu promtail
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
cd ~/lwa-homelab/services/watchtower/ansible

# Deploy full monitoring stack (Prometheus, Alertmanager, Loki, Promtail, Grafana, daily summary, Argus, NUT)
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass

# Dry run first
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --check --vault-password-file=~/lwa-homelab/.vault_pass

# Deploy only exporters (node_exporter, blackbox, snmp, adguard, reolink, tmobile)
ansible-playbook -i inventory.ini playbooks/exporters.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass
```

The `monitoring.yml` playbook applies roles **in order**:
`prometheus → alertmanager → loki → promtail → netdata → grafana → daily_summary → argus → nut`

**Order matters more than it looks.** Ansible halts a play on the first task failure with
no rescue block configured here. A failure in `prometheus` (most commonly a Jinja2
template error — see the note under **Alert Rules**) means every role listed after it
never runs at all, with no obvious error surfaced beyond the one failed task in the CI log.
If a deploy looks "mostly successful" but specific services seem stuck on old config,
check the role order against what's actually running before assuming the change didn't
get committed.

The GitHub Actions deploy workflow triggers automatically on push to `master` for paths
under `services/watchtower/**` or `ansible/vars/**`. Merges via PRs that only touch
`docs/**` do **not** trigger a redeploy — if a config change needs to go live and the
only paths touched are docs, you'll need `workflow_dispatch` (Actions → Deploy Watchtower
Config → Run workflow) instead of waiting on an automatic trigger.

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
curl -s 'http://192.168.0.21:9090/api/v1/query?query=probe_success' | python3 -m json.tool
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

### A whole deploy seems to have silently not happened

```bash
# Check the actual restart/start time of the service in question —
# if it predates the merge you're troubleshooting, the role never ran
systemctl status <service> | grep Active

# Check Alertmanager's LIVE config against the repo template —
# confirms whether the new config actually loaded, not just whether
# the file on disk looks right
curl -s http://192.168.0.21:9093/api/v2/status | python3 -m json.tool
```
Then check whether an earlier role in the `monitoring.yml` role list failed — see
**Ansible Deployment → Order matters more than it looks** above.

### Healthchecks.io watchdog ping never arrives

```bash
# Confirm the var exists in vault (will show ciphertext if not decrypted —
# run this on apex with the vault password available)
ansible-vault view ansible/vars/vault.yml | grep watchdog

# Confirm the route exists in Alertmanager's LIVE config
curl -s http://192.168.0.21:9093/api/v2/status | python3 -m json.tool | grep -A10 watchdog
```
If the var is missing from vault, the `Deploy alertmanager config` task fails on an
undefined-variable error at render time — same halting behavior described above, just
one role later in the chain.

### Loki / Promtail show no log data

See **Loki & Promtail → Troubleshooting** above.

### Journal corruption / Promtail read errors

See **Journald Health** above.

---

## Label Conventions

Consistent labels across the stack — changing these requires updating Prometheus config,
alert rules, and the daily summary script simultaneously.

| Label | Values | Notes |
|-------|--------|-------|
| `job` | `watchtower`, `monolith`, `adguard`, `blackbox`, `blackbox-http`, `blackbox-icmp`, `snmp-*`, `tmobile`, `reolink_nvr`, `kube-state-metrics`, `argocd-app-controller`, `argocd-server`, `obelisk`, `loki`, `promtail` | Identifies the scrape job / service type |
| `instance` | `watchtower`, `monolith`, `argocd`, `obelisk` (relabeled); raw address for others | Relabeled to clean hostnames for node_exporter and several NodePort-scraped jobs |
| `severity` | `warning`, `critical`, `none` (`DeadManSwitch` only) | Used in Alertmanager routing and Slack formatting |
| `host` | `watchtower`, `monolith` | Custom label on Prometheus alert rules — not present on `DeadManSwitch` or ArgoCD alerts, which use `host: monolith` for ArgoCD specifically since ArgoCD runs there |

> The `instance` relabeling for node exporters was introduced in May 2026 to fix the Grafana
> Node Exporter Full dashboard losing variable selections on Grafana restart.
