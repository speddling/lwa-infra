# Monolith — Storage Layout

## Physical Drives

| Device  | Size   | Type     | Mount          | Purpose                                       |
| ------- | ------ | -------- | -------------- | --------------------------------------------- |
| nvme0n1 | 476.9G | NVMe SSD | `/` (150G LVM) | Boot / OS / k3s / unallocated headroom        |
| sda     | 465.8G | SATA SSD | `/mnt/ssd-a`   | k8s local-path provisioner (PVC storage)      |
| sdb     | 238.5G | SATA SSD | `/mnt/ssd-b`   | isolated `work space`/`client jumpbox`        |
| sdc     | 3.6T   | SATA HDD | `/mnt/hdd-c`   | Music library / fileserver / bulk drive space |
| sdd     | 1.8T   | SATA HDD | `/mnt/hdd-d`   | music-library / specific file mirror          |

> **Note:** The AB350 Pro4 throttles NVMe to PCIe 2.0 x2. 
> The unallocated NVMe space is intentional headroom for future growth, not an oversight.

---

## Mount Points 

All mounts are UUID-based in `/etc/fstab` to survive drive reordering on reboot.

```bash
# 512GB SSD - k8s local-path provisioner
UUID=2903b345-9ec9-4524-9a59-c065f1a7c67c  /mnt/ssd-a  ext4  defaults  0  2

# 256GB SSD - Isolated workspace / client jumpbox
UUID=6ec61651-6596-4f29-82e5-ca6c43b6f552  /mnt/ssd-b  ext4  defaults  0  2

# 4TB HDD - Music library / fileserver / bulk storage
UUID=5d036336-cc84-48ba-9f36-d403d4c75145  /mnt/hdd-c  ext4  defaults  0  2

# 2TB HDD - Music library / fileshare mirror
UUID=725e0389-8e5b-431f-bdb4-1c59ab79ddf6  /mnt/hdd-d  ext4  defaults  0  2
```

---
*Last updated: 2026-05-13*
