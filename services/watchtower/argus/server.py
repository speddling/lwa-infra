"""
argus — Local MCP server for Little Wolf Acres / Watchtower

Gives Claude structured, read-only access to Watchtower's live state:
filesystem (configs, deployed scripts), systemd service and timer status,
journald logs, and the Alertmanager + Prometheus HTTP APIs.

Counterpart to Synapse (Monolith) and Scribe (Apex).
Synapse has eyes on the k3s cluster; Argus has eyes on the monitoring layer.

Tools:
  fs_read_file        Read a file — path-allowlisted to safe directories
  fs_list_dir         List a directory — same allowlist
  systemd_status      systemctl status for a named unit (services and timers)
  journald_tail       Recent journal entries for a named unit
  alertmanager_alerts Active alerts from the Alertmanager API
  alertmanager_status Live routing config and version from the Alertmanager API
  prometheus_rules    Loaded alert rules from the Prometheus API

Transport: Streamable HTTP via FastMCP
Auth:      None — UFW on Watchtower restricts port 9800 to apex only
"""

import logging
import os
import pathlib
import re
import subprocess

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("argus")

ARGUS_PORT      = int(os.environ.get("ARGUS_PORT", "9800"))
PROMETHEUS_URL  = os.environ.get("PROMETHEUS_URL",  "http://localhost:9090")
ALERTMANAGER_URL = os.environ.get("ALERTMANAGER_URL", "http://localhost:9093")

ALLOWED_READ_PATHS = [
    p.strip()
    for p in os.environ.get(
        "ALLOWED_READ_PATHS",
        "/etc/alertmanager,/etc/prometheus,/etc/systemd/system,/usr/local/bin,/opt/argus",
    ).split(",")
    if p.strip()
]

# Unit names must be alphanumeric + a safe set of punctuation — no shell chars.
_UNIT_RE = re.compile(r"^[a-zA-Z0-9._@:-]+$")

mcp = FastMCP("argus", host="0.0.0.0", port=ARGUS_PORT)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_allowed(requested: str) -> bool:
    """Resolve symlinks and check against ALLOWED_READ_PATHS (no traversal)."""
    try:
        resolved = pathlib.Path(requested).resolve(strict=False)
        return any(
            str(resolved).startswith(str(pathlib.Path(p).resolve()))
            for p in ALLOWED_READ_PATHS
        )
    except Exception:
        return False


def _validate_unit(unit: str) -> None:
    if not _UNIT_RE.match(unit):
        raise ValueError(
            f"Invalid unit name '{unit}'. Only alphanumeric characters and "
            ". _ @ : - are allowed."
        )


# ---------------------------------------------------------------------------
# Filesystem tools
# ---------------------------------------------------------------------------

@mcp.tool()
def fs_read_file(path: str) -> str:
    """Read a file on Watchtower. Restricted to config and script directories.

    Allowed paths: /etc/alertmanager, /etc/prometheus, /etc/systemd/system,
    /usr/local/bin, /opt/argus.
    """
    if not _is_allowed(path):
        allowed = ", ".join(ALLOWED_READ_PATHS)
        return f"Access denied: '{path}' is outside allowed paths ({allowed})"
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_file():
        return f"Not a file: {path}"
    try:
        return resolved.read_text(errors="replace")
    except PermissionError:
        return f"Permission denied: {path}"


@mcp.tool()
def fs_list_dir(path: str) -> str:
    """List a directory on Watchtower. Restricted to config and script directories.

    Allowed paths: /etc/alertmanager, /etc/prometheus, /etc/systemd/system,
    /usr/local/bin, /opt/argus.
    """
    if not _is_allowed(path):
        allowed = ", ".join(ALLOWED_READ_PATHS)
        return f"Access denied: '{path}' is outside allowed paths ({allowed})"
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_dir():
        return f"Not a directory: {path}"
    entries = sorted(resolved.iterdir(), key=lambda e: (e.is_file(), e.name))
    return "\n".join(
        f"[{'FILE' if e.is_file() else 'DIR '}] {e.name}" for e in entries
    ) or "(empty)"


# ---------------------------------------------------------------------------
# Systemd tools
# ---------------------------------------------------------------------------

@mcp.tool()
def systemd_status(unit: str) -> str:
    """Show systemctl status for a service or timer on Watchtower.

    Includes active state, last run result, and — for timers — the next
    scheduled trigger time.

    Args:
        unit: Unit name including suffix, e.g. 'daily-summary.timer',
              'alertmanager.service', 'prometheus.service'.
    """
    _validate_unit(unit)
    result = subprocess.run(
        ["systemctl", "status", "--no-pager", "--lines=0", unit],
        capture_output=True,
        text=True,
    )
    # systemctl exits non-zero for inactive/failed units — still return output.
    output = (result.stdout + result.stderr).strip()
    return output or f"(no output for unit '{unit}')"


@mcp.tool()
def journald_tail(unit: str, lines: int = 50) -> str:
    """Return the most recent journal entries for a systemd unit on Watchtower.

    Args:
        unit:  Unit name including suffix, e.g. 'daily-summary.service'.
        lines: Number of log lines to return (default 50, max 200).
    """
    _validate_unit(unit)
    lines = max(1, min(lines, 200))
    result = subprocess.run(
        ["journalctl", "-u", unit, "--no-pager", f"-n{lines}",
         "--output=short-iso"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() or f"(no journal entries for '{unit}')"


# ---------------------------------------------------------------------------
# Alertmanager tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def alertmanager_alerts() -> str:
    """Return all currently active alerts from the Alertmanager API."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{ALERTMANAGER_URL}/api/v2/alerts")
        r.raise_for_status()
        alerts = r.json()

    if not alerts:
        return "No active alerts."

    lines = [f"{len(alerts)} active alert(s):", ""]
    for a in alerts:
        lb  = a.get("labels", {})
        an  = a.get("annotations", {})
        lines.append(
            f"  [{lb.get('alertname', '?')}]  severity={lb.get('severity', '?')}"
            f"  state={a.get('status', {}).get('state', '?')}"
        )
        if desc := an.get("description"):
            lines.append(f"    {desc}")
    return "\n".join(lines)


@mcp.tool()
async def alertmanager_status() -> str:
    """Return the live Alertmanager routing config and version via its API.

    Useful for confirming what is actually deployed vs what the repo template
    would generate.
    """
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{ALERTMANAGER_URL}/api/v2/status")
        r.raise_for_status()
        data = r.json()

    config = data.get("config", {}).get("original", "(not returned)")
    version_info = data.get("versionInfo", {})
    uptime = data.get("uptime", "?")

    lines = [
        f"Alertmanager {version_info.get('version', '?')}",
        f"Uptime: {uptime}",
        "",
        "— Live config ——————————————————————————",
        config,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prometheus tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def prometheus_rules() -> str:
    """Return all alert rules currently loaded by Prometheus.

    Confirms what rules are actually active vs what alert_rules.yml.j2
    would render.
    """
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(f"{PROMETHEUS_URL}/api/v1/rules")
        r.raise_for_status()
        data = r.json()

    groups = data.get("data", {}).get("groups", [])
    if not groups:
        return "No rule groups loaded."

    lines = []
    for group in groups:
        lines.append(f"Group: {group['name']}  (interval: {group.get('interval', '?')}s)")
        for rule in group.get("rules", []):
            if rule.get("type") == "alerting":
                state = rule.get("state", "?")
                lines.append(f"  [{state:>8}] {rule['name']}  — {rule.get('query', '')[:80]}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
