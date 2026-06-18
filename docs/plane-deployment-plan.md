# Plane Deployment Plan

Self-hosted Plane Community Edition (open source, AGPL-3.0) as the ticket/issue tracker, replacing the implicit `homelab-todo.md` / `homelab-roadmap.md` workflow for anything that benefits from status tracking, assignment, and a board view.

This document is the **design**. There is no migration runbook yet — unlike the network rebuild, this isn't a cutover of something live, it's a net-new service with no prior state to protect.

---

## Why Plane over GitHub Issues

Covered in chat at decision time; the short version: GitHub Issues is free and zero-infra but isn't open source software, and ties tickets to the code repo rather than a dedicated tool. Plane Community Edition is genuinely open source (AGPL-3.0), fits the homelab's self-host-everything philosophy, and ships official MCP support for AI agents — a closer match to how Synapse/Scribe/Argus already work than bolting issue-tracking onto Scribe's git-scoped tool surface would be.

## Why Helm + ArgoCD, not Ansible

Every other Watchtower/Monolith service in this repo is Ansible-templated systemd units. Plane is a Kubernetes-native, multi-service stack (web, api, admin, space, live, worker, beat-worker, plus Postgres, Redis/Valkey, RabbitMQ, MinIO — 13 containers per the chart's own sizing guidance). It belongs in k3s, managed by ArgoCD, exactly like Navidrome and Minecraft — `kubernetes/apps/plane.yaml` is the single file that needs to land in this repo for ArgoCD's app-of-apps to pick it up.

## Resource footprint

Chart guidance recommends **8GB RAM minimum** for a comfortable install across all 13 services. Monolith was sitting at ~3.8GB used of 32GB before the RAM upgrade — there's room now, and considerably more once the 64GB upgrade lands. Not a blocker.

## Decisions

| Item | Decision | Rationale |
|---|---|---|
| Chart | `makeplane/plane-ce` from `https://helm.plane.so/` | Official chart, Community Edition specifically — the open-source path. Avoid `plane-enterprise` chart entirely. |
| Namespace | `plane` | Matches single-word namespace convention (navidrome, minecraft, synapse) |
| Release name | `plane` (explicit, via `source.helm.releaseName`) | Pinned explicitly rather than left to ArgoCD's default inference, since in-cluster service DNS names (e.g. `plane-pgdb.plane.svc.cluster.local`) depend on it and the bootstrap workflow's secrets reference those names directly |
| Hostname | `plane.littlewolfacres.com` | Matches existing `*.littlewolfacres.com` convention |
| Exposure | Internal LAN + WireGuard only | Matches the established remote-access architecture in `network-rebuild-plan.md` — no public port forward, no Cloudflare Tunnel. Reachable from outside only via the WireGuard tunnel once that's configured. |
| Ingress class | `traefik` | k3s ships Traefik by default; same as every other ingress in this cluster. No need to install nginx-ingress just for this chart's documented default. |
| Storage class | `local-path` | Matches existing PVC convention (`navidrome-db`, `minecraft-data`) |
| TLS | Standard `cert-manager.io/cluster-issuer: letsencrypt-prod` annotation, reusing the existing cluster-wide ClusterIssuer — chart's own `ssl.createIssuer` automation deliberately NOT used | The chart's own TLS automation requires embedding the Cloudflare API token directly as a literal Helm value, which would mean committing it to git in plaintext. The existing ClusterIssuer already has that credential wired up via its own out-of-band secret (confirmed: lives as the `CLOUDFLARE_API_TOKEN` GitHub Actions secret, created once by `bootstrap-argocd.yml`) — Plane just needs the standard annotation, same as Navidrome and ArgoCD's own ingress, and never needs to know about that credential at all. |
| Postgres / Redis / RabbitMQ / MinIO | All `local_setup: true` (in-cluster, chart-managed) | No existing shared Postgres/Redis in this homelab to point at instead; simplest path for a first deploy |
| Secrets | Generated fresh at runtime by `bootstrap-plane.yml`, masked in CI logs, created as native Kubernetes Secrets, **never committed to git or stored in Ansible Vault** | Confirmed via `helm show values makeplane/plane-ce`: a top-level `external_secrets:` map takes the literal name of a pre-existing Secret per logical group (`pgdb_existingSecret`, `rabbitmq_existingSecret`, `doc_store_existingSecret`, `app_env_existingSecret`, `live_env_existingSecret`). Since these are locally-generated credentials with no external counterpart to preserve, the Kubernetes Secret objects themselves are the only copy that needs to exist — a full namespace rebuild just re-runs the bootstrap workflow to generate fresh ones. |
| Initial sync policy | **Automated** (`prune: true, selfHeal: true`) | Started manual for the first stateful install, since that's exactly the kind of thing worth watching happen rather than silently triggering. Flipped on once pod-level health was directly verified (all 13 components confirmed `Running`/`Succeeded`) after surviving real fixes for OOM, TLS, a missing secret key, and an upstream templating bug. |

| TLS | Explicit `cert-manager.io/v1 Certificate` resource (`kubernetes/apps/plane-certificate.yaml`), applied directly by `bootstrap-plane.yml` | The chart generates a Traefik-native `IngressRoute`, not a standard Kubernetes `Ingress`. cert-manager's annotation-based auto-issuance (`cert-manager.io/cluster-issuer`) only watches `Ingress` objects — it never saw the annotation originally set here, so no certificate was ever actually requested and the browser fell back to a self-signed cert ("Not Secure"). An explicit `Certificate` resource sidesteps the annotation mechanism entirely and works regardless of what Ingress-like resource the chart produces. |
| `WEB_URL` (app's own canonical URL) | Live-patched to `https://...`, protected from reverting via `ignoreDifferences` on the `plane-app-vars` ConfigMap | The chart hardcodes `WEB_URL=http://<appHost>` with no override field anywhere in `values.yaml` (confirmed by grepping the full output for web_url/base_url/protocol/scheme/https — nothing). Since the IngressRoute is HTTPS-only with no plain-HTTP entrypoint, the app's own `http://` self-image caused self-referential redirects to fall back to its internal container port (`:3000`) rather than the real external URL — the actual symptom that surfaced as "loads for a second, then times out." |
| `CORS_ALLOWED_ORIGINS` | `env.cors_allowed_origins: "https://plane.littlewolfacres.com"` — a real, documented Helm override | Unlike `WEB_URL`, this one has a clean field. Set to https-only since there's no plain-HTTP route for it to matter. |
| `LIVE_SERVER_SECRET_KEY` | Added to `plane-live-env-secret` via `bootstrap-plane.yml`, reusing the same value as the main app `SECRET_KEY` | The chart's documented `live_env_existingSecret` table only lists `REDIS_URL` as required — `live` actually also requires this key at startup (`live`'s own Node.js service threw a hard "Required" validation error without it). Not documented in the chart README at the version installed; discovered via the pod's crash log. |
| `worker` memory limit | Raised from the chart default `1000Mi` to `4096Mi` | `plane-worker` was repeatedly OOMKilled (`exitCode 137`). Its own startup banner showed `concurrency: 16 (prefork)` — Celery's default concurrency equals the detected CPU count, and Monolith is 8c/16t, so it spawned 16 separate full Python processes rather than lightweight threads. No traceback ever appeared in logs since this is a kernel-level OOM kill, not an application exception. |

## Onboarding flow postmortem (resolved — June 2026)

After all 13 pods were Running/Succeeded and `https://plane.littlewolfacres.com` loaded the welcome screen correctly, the **"Get Started"** button hung and timed out on every client. Root cause and resolution:

**Root cause:** The `GET /api/instances/` response returns three fields — `admin_base_url`, `space_base_url`, `app_base_url` — that were all `null` because they had never been set (this is normal for a fresh install before the setup wizard completes). When these are null, the Next.js web frontend falls back to constructing the god-mode redirect URL client-side as `window.location.hostname + ":3000"`, producing `https://plane.littlewolfacres.com:3000/god-mode/`. Port 3000 is the admin container's internal listen port — it is not exposed externally and is not an entrypoint Traefik listens on. The request never reached the cluster, which is why `plane-api-wl` logs showed zero trace of the request.

**The IngressRoute was already correct.** The chart-generated `plane-ingress` IngressRoute routes `Host(plane.littlewolfacres.com) && PathPrefix(/god-mode)` → `plane-admin:3000` on the `websecure` (443) entrypoint. `https://plane.littlewolfacres.com/god-mode/` works fine — the only broken path was the one the frontend generated with `:3000` appended.

**Fix:** Navigate directly to `https://plane.littlewolfacres.com/god-mode/` in a browser (Chrome, with AdGuard DNS resolving the hostname), bypassing the "Get Started" button entirely. Complete the setup wizard — this sets `is_setup_done: true`, creates the first workspace, and populates the instance name. After setup, normal navigation goes straight to login/workspace and never touches the broken welcome-screen redirect again.

**Note on `admin_base_url` / `space_base_url` / `app_base_url`:** These fields are not exposed anywhere in the god-mode UI in v1.3.1. They may be settable via env vars but were never needed — once `is_setup_done: true`, the welcome screen's "Get Started" redirect is no longer part of the flow. If a future DB reset forces another initial setup, navigate directly to `/god-mode/` again rather than using the welcome screen button.

**What was ruled out during investigation:**
- SMTP (both `ENABLE_SMTP` and `EMAIL_HOST` in `plane-app-vars` are empty — no mail server to hang on)
- `WEB_URL` revert (confirmed still `https://plane.littlewolfacres.com`, `ignoreDifferences` + `RespectIgnoreDifferences=true` held)
- Android Private DNS (red herring from an earlier session — DNS was fine)
- Missing IngressRoute path for `/god-mode` (it was already there)

## Chart version pinning

Pinned to `targetRevision: "1.5.1"` (chart 1.5.1 = app 1.3.1) in `kubernetes/apps/plane.yaml`. When upgrading, check the release notes for schema migrations before bumping the pin — the `plane-api-migrate` Job will re-run on the next sync and the immutable-pod-template issue documented above may require a `kubectl delete job plane-api-migrate-1 -n plane` before selfHeal can recreate it cleanly.

## Lesson learned: Replace=true and ignoreDifferences are incompatible

Briefly tried `syncOptions: Replace=true` app-wide to solve the migrate Job's immutable-pod-template conflict (the chart embeds a fresh timestamp annotation on every Helm render, and Kubernetes Job pod templates can't be patched post-creation). This backfired: `ignoreDifferences` only affects how ArgoCD computes a *patch* — it has no effect at all on `Replace`, which does a full delete-and-recreate using exactly what's rendered from git. The very next sync silently wiped the live `WEB_URL` fix back to the chart's broken `http://` default, breaking the site with no error or warning — a worse failure mode than the loud, clear "field is immutable" error Replace was meant to solve.

Reverted to no `Replace=true`. The accepted tradeoff instead: if a future chart/values change ever re-triggers a sync that touches the already-existing migrate Job, that one sync will fail with the immutable-field error, requiring a one-time manual `kubectl delete job plane-api-migrate-1 -n plane` before `selfHeal` can recreate it cleanly. Rare (only on an actual chart/values change, not routine reconciliation), loud when it happens, and doesn't silently corrupt anything else — a better trade than `Replace=true`'s silent `ignoreDifferences` bypass.

## Bootstrap sequence

1. Merge this PR. `bootstrap-plane.yml` auto-triggers on the push (path filter on `kubernetes/apps/plane.yaml`) — no manual Actions click needed for this step. It's also safe to re-run manually or via future pushes to that file: it checks whether `plane-pgdb-secret` already exists and no-ops if so, rather than regenerating credentials that would no longer match whatever Postgres/RabbitMQ/MinIO already initialized with.
2. ArgoCD's app-of-apps picks up `plane.yaml`, creates the child Application — shows as **OutOfSync**, does **not** auto-deploy
3. Manually trigger Sync in the ArgoCD UI — kept manual deliberately, given this is a 13-container stateful stack's actual first boot (Postgres schema init, MinIO bucket creation, RabbitMQ, the migrator job). Worth watching happen once rather than chaining unverified automation (ArgoCD CLI auth from the runner, RBAC for patching Application objects, sync-timing assumptions) onto an already-complex first run.
4. Verify all pods come up, `https://plane.littlewolfacres.com` loads, complete the `/god-mode` instance admin setup
5. AdGuard rewrite is already included in this PR
6. **Done** — `syncPolicy.automated` flipped on once pod health was directly verified

## Slack integration (manual, post-deploy)

Self-hosted Plane's Slack integration requires creating a Slack App via manifest in your own Slack workspace — this is an action only you can take (Slack admin console), not something achievable through any tool available here. Once Plane is running: Plane → Workspace Settings → Integrations → Slack → Configure, which walks through the Slack App manifest creation.

## MCP follow-up (future)

Plane documents official MCP support for AI agents (`developers.plane.so` → Setup MCP). Once Plane is live and has real workspaces/projects, a dedicated Plane MCP connection is worth setting up alongside Synapse/Scribe/Argus — likely as a `search_mcp_registry` lookup once the workspace exists, since the connector needs a real Plane API token to configure.

## Not in scope for this round

- Migrating existing `homelab-todo.md` content into Plane work items (do this once the instance is confirmed stable)
- Slack App configuration (manual, post-deploy, by you)
- MCP connector setup (post-deploy, needs a live workspace first)
