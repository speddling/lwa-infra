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
