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
