"""Run the role's manager detection/stop/verification with an isolated fake systemctl."""
from pathlib import Path
import os
import socket
import subprocess
import tempfile
import yaml

role = Path(__file__).resolve().parents[1] / "roles/wmux_remove/tasks/main.yml"
source = yaml.safe_load(role.read_text())
names = {
    "Check for a running user service manager",
    "Inspect wmux user unit",
    "Inspect wmux activity independently of its unit file",
    "Stop wmux even if its unit file has already been removed",
    "Verify wmux is no longer running",
}
for initial, load, broken in [("active", "loaded", False), ("active", "not-found", False),
                              ("inactive", "not-found", False), ("active", "loaded", True)]:
    with tempfile.TemporaryDirectory(prefix="wmux-stop-") as directory:
        root = Path(directory)
        runtime = root / "runtime"
        (runtime / "systemd").mkdir(parents=True)
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(runtime / "systemd/private"))
        assert not (runtime / "bus").exists()
        state = root / "state"
        state.write_text(initial)
        fake = root / "systemctl"
        fake.write_text("#!/usr/bin/env python3\n" +
            "import sys\nfrom pathlib import Path\n" +
            f"p=Path({str(state)!r})\n" +
            f"load={load!r}\nbroken={broken!r}\n" +
            "if 'stop' in sys.argv:\n    if not broken: p.write_text('inactive')\n" +
            "elif '--property=LoadState' in sys.argv: print(load)\n" +
            "else: print(p.read_text())\n")
        fake.chmod(0o700)
        tasks = yaml.safe_load(yaml.safe_dump([t for t in source if t['name'] in names]))
        for task in tasks:
            task.pop("become_user", None)
            task.pop("environment", None)
            if "ansible.builtin.stat" in task:
                original = task["ansible.builtin.stat"]["path"]
                task["ansible.builtin.stat"]["path"] = original.replace(
                    "/run/user/{{ dev_uid.stdout }}", str(runtime))
            if "ansible.builtin.command" in task:
                task["ansible.builtin.command"] = task["ansible.builtin.command"].replace(
                    "systemctl", str(fake), 1)
        play = root / "test.yml"
        play.write_text(yaml.safe_dump([{"hosts": "localhost", "gather_facts": False, "tasks": tasks}]))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(play)],
            capture_output=True, text=True,
            env={**os.environ, "ANSIBLE_LOCAL_TEMP": str(root / "ansible"), "ANSIBLE_NOCOLOR": "1"})
        assert (result.returncode == 0) == (not broken), result.stdout + result.stderr
        if not broken:
            assert state.read_text() == "inactive", result.stdout
        else:
            assert "Verify wmux is no longer running" in result.stdout
        sock.close()
print("wmux stops without session D-Bus, handles missing units, and rejects a surviving process.")
