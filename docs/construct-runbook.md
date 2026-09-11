# Construct runbook

Updated: 2026-09-11. Desired access is LAN SSH through Monolith. The retirement
workflow must complete before Tailscale and wmux can be considered removed live.

## Access

From Apex or Studio:

```bash
ssh -p 2222 speddling@monolith.littlewolfacres.com
```

Client SSH configuration (replace an older Tailscale-based `Host construct` entry):

```sshconfig
Host construct
    HostName monolith.littlewolfacres.com
    Port 2222
    User speddling
    IdentitiesOnly yes
    IdentityFile ~/.ssh/id_ed25519
```

Then use `ssh construct`. The alias names the guest; its connection goes to
Monolith's LAN address, currently `192.168.30.10`, port 2222. Confirm addressing
against current network state before changing it. No WAN port forward is intended.
A separate LAN IP for Construct is deferred; it would require a separate networking change.

Monolith's UFW role allows this port from Apex (`192.168.20.2`) and Studio
(`192.168.20.3`). QEMU forwards it to guest port 22. Existing broad or manually
added firewall rules are not automatically removed by these additive rules.

## Retire Tailscale and wmux on existing hosts

1. Review and merge the migration PR. Let **Deploy Monolith Config** complete;
   it applies the SSH firewall rules and no longer installs Tailscale.
2. From Apex or Studio, verify a fresh key-authenticated SSH login through
   `monolith:2222`. Verify the host key against a trusted existing connection;
   do not disable host-key checking. Confirm the guest hostname is `construct`.
3. Move active work to an ordinary SSH session. Stopping wmux terminates its
   terminal sessions. Herdr is separately installed; this migration does not
   install, configure or remove it.
4. The Monolith runner's `gh-runner` account needs its existing SSH key authorized
   for `speddling` on both Monolith and Construct, passwordless sudo on both,
   and trusted known-host entries for `192.168.30.10` and `[127.0.0.1]:2222`.
   Ansible must already be installed (the Monolith deploy installs it).
5. Dispatch **Retire Tailscale and wmux** from `master`, checking
   `lan_ssh_verified` only after step 2. It runs
   `services/construct/ansible/playbooks/retire-remote-access.yml` on Monolith.
6. Verify a new `ssh construct` session from the workstation, DNS resolution,
   and cluster/application health. The workflow checks fresh runner SSH
   connections, internal/public DNS, and the k3s API after removal.

The workflow preflights both hosts before mutation, retires Construct first,
then Monolith only after Construct verifies successfully. It does not invoke
`construct-vm`, restart QEMU, change disks, or reconfigure guest networking.
It removes the Tailscale packages, apt sources, keyring and local node identity;
wmux's user service/application; and its specific live/persisted iptables redirect.
Unrelated iptables rules, development tools, user lingering, and `~/.wmux` session
records are retained. Cloud-init on future VMs installs neither service.

The live DNS check on 2026-09-11 found systemd-resolved using QEMU's DHCP resolver
(`10.0.2.3`). The migration leaves that configuration intact. Older documentation
about immutable `/etc/resolv.conf` does not describe this inspected VM.

Tailnet device records, reusable auth keys, old workstation SSH aliases and any
Cloudflare/AdGuard records pointing to tailnet addresses are outside this workflow.
Review/remove obsolete entries separately after successful migration; do not
publish Construct's QEMU-private address as a LAN DNS record.

## Failure handling

If preflight fails, fix the SSH key, host trust, sudo or resolver problem before
retrying. If a later check fails, stop and use Monolith's LAN SSH connection to
inspect Construct through `127.0.0.1:2222`. The removal workflow can be rerun after
the failure is resolved; it is not a VM rebuild or an automated rollback.

## VM and storage

Debian 12, 8 vCPUs, 16 GB RAM, QEMU/KVM with user-mode NAT. Guest address is normally
`10.0.2.15`; this is not directly reachable from LAN clients.
`construct.service` on Monolith manages `/vm/construct/disk.img` (80 GB qcow2)
backed by `/dev/ubuntu-vg/construct`. The base Debian qcow2 image is a backing-file
dependency and must be preserved with the VM disk.

```bash
# Read-only inspection on Monolith
systemctl status construct
journalctl -u construct -n 50
sudo qemu-img info /vm/construct/disk.img
```

**Do not run Bootstrap Construct or the construct-vm provisioning role to apply
this migration.** That role unconditionally deletes the VM disk, including with
`--tags cloud-init` because deletion tasks use `always`. The bootstrap workflow's
`rebuild=false` does not protect an existing disk; `rebuild=true` also kills other
QEMU processes. Use provisioning only as an explicitly reviewed rebuild operation.

Git, GitHub CLI, Node 22, Python, Go, tmux and Pi remain in first-boot provisioning.
Fresh provisioning uses SSH keys and disables password authentication. Existing
SSH authentication settings are not altered during retirement.
