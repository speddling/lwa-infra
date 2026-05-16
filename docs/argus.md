# Argus — Watchtower MCP Server

Argus is the MCP server running on Watchtower. It gives Claude structured,
read-only access to the live monitoring layer — configs, systemd state, logs,
and the Alertmanager and Prometheus APIs.

Named for the hundred-eyed giant of Greek mythology: perpetual vigilance,
nothing escapes notice.

---

## Role in the AI tooling stack

| Server | Host | Sees |
|---|---|---|
| **Scribe** | apex | Git — branch, commit, push, PR |
| **Synapse** | monolith | k3s cluster, Prometheus metrics, monolith filesystem |
| **Argus** | watchtower | Live monitoring configs, systemd, journald, Alertmanager API, Prometheus rules |

---

## Tools

### `fs_read_file(path)`
Read a file from an allowlisted directory on Watchtower.

**Allowed paths:** `/etc/alertmanager`, `/etc/prometheus`, `/etc/systemd/system`, `/usr/local/bin`, `/opt/argus`

Useful for:
- Comparing live `/etc/alertmanager/alertmanager.yml` against the repo template
- Verifying deployed `/usr/local/bin/daily-summary.py` matches `daily-summary.py.j2`
- Reading `/etc/systemd/system/daily-summary.timer` to confirm schedule

### `fs_list_dir(path)`
List a directory within the same allowlist.

### `systemd_status(unit)`
Run `systemctl status <unit> --no-pager` on Watchtower and return the output.

```
systemd_status("daily-summary.timer")
→ Shows next scheduled trigger, last run result, active state
```

### `journald_tail(unit, lines=50)`
Return recent journal entries for a systemd unit (max 200 lines).

```
journald_tail("daily-summary.service", lines=20)
→ Last 20 lines from the most recent summary run
```

### `alertmanager_alerts()`
Query the live Alertmanager API (`/api/v2/alerts`) and return all active alerts with their labels, severity, and description.

### `alertmanager_status()`
Query `/api/v2/status` and return the **live routing config** as Alertmanager has parsed it, plus version and uptime. This is the ground truth — what matters is what Alertmanager actually loaded, not what the repo template says.

### `prometheus_rules()`
Query `/api/v1/rules` and return all alert rules currently loaded by Prometheus, grouped by rule group, with each rule's current state (`inactive`, `pending`, `firing`).

---

## Deployment

- **Host:** `watchtower.littlewolfacres.com`
- **Port:** `9800` (UFW restricts to `apex` only — `192.168.0.19`)
- **User:** `argus` (dedicated system user, no shell, no home dir)
- **Venv:** `/opt/argus/venv`
- **Script:** `/opt/argus/server.py`
- **Transport:** Streamable HTTP (FastMCP)
- **MCP URL:** `http://watchtower.littlewolfacres.com:9800/mcp`

Deployed via the `argus` Ansible role, triggered by any push to `services/watchtower/**`
or `ansible/vars/**` on `master`.

### Operations

```bash
# Check status
systemctl status argus

# Logs
journalctl -u argus -n 50

# Restart
sudo systemctl restart argus
```

---

## Security

- Listens on all interfaces, UFW restricted to `192.168.0.19` (apex)
- Runs as the `argus` system user — no sudo, no shell
- Filesystem reads allowlisted in the systemd `Environment=` — not user-supplied at runtime
- Unit name validation for `systemd_status` and `journald_tail` — regex whitelist, no shell passthrough (`subprocess` list args only)
- No write tools — Argus is read-only by design
