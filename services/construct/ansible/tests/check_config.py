"""Validate rendered cloud-init and its embedded shell without executing it."""
from pathlib import Path
import subprocess

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[4]
ROLE = ROOT / "services/monolith/ansible/roles/construct-vm"
variables = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
variables.update(
    ansible_date_time={"iso8601": "2026-09-11T00:00:00Z"},
    ssh_public_key_construct="ssh-ed25519 AAAA-validation-only",
)
rendered = Environment(undefined=StrictUndefined).from_string(
    (ROLE / "templates/cloud-init-user-data.j2").read_text()
).render(**variables)
cloud = yaml.safe_load(rendered)
for snippet in cloud["write_files"]:
    subprocess.run(["bash", "-n"], input=snippet["content"], text=True, check=True)
for command in cloud["runcmd"]:
    if isinstance(command, str):
        subprocess.run(["bash", "-n"], input=command, text=True, check=True)

# Parse removal tasks too; ansible-playbook --syntax-check checks role/module
# resolution and play structure separately in CI, without touching live hosts.
for path in (ROOT / "services/construct/ansible").rglob("*.yml"):
    yaml.safe_load(path.read_text())

print("Cloud-init renders with declared defaults; YAML and shell syntax pass.")
