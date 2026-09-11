# construct-vm

First-boot provisioning for Construct: Debian 12, QEMU/KVM, systemd, 8 vCPUs,
16 GB RAM and an 80 GB disk on `/dev/ubuntu-vg/construct` at `/vm/construct`.
Defaults are in `defaults/main.yml`. Access is through Monolith TCP 2222 to guest
SSH port 22. Tailscale and wmux are no longer installed by cloud-init.

**Destructive:** tasks unconditionally stop Construct and remove `disk.img`,
including when `--tags cloud-init` is used. Do not rerun against a VM you need
to preserve. The bootstrap workflow's `rebuild=false` does not prevent this.

For retirement of existing Tailscale/wmux installations use the separate manual
`retire-remote-access.yml` workflow. See `docs/construct-runbook.md`.
