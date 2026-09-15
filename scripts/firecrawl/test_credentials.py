"""Credential handoff gates and a disposable PostgreSQL password-change test."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('firecrawl_credentials', Path(__file__).with_name('credentials.py'))
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


def fixture():
    data = {'POSTGRES_PASSWORD': 'changeme-fixture', 'OPENAI_API_KEY': 'changeme-openai',
            'PROXY_PASSWORD': 'changeme-proxy', 'OTHER_KEY': 'retain-me'}
    for key in ['DATABASE_URL', 'NUQ_DATABASE_URL']:
        data[key] = 'postgresql://firecrawl:changeme-fixture@firecrawl-postgres:5432/firecrawl'
    return {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
            'metadata': {'name': 'firecrawl-secret', 'namespace': 'firecrawl',
                         'uid': credentials.SECRET_UID, 'resourceVersion': '42',
                         'labels': {'app': 'firecrawl', 'app.kubernetes.io/instance': 'firecrawl'},
                         'annotations': {'argocd.argoproj.io/sync-options': 'Prune=false,Delete=false',
                                         'argocd.argoproj.io/tracking-id': 'fixture',
                                         'kubectl.kubernetes.io/last-applied-configuration': 'old-fixture'}},
            'data': {key: base64.b64encode(value.encode()).decode() for key, value in data.items()}}


class CredentialsTests(unittest.TestCase):
    def test_plan_keeps_identity_and_coordinates_urls(self):
        secret = fixture()
        original = copy.deepcopy(secret)
        planned = credentials.plan_secret(secret)
        values = credentials.values(planned)
        self.assertEqual(secret, original)
        self.assertEqual(planned['metadata']['uid'], secret['metadata']['uid'])
        self.assertEqual(planned['metadata']['resourceVersion'], '42')
        self.assertNotIn('argocd.argoproj.io/tracking-id', planned['metadata']['annotations'])
        self.assertNotIn('kubectl.kubernetes.io/last-applied-configuration', planned['metadata']['annotations'])
        self.assertNotIn('app.kubernetes.io/instance', planned['metadata']['labels'])
        self.assertEqual(planned['metadata']['labels']['app'], 'firecrawl')
        self.assertEqual(values['OTHER_KEY'], 'retain-me')
        self.assertEqual(values['OPENAI_API_KEY'], '')
        self.assertEqual(values['PROXY_PASSWORD'], '')
        self.assertEqual(credentials.urlsplit(values['NUQ_DATABASE_URL']).password, values['POSTGRES_PASSWORD'])
        self.assertEqual(credentials.urlsplit(values['NUQ_RABBITMQ_URL']).password, values['RABBITMQ_PASSWORD'])
        self.assertNotEqual(values['POSTGRES_PASSWORD'], values['RABBITMQ_PASSWORD'])

    def test_refuses_managed_or_mismatched_database_password(self):
        for key, value in [('POSTGRES_PASSWORD', 'already-private'),
                           ('DATABASE_URL', 'postgresql://wrong:changeme-fixture@other/db')]:
            secret = fixture()
            secret['data'][key] = base64.b64encode(value.encode()).decode()
            with self.assertRaises(RuntimeError):
                credentials.plan_secret(secret)

    def test_handoff_requires_exclusion_retention_and_same_uid(self):
        app = {'spec': {'source': {'path': 'services/firecrawl/kubernetes',
                                  'directory': {'exclude': 'secret.yaml'}}}}
        credentials.require_handoff(app, fixture())
        for source in [{}, {'path': 'services/firecrawl/kubernetes'}]:
            with self.assertRaises(RuntimeError):
                credentials.require_handoff({'spec': {'source': source}}, fixture())
        for field, value in [('uid', 'recreated'), ('annotations', {})]:
            secret = fixture()
            secret['metadata'][field] = value
            with self.assertRaises(RuntimeError):
                credentials.require_handoff(app, secret)

    def test_failed_secret_write_restores_original_password(self):
        secret = fixture()
        planned = credentials.plan_secret(secret)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(credentials, 'set_password') as set_password, \
                patch.object(credentials, 'run', side_effect=RuntimeError('conflict')), \
                patch.object(credentials, 'get', return_value=secret):
            with self.assertRaisesRegex(RuntimeError, 'original database password restored'):
                credentials.apply_credentials(secret, planned, Path(directory))
            self.assertEqual(set_password.call_args_list[-1].args, ('changeme-fixture',))
            self.assertTrue((Path(directory) / 'secret-planned.json').exists())

    def test_timed_out_successful_write_does_not_rollback(self):
        secret = fixture()
        planned = credentials.plan_secret(secret)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(credentials, 'set_password') as set_password, \
                patch.object(credentials, 'run', side_effect=subprocess.TimeoutExpired('kubectl', 120)), \
                patch.object(credentials, 'get', return_value=planned):
            credentials.apply_credentials(secret, planned, Path(directory))
            self.assertEqual(set_password.call_count, 1)

    def test_sql_injection_rejected_before_execution(self):
        with patch.object(credentials, 'sql') as sql:
            with self.assertRaises(RuntimeError):
                credentials.set_password("unsafe'; SELECT 1;")
            sql.assert_not_called()

    def test_failed_backup_prevents_all_credential_writes(self):
        secret = fixture()
        app = {'spec': {'source': {'path': 'services/firecrawl/kubernetes',
                                  'directory': {'exclude': 'secret.yaml'}}}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(credentials, 'LOCK_PATH', Path(directory) / 'lock'), \
                patch.object(credentials.os, 'geteuid', return_value=0), \
                patch.object(credentials.os, 'umask'), \
                patch.object(credentials.socket, 'gethostname', return_value='monolith'), \
                patch.object(credentials, 'get', side_effect=[secret, app]), \
                patch.object(credentials, 'require_unused'), \
                patch.object(credentials, 'verify_original_database'), \
                patch.object(credentials, 'backup', side_effect=RuntimeError('backup failed')), \
                patch.object(credentials, 'apply_credentials') as apply, \
                patch.object(credentials, 'reload_consumers') as reload:
            with self.assertRaisesRegex(RuntimeError, 'backup failed'):
                credentials.provision(True)
            apply.assert_not_called()
            reload.assert_not_called()


@unittest.skipUnless(os.environ.get('FIRECRAWL_TEST_POSTGRES_CONTAINER'), 'Hosted CI disposable PostgreSQL only')
class PostgreSQLTests(unittest.TestCase):
    def test_real_password_change_and_rollback(self):
        container = os.environ['FIRECRAWL_TEST_POSTGRES_CONTAINER']

        def sql(query):
            result = subprocess.run(['docker', 'exec', '-i', container, 'psql', '-X', '-qAt',
                                     '-U', 'firecrawl', '-d', 'firecrawl', '-v', 'ON_ERROR_STOP=1'],
                                    input=query.encode(), capture_output=True, check=True)
            return result.stdout

        def authenticates(password):
            return subprocess.run(['docker', 'exec', '-e', 'PGPASSWORD=' + password, container,
                                   'psql', '-h', '127.0.0.1', '-U', 'firecrawl', '-d', 'firecrawl',
                                   '-c', 'SELECT 1'], capture_output=True).returncode == 0

        with patch.object(credentials, 'sql', side_effect=sql):
            credentials.set_password('fixture-new-password')
            self.assertTrue(authenticates('fixture-new-password'))
            self.assertFalse(authenticates('changeme-fixture'))
            credentials.set_password('changeme-fixture')
            secret = fixture()
            planned = credentials.plan_secret(secret)
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(credentials, 'run', side_effect=RuntimeError('conflict')), \
                    patch.object(credentials, 'get', return_value=secret):
                with self.assertRaisesRegex(RuntimeError, 'original database password restored'):
                    credentials.apply_credentials(secret, planned, Path(directory))
            self.assertTrue(authenticates('changeme-fixture'))
            self.assertFalse(authenticates(credentials.values(planned)['POSTGRES_PASSWORD']))


if __name__ == '__main__':
    unittest.main()
