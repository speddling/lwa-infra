# Monolith — Storage Layout

## Physical Drives

| Device | Size | Type | Mount | Purpose |
|---|---|---|---|---|
| nvme0n1 | 476.9G | NVMe SSD | `/` (150G LVM) | Boot / OS / k3s — remaining space is unallocated headroom |
| sda | 465.8G | SATA SSD | `/mnt/ssd-a` | k8s local-path provisioner (PVC storage) |
| sdb | 238.5G | SATA SSD | `/mnt/ssd-b` | File server / family backups |
| sdc | 1.8T | SATA HDD | `/mnt/lab-backups` | Music library — replace with 8TB HDD when upgraded |

> **Note:** The AB350 Pro4 throttles NVMe to PCIe 2.0 x2. The unallocated NVMe space is intentional headroom for future growth, not an oversight.

---

## Mount Points

All mounts are UUID-based in `/etc/fstab` to survive drive reordering on reboot.

```
UUID=2903b345-9ec9-4524-9a59-c065f1a7c67c  /mnt/ssd-a       ext4  defaults  0  2
UUID=6ec61651-6596-4f29-82e5-ca6c43b6f552  /mnt/ssd-b       ext4  defaults  0  2
UUID=725e0389-8e5b-431f-bdb4-1c59ab79ddf6  /mnt/lab-backups ext4  defaults  0  2
```

---

## k3s Storage Classes

| Class | Provisioner | Path | Used By |
|---|---|---|---|
| `local-path` (default) | rancher.io/local-path | `/mnt/ssd-a` | Navidrome DB, future service PVCs |

The music library is mounted directly via `hostPath` in the Navidrome deployment — it is too large and too static to benefit from PVC abstraction at this scale.

---

## Directory Structure

```
/mnt/ssd-a/
└── pvc-*/                        ← k3s local-path provisioner directories

/mnt/ssd-b/
└── (reserved for file server)

/mnt/lab-backups/
└── music-library/                ← Navidrome audio library (~605G)
```

---

## Planned Changes

### 8TB HDD Upgrade
When the 8TB HDD arrives to replace the 2TB:

1. Install 8TB, identify device with `lsblk`
2. Format: `sudo mkfs.ext4 /dev/sdX`
3. Mount temporarily: `sudo mount /dev/sdX /mnt/hdd-new`
4. Rsync music library: `sudo rsync -av /mnt/lab-backups/ /mnt/hdd-new/`
5. Update `/etc/fstab` — replace `sdc` UUID with new drive UUID, change mount point to `/mnt/hdd`
6. Unmount old, mount new: `sudo umount /mnt/lab-backups && sudo mount -a`
7. Update `deployment.yaml` hostPath: `/mnt/lab-backups/music-library` → `/mnt/hdd/music-library`
8. Redeploy via GitHub Actions: `deploy-navidrome.yml`
9. Navidrome will rescan the library automatically within 1 hour (or trigger manually)

> DB loss on redeploy is acceptable — library reindexes automatically, playlists must be recreated manually.

---

## Post-Watchtower Cleanup
- Remove UFW from fileserver Ansible playbook — firewall policy will be managed at the network layer via ER605 / Watchtower


## Working With Claude

To share this repo with Claude for review or updates, run from the repo root:

```bash
find . -type f \( -name "*.yaml" -o -name "*.md" -o -name "*.yml" \) \
  ! -path "./.obsidian/*" \
  | sort | while read f; do
    echo "=== $f ==="
    cat "$f"
    echo ""
  done > homelab-dump.txt
```

Upload `homelab-dump.txt` directly in the Claude chat window.

---

*Last updated: 2026-04-23*
