# Construct

Debian 12 development VM on Monolith, managed by QEMU/KVM and systemd.
8 vCPUs, 16 GB RAM, 80 GB qcow2 on NVMe at `/vm/construct` (`ubuntu-vg`).

Access from Apex or Studio: `ssh -p 2222 speddling@monolith.littlewolfacres.com`.
Configure a client SSH alias named `construct` as shown in
[the runbook](../../docs/construct-runbook.md). A dedicated LAN IP is deferred.

Tailscale and wmux are being retired from existing hosts by the manual
`retire-remote-access.yml` workflow. Future provisioning installs neither.
Herdr is installed independently; its setup is outside this migration.

`ansible/` contains the retirement inventory, playbook and removal roles.
VM provisioning remains under `services/monolith/ansible/roles/construct-vm/`.
Do not use that disk-destructive provisioning role to update a running VM.

See [the runbook](../../docs/construct-runbook.md) for migration prerequisites,
verification and recovery access. Scribe/Zombatron deployment code remains under
`services/apex/`; no Construct deployment for those services is defined here.
