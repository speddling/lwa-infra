# LWA Infra -- Daily Summary
> Last updated: 2026-06-16

Two reports per day, 8 AM and 8 PM (America/New_York), posted to `#sentinel` via Slack.
Driven by a **systemd timer** on Watchtower — no Alertmanager involvement, no timing drift on deploys.

---

## What the current report shows

| Section | Source | Metric |
|---|---|---|
| Monolith online | node_exporter | `up{job="monolith"}` |
| Monolith CPU (12 h avg) | node_exporter | `rate(node_cpu_seconds_total{mode="idle"}[5m])` averaged over 12 h |
| Monolith memory | node_exporter | `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes` |
| Monolith disk `/` | node_exporter | `node_filesystem_avail_bytes{mountpoint="/"}` |
| Monolith music library (`/mnt/hdd-c`) | node_exporter | `node_filesystem_avail_bytes{mountpoint="/mnt/hdd-c"}` |
| Monolith mirror (`/mnt/hdd-d`) | node_exporter | `node_filesystem_avail_bytes{mountpoint="/mnt/hdd-d"}` |
| Watchtower online | node_exporter | `up{job="watchtower"}` |
| Watchtower CPU / memory / disk | node_exporter | same as Monolith, `instance="localhost:9100"` |
| AdGuard online | adguard_exporter | `up{job="adguard"}` |

---

## What else is available (roadmap)

### AdGuard DNS (`adguard_exporter` on port 9618)
Confirm metric names by querying `http://localhost:9090/api/v1/label/__name__/values` and filtering for `adguard_`.

Likely available:
- `adguard_num_dns_queries_total` — total DNS queries since last AdGuard restart
- `adguard_num_blocked_filtering_total` — queries blocked by filter lists
- `adguard_num_replaced_safesearch_total` — safe-search substitutions
- `adguard_num_replaced_parental_total` — parental control blocks
- Derived: block rate = `blocked / total * 100`

**Suit-level language:** "Your network handled X DNS lookups since the last report. Y% were blocked — ads, trackers, or malicious domains that never reached your devices."

### T-Mobile Gateway (`tmobile_exporter` on port 9719)
Confirm metric names by filtering for `tmobile_` or `gateway_`.

Likely available:
- Signal strength / RSSI / RSRQ / RSRP
- Connected band (4G LTE vs 5G)
- Gateway uptime

**Suit-level language:** "Home internet is up and connected on 5G. Signal quality: good."

### Reolink NVR (`reolink_exporter` on port 9720)
Confirm metric names by filtering for `reolink_`.

Likely available:
- Camera online/offline status per channel
- Recording status

**Suit-level language:** "All 4 cameras are recording normally." or "Camera [name] went offline at [time]."

### Active alerts in the reporting window
Use the Prometheus `ALERTS` metric:
```promql
count(ALERTS{alertstate="firing", severity!="info"})
```
Or for a list: query `ALERTS{alertstate="firing"}` and format each result's `alertname` label.

**Suit-level language:** "No issues flagged since the last report." or "1 issue flagged: MonolithLowDisk — storage on the music drive is above 80%."

### Mirror job health
The nightly mirror runs at 02:00 via systemd. Track last-run success by:
- Exposing `/var/log/mirror-hdd.log` via a Prometheus textfile collector, or
- Checking systemd unit state via `node_systemd_unit_state` metric (requires `--collector.systemd` on node_exporter)

**Suit-level language:** "Nightly backup completed successfully at 2:14 AM." or "Nightly backup did not run — check Grafana."

---

## Thresholds used for traffic-light icons

| Icon | Meaning | CPU / Memory / Disk |
|---|---|---|
| 🟢 | Healthy | < 70% |
| 🟡 | Warning | 70–84% |
| 🔴 | Critical | ≥ 85% |
| ❓ | Unknown | Prometheus query returned no data |

---

## Target output (fully built out)

```
🏠 Little Wolf Acres — Morning Summary
_Friday, May 16 at 8:00 AM_

Status: ✅ All systems nominal

💻 Monolith 🟢
  CPU (12 h avg): 🟢 8%   Memory: 🟢 52%
  Disk  /: 🟢 34%   Music library: 🟡 74%   Mirror: 🟡 74%

🖥️  Watchtower 🟢
  CPU (12 h avg): 🟢 4%   Memory: 🟢 31%   Disk: 🟢 19%

🛡️  DNS (AdGuard) 🟢
  14,302 lookups since last report   31% blocked

🌐 Internet 🟢
  Connected on 5G   Signal: good

📷 Cameras 🟢
  All 4 online and recording

No issues flagged since the last report.

Full dashboard: http://grafana.littlewolfacres.com:3001
```

---

## Operations

- Script: `/usr/local/bin/daily-summary.py` on Watchtower
- Check timer schedule: `systemctl status daily-summary.timer`
- Manual test run: `sudo systemctl start daily-summary.service`
- Logs: `journalctl -u daily-summary.service -n 50`
