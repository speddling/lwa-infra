"""Isolated process/SSH mocks and forced-command fixtures; no real power commands."""
import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
import os

files = Path(__file__).resolve().parents[1] / 'roles/graceful_shutdown/files'
loader = importlib.machinery.SourceFileLoader('construct_stop', str(files / 'construct-stop'))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class StopTests(unittest.TestCase):
    def exercise(self, events, ssh_result=0, timeout=False, bad_process=False):
        with patch.object(module.os, 'pidfd_open', return_value=42), \
             patch.object(module.os, 'close') as close, \
             patch.object(module, 'validate_process', side_effect=RuntimeError('wrong VM') if bad_process else None), \
             patch.object(module, 'exited', side_effect=events), \
             patch.object(module.subprocess, 'run', return_value=Mock(returncode=ssh_result),
                          side_effect=subprocess.TimeoutExpired('fake ssh', 15) if timeout else None) as run:
            try:
                module.stop(1234)
            finally:
                close.assert_called_once_with(42)
                if bad_process or events[0]:
                    run.assert_not_called()
                else:
                    self.assertEqual(run.call_args.args[0][-1], 'poweroff')

    def test_orderly_exit(self):
        self.exercise([False, False, True])

    def test_disconnect_during_shutdown_can_still_succeed(self):
        self.exercise([False, False, True], ssh_result=255)

    def test_ssh_timeout_still_waits_for_original_process(self):
        self.exercise([False, False, True], timeout=True)

    def test_unresponsive_guest_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'did not exit'):
            self.exercise([False, False, False])

    def test_wrong_process_never_sends_poweroff(self):
        with self.assertRaisesRegex(RuntimeError, 'wrong VM'):
            self.exercise([False], bad_process=True)

    def test_already_exited_never_sends_poweroff(self):
        self.exercise([True])

    def test_missing_process(self):
        with patch.object(module.os, 'pidfd_open', side_effect=ProcessLookupError), \
             patch.object(module.subprocess, 'run') as run:
            module.stop(1234)
            run.assert_not_called()

    def test_probe_rejects_wrong_identity(self):
        with patch.object(module.subprocess, 'run', return_value=Mock(returncode=0, stdout='wrong host')):
            with self.assertRaises(RuntimeError):
                module.probe()

    def test_probe_accepts_only_expected_response(self):
        with patch.object(module.subprocess, 'run', return_value=Mock(returncode=0, stdout='construct-power-control-ready\n')) as run:
            module.probe()
            self.assertEqual(run.call_args.args[0][-1], 'probe')

    def test_pid_identity_checks(self):
        with patch.object(module.os, 'readlink', return_value='/usr/bin/qemu-system-x86_64'), \
             patch.object(Path, 'read_bytes', return_value=b'qemu\0-drive\0file=/vm/construct/disk.img,if=virtio\0'), \
             patch.object(Path, 'read_text', return_value='0::/system.slice/construct.service\n'):
            module.validate_process(1234)
        for executable, disk, group in [
            ('/usr/bin/python3', b'file=/vm/construct/disk.img,', '0::/construct.service'),
            ('/usr/bin/qemu-system-x86_64', b'file=/mnt/ssd-b/obelisk.img,', '0::/construct.service'),
            ('/usr/bin/qemu-system-x86_64', b'file=/vm/construct/disk.img,', '0::/obelisk.service'),
        ]:
            with patch.object(module.os, 'readlink', return_value=executable), \
                 patch.object(Path, 'read_bytes', return_value=disk), \
                 patch.object(Path, 'read_text', return_value=group):
                with self.assertRaises(RuntimeError):
                    module.validate_process(1234)


class DispatcherTests(unittest.TestCase):
    def test_exact_commands_and_host_guard(self):
        with tempfile.TemporaryDirectory(prefix='power-dispatch-') as directory:
            root = Path(directory)
            hostname = root / 'hostname'
            sudo = root / 'sudo'
            log = root / 'calls'
            hostname.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_HOST"\n')
            sudo.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\nexit "${TEST_SUDO_RC:-0}"\n')
            hostname.chmod(0o700)
            sudo.chmod(0o700)
            script = root / 'dispatch'
            script.write_text((files / 'construct-power-control').read_text().replace('/bin/hostname', str(hostname)).replace('/usr/bin/sudo', str(sudo)))
            subprocess.run(['sh', '-n', str(script)], check=True)
            for command, host, sudo_rc, expected in [
                ('probe', 'construct', '0', 0), ('poweroff', 'construct', '0', 0),
                ('probe', 'construct', '1', 1), ('poweroff', 'monolith', '0', 1),
                ('', 'construct', '0', 64), ('poweroff; touch /tmp/no', 'construct', '0', 64),
                ('reboot', 'construct', '0', 64),
            ]:
                log.write_text('')
                result = subprocess.run(['sh', str(script)], capture_output=True, text=True,
                    env={**os.environ, 'SSH_ORIGINAL_COMMAND': command, 'TEST_HOST': host,
                         'TEST_LOG': str(log), 'TEST_SUDO_RC': sudo_rc})
                self.assertEqual(result.returncode, expected, result.stderr)
                if command not in ('probe', 'poweroff') or host != 'construct':
                    self.assertEqual(log.read_text(), '')
                elif command == 'poweroff':
                    self.assertEqual(log.read_text().strip(), '-n /usr/bin/systemctl --no-block poweroff')
                else:
                    self.assertEqual(log.read_text().strip(), '-n -l /usr/bin/systemctl --no-block poweroff')


if __name__ == '__main__':
    unittest.main()
