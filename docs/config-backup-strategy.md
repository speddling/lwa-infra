# Config Backup Strategy

Automated, change-triggered configuration backups for every networked device in the homelab. Off-site versioning via a dedicated private GitHub repo; fast-recovery copies on watchtower's SSD.

This document is the **design** for how config backups work across the homelab. Per-device implementation specifics live in `kubernetes/services/config-backup/` as code.

---

## Goals & Principles

- **Single source of truth for config history** — one repo holds the current configuration of every device in the homelab, with git providing the full version history
- **Change-triggered, not change-spammed** — daily polling, but only retain/commit when the config actually differs from the previous version
- **Two-tier storage** — fast local recovery on watchtower, off-site versioning on GitHub
- **No silent failures** — every backup CronJob notifies via ntfy on error
- **Annual restore drill** — backups you've never tested aren't backups

---

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌────────────────┐
│ Device(s)   │  pull   │  watchtower  │  push   │  GitHub        │
│ OC200, etc. │ ──────► │  k3s CronJob │ ──────► │  LWA-cfg       │
└─────────────┘         │  + local PVC │         │  (private)     │
                        └──────────────┘         └────────────────┘
                              │
                              │ on failure
                              ▼
                        ┌──────────────┐
                        │  ntfy alert  │
                        └──────────────┘
```

**Where each layer lives:**

| Layer | Location | Purpose |
|---|---|---|
| Device API | OC200, ER605, AdGuard, etc. | Source of truth at the moment of backup |
| watchtower local | k3s PVC on watchtower SSD | 5-deep rotation per device for fast recovery |
| GitHub private | `speddling/LWA-cfg` | Off-site, version-controlled history |
| ntfy | watchtower | Failure notification |

**Why two tiers:** if GitHub is unreachable during the disaster you're recovering from, watchtower's local copy is a `kubectl cp` away. If watchtower itself is the failure, GitHub is the source of truth. The two failure modes don't overlap.

---

## Repository Layout — `speddling/LWA-cfg`

Private GitHub repo, one subdirectory per device. Each subdirectory holds only the latest config; git history provides versioning.

```
LWA-cfg/
├── README.md
├── omada/
│   └── omada-latest.cfg
├── er605/
│   └── er605-latest.cfg
├── sg2218p/
│   └── sg2218p-latest.cfg
├── adguard/
│   ├── AdGuardHome.yaml
│   └── filters/
├── nvr/
│   └── bigbrother-latest.cfg
├── reolink/
│   ├── cam1-latest.cfg
│   └── cam2-latest.cfg
├── printer/
│   └── brother-latest.cfg
└── monolith/
    └── pve-etc-snapshot.tar.gz
```

**Commit message format:** `chore(<device>): config snapshot YYYY-MM-DD` — keeps history readable and makes per-device filtering trivial (`git log --grep='omada'`).

**Why private:** even encrypted device configs leak metadata (SSID PSKs, MAC reservations, firewall topology, internal IP ranges, connected device fingerprints). Public-repo storage is a non-starter.

---

## Workflow — per device

Each device gets its own k3s CronJob with the same pattern:

1. **Pull** current config from device via API or scraping
2. **Hash** the result and compare to the most recent stored hash
3. **If different:**
   - Rotate local copies on watchtower's PVC (latest → .1, .1 → .2, ..., .4 drops off)
   - Save new file as `latest`
   - Commit to LWA-cfg with the standard message format
   - Push to GitHub
   - ntfy success notification (low priority)
4. **If unchanged:** discard the new file, log silently, exit clean
5. **On any failure:** ntfy high-priority alert with the error

**Daily cadence by default.** Per-device override possible if a particular device justifies more or less frequent polling (e.g., k3s manifests already in main homelab repo don't need this; the NVR may benefit from weekly only).

---

## Per-Device Backup Specs

### OC200 — Omada Controller *(first implementation)*

| Property | Value |
|---|---|
| Schedule | Daily 03:00 local |
| Source | Omada API at `https://192.168.10.3` |
| Backup type | Settings-only (`retainedDataBackup: 0, hasData: false`) |
| Auth | Credentials in Kubernetes Secret, Ansible-managed |
| Output | `omada-latest.cfg` |
| Hash check | Need to validate — Omada cfg may include timestamps that change every export. If byte-comparison proves unreliable, fall back to size-delta or accept daily commits |

### ER605 — Router *(future)*

Config export available via Omada controller (since adopted) or direct web UI. Same Omada API pattern likely applies — investigate.

### SG2218P — Switch *(post-cutover)*

Config managed through OC200, so theoretically captured by the OC200 backup. Validate this once the switch is adopted — if the OC200 backup includes downstream device configs, no separate CronJob needed.

### AdGuard Home *(future)*

Watchtower-local files at `/opt/AdGuardHome/AdGuardHome.yaml` and `/opt/AdGuardHome/data/`. Simpler than API-based backups — just copy files. Possibly handled directly by the existing watchtower Ansible role.

### Big Brother NVR *(future)*

Config export via NVR web UI. Likely needs a different approach — possibly manual export to a watched directory, or screen-scraping the web UI.

### Reolink cameras *(future)*

API export per camera via Reolink's API.

### Brother HL-L3290CWD *(future)*

Config export via the printer's web UI.

### Monolith Proxmox `/etc/pve/` *(future)*

Tarball of `/etc/pve/` directory. Doesn't change frequently; weekly schedule likely sufficient.

---

## Operational Concerns

**Secrets management.** Device credentials (OC200 admin password, ER605 admin password, etc.) live in the Ansible vault. The vault is decrypted at deploy time to populate Kubernetes Secrets that the CronJobs mount. Single source of truth: vault.

**Notifications.** ntfy topic `homelab-backup` for backup events. Three priority levels:
- Info: successful new backup committed (one per device per change)
- Warning: device unreachable but expected to be transient (will retry tomorrow)
- High: backup or git push failed multiple consecutive days

**Retention.**
- Watchtower local: 5-deep ring per device
- GitHub: unbounded (git history)
- No automatic purge of git history — disk usage on watchtower stays bounded by the local ring; GitHub usage grows linearly with changes (small)

**Restore drill — annual.**
1. Pull `LWA-cfg` to a workstation
2. For each device, attempt to import the latest config into a test instance:
   - OC200: TP-Link offers a software controller for testing; import the cfg there
   - ER605: factory-reset spare unit if available, or skip if not
   - AdGuard: spin up a Docker container of AdGuard and load the yaml
3. Verify config loads cleanly; check key settings (VLANs, firewall rules, DHCP scopes)
4. Document any restore-procedure quirks discovered in this doc

---

## Implementation Order

1. Create `speddling/LWA-cfg` private repo on GitHub
2. Generate deploy key (read+write) for the repo; store private key in Ansible vault
3. Provision Kubernetes Secret on watchtower with: deploy key, OC200 credentials, ntfy endpoint
4. Write k3s CronJob manifest for OC200 backup
5. Deploy via ArgoCD
6. Validate the byte-equality question with two back-to-back manual runs
7. If byte-equality fails, adjust hash check logic before committing the CronJob long-term
8. Add subsequent devices one at a time, each as its own CronJob

---

## Deferred / Open

- Whether the OC200 backup already captures SG2218P state (avoiding a duplicate CronJob)
- Reolink API specifics for headless export
- Whether Brother's web UI exposes config export programmatically or requires manual save
- Long-term: should ER605 / OC200 backups go through a unified Omada-controller-aware script vs per-device scripts
