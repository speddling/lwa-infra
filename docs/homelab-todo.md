# Little Wolf Acres — Homelab Todo
> Operational debt, one-off tasks, and things that need doing but don't belong in current state or roadmap.
> Last updated: 2026-06-15

---

## Client Contract — Security & Compliance (Obelisk / Win11 VM)

> Engineering translation of DPA obligations from the Swiss client contract (nFADP/OFADP, GDPR where applicable) into concrete infra tasks. This is **not** a legal compliance review — confirm with the client or counsel that these implementations actually satisfy the contract language once built.

| Item | Priority | Notes |
|---|---|---|
| MFA on Obelisk admin accounts | High | `speddling` and `obelisk` are currently password-only on the Win11 guest. Add a second factor before any client RDP session — options: Windows Hello for Business, a TOTP-gated RDP gateway in front of port 33389, or MFA on a VPN hop placed before RDP. |
| Encrypt all administrative connections | High | RDP currently has NLA enabled (`UserAuthentication=1`) — that's authentication, not necessarily transport encryption. Verify/enforce TLS-encrypted RDP. SSH to monolith is already key-based — confirm and document this satisfies the requirement. Any future VPN (see Obelisk's "inbound RDP from internet" TODO) must use strong ciphers — WireGuard or OpenVPN w/ AES-256 — and that work should not proceed until this item and the two below are in place. |
| Access logging for Obelisk | High | No audit/access logging exists today — `windows_exporter` (planned) is performance metrics only, not login activity. Enable Windows Security event logging for logon/logoff + RDP connection events, and ship logs off the VM to Watchtower. This is a strong argument to bump the existing Loki (log aggregation) item above "Low" priority. |
| Data subject request procedure | Medium | Document a repeatable process for locating, exporting, or deleting an individual's personal data if the client passes along a data-subject request — needs to cover anywhere "Client Data" might live (see inventory item below). |
| Breach notification runbook | High | Contract requires notifying the client within 24 hours of becoming aware of a breach or security incident. Add an incident-response entry to `runbook.md`: who to contact, what to capture/preserve immediately, a notification template. |
| Client Data location inventory | Medium | The contract's "Client Data" definition is broad — personal data, docs, business plans, passwords, access tokens, source code, db schemas. Inventory where this actually lives in practice (Obelisk's disk, the `vault` Samba share, anywhere else) so it's unambiguous what's in scope for the controls above. |
| Certificate of destruction process | High | Contract requires a **signed written certificate within 7 days of termination** confirming all Client Data is permanently destroyed. Plan: destroy Obelisk (disk image + any VNC/RDP recordings + anything synced to `vault`), but plain delete/overwrite isn't a reliable proof of destruction on SSD (`/mnt/ssd-b`) due to wear-leveling — the drive may retain physical copies of "deleted" blocks elsewhere. Recommended approach: encrypt Obelisk's disk at rest (LUKS) now, so destruction-on-termination = destroying the encryption key (crypto-shred) — fast, complete, and provable, rather than trying to certify a wipe reached every physical cell. Still need: a destruction-certificate letter template (what was destroyed, method, date, signature) ready in advance so it's a fill-in-the-blanks exercise within the 7-day window, not a from-scratch draft under deadline pressure. |

> See also: `docs/obelisk-runbook.md` → TODO, which has related items ("Document Swiss client RDP access procedure", "inbound RDP from internet") that should be sequenced after the High-priority items above.

---

## Software

| Item | Priority | Notes |
|---|---|---|
| Minecraft — realm world import | Pending | Export from Realm → drop in `#zombatron` → cancel $8/month subscription |
| Minecraft — automated PVC backups | Low | k8s CronJob to tarball `/data` nightly to `/mnt/hdd-c` |
| Navidrome — DB backup CronJob | Low | `sqlite3 .backup` snapshot of `/data/navidrome.db` (~96MB of ~260MB `/data`) → watchtower SSD. Reuse config-backup-strategy.md rotation/ntfy pattern. Goal: restore users/playlists/ratings without a full PVC wipe next time. Not urgent — UPS arriving ~1 week closes the immediate power-outage risk. |
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
| `argocd-homelab-reader` | `lwa-homelab` | ArgoCD repo auth | Contents: read | Rotated quarterly via `rotate-argocd-credentials.yml` |
| `homelab-action-dispatch` | `lwa-homelab` | GitHub Actions | TBD | Audit scope — confirm what this token actually needs |
| `lwa-web-scribe` | `lwa-web` | Scribe MCP git ops | Contents r/w, PRs r/w, Metadata r | Added May 2026 — currently stored as account-wide gh CLI credential in macOS keychain. Scope to `lwa-web` repo only on next quarterly rotation |

**Outstanding:**
- `lwa-web-scribe` is account-wide — scope it to `lwa-web` only on next rotation
- Create `lwa-web-deploy` PAT for GitHub Actions SFTP deploy workflow when that pipeline is built
- Audit `homelab-action-dispatch` scope — confirm minimum permissions and document

---

## Incidents & Follow-up

| Date | Symptom | Fix | Tag |
|---|---|---|---|
| 2026-05-31 | iPad — YouTube pages loaded but video would not play, on LAN only. Both native app and Safari affected. Other devices (Android, Apex) unaffected. | AdGuard blocklist update had blocked `googlevideo.com` (YouTube's primary video CDN). Whitelisted via custom rule: `@@||googlevideo.com^` | `#adguard` `#blocklist` `#youtube` `#cdn` `#todo-research` |

> **TODO (research):** Identify which filter list flagged `googlevideo.com` and whether it's a recurring false-positive. Consider swapping for a less aggressive list or making `googlevideo.com` a permanent custom allowlist entry. Diagnostic pattern: page loads fine but media won't play → check AdGuard query log filtered by client IP for red (blocked) entries.
