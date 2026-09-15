# Firecrawl commissioning

Owner confirmed on 2026-09-14 that Firecrawl was installed but never used. The
reported symptom was Synced but pending in ArgoCD. Treat this as an incomplete
installation, not a previously accepted scraping service.

## Initial evidence

- API, PostgreSQL and Redis each have a running Ready pod. The PostgreSQL PVC is
  Bound, 20Gi, local-path. Preserve it while checking the schema.
- RabbitMQ repeatedly starts successfully, then Kubernetes kills it because
  `rabbitmq-diagnostics check_running` exceeds its implicit one-second liveness
  timeout. The current pod had 398 restarts; older retained pods had much larger
  counts. Broker logs show startup completion followed by SIGTERM.
- HTTPS `/`, `/v0/health/liveness` and `/v0/health/readiness` return HTTP 200.
  These responses do not establish queue, worker, browser or scrape functionality.
- The deployed API image digest is
  `sha256:20ea02d51fb5e1063637d7e43b5dcdf429bf69b7e1c1615b48b24bff1d0c13ae`.
  Public image metadata declares `node dist/src/harness.js --start-docker` as its
  default command. The deployment overrides that with `dist/src/index.js`.
  API logs only show the HTTP worker starting; queue-worker processes need inspection.
- No Playwright deployment exists. `PLAYWRIGHT_MICROSERVICE_URL` points back to
  the API itself. Confirm the installed release's browser service and request path.
- The repository declares plain PostgreSQL 17. The required NuQ tables and
  initialization are not yet verified. Do not replace its image or reset its volume
  merely to make the schema resemble the latest upstream Compose example.
- The committed Secret contains placeholders. Its comment refers to an Ansible
  generator that is not present in this repository; the deployment workflow applies
  the manifest directly and ArgoCD also manages it. Actual runtime credential state
  needs boolean-only inspection before changing credentials or connection URLs.

## First correction and inspection

Replace RabbitMQ's CLI liveness check with an AMQP TCP readiness check and a TCP
startup probe allowing up to ten minutes. This removes repeated Erlang CLI startup
overhead and prevents a slow diagnostic command from killing the broker. Readiness
withdraws the service endpoint when the AMQP listener is unavailable; a running
broker is not killed just for a failed readiness check. Container exits still restart
normally, and startup failure remains bounded. Resource limits and image are unchanged.

Deploy verification now waits for all four Deployment rollouts instead of sleeping
30 seconds and checking the first API pod, which could be a historical pod. This
is infrastructure readiness only, not end-to-end commissioning.

After merge and broker rollout, dispatch **Inspect Firecrawl commissioning** on
master. The Monolith runner is `gh-runner`; it SSHes as `speddling` with sudo using
its existing trusted key. Inspection reports pod images/restarts, ArgoCD state,
API build revision and worker entrypoints, connection hosts and credential
presence/placeholder flags, PostgreSQL schema/table names, and RabbitMQ version.
It never prints credential values, queries user data, changes the schema, or submits
a scrape. SQL runs in a PostgreSQL read-only session. Errors fail the workflow.

PR #272 deployed successfully in Actions run `34905117177`. RabbitMQ is Ready
with zero restarts and ArgoCD reports Healthy/Synced. Inspection run `34905198676`
failed because the runtime probe assumed `/app/package.json` existed. The image
only copies built output and `BUILD_SHA`; the corrected probe reads that file
and allows independent database and broker checks to finish even if one fails.
A Node fixture test covers the absent package metadata and credential redaction.

The deployed image's public `BUILD_SHA` is
`0344bc87a64b455d6e06c7d1eb74ba5ebe007b1c`. Use that upstream revision when
checking harness, browser and NuQ requirements. Infrastructure readiness does
not yet establish successful scraping. After the corrected inspection,
prepare matching worker/browser startup and queue configuration, establish proper
credential ownership, and pin compatible images. Acceptance requires a successful
plain-page scrape and crawl, worker processing, broker restart counts remaining
stable, and Healthy/Synced in ArgoCD. Optional LLM-backed extraction is separate
from basic scraping; do not configure paid provider access as part of this test.

Reference: [RabbitMQ health-check guidance](https://www.rabbitmq.com/docs/monitoring#health-checks-as-readiness-probes).

## Confirmed commissioning gaps and Secret handoff

Corrected inspection `34909942525` succeeded on 2026-09-14 at 23:41 UTC:

- RabbitMQ 3.13.7 remains Ready with zero restarts; ArgoCD is Healthy/Synced.
- API build matches the revision above. Its only service process is `index.js`.
- Database `firecrawl` has no tables in `public` or `nuq`, no `nuq` schema,
  and only the `plpgsql` extension. Its volume is retained.
- The API's database URLs and credential variables contain placeholders.
  Its broker URL has neither username nor password. The browser URL points
  back to the API, and there is no browser deployment.

The next rollout adds `Prune=false,Delete=false` to the existing Secret and
stops the deployment workflow from applying its placeholder manifest. This is
the **first stage** of a handoff, not credential rotation: ArgoCD still manages
the manifest and can still reapply its data until the second stage is deployed.
Do not generate new passwords yet. After merge, run the inspection and verify
both retention flags on the live Secret. Record its UID so the next stage can
confirm it was retained rather than deleted and recreated.

Only after that verification, exclude the legacy Secret manifest from ArgoCD
and provision credentials outside Git using a reviewed, backup-gated workflow.
Preserve the PostgreSQL volume and coordinate database password changes with
the connection URLs. Reapplying a Secret alone does not change an existing
PostgreSQL role password. The deployment workflow must never resume applying
the legacy manifest. On a fresh cluster, secret provisioning must precede
workload startup; the legacy file is not a production credential source.

Subsequent commissioning needs version-matched NuQ initialization and pg_cron,
the harness workers, a separate Playwright service, compatible image pins, and
bounded scrape/crawl acceptance tests. Do not call the service commissioned
until those tests pass.

Reference: [ArgoCD resource retention options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/).

## Credential provisioning procedure

Retention inspection `34910249760` passed on 2026-09-14 at 23:45 UTC. Both
retention flags are present on Secret UID
`c511c3ba-ce83-4db6-a3c5-d4bad0db88d3`. The second stage excludes `secret.yaml`
from the ArgoCD directory source; the file remains a legacy example only.
CI checks the live Secret exists but never reapplies its data. A retained Secret
may temporarily appear as an extraneous resource until provisioning removes its
ArgoCD tracking metadata. Do not delete it to resolve that difference.

After merging and waiting for deployment/ArgoCD synchronization to finish, run
**Provision Firecrawl credentials** on master with `maintenance_ack=true`.
This is a one-time commissioning workflow, not a general password rotation tool.
It checks the original Secret UID, retention, source exclusion, fixed database
identity, pinned API/broker images, API-only startup, no application tables, and
no queued broker messages. It refuses to run against a commissioned installation.

The root process on Monolith verifies the old database password over TCP, saves
the Secret, PostgreSQL roles and a custom database archive under
`/var/backups/lwa-firecrawl/<timestamp>-<suffix>/`, and decodes the archive before
making any changes. The directory is root-only. This is a local recovery copy,
not an off-host backup or a full production restore test. Generated credentials
are saved in `secret-planned.json` before the first database write; no credential
values are printed to Actions logs or committed to Git.

The workflow changes the database role password and replaces the same Secret
using its resource version. Database URLs and the authenticated RabbitMQ URL
are updated together. It generates broker, dashboard, test and webhook secrets,
and clears only placeholder OpenAI/proxy credentials; it does not enable a paid
provider. On a rejected Secret update, it checks the live data before restoring
the original database password. A timeout after a successful Secret update does
not trigger an incorrect rollback.

It then replaces the unused broker and API pods to load their new environment,
without changing deployment templates. Broker queues are ephemeral, hence the
empty-queue gate. PostgreSQL's volume and process remain in place; its
`POSTGRES_PASSWORD` environment can remain stale until its next restart, but the
actual database role password is changed by SQL and tested over TCP. The database
Deployment uses `Recreate` to avoid overlapping processes on its existing PVC.
API/broker images are pinned to the already-inspected digests for these reloads.

Acceptance for this stage is successful PostgreSQL and AMQP authentication from
the refreshed API container, a `success.json` recovery marker, and a subsequent
read-only inspection showing the retained Secret UID and non-placeholder runtime
credentials. A repeat run verifies the already-provisioned credentials instead
of generating another set, and can finish an interrupted consumer reload.

If interrupted before the Secret update, keep all files in the reported private
backup directory. Compare `secret-before.json`, `secret-planned.json`, and the
live Secret locally without printing their data. Do not blindly restore just the
Secret: the database role may already have its new password. The workflow can
retry only after the original database authentication check passes; otherwise
coordinate role-password recovery using the saved role/credential files first.
If the Secret update completed, preserve the new credentials and retry the
consumer verification. Uncertain concurrent changes require inspection, not an
automatic overwrite. Never use `kubectl apply` on the legacy placeholder file.

For disaster recovery, restore the database and matching private Secret from a
verified backup before starting dependent workloads; this existing-installation
workflow intentionally refuses a newly created Secret UID. Fresh installation
bootstrap and normal post-commissioning rotation need separate reviewed paths.
Workers, NuQ initialization, the browser service, and end-to-end scraping remain
the next commissioning stage.
