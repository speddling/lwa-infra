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

## Read-only diagnostic

Dispatch **Inspect Plane startup** on master. It runs on Monolith as
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

Recovery [34865073606](https://github.com/speddling/lwa-infra/actions/runs/34865073606)
passed on 2026-09-14. Backup is on Monolith at
`/var/backups/lwa-plane/20260914T155329Z-yxq5mb3r`. Both migrations completed;
API/worker rollouts, actual Celery processes and the internal instance endpoint
passed. An independent Construct request to
`https://plane.littlewolfacres.com/api/instances/` returned HTTP 200 and a JSON
object with `instance` and `config`. User login and normal workspace interaction
still need owner confirmation.

## Release and reconciliation correction

The follow-up pins all chart application images to `v1.4.2`. Registry comparisons
confirmed that backend, frontend, admin, space and live v1.4.2 image digests match
the stable images inspected during recovery; this is not another application upgrade.
The chart remains pinned at 1.5.1.

A second Application source, `kubernetes/plane-overrides`, replaces only
`plane-api-migrate-1` with a Sync hook using the exact recovered backend digest.
`BeforeHookCreation` replaces the old completed Job before each full sync and
retains the latest Job/logs afterward. There is no generated timestamp in this
Job. A failed migration command or remaining migration causes the hook to fail,
and therefore fails the sync. Do not use selective sync for application upgrades:
ArgoCD does not execute hooks during selective sync.

ArgoCD intentionally reports `RepeatedResourceWarning` for this one Job because
both sources declare its identity; the Git override wins. This is expected only
for `Job/plane/plane-api-migrate-1`, not a blanket exemption for warnings.
The override retains the chart's service account and existing secret/config references.
The five Secrets, data volumes and bootstrap-managed Certificate retain their owners.

For Deployments, ignore only `/spec/template/metadata/annotations/timestamp`,
with `RespectIgnoreDifferences=true`. This prevents the upstream chart's `now()`
from triggering pod replacements during routine rendering/sync. Image changes,
resource changes and all other annotations remain managed. The existing WEB_URL
HTTPS exception remains, pending a separate declarative replacement.

Merge deploys this correction through ArgoCD. Expect one rollout for the change
from the stable tag to the equivalent version tag, plus replacement of the old
migration Job. After merge, require a successful hook, healthy API/workers,
zero pending migrations and an HTTPS API response. Compare pod identities across
later reconciliation to verify there are no timestamp-only replacements.
Release pin and timestamp suppression were deployed by PR #269. Inspection
[34866110751](https://github.com/speddling/lwa-infra/actions/runs/34866110751)
confirmed zero pending migrations. All running Plane pods subsequently became
Ready, and ArgoCD logged Healthy at 16:03:05 UTC on 2026-09-14. Later reconciliations
at 16:04:19 and 16:05:16 found the application Synced without another rollout.

Hook acceptance remains open. The initial conversion from a normal Job into a
same-name hook produced both a prune task and a hook task. Controller logs show
the hook inherited the prune task's `Pruned/Succeeded` result; no new migration
pod ran. This is not successful hook execution, despite the overall sync result.
The old normal Job is now absent. Explicit wave 0 on the hook and wave 1 on the
API Deployment establish the intended migration-before-API order and trigger a
new sync through the Deployment metadata change. These annotations do not change
the API pod template. After merge, require an actual completed hook pod before
closing this acceptance item; do not repeat schema recovery just to test a hook.

For future upgrades, capture and verify a fresh database/secret backup before
merging the version change. Update the Helm application version and matching
migration-hook version/digest together, review the migration path, and validate
full sync and API/worker operation. The emergency recovery script is deliberately
restricted to the reviewed v1.4.2 digest and migration set; it is not a generic
upgrade tool. Preserve backups until recovery and normal user operations are verified.

References: [ArgoCD multi-source overrides](https://argo-cd.readthedocs.io/en/stable/user-guide/multiple_sources/),
[ArgoCD hook lifecycle and selective-sync limitation](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/).
