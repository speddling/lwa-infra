"""Exercise address delay, retry bounds and listener failure without host changes."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch

path = Path(__file__).resolve().parents[1] / 'roles/nut_network/files/lwa-nut-network-ready'
loader = importlib.machinery.SourceFileLoader('nut_network', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
network = importlib.util.module_from_spec(spec)
loader.exec_module(network)


class ReadinessTests(unittest.TestCase):
    def test_waits_for_delayed_address(self):
        check = Mock(side_effect=[OSError('not available'), None])
        pause = Mock()
        network.wait(check, 90, clock=Mock(side_effect=[0, 1]), pause=pause)
        self.assertEqual(check.call_count, 2)
        pause.assert_called_once_with(1)

    def test_timeout_fails_instead_of_starting_loopback_only(self):
        check = Mock(side_effect=OSError('not available'))
        with self.assertRaises(OSError):
            network.wait(check, 90, clock=Mock(side_effect=[0, 90]), pause=Mock())

    def test_address_probe_binds_only_an_ephemeral_port(self):
        connection = MagicMock()
        with patch.object(network.socket, 'socket', return_value=connection):
            network.address_ready()
        connection.__enter__.return_value.bind.assert_called_once_with(('192.168.30.11', 0))
        connection.__enter__.return_value.listen.assert_not_called()

    def test_missing_lan_listener_fails_even_with_loopback_working(self):
        with patch.object(network.socket, 'create_connection', side_effect=[MagicMock(), OSError('refused')]) as connect:
            with self.assertRaises(OSError):
                network.listeners_ready()
        self.assertEqual([c.args[0] for c in connect.call_args_list], [('127.0.0.1', 3493), ('192.168.30.11', 3493)])

    def test_both_listeners_succeed_without_sending_commands(self):
        connection = MagicMock()
        with patch.object(network.socket, 'create_connection', return_value=connection):
            network.listeners_ready()
        connection.__enter__.return_value.sendall.assert_not_called()

    def test_unknown_mode_is_rejected(self):
        self.assertEqual(network.main(['--unknown']), 2)


if __name__ == '__main__':
    unittest.main()
