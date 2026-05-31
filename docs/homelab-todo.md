# Little Wolf Acres — Homelab Todo
> Operational debt, one-off tasks, and things that need doing but don't belong in current state or roadmap.
> Last updated: 2026-05-30

---

## Software

| Item | Priority | Notes |
|---|---|---|
| Minecraft — realm world import | Pending | Export from Realm → drop in `#zombatron` → cancel $8/month subscription |
| Minecraft — automated PVC backups | Low | k8s CronJob to tarball `/data` nightly to `/mnt/hdd-c` |
| Fileserver idempotency | Low | Fix `smbpasswd -a` in fileserver playbook — fails on re-run when user exists. Use `pdbedit -L` to check before adding |
| Loki — log aggregation | Low | Add to Watchtower stack |
| Synapse — health endpoint | Low | Add `/health` route to FastMCP app for proper k8s liveness/readiness probes |
| Healthchecks.io dead-man's switch | Pending | Code deployed — add `vault_healthchecks_daily_summary_url` to `ansible/vars/vault.yml` with ping URL from healthchecks.io (period: 12h, grace: 1h) |

---

## Post-Watchtower Cleanup

| Item | Notes |
|---|---|
| Remove UFW install task from fileserver Ansible playbook | UFW is now managed by `deploy-monolith.yml` via the `ufw` role — duplicate task in fileserver is redundant |
| Fix `smbpasswd -a` idempotency in fileserver playbook | Use `pdbedit -L` to check if user exists before attempting add |

---

## GitHub PAT Audit

One PAT per repo, one PAT per role. Review and rotate quarterly alongside ArgoCD credentials.

| Token Name | Repo | Role | Scope | Notes |
|---|---|---|---|---|
| `argocd-homelab-reader` | `homelab` | ArgoCD repo auth | Contents: read | Rotated quarterly via `rotate-argocd-credentials.yml` |
| `homelab-action-dispatch` | `homelab` | GitHub Actions | TBD | Audit scope — confirm what this token actually needs |
| `lwa-web-scribe` | `lwa-web` | Scribe MCP git ops | Contents r/w, PRs r/w, Metadata r | Added May 2026 — currently stored as account-wide gh CLI credential in macOS keychain. Scope to `lwa-web` repo only on next quarterly rotation |

**Outstanding:**
- `lwa-web-scribe` is account-wide — scope it to `lwa-web` only on next rotation
- Create `lwa-web-deploy` PAT for GitHub Actions SFTP deploy workflow when that pipeline is built
- Audit `homelab-action-dispatch` scope — confirm minimum permissions and document
