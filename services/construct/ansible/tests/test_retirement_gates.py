"""Exercise the real Ansible gates using local, assertion-only test plays."""
from pathlib import Path
import os
import subprocess
import tempfile

import yaml


source = Path(__file__).resolve().parents[1] / "playbooks/retire-remote-access.yml"
plays = yaml.safe_load(source.read_text())

with tempfile.TemporaryDirectory(prefix="retirement-gates-") as directory:
    env = {**os.environ, "ANSIBLE_LOCAL_TEMP": directory, "ANSIBLE_NOCOLOR": "1"}
    cases = [
        ("construct", {"construct": True, "monolith": False}, False, False),
        ("construct", {"construct": True, "monolith": True}, False, True),
        ("monolith", {"construct": True, "monolith": True}, False, False),
        ("monolith", {"construct": True, "monolith": True}, True, True),
    ]
    for target, preflight, verified, should_pass in cases:
        test_plays = []
        for host in ("construct", "monolith"):
            test_plays.append({
                "hosts": host, "gather_facts": False,
                "tasks": [{"ansible.builtin.set_fact": {
                    "retirement_preflight_passed": preflight[host],
                    "construct_retirement_verified": verified,
                }}],
            })
        gate = plays[1 if target == "construct" else 2]["pre_tasks"]
        test_plays.append({
            "hosts": target, "gather_facts": False,
            "tasks": gate + [{"ansible.builtin.debug": {"msg": "REMOVAL_ALLOWED"}}],
        })
        path = Path(directory) / "gate.yml"
        path.write_text(yaml.safe_dump(test_plays))
        result = subprocess.run(
            ["ansible-playbook", "-i", "construct,monolith,", "-c", "local", str(path)],
            env=env, capture_output=True, text=True,
        )
        passed = result.returncode == 0 and "REMOVAL_ALLOWED" in result.stdout
        assert passed == should_pass, result.stdout + result.stderr
        if not should_pass:
            assert "REMOVAL_ALLOWED" not in result.stdout, result.stdout
            assert "Assertion failed" in result.stdout, result.stdout + result.stderr
    print("Retirement gates reject missing verification and accept completed prerequisites.")
