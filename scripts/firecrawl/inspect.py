#!/usr/bin/env python3
"""Read-only Firecrawl commissioning checks; never print credentials or user rows."""
import json
import socket
import subprocess


def run(*args, timeout=90):
    result = subprocess.run(["k3s", "kubectl", "--request-timeout=20s", *args],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"kubectl {args[0]} failed (exit {result.returncode}); raw output withheld")
    return result.stdout


RUNTIME = r"""
const fs = require('fs');
const targets = ['index.js', 'harness.js', 'queue-worker.js', 'nuq-worker.js',
  'nuq-prefetch-worker.js', 'nuq-reconciler-worker.js', 'extract-worker.js', 'cclog-worker.js'];
const processes = [];
for (const pid of fs.readdirSync('/proc').filter(x => /^\d+$/.test(x))) {
  try {
    const args = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').split('\0');
    const entries = args.filter(x => targets.includes(x.split('/').pop()));
    if (entries.length) processes.push({pid, entrypoints: entries});
  } catch (_) {}
}
const connections = {};
for (const key of ['DATABASE_URL', 'NUQ_DATABASE_URL', 'NUQ_RABBITMQ_URL',
  'REDIS_URL', 'PLAYWRIGHT_MICROSERVICE_URL']) {
  const value = process.env[key];
  if (!value) { connections[key] = {present: false}; continue; }
  try {
    const u = new URL(value);
    connections[key] = {present: true, protocol: u.protocol, host: u.hostname,
      port: u.port, username_set: !!u.username, password_set: !!u.password,
      placeholder_password: u.password.startsWith('changeme')};
  } catch (_) { connections[key] = {present: true, valid_url: false}; }
}
const credentials = {};
for (const key of ['POSTGRES_PASSWORD', 'RABBITMQ_PASSWORD', 'BULL_AUTH_KEY',
  'OPENAI_API_KEY', 'SELF_HOSTED_WEBHOOK_HMAC_SECRET']) {
  const value = process.env[key] || '';
  credentials[key] = {present: !!value, placeholder: value.startsWith('changeme')};
}
// Production image copies dist and BUILD_SHA, but does not include package.json.
const buildSha = fs.existsSync('BUILD_SHA') ? fs.readFileSync('BUILD_SHA', 'utf8').trim() : null;
console.log(JSON.stringify({build_sha: /^[0-9a-f]{40}$/.test(buildSha || '') ? buildSha : null,
  processes, connections, credentials,
  entrypoint_files: fs.readdirSync('dist/src').filter(x => /harness|worker|index/.test(x))}));
"""

SCHEMA = """
SELECT json_build_object(
 'database', current_database(),
 'nuq_schema', EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name='nuq'),
 'tables', (SELECT coalesce(json_agg(json_build_object('schema', schemaname, 'table', tablename)), '[]'::json)
            FROM pg_tables WHERE schemaname IN ('public','nuq')),
 'extensions', (SELECT json_agg(extname) FROM pg_extension));
"""


def main():
    if socket.gethostname().split('.')[0] != 'monolith':
        raise RuntimeError('Inspection requires Monolith')
    pods = json.loads(run('get', 'pods', '-n', 'firecrawl', '-o', 'json'))['items']
    summary = []
    for pod in pods:
        summary.append({
            'name': pod['metadata']['name'], 'uid': pod['metadata']['uid'],
            'phase': pod['status'].get('phase'),
            'containers': [{k: c.get(k) for k in ('name', 'ready', 'restartCount', 'image', 'imageID')}
                           for c in pod['status'].get('containerStatuses', [])],
        })
    print(json.dumps({'pods': summary}), flush=True)
    app = json.loads(run('get', 'application', 'firecrawl', '-n', 'argocd', '-o', 'json'))
    status = app.get('status', {})
    print(json.dumps({'argocd': {
        'health': status.get('health', {}).get('status'),
        'sync': status.get('sync', {}).get('status'),
        'operation': status.get('operationState', {}).get('phase'),
    }}), flush=True)
    errors = []
    def check(name, action):
        try:
            print(json.dumps({name: action()}), flush=True)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            # Continue independent checks; report no raw subprocess output.
            errors.append(name)
            print(json.dumps({name: {'error_type': type(error).__name__}}), flush=True)
    check('api_runtime', lambda: json.loads(run('exec', '-n', 'firecrawl', 'deployment/firecrawl-api',
                             '-c', 'api', '--', 'node', '-e', RUNTIME)))
    # SELECT only, with a server-side read-only session and no application rows.
    check('database_schema', lambda: json.loads(run('exec', '-n', 'firecrawl', 'deployment/firecrawl-postgres',
        '-c', 'postgres', '--', 'sh', '-c',
        'PGOPTIONS="-c default_transaction_read_only=on" exec psql -X -U "$POSTGRES_USER" '
        '-d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "$1"', 'inspect', SCHEMA)))
    check('rabbitmq_version', lambda: run('exec', '-n', 'firecrawl', 'deployment/firecrawl-rabbitmq', '-c', 'rabbitmq',
                  '--', 'rabbitmq-diagnostics', '-q', 'server_version').strip())
    if errors:
        raise RuntimeError('Incomplete commissioning checks: ' + ', '.join(errors))


if __name__ == '__main__':
    main()
