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
| Initial sync policy | **Manual**, not `automated` | Unlike every other app in `kubernetes/apps/`, this one should NOT auto-sync on merge. First-time stateful multi-service installs are exactly the kind of thing you want to watch happen, not have silently triggered the moment a PR lands on master. Flip to `automated: {prune: true, selfHeal: true}` in a follow-up PR once it's confirmed healthy. |

## Resolved during review

Two items were flagged as open in the first draft of this plan and are now resolved:

1. **Secret field names** — confirmed via `helm show values makeplane/plane-ce`. See the `external_secrets:` row above.
2. **Cloudflare credential location** — confirmed via reading `bootstrap-argocd.yml`: it's the `CLOUDFLARE_API_TOKEN` GitHub Actions secret, not an Ansible Vault variable. Resolved by routing around the question entirely — Plane reuses the existing ClusterIssuer via annotation rather than referencing that credential directly.

## Remaining open item

The ArgoCD Application currently uses `targetRevision: "*"` for the Helm chart, which floats to whatever the latest version is on every sync. Run `helm search repo makeplane/plane-ce -l` to see available versions and pin to a specific one before this is considered production-stable — floating chart versions on a stateful service is asking for an unplanned schema migration at a bad time.

## Bootstrap sequence

1. `bootstrap-plane.yml` GitHub Actions workflow (manual trigger, run once — same pattern as `bootstrap-argocd.yml`) is written and ready:
   - Creates the `plane` namespace
   - Generates random values for Postgres password, RabbitMQ password, MinIO root password, and the Plane `SECRET_KEY`, masking each immediately so they never appear in workflow logs
   - Creates the 5 Kubernetes Secrets the chart's `external_secrets` config references
   - No values are written to Ansible Vault or git — the Secret objects in the cluster are the only copy
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
