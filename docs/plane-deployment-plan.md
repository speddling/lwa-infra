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
| Hostname | `plane.littlewolfacres.com` | Matches existing `*.littlewolfacres.com` convention |
| Exposure | Internal LAN + WireGuard only | Matches the established remote-access architecture in `network-rebuild-plan.md` — no public port forward, no Cloudflare Tunnel. Reachable from outside only via the WireGuard tunnel once that's configured. |
| Ingress class | `traefik` | k3s ships Traefik by default; same as every other ingress in this cluster. No need to install nginx-ingress just for this chart's documented default. |
| Storage class | `local-path` | Matches existing PVC convention (`navidrome-db`, `minecraft-data`) |
| TLS | Chart's own cert-manager automation (`ssl.createIssuer=true`, `ssl.issuer=cloudflare`), reusing the same Cloudflare credential the existing `letsencrypt-prod` ClusterIssuer uses | Creates a namespace-scoped Issuer rather than touching the existing cluster-wide `letsencrypt-prod`/`letsencrypt-staging` ClusterIssuers — no interference with what's already working. **Unconfirmed:** where that credential actually lives (vault vs. a GitHub Actions secret injected by `bootstrap-argocd.yml`) — check that workflow before assuming a vault variable name. |
| Postgres / Redis / RabbitMQ / MinIO | All `local_setup: true` (in-cluster, chart-managed) | No existing shared Postgres/Redis in this homelab to point at instead; simplest path for a first deploy |
| Secrets | Generated random values, created as native Kubernetes Secrets by a bootstrap workflow, **never committed to git** | Same pattern as the `cloudflare-api-token` secret for cert-manager — out-of-band creation, `ignoreDifferences` in the ArgoCD Application so GitOps sync never tries to overwrite or diff it |
| Initial sync policy | **Manual**, not `automated` | Unlike every other app in `kubernetes/apps/`, this one should NOT auto-sync on merge. First-time stateful multi-service installs are exactly the kind of thing you want to watch happen, not have silently triggered the moment a PR lands on master. Flip to `automated: {prune: true, selfHeal: true}` in a follow-up PR once it's confirmed healthy. |

## Open item — needs verification before merge

The chart's README documents an "External Secrets Config" mechanism (`pgdb_existingSecret`, `rabbitmq_existingSecret`, `doc_store_existingSecret`, `app_env_existingSecret`, `live_env_existingSecret`) listing which environment variables each secret group should contain, but does **not** show the literal `values.yaml` field path for telling the chart "use this pre-existing Secret object by name." Run this on a machine with `helm` installed and paste the output back:

```bash
helm repo add makeplane https://helm.plane.so/
helm repo update
helm show values makeplane/plane-ce | grep -B2 -A2 -i "existingsecret\|existing_secret"
```

Once that's confirmed, the bootstrap workflow and Application values can be finalized with the real field names instead of the placeholder marked below.

## Bootstrap sequence (once the open item above is resolved)

1. `bootstrap-plane.yml` GitHub Actions workflow (manual trigger, runs once — same pattern as `bootstrap-argocd.yml`):
   - Generates random values for: Postgres password, RabbitMQ password, MinIO root password, Plane `SECRET_KEY`
   - Creates the `plane` namespace
   - `kubectl create secret` for each of the five secret groups documented above, using the confirmed field structure
   - Secrets stored in `ansible/vars/vault.yml` so they're recoverable if the namespace is ever rebuilt, but never applied via Ansible directly — Ansible isn't part of k3s's deployment path
2. Merge `kubernetes/apps/plane.yaml` — ArgoCD picks it up via the app-of-apps, shows as a new Application, **does not auto-sync**
3. Manually trigger Sync in the ArgoCD UI once the bootstrap secrets exist
4. Verify all pods come up, `https://plane.littlewolfacres.com` loads, complete the `/god-mode` instance admin setup
5. Add the AdGuard rewrite (already included in this round's PR — see below)
6. Flip `syncPolicy.automated` on in a follow-up PR once confirmed stable

## Slack integration (manual, post-deploy)

Self-hosted Plane's Slack integration requires creating a Slack App via manifest in your own Slack workspace — this is an action only you can take (Slack admin console), not something achievable through any tool available here. Once Plane is running: Plane → Workspace Settings → Integrations → Slack → Configure, which walks through the Slack App manifest creation.

## MCP follow-up (future)

Plane documents official MCP support for AI agents (`developers.plane.so` → Setup MCP). Once Plane is live and has real workspaces/projects, a dedicated Plane MCP connection is worth setting up alongside Synapse/Scribe/Argus — likely as a `search_mcp_registry` lookup once the workspace exists, since the connector needs a real Plane API token to configure.

## Not in scope for this round

- Migrating existing `homelab-todo.md` content into Plane work items (do this once the instance is confirmed stable)
- Slack App configuration (manual, post-deploy, by you)
- MCP connector setup (post-deploy, needs a live workspace first)
- Flipping `syncPolicy.automated` on (follow-up PR after first successful manual sync)
