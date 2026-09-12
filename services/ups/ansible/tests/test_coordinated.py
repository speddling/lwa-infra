"""Policy simulation and actual assertion tests; never run a power command."""
import importlib.machinery
import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch
import yaml
from jinja2 import Environment, StrictUndefined

root = Path(__file__).resolve().parents[1]
files = root / 'roles/coordinated/files'
loader = importlib.machinery.SourceFileLoader('ups_policy', str(files / 'lwa-ups-policy'))
spec = importlib.util.spec_from_loader(loader.name, loader)
policy = importlib.util.module_from_spec(spec)
loader.exec_module(policy)


class PolicyTests(unittest.TestCase):
    def test_five_minutes_and_single_signal(self):
        trigger = Mock()
        state, due = policy.tick({}, 'OB', 0, True, trigger)
        self.assertFalse(due)
        state, due = policy.tick(state, 'OB', 299, True, trigger)
        trigger.assert_not_called()
        state, due = policy.tick(state, 'OB', 300, True, trigger)
        self.assertTrue(due)
        policy.tick(state, 'OB', 400, True, trigger)
        trigger.assert_called_once()

    def test_restoration_resets_grace(self):
        state, _ = policy.decide({}, 'OB', 0)
        state, due = policy.decide(state, 'OL', 299)
        self.assertEqual(state, {})
        state, due = policy.decide(state, 'OB', 301)
        self.assertFalse(due)
        self.assertFalse(policy.decide(state, 'OB', 600)[1])
        self.assertTrue(policy.decide(state, 'OB', 601)[1])

    def test_unknown_preserves_elapsed_without_triggering(self):
        state, _ = policy.decide({}, 'OB', 0)
        later, due = policy.decide(state, None, 400)
        self.assertEqual(later, state)
        self.assertFalse(due)
        self.assertTrue(policy.decide(later, 'OB', 405)[1])

    def test_critical_and_reserve_override_grace_only_on_battery(self):
        self.assertTrue(policy.decide({}, 'OB LB', 0)[1])
        self.assertTrue(policy.decide({}, 'OB', 0, 600)[1])
        self.assertFalse(policy.decide({}, 'OB', 0, 601)[1])
        self.assertFalse(policy.decide({}, 'OL', 0, 100)[1])
        self.assertFalse(policy.decide({}, 'OB', 0, None)[1])

    def test_observation_never_signals(self):
        trigger = Mock()
        state, due = policy.tick({}, 'OB LB', 0, False, trigger)
        self.assertTrue(due)
        policy.tick(state, 'OB', 999, False, trigger, runtime=50)
        trigger.assert_not_called()

    def test_failed_signal_can_retry(self):
        state, _ = policy.decide({}, 'OB', 0)
        trigger = Mock(side_effect=subprocess.CalledProcessError(1, 'mock'))
        with self.assertRaises(subprocess.CalledProcessError):
            policy.tick(state, 'OB', 301, True, trigger)
        self.assertNotIn('fsd_sent', state)
        trigger = Mock()
        policy.tick(state, 'OB', 306, True, trigger)
        trigger.assert_called_once()

    def test_saved_state_survives_policy_restart(self):
        import json
        state, _ = policy.decide({}, 'OB', 10)
        restored = json.loads(json.dumps(state))
        self.assertTrue(policy.decide(restored, 'OB', 310)[1])


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('ups_auth', str(files / 'lwa-ups-auth-check'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.auth = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.auth)

    def test_credentials_are_used_only_for_login_not_power_commands(self):
        connection = MagicMock()
        stream = connection.__enter__.return_value.makefile.return_value
        stream.readline.return_value = b'OK\n'
        config = 'MONITOR cyberpower@127.0.0.1 1 test-user test-password primary\n'
        with patch.object(Path, 'read_text', return_value=config), patch.object(self.auth.socket, 'create_connection', return_value=connection):
            self.auth.check()
        writes = [call.args[0] for call in stream.write.call_args_list]
        self.assertEqual(writes, [b'USERNAME test-user\n', b'PASSWORD test-password\n', b'LOGIN cyberpower\n', b'PRIMARY cyberpower\n', b'LOGOUT\n'])
        self.assertFalse(any(b'FSD' in value or b'INSTCMD' in value for value in writes))

    def test_monitor_count_does_not_count_the_probe_as_a_login(self):
        for count, allowed in [(1, False), (2, True)]:
            connection = MagicMock()
            stream = connection.__enter__.return_value.makefile.return_value.__enter__.return_value
            stream.readline.return_value = f'NUMLOGINS cyberpower {count}\n'.encode()
            with patch.object(self.auth.socket, 'create_connection', return_value=connection):
                if allowed:
                    self.auth.require_two_monitors()
                else:
                    with self.assertRaises(ValueError):
                        self.auth.require_two_monitors()
            stream.write.assert_called_once_with(b'GET NUMLOGINS cyberpower\n')


class ConfigTests(unittest.TestCase):
    def test_monitor_roles_and_no_output_powercut(self):
        env = Environment(undefined=StrictUndefined)
        template = env.from_string((root / 'roles/coordinated/templates/upsmon.conf.j2').read_text())
        for host, role in [('watchtower', 'primary'), ('monolith', 'secondary')]:
            rendered = template.render(inventory_hostname=host, nut_server_address='127.0.0.1',
                                       nut_login='fixture', nut_login_password='fixture')
            directives = [line for line in rendered.splitlines() if line and not line.startswith('#')]
            self.assertTrue(directives[0].endswith(role))
            self.assertFalse(any(line.startswith('POWERDOWNFLAG') for line in directives))
            self.assertIn('SHUTDOWNCMD "/usr/bin/systemctl poweroff"', directives)

    def test_construct_inventory_host_pin_resolves(self):
        self.assertTrue((root / '../../construct/ansible/files/construct_known_hosts').resolve().is_file())
        self.assertIn('../../construct/ansible/files/construct_known_hosts', (root / 'inventory.ini').read_text())

    def test_activation_gate_defaults_closed(self):
        plays = yaml.safe_load((root / 'playbooks/activate-shutdown.yml').read_text())
        gate = plays[1]['tasks'][0]
        self.run_gate(gate, {}, False)
        self.run_gate(gate, {'activate_shutdown': True}, True)

    def test_maintenance_gate_defaults_closed(self):
        plays = yaml.safe_load((root / 'playbooks/apply-kubelet.yml').read_text())
        gate = plays[0]['tasks'][0]
        self.run_gate(gate, {'ansible_facts': {'hostname': 'monolith'}}, False)
        self.run_gate(gate, {'ansible_facts': {'hostname': 'monolith'}, 'maintenance_ack': True}, True)

    def test_k3s_version_gate(self):
        plays = yaml.safe_load((root / 'playbooks/prepare-shutdown.yml').read_text())
        gate = next(t for t in plays[0]['pre_tasks'] if t['name'] == 'Check k3s version supports the configuration directory')
        for version, allowed in [('k3s version v1.32.0+k3s1\ngo version go1.23.4', True),
                                 ('k3s version v1.34.1+k3s1', True),
                                 ('k3s version v1.31.9+k3s1', False),
                                 ('unrecognized output', False), ('', False)]:
            self.run_gate(gate, {'ups_target': 'monolith', 'k3s_version': {'stdout': version}}, allowed)

    def test_outage_and_fsd_block_readiness(self):
        plays = yaml.safe_load((root / 'playbooks/readiness.yml').read_text())
        gate = next(t for t in plays[0]['tasks'] if t['name'] == 'Reject activation during an outage or committed shutdown')
        for status, allowed in [('OL', True), ('OB', False), ('OL FSD', False), ('OL LB', False), ('', False)]:
            self.run_gate(gate, {'live_status': {'stdout': status}}, allowed)

    def run_gate(self, gate, variables, expected):
        with tempfile.TemporaryDirectory(prefix='ups-gate-') as directory:
            play = Path(directory) / 'test.yml'
            play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                'vars': variables, 'tasks': [gate, {'ansible.builtin.debug': {'msg': 'GATE_PASSED'}}]}]))
            result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
                capture_output=True, text=True, env={**os.environ, 'ANSIBLE_LOCAL_TEMP': directory})
            self.assertEqual(result.returncode == 0, expected, result.stdout + result.stderr)
            self.assertEqual('GATE_PASSED' in result.stdout, expected)
            if not expected:
                self.assertIn('evaluated_to', result.stdout)


if __name__ == '__main__':
    unittest.main()
