# Monolith — Storage Layout

## Physical Drives

| Device  | Size   | Type     | Mount          | Purpose                                       |
| ------- | ------ | -------- | -------------- | --------------------------------------------- |
| nvme0n1 | 476.9G | NVMe SSD | `/` (150G LVM) | Boot / OS / k3s / unallocated headroom        |
| sda     | 465.8G | SATA SSD | `/mnt/ssd-a`   | k8s local-path provisioner (PVC storage)      |
| sdb     | 238.5G | SATA SSD | `/mnt/ssd-b`   | isolated `work space` and  `client jumpbox`   |
| sdc     | 3.6T   | SATA HDD | `/mnt/hdd-c`   | Music library / fileserver / bulk drive space |
| sdd     | 1.8T   | SATA HDD | `/mnt/hdd-d`   | music-library / specific file mirror          |

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
└── (fileserver)

/mnt/lab-backups/
└── music-library/                ← Navidrome audio library (~605G)
```

---



## Post-Watchtower Cleanup
- Remove UFW from fileserver Ansible playbook — firewall policy will be managed at the network layer via ER605 / Watchtower

---

*Last updated: 2026-05-09*
