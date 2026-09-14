"""Exercise the actual runtime probe in the production image's minimal layout."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest


RUNTIME = runpy.run_path(str(Path(__file__).with_name('inspect.py')))['RUNTIME']


class RuntimeTests(unittest.TestCase):
    def test_image_without_package_json_and_no_credential_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'dist/src').mkdir(parents=True)
            (root / 'dist/src/harness.js').touch()
            (root / 'BUILD_SHA').write_text('0344bc87a64b455d6e06c7d1eb74ba5ebe007b1c\n')
            env = {'PATH': os.environ['PATH'],
                   'NUQ_RABBITMQ_URL': 'amqp://fixture-user:fixture-private-password@firecrawl-rabbitmq:5672',
                   'OPENAI_API_KEY': 'fixture-private-provider-key'}
            result = subprocess.run(['node', '-e', RUNTIME], cwd=temp, env=env,
                                    capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            self.assertEqual(data['build_sha'], '0344bc87a64b455d6e06c7d1eb74ba5ebe007b1c')
            self.assertTrue(data['connections']['NUQ_RABBITMQ_URL']['password_set'])
            self.assertNotIn('fixture-private', result.stdout)
            self.assertNotIn('fixture-user', result.stdout)


if __name__ == '__main__':
    unittest.main()
