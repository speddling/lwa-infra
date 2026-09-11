"""Exercise the real preflight assertion without touching services or packages."""
import os
from pathlib import Path
import subprocess
import tempfile
import yaml

play = yaml.safe_load((Path(__file__).resolve().parents[1] / 'playbooks/telemetry.yml').read_text())[0]
gate = play['pre_tasks'][-1]
cases = [
    # hostname, legacy enabled, config exists, marker exists, monitor state, allowed
    ('watchtower', False, False, False, 'stopped', True),
    ('watchtower', False, True, True, 'stopped', True),
    ('monolith', False, False, False, 'stopped', False),
    ('watchtower', True, False, False, 'stopped', False),
    ('watchtower', False, True, False, 'stopped', False),
    ('watchtower', False, True, True, 'running', False),
]
for host, enabled, config, marker, state, allowed in cases:
    with tempfile.TemporaryDirectory(prefix='ups-gates-') as directory:
        variables = {
            'ansible_hostname': host, 'nut_enabled': enabled,
            'existing_config': {'stat': {'exists': config}},
            'telemetry_marker': {'stat': {'exists': marker}},
            'ansible_facts': {'services': {'nut-monitor.service': {'state': state}}},
        }
        path = Path(directory) / 'gate.yml'
        path.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
            'vars': variables, 'tasks': [gate, {'ansible.builtin.debug': {'msg': 'TELEMETRY_ALLOWED'}}]}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
            env={**os.environ, 'ANSIBLE_LOCAL_TEMP': directory}, capture_output=True, text=True)
        assert (result.returncode == 0) == allowed, result.stdout + result.stderr
        assert ('TELEMETRY_ALLOWED' in result.stdout) == allowed, result.stdout
        if not allowed:
            assert 'Refusing to replace existing NUT management' in result.stdout, result.stdout + result.stderr
print('Telemetry gates accept fresh/owned deployment and reject wrong hosts or existing shutdown management.')
