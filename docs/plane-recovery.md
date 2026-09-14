# Plane startup investigation

## Verified 2026-09-14

Owner reports Plane has never been stable and currently displays “Looks like
Plane didn't start up correctly”. Read-only Synapse inspection confirms both API
pods are Running but 0/1 Ready. Their readiness probes receive connection refused
on port 8000. Logs report the database available, then repeatedly wait for migrations.
Worker and beat-worker logs show the same wait despite their 1/1 Ready status.

The completed `plane-api-migrate-1-dvtbg` job reports no migrations to apply, but
Prometheus container metadata shows it used backend digest
`sha256:2cdcb5f778c6ccacebce0e5a751d39fac4a549a44e049a5b110a7623cfdad139`.
Current API and worker containers use
`sha256:90032ce088708889b60c00d491897916f4deb882facda27db59fd10fb68729ef`.
All declare the mutable image tag `stable`. Therefore job success does not prove
the current backend's migrations were applied. Version drift is confirmed;
the exact pending migrations and any additional schema errors remain unverified.

The repository pins chart 1.5.1 but overrides its application version with
`planeVersion: stable`. Its comments describing app 1.3.1 and a healthy first
installation do not establish the current image version or service health.
Existing Job immutability workarounds also require review before changing versions.

## Next diagnostic

After merge, dispatch **Inspect Plane startup** on master. It runs on Monolith as
`gh-runner`, using the runner's existing key to SSH as `speddling` with sudo.
It reports selected pod metadata, ArgoCD health/sync state, and a migration plan
from the newest running API container. `showmigrations --plan` runs with PostgreSQL
`default_transaction_read_only=on`; it does not apply migrations. Output excludes
environment values, Secrets, and arbitrary command error text. A failed or
unrecognized plan makes the workflow fail rather than implying there is no work.

Before remediation, establish the pending schema changes and a recoverable
database backup, select a fixed compatible release, and arrange for its matching
migration job to run. Preserve existing database volumes and generated secrets.
Do not recreate the namespace or blindly rerun bootstrap. Verify API and worker
startup logs and the actual Plane API after recovery; pod phase alone is inadequate.

## Confirmed migration gap and guarded recovery

[Diagnostic 34863808482](https://github.com/speddling/lwa-infra/actions/runs/34863808482)
passed on 2026-09-14. ArgoCD reported Synced/Progressing with a successful sync;
the migration job was created on 2026-07-09. Exactly two migrations were pending:

- `db.0122_alter_draftissue_assignees_alter_issue_assignees_and_more`
- `django_celery_beat.0019_alter_periodictasks_options`

Public registry manifest comparison identifies the old backend digest as v1.3.1
and the current backend digest as v1.4.2. Chart 1.5.1 does not pin the application
while `planeVersion: stable` overrides it. The v1.4.2 Plane migration updates
ManyToMany field definitions using existing through models; use Django's normal
migrator rather than hand-editing migration records.

After merge, dispatch **Recover Plane migrations** on master with
`maintenance_ack=true`. This is a database-writing maintenance action. It checks
the current backend digest, completed old job, and reviewed pending migration set,
then saves a custom-format Postgres dump plus the five existing Secrets and two
ConfigMaps in a unique root-only directory under `/var/backups/lwa-plane` on Monolith.
No backup or secret contents are uploaded to GitHub. `pg_restore --file=/dev/null`
decodes the archive without connecting to a database. This checks archive readability;
it is not a full test restore or an off-host disaster-recovery backup.

Only after backup succeeds and the API pod identity and migration plan are checked
again does it run `manage.py migrate --noinput` in the reviewed API container.
Migration output stays in the private backup directory. A local lock and workflow
concurrency serialize this recovery action; avoid concurrent Plane deployments or
manual migrations. Failure stops the action without automatic rollback or retry.
If a connection drops during migration, inspect database and pod state before retrying.

Acceptance requires zero pending migrations, API/worker Deployment rollouts,
Celery processes in worker and beat-worker, and HTTP 200 from `/api/instances/`
through the internal API Service. Check the external HTTPS page and user login
afterward. Existing volumes and Secrets are retained; the old Job is not deleted.

Recovery is not deployed or verified yet. Once serving again, pin the application
to the verified release and correct Job replacement for future migrations.
Also suppress only the chart's generated pod-template timestamp drift: fresh pod
replacements were observed during ordinary reconciliation. Do not treat this
one-time migration repair as the completed long-term stability correction.
