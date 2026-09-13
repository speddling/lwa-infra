#!/usr/bin/env python3
"""Read-only UPS/shutdown inventory. Never read credential files or send UPS commands."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import socket
import subprocess
import sys


def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return {"exit_code": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


expected = sys.argv[1] if len(sys.argv) == 2 else ""
host = socket.gethostname().split(".")[0]
if expected not in {"monolith", "watchtower"} or host != expected:
    sys.exit("Expected host does not match; refusing inspection.")

report = {"host": host}
report["packages"] = run(["dpkg-query", "-W", "-f=${Package} ${Version} ${Status}\n",
                          "nut-client", "nut-server", "qemu-system-x86", "systemd"])
report["tools"] = {tool: shutil.which(tool) for tool in ("upsc", "upsmon", "upssched", "qemu-system-x86_64")}
properties = ["LoadState", "ActiveState", "SubState", "TimeoutStopUSec", "KillMode", "KillSignal", "SendSIGKILL"]
report["services"] = {}
for unit in ("nut-server", "nut-monitor", "nut-driver.target", "construct", "k3s", "lwa-ups-policy"):
    report["services"][unit] = run(["systemctl", "show", unit, *["--property=" + p for p in properties]])

# Previous-boot evidence is read-only and scoped to shutdown-related services.
# Missing persistent journals are reported as missing evidence, not a passing test.
report["boot_history"] = run(["journalctl", "--list-boots", "--no-pager"])
report["previous_shutdown"] = run(["journalctl", "-b", "-1", "--no-pager",
    "-o", "short-iso-precise", "-n", "300", "-u", "nut-monitor.service",
    "-u", "lwa-ups-policy.service", "-u", "construct.service"])
report["previous_systemd_shutdown"] = run(["journalctl", "-b", "-1", "--no-pager",
    "-o", "short-iso-precise", "-n", "100", "_PID=1"])
report["previous_logind_shutdown"] = run(["journalctl", "-b", "-1", "--no-pager",
    "-o", "short-iso-precise", "-n", "100", "-u", "systemd-logind.service"])
# Bound expensive kubelet searches to the final ten minutes of the previous boot.
# A line limit alone still scans a long boot when few lines match the expression.
try:
    last_systemd_line = report["previous_systemd_shutdown"]["stdout"].splitlines()[-1]
    shutdown_end = datetime.fromisoformat(last_systemd_line.split()[0])
    shutdown_since = (shutdown_end - timedelta(minutes=10)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
except (KeyError, IndexError, ValueError):
    shutdown_since = None
report["shutdown_armed"] = Path("/etc/nut/lwa-shutdown-armed").is_file()
report["failed_units"] = run(["systemctl", "--failed", "--no-pager", "--no-legend"])
report["dns_recovery"] = run(["getent", "hosts", "watchtower.littlewolfacres.com"])

if host == "watchtower":
    probe = Path("/usr/local/sbin/lwa-ups-auth-check")
    if probe.is_file():
        report["persistent_monitors"] = run([str(probe), "--require-two-monitors"])
    report["current_policy_log"] = run(["journalctl", "-b", "0", "--no-pager",
        "-o", "short-iso-precise", "-n", "30", "-u", "lwa-ups-policy.service"])
    # USB manufacturer/product IDs and model text only; omit serial identifiers.
    report["usb_devices"] = []
    for device in sorted(Path("/sys/bus/usb/devices").glob("*")):
        if not (device / "idVendor").exists():
            continue
        item = {"bus_path": device.name}
        for field in ("idVendor", "idProduct", "manufacturer", "product"):
            try:
                item[field] = (device / field).read_text().strip()
            except OSError:
                pass
        report["usb_devices"].append(item)
    # Query individual public telemetry fields, never dump all server variables.
    if shutil.which("upsc"):
        report["ups_telemetry"] = {field: run(["upsc", "cyberpower@127.0.0.1", field])
            for field in ("ups.status", "ups.model", "ups.load", "battery.charge", "battery.runtime")}
    else:
        report["ups_telemetry"] = "upsc unavailable; no packages installed by this inspection"
else:
    if shutdown_since:
        report["previous_kubelet_shutdown"] = run(["journalctl", "-b", "-1", "--no-pager",
            "--since", shutdown_since, "-o", "short-iso-precise", "-n", "100",
            "-u", "k3s.service", "--grep", "(?i)shutdown|shutting down|inhibit|kill|timed out"])
    else:
        report["previous_kubelet_shutdown"] = {"error": "Cannot determine previous boot's final journal timestamp"}
    report["pods"] = run(["k3s", "kubectl", "--request-timeout=10s", "get", "pods", "-A",
        "-o", "custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount"])
    report["persistent_volume_claims"] = run(["k3s", "kubectl", "--request-timeout=10s", "get", "pvc", "-A",
        "-o", "custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase"])
    # Read only selected lifecycle directives. Do not dump unit environments.
    report["construct_stop"] = run(["systemctl", "show", "construct", "--property=ExecStop"])
    pid_result = run(["systemctl", "show", "construct", "--property=MainPID", "--value"])
    pid = pid_result.get("stdout", "")
    if pid.isdigit() and int(pid) > 0:
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
            # Expose monitor/agent capability, not arbitrary process arguments.
            report["construct_control_options"] = [
                {"option": arg, "value": argv[i + 1]}
                for i, arg in enumerate(argv[:-1])
                if arg in {"-qmp", "-monitor", "-chardev"}
            ]
        except OSError as exc:
            report["construct_control_options"] = {"error": str(exc)}
    report["watchtower_route"] = run(["ip", "route", "get", "192.168.30.11"])
    report["logind_limit"] = run(["busctl", "get-property", "org.freedesktop.login1",
        "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "InhibitDelayMaxUSec"])
    report["shutdown_inhibitors"] = run(["systemd-inhibit", "--list", "--no-pager", "--no-legend"])
    # Selected public directives and source filenames only; omit other configuration.
    config = run(["systemd-analyze", "cat-config", "systemd/logind.conf"])
    report["logind_delay_sources"] = {
        "exit_code": config.get("exit_code"),
        "lines": [line for line in config.get("stdout", "").splitlines()
                  if line.startswith("# /") or line.strip().startswith("InhibitDelayMaxSec=")],
        "stderr": config.get("stderr", ""),
    }
    report["node_ready"] = run(["k3s", "kubectl", "--request-timeout=10s", "get", "node",
        "monolith", "-o", "jsonpath={.status.conditions[?(@.type==\"Ready\")].status}"])


print(json.dumps(report, indent=2))
