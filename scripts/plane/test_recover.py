import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recover


class RecoveryTests(unittest.TestCase):
    def test_unreviewed_backend_refused(self):
        pod = {"status": {"containerStatuses": [{"name": "plane-api",
               "state": {"running": {}}, "imageID": "example@sha256:changed"}]}}
        with patch.object(recover, "run", return_value=json.dumps({"items": [pod]}).encode()):
            with self.assertRaisesRegex(RuntimeError, "digest"):
                recover.api_pod()

    def test_verification_commands_compile(self):
        calls = []
        with patch.object(recover, "run", side_effect=lambda *a, **k: calls.append(a)):
            recover.verify()
        code = [args[-1] for args in calls if "python" in args]
        self.assertEqual(len(code), 3)
        for source in code:
            compile(source, "verification", "exec")

    def test_unknown_migration_refused(self):
        with patch.object(recover, "run", return_value=b"[ ]  db.9999_unreviewed\n"):
            with self.assertRaisesRegex(RuntimeError, "unreviewed"):
                recover.pending({"metadata": {"name": "plane-api-example"}})

    def test_no_ack_cannot_contact_cluster(self):
        with patch.object(recover, "run") as command:
            with self.assertRaises(RuntimeError):
                recover.recover(False)
            command.assert_not_called()

    def test_readonly_plan(self):
        with patch.object(recover, "run", return_value=b"[X]  db.0001_initial\n") as command:
            self.assertEqual(recover.pending({"metadata": {"name": "example"}}), set())
            self.assertIn("PGOPTIONS=-c default_transaction_read_only=on", command.call_args.args)

    def scenario(self, backup_error=None, changed_pod=False):
        pod = {"metadata": {"name": "plane-api-example", "uid": "original"}}
        replacement = {"metadata": {"name": "replacement", "uid": "replacement"}}
        order = []
        def save(directory):
            order.append("backup")
            if backup_error:
                raise RuntimeError(backup_error)
        def command(*args, **kwargs):
            order.append("migrate")
            self.assertIn("migrate", args)
        original_umask = os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
                root = Path(temp)
                stack.enter_context(patch.object(recover, "BACKUP_ROOT", root))
                stack.enter_context(patch.object(recover, "LOCK_PATH", root / "lock"))
                stack.enter_context(patch.object(recover.os, "geteuid", return_value=0))
                # Unit tests run unprivileged in CI. Only ownership is mocked.
                real_stat = Path.stat
                def stat(path, *args, **kwargs):
                    value = real_stat(path, *args, **kwargs)
                    if path == root:
                        fields = list(value); fields[4] = 0
                        return os.stat_result(fields)
                    return value
                stack.enter_context(patch.object(Path, "stat", stat))
                stack.enter_context(patch.object(recover.socket, "gethostname", return_value="monolith"))
                stack.enter_context(patch.object(recover, "get", return_value={"status": {"succeeded": 1}}))
                stack.enter_context(patch.object(recover, "api_pod", side_effect=[pod, replacement if changed_pod else pod, pod]))
                stack.enter_context(patch.object(recover, "pending", side_effect=[recover.EXPECTED, recover.EXPECTED, set()]))
                stack.enter_context(patch.object(recover, "backup", side_effect=save))
                stack.enter_context(patch.object(recover, "run", side_effect=command))
                stack.enter_context(patch.object(recover, "verify", side_effect=lambda: order.append("verify")))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if backup_error or changed_pod:
                    with self.assertRaises(RuntimeError):
                        recover.recover(True)
                    self.assertEqual(order, ["backup"])
                else:
                    recover.recover(True)
                    self.assertEqual(order, ["backup", "migrate", "verify"])
        finally:
            os.umask(original_umask)

    def test_backup_failure_prevents_migration(self):
        self.scenario(backup_error="archive invalid")

    def test_replaced_pod_prevents_migration(self):
        self.scenario(changed_pod=True)

    def test_backup_precedes_migration_and_verification(self):
        self.scenario()


if __name__ == "__main__":
    unittest.main()
