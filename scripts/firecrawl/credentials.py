#!/usr/bin/env python3
"""One-time, backup-gated credential handoff for the unused installation."""
import argparse
import base64
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

SECRET_UID = 'c511c3ba-ce83-4db6-a3c5-d4bad0db88d3'
MANAGER = 'lwa.littlewolfacres.com/credentials-version'
BACKUP_ROOT = Path('/var/backups/lwa-firecrawl')
LOCK_PATH = Path('/run/lock/lwa-firecrawl-credentials.lock')
API_IMAGE = 'ghcr.io/firecrawl/firecrawl@sha256:20ea02d51fb5e1063637d7e43b5dcdf429bf69b7e1c1615b48b24bff1d0c13ae'
BROKER_IMAGE = 'rabbitmq@sha256:e582c0bc7766f3342496d8485efb5a1df782b5ce3886ad017e2eaae442311f69'


def run(*args, input=None, stdout=subprocess.PIPE, timeout=120):
    result = subprocess.run(['k3s', 'kubectl', '--request-timeout=20s', *args],
                            input=input, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Kubernetes operation failed; raw output withheld')
    return result.stdout


def get(kind, name, namespace='firecrawl'):
    return json.loads(run('get', kind, name, '-n', namespace, '-o', 'json'))


def sql(query):
    # SQL and passwords travel on stdin, never command arguments or Actions logs.
    return run('exec', '-i', '-n', 'firecrawl', 'deployment/firecrawl-postgres',
               '-c', 'postgres', '--', 'psql', '-X', '-qAt', '-U', 'firecrawl',
               '-d', 'firecrawl', '-v', 'ON_ERROR_STOP=1', input=query.encode())


def values(secret):
    return {key: base64.b64decode(value).decode() for key, value in secret['data'].items()}


def require_handoff(app, secret):
    source = app['spec'].get('source', {})
    if (source.get('path') != 'services/firecrawl/kubernetes'
            or source.get('directory', {}).get('exclude') != 'secret.yaml'):
        raise RuntimeError('ArgoCD must exclude the legacy Secret first')
    if app.get('status', {}).get('operationState', {}).get('phase') == 'Running':
        raise RuntimeError('Wait for the ArgoCD sync to finish before provisioning')
    if secret['metadata']['uid'] != SECRET_UID:
        raise RuntimeError('Secret identity changed; inspect before provisioning')
    options = {x.strip() for x in secret['metadata'].get('annotations', {}).get(
        'argocd.argoproj.io/sync-options', '').split(',')}
    if not {'Prune=false', 'Delete=false'} <= options:
        raise RuntimeError('Live Secret retention protections are missing')


def require_unused():
    config = get('configmap', 'firecrawl-config')['data']
    if any(config.get(key) != value for key, value in {
            'POSTGRES_USER': 'firecrawl', 'POSTGRES_DB': 'firecrawl',
            'POSTGRES_HOST': 'firecrawl-postgres', 'RABBITMQ_USER': 'firecrawl'}.items()):
        raise RuntimeError('Database or broker identity differs from the inspected installation')
    for component, image in [('api', API_IMAGE), ('rabbitmq', BROKER_IMAGE)]:
        deployment = get('deployment', 'firecrawl-' + component)
        container = deployment['spec']['template']['spec']['containers'][0]
        if container['image'] != image:
            raise RuntimeError('Reload requires the reviewed image digest')
        if component == 'api' and container.get('args') != ['--max-old-space-size=6144', 'dist/src/index.js']:
            raise RuntimeError('Workers may be enabled; this one-time workflow is no longer appropriate')
        run('rollout', 'status', 'deployment/firecrawl-' + component,
            '-n', 'firecrawl', '--timeout=180s', timeout=200)
    # Refuse to rotate once application tables exist, even if currently empty.
    count = sql("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema');")
    if count.strip() != b'0':
        raise RuntimeError('Application tables exist; inspect before credential maintenance')
    queues = json.loads(run('exec', '-n', 'firecrawl', 'deployment/firecrawl-rabbitmq',
        '-c', 'rabbitmq', '--', 'rabbitmqctl', '-q', 'list_queues', 'name', 'messages', '--formatter', 'json'))
    if any(int(queue['messages']) for queue in queues):
        raise RuntimeError('Broker has queued messages; refuse to replace its ephemeral pod')


def plan_secret(secret):
    old = values(secret)
    if not old.get('POSTGRES_PASSWORD', '').startswith('changeme'):
        raise RuntimeError('Expected inspected placeholder password; refuse unreviewed rotation')
    for key in ['DATABASE_URL', 'NUQ_DATABASE_URL']:
        url = urlsplit(old[key])
        if (url.scheme != 'postgresql' or url.hostname != 'firecrawl-postgres'
                or url.port != 5432 or url.username != 'firecrawl'
                or url.password != old['POSTGRES_PASSWORD'] or url.path != '/firecrawl'):
            raise RuntimeError('Database URL does not match the inspected database credentials')
    new = old.copy()
    for key in ['POSTGRES_PASSWORD', 'RABBITMQ_PASSWORD', 'BULL_AUTH_KEY',
                'SELF_HOSTED_WEBHOOK_HMAC_SECRET', 'TEST_API_KEY']:
        new[key] = secrets.token_hex(32)
    for key in ['OPENAI_API_KEY', 'PROXY_PASSWORD']:
        if new.get(key, '').startswith('changeme'):
            new[key] = ''
    for key in ['DATABASE_URL', 'NUQ_DATABASE_URL']:
        new[key] = f"postgresql://firecrawl:{new['POSTGRES_PASSWORD']}@firecrawl-postgres:5432/firecrawl"
    new['NUQ_RABBITMQ_URL'] = f"amqp://firecrawl:{new['RABBITMQ_PASSWORD']}@firecrawl-rabbitmq:5672"
    result = copy.deepcopy(secret)
    result.pop('managedFields', None)
    metadata = result['metadata']
    metadata.pop('managedFields', None)
    annotations = metadata.setdefault('annotations', {})
    # Detach both supported tracking mechanisms after exclusion, preserving UID.
    for key in ['argocd.argoproj.io/tracking-id', 'kubectl.kubernetes.io/last-applied-configuration']:
        annotations.pop(key, None)
    for key in ['argocd.argoproj.io/instance', 'app.kubernetes.io/instance']:
        metadata.get('labels', {}).pop(key, None)
    annotations[MANAGER] = '1'
    result['data'] = {key: base64.b64encode(value.encode()).decode() for key, value in new.items()}
    result.pop('stringData', None)
    return result


def backup(secret):
    BACKUP_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = BACKUP_ROOT.stat()
    if BACKUP_ROOT.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('Backup root must be private and root-owned')
    directory = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=BACKUP_ROOT))
    (directory / 'secret-before.json').write_text(json.dumps(secret))
    with (directory / 'roles-before.sql').open('xb') as output:
        run('exec', '-n', 'firecrawl', 'deployment/firecrawl-postgres', '-c', 'postgres',
            '--', 'pg_dumpall', '-U', 'firecrawl', '--globals-only', stdout=output)
    with (directory / 'database.dump').open('xb') as output:
        run('exec', '-n', 'firecrawl', 'deployment/firecrawl-postgres', '-c', 'postgres',
            '--', 'pg_dump', '-U', 'firecrawl', '-d', 'firecrawl', '--format=custom', stdout=output, timeout=600)
    archive = directory / 'database.dump'
    if archive.stat().st_size < 1024:
        raise RuntimeError('Database backup is unexpectedly small')
    # Decode every archive entry without restoring into a database.
    run('exec', '-i', '-n', 'firecrawl', 'deployment/firecrawl-postgres', '-c', 'postgres',
        '--', 'pg_restore', '--file=/dev/null', input=archive.read_bytes(), timeout=600)
    (directory / 'sha256-before.json').write_text(json.dumps({
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}))
    print(f'Private backup saved and archive decoded: {directory}', flush=True)
    return directory


def set_password(password):
    # Reviewed old placeholder and generated hex strings only. Avoid SQL injection.
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', password):
        raise RuntimeError('Unexpected password format')
    sql("SET log_statement = 'none'; SET log_min_error_statement = 'panic'; "
        "SET password_encryption = 'scram-sha-256'; "
        f"ALTER ROLE firecrawl PASSWORD '{password}';")


VERIFY = r"""
const timer = setTimeout(() => process.exit(1), 25000);
(async () => {
  const { Client } = require('pg');
  const pg = new Client({connectionString: process.env.NUQ_DATABASE_URL, connectionTimeoutMillis: 10000});
  await pg.connect(); await pg.query('SELECT 1'); await pg.end();
  const broker = await require('amqplib').connect(process.env.NUQ_RABBITMQ_URL);
  await broker.close();
  if (['POSTGRES_PASSWORD','RABBITMQ_PASSWORD'].some(k => !process.env[k] || process.env[k].startsWith('changeme')))
    throw new Error('unprovisioned');
  clearTimeout(timer);
})().catch(() => process.exit(1));
"""


def verify():
    run('exec', '-n', 'firecrawl', 'deployment/firecrawl-api', '-c', 'api', '--',
        'node', '-e', VERIFY, timeout=40)


def verify_original_database(secret):
    # Confirm rollback's original password really authenticates before changing it.
    probe = r"""
const timer = setTimeout(() => process.exit(1), 20000);
(async () => {
  const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
  const pg = new (require('pg').Client)({connectionString: input.url, connectionTimeoutMillis: 10000});
  await pg.connect(); await pg.query('SELECT 1'); await pg.end(); clearTimeout(timer);
})().catch(() => process.exit(1));
"""
    run('exec', '-i', '-n', 'firecrawl', 'deployment/firecrawl-api', '-c', 'api', '--',
        'node', '-e', probe, input=json.dumps({'url': values(secret)['DATABASE_URL']}).encode(), timeout=30)


def reload_consumers():
    # No template patch: replacement pods use the same Git-managed template.
    # This path is gated on the unused installation and empty broker above.
    for component in ['rabbitmq', 'api']:
        pods = json.loads(run('get', 'pods', '-n', 'firecrawl', '-l',
                             'app=firecrawl,component=' + component, '-o', 'json'))['items']
        for pod in pods:
            if pod['status'].get('phase') in ['Running', 'Pending'] and not pod['metadata'].get('deletionTimestamp'):
                run('delete', 'pod', pod['metadata']['name'], '-n', 'firecrawl', '--wait=true',
                    '--timeout=240s', timeout=260)
        run('rollout', 'status', 'deployment/firecrawl-' + component,
            '-n', 'firecrawl', '--timeout=600s', timeout=620)
    deadline = time.monotonic() + 90
    while True:
        try:
            verify()
            return
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)


def apply_credentials(secret, planned, directory):
    # Persist planned credentials before touching the database for interrupted-run recovery.
    (directory / 'secret-planned.json').write_text(json.dumps(planned))
    set_password(values(planned)['POSTGRES_PASSWORD'])
    try:
        run('replace', '-f', '-', input=json.dumps(planned).encode())
    except (RuntimeError, subprocess.TimeoutExpired):
        # A timeout can occur after a successful write. Read back before rollback.
        live = get('secret', 'firecrawl-secret')
        if live['data'] != planned['data']:
            if live['data'] != secret['data']:
                raise RuntimeError('Concurrent Secret change; inspect the private backup before recovery') from None
            set_password(values(secret)['POSTGRES_PASSWORD'])
            raise RuntimeError('Secret write failed; original database password restored') from None
    (directory / 'secret-applied.json').write_text(json.dumps(get('secret', 'firecrawl-secret')))


def provision(ack):
    if not ack or os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'monolith':
        raise RuntimeError('Requires maintenance acknowledgement and root on Monolith')
    os.umask(0o077)
    with LOCK_PATH.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        secret = get('secret', 'firecrawl-secret')
        require_handoff(get('application', 'firecrawl', 'argocd'), secret)
        require_unused()
        if secret['metadata'].get('annotations', {}).get(MANAGER) == '1':
            try:
                verify()
            except RuntimeError:
                reload_consumers()
            print('Existing provisioned credentials verified; no rotation needed', flush=True)
            return
        planned = plan_secret(secret)
        verify_original_database(secret)
        directory = backup(secret)
        require_unused()
        live = get('secret', 'firecrawl-secret')
        require_handoff(get('application', 'firecrawl', 'argocd'), live)
        if live['metadata']['resourceVersion'] != secret['metadata']['resourceVersion']:
            raise RuntimeError('Secret changed during backup; inspect before retry')
        apply_credentials(secret, planned, directory)
        reload_consumers()
        (directory / 'success.json').write_text(json.dumps({'secret_uid': SECRET_UID, 'connections_verified': True}))
        print('Credentials provisioned; PostgreSQL and RabbitMQ connections verified from the API', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--maintenance-ack', action='store_true')
    try:
        provision(parser.parse_args().maintenance_ack)
    except Exception as error:
        # Never expose raw SQL, credentials, subprocess output or exception payloads.
        reason = str(error) if type(error) is RuntimeError else type(error).__name__
        print(f'Credential provisioning stopped: {reason}; inspect the private backup before retrying', flush=True)
        raise SystemExit(1)
