# Construct graceful shutdown

Installed 2026-09-12 by [run 34663861718](https://github.com/speddling/lwa-infra/actions/runs/34663861718).
The dedicated SSH probe and live process checks passed; the same QEMU PID remained
running. A real shutdown/recovery acceptance test is still pending.

Construct must finish guest shutdown before Monolith terminates its QEMU process.
Inspection run 34629066497 found an immediate `kill -9` ExecStop and no QEMU
monitor/QMP socket. Use the existing localhost SSH forward to request guest
poweroff; no QEMU restart, VM rebuild, disk change or new network listener is
needed to install this approach.

## Install and verify without an outage

After human merge, dispatch **Configure graceful Construct shutdown**
(`configure-construct-shutdown.yml`) from `master`. It runs on Monolith as
`gh-runner`; Ansible logs into both hosts as `speddling` with sudo, using the
existing retirement inventory and pinned Construct host key.

The playbook preflights both hosts, creates a separate lifecycle key locally on
Monolith, installs the restricted guest command, and probes it. Only after the
probe and QEMU process identity checks succeed does it install the systemd drop-in
and reload systemd. It checks that the same QEMU PID remains active afterward.
It never calls the destructive `construct-vm` provisioning role.

## Identities and boundaries

- `/etc/construct-power/id_ed25519` stays on Monolith, owned by root, mode 0600
  in a 0700 directory. It is separate from the runner/developer keys; no private
  key is fetched into Actions, the checkout or Construct.
- Its public key is appended to Construct's existing `speddling` authorized_keys
  with `restrict` and a forced command. Existing keys remain intact. No root SSH
  login or new sudo grant is introduced; the playbook verifies the existing
  `speddling` poweroff privilege before making changes.
- The root-owned guest dispatcher accepts exactly `probe` or `poweroff` and
  checks the hostname. Probe checks sudo authorization without running poweroff.
  Client strings are never evaluated as shell code. PTY and forwarding are disabled.
- Monolith's client pins the same ED25519 host key as the retirement workflow;
  it does not use an agent, DNS, developer SSH settings or interactive passwords.
  A guest rebuild/key change requires re-verifying trust and reinstalling this
  authorization before relying on automatic shutdown.

OpenSSH key restrictions follow [sshd authorized_keys documentation](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT).

## Stop behavior

The drop-in at `/etc/systemd/system/construct.service.d/20-graceful-shutdown.conf`
replaces the immediate SIGKILL with `/usr/local/sbin/construct-stop $MAINPID`.
The helper verifies the executable, Construct disk argument and service cgroup,
then requests `systemctl --no-block poweroff` inside the guest. It waits up to
120 seconds, including the SSH request, for the original QEMU process to exit.
A Linux pidfd tracks that process even if its numeric PID is later reused.

SSH disconnection alone is not considered successful shutdown: QEMU must exit.
If the guest does not exit, the helper fails loudly and systemd retains its normal
termination fallback. TimeoutStopSec is 135 seconds; systemd can apply a separate
termination timeout after the helper, so this is not a claim that the entire
failure path is capped at 135 seconds. Budget up to approximately 255 seconds for
helper plus fallback, and measure the actual normal shutdown time. Forced fallback
is still possible; this change provides a graceful first attempt, not a guarantee
against every guest failure.

Installing the override changes subsequent service stops/restarts and host
shutdowns. It does not enable NUT, trigger a stop, or change boot behavior.

## Acceptance test still required

Arrange a Construct outage window after installation. Stop/start only the
`construct.service` on Monolith using an independent LAN session or runner;
keep the SSH-forward recovery path available. Active Construct sessions will end.
Verify guest clean shutdown/journal, the host helper result, elapsed time, and
successful guest boot with the existing disk before recording shutdown as tested.
Do not run host poweroff, unplug UPS input, or use Bootstrap Construct for this test.

Until acceptance passes, keep Watchtower's UPS shutdown monitor masked. Monolith's
NUT client, k3s workload shutdown and Watchtower's five-minute coordination timer
are prepared in [the coordinated workflow](ups-shutdown-runbook.md), with explicit
maintenance and activation gates. Obelisk files remain preserved.
