#!/usr/bin/env python3
"""Read-only UPS/shutdown inventory. Never read credential files or send UPS commands."""
import json
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
for unit in ("nut-server", "nut-monitor", "nut-driver.target", "construct", "k3s"):
    report["services"][unit] = run(["systemctl", "show", unit, *["--property=" + p for p in properties]])

if host == "watchtower":
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

print(json.dumps(report, indent=2))
