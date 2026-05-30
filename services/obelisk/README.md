# Obelisk

Windows 11 VM running on monolith via QEMU/KVM.

**Not managed by KubeVirt or ArgoCD.** Previous KubeVirt manifests removed after repeated boot failures due to OVMF/virtio-blk incompatibility and CDI import issues with Microsoft's session-authenticated ISO URLs.

## Current Setup

- QEMU/KVM process on monolith — see `docs/obelisk-runbook.md`
- Disk image: `/mnt/ssd-b/obelisk-disk/disk.img` (100G qcow2)
- ISO: `/mnt/ssd-b/obelisk-win11-iso/disk.img` (permanent artifact)
- RDP: `192.168.0.20:33389`

## What's Here

- `autounattend.xml` — Windows answer file for future reinstalls
- `docs/obelisk-runbook.md` — full operational runbook

## TODO

- Systemd service for QEMU process lifecycle
- Second Windows instance on remaining ~100G of ssd-b
- Fix autounattend boot detection for future unattended installs
- windows_exporter + Prometheus scrape config
