# Coordinated UPS shutdown

## Latest acceptance result: repeat physical test

[Inspection 34778571656](https://github.com/speddling/lwa-infra/actions/runs/34778571656)
confirms the 2026-09-13 repeat test's coordinated shutdown sequence:

| UTC | Evidence |
|---|---|
| 19:34:19 | Watchtower policy observed OB. |
| 19:39:20 | Policy requested FSD after approximately 5m01s. |
| 19:39:23 | Monolith received FSD and initiated automatic power-fail shutdown. |
| 19:39:28 | Monolith kubelet reported the node shutting down. |
| 19:39:39 | Watchtower reached its poweroff target. |
| 19:40:30–34 | Construct received orderly poweroff and QEMU exited successfully. |
| 19:40:35 | Monolith reached its poweroff target after unmounting storage. |

**Shutdown sequence passed; recovery acceptance remains open.** Both monitors are
running and arming markers persist, but the persistent-monitor probe failed in
both the initial inspection and [follow-up 34778641337](https://github.com/speddling/lwa-infra/actions/runs/34778641337).
A running process alone does not establish NUT login/coordination. Inspection now
includes current-boot NUT logs and a numeric unauthenticated login-count query to
resolve that failure without changing the policy or restarting services.

Monolith is Ready, Construct is running, DNS resolves, and all PVCs are Bound.
The initial recovery sample reported OL CHRG, 69% charge, 23% load and 1076 seconds
estimated runtime. Existing Watchtower unbound-resolvconf failure and Plane API
pods not Ready remain separate unresolved findings. Allow the battery to recharge
before considering another physical discharge test.

## LAN listener recovery correction

[Inspection 34783301802](https://github.com/speddling/lwa-infra/actions/runs/34783301802)
identified the post-reboot failure: Watchtower upsd bound 127.0.0.1 but logged
`not listening on 192.168.30.11 port 3493`. Login count was one (the local primary),
and Monolith repeatedly received connection refused. Credentials are not the
observed failure; the LAN listener is missing. Early startup before address
assignment is the likely cause. Older infrastructure files predate the UPS purchase;
the deployed configuration and commissioning evidence define this installation.

The correction is prepared, not deployed yet. `nut-server.service` now waits for
network-online and a bounded, explicit local-address check. A post-start check
requires both TCP listeners. Failures cause systemd to retry, retaining the same
loopback/Infra addresses and firewall boundary. The helper binds only an ephemeral
port to test local address availability and opens TCP connections to test listeners;
it never authenticates or sends UPS commands.

After human merge, run **Coordinated UPS shutdown → repair-network** from master.
It requires OL without OB/LB/FSD and coordinated ownership, installs the override,
restarts only nut-server, and waits for both existing monitors to reconnect. It
preserves credentials, active monitors and the arming policy. A failure leaves
recovery unverified; inspect the server log rather than repeatedly cycling services.
Normal disarmed preparation installs the same override for future deployments.

After the repair passes, run **Inspect UPS and shutdown prerequisites** to verify
Monolith communications and two persistent logins. A separately scheduled Watchtower
reboot on mains is required to verify boot recovery; this repair action itself
neither reboots a host nor repeats the battery-discharge test.

References: [upstream NUT startup ordering](https://raw.githubusercontent.com/networkupstools/nut/v2.8.1/scripts/systemd/nut-server.service.in),
[network-online semantics](https://wiki.freedesktop.org/www/Software/systemd/NetworkTarget/).

## Earlier commissioning and first-test history

Coordinated shutdown is **active** following [activation 34723961571](https://github.com/speddling/lwa-infra/actions/runs/34723961571).
Both persistent NUT monitors were connected and the five-minute policy was armed.
[Maintenance 34723553105](https://github.com/speddling/lwa-infra/actions/runs/34723553105)
verified live Kubernetes grace periods, the logind limit, kubelet inhibitor and node Ready.
[Construct acceptance 34723605172](https://github.com/speddling/lwa-infra/actions/runs/34723605172)
verified successful graceful stop, a new boot ID, SSH and DNS recovery.

Inspection 34721300124 confirmed that unattended-upgrades' later-sorting fragment
had overridden the earlier managed setting with 30 seconds. Preparation 34721344590
installed `zz-lwa-ups.conf`; the effective 150-second limit now survives reboot.

The owner completed the physical outage simulation on 2026-09-13. [Recovery inspection
34733935325](https://github.com/speddling/lwa-infra/actions/runs/34733935325) confirms both
NUT monitors active, Construct/k3s running, Monolith Ready and its kubelet inhibitor
present. UPS telemetry is OL, 100% charge, 22% load, 1700 seconds estimated runtime.
Construct's local previous-boot log records the poweroff request at 01:00:10 UTC
and shutdown activity, with a new boot at approximately 01:04 UTC.
[Evidence run 34738504187](https://github.com/speddling/lwa-infra/actions/runs/34738504187)
confirms Watchtower observed OB at 00:58:08 and requested FSD at 01:03:09 UTC
(5m01s). Monolith instead started stopping services at 01:00:10, before that FSD;
its NUT log shows exit on SIGTERM, not an automatic shutdown request. Construct
exited gracefully at 01:00:14 and Monolith unmounted its storage and reached
poweroff at 01:00:18. Both monitors are connected and armed after recovery.

**First-test limitation (resolved by the repeat shutdown test above):**
[Inspection 34739134859](https://github.com/speddling/lwa-infra/actions/runs/34739134859)
confirmed a short power-key press on Monolith at 00:57:39 UTC. Logind waited
150 seconds, with unattended-upgrades still holding an inhibitor at timeout,
before stopping services. The first test therefore did not exercise Monolith's
FSD response. The later repeat test did.

Recovery also shows `unbound-resolvconf.service` failed on Watchtower, two Plane API
pods running but not Ready, and Firecrawl RabbitMQ with 57 restarts. DNS resolution
and all PVC bindings passed. These findings are not yet attributed to the outage.

**Inspect UPS and shutdown prerequisites** now collects selected previous-boot NUT,
policy, Construct, kubelet and systemd records, plus current policy logs, arming
markers, persistent monitor count, failed units, DNS, pod status and PVC status.
Missing journals or nonzero embedded command results are missing/failed evidence;
the inspection workflow completing is not itself proof that every check passed.

## Policy and sequence

All data-connected equipment is owner-confirmed battery-backed. The grace period
is five minutes because most outages last two to three minutes.

Watchtower polls NUT every five seconds. Continuous observed `OB` starts a
monotonic timer; `OL` clears it. The timer survives policy-service restarts within
the same host boot. At 300 seconds it signals the local primary upsmon to initiate
NUT forced shutdown (FSD). It acts earlier on `OB LB` or reported remaining runtime
at or below 600 seconds. The ten-minute reserve accommodates Kubernetes shutdown,
Construct's bounded graceful/fallback path and some operating-system shutdown time;
it is a conservative configuration budget, not a measured guarantee.

The timer starts in observation mode: no FSD signal is sent without the root-owned
arming marker. Native upsmon independently handles low battery and communication
loss after being armed. Loss of communication after the UPS was last seen on
battery can trigger an earlier emergency shutdown; the five-minute timer is not
a reason to wait through loss of monitoring.

Monolith's secondary upsmon receives FSD. Both monitors use ordinary systemd
poweroff. Monolith's kubelet delays host shutdown for up to 120 seconds: 90 seconds
for ordinary pods and 30 for critical pods. Its shutdown inhibitor must be verified
live. Construct then follows its installed graceful stop handler during systemd
service shutdown. Watchtower can finish shutting down sooner; Construct's SSH
control uses Monolith loopback and a pinned host key, so it does not need Watchtower DNS.

**UPS output power is deliberately not switched off by NUT.** No POWERDOWNFLAG is
configured and stale flags block preparation. This avoids cutting power while
Monolith is still stopping workloads. Network equipment remains on battery until
mains returns or the battery physically runs out. After a test, manually power
on Watchtower and Monolith as needed; restoring mains alone is not guaranteed to
restart them because we do not cycle UPS outputs.

FSD is a committed shutdown. Restoring mains after FSD does not cancel that process.
The current GPU workload does not exist yet, so no inference service is stopped
by this PR. Disconnecting a client is not proof inference stopped. Reassess load,
runtime and explicit workload suspension when the GPU/SGLang deployment is built.

## Deployment workflow

Use **Coordinated UPS shutdown** (`coordinated-ups-shutdown.yml`) from `master`,
after human PR merge. All production actions are manual. PR checks run only on
GitHub-hosted runners with a public test fixture, without live credentials.

| Action | Effect and validation |
|---|---|
| `prepare` | Watchtower first: separate NUT accounts, LAN listener/firewall, policy in observation mode. Monolith second: NUT client, kubelet/logind files. Both monitors remain masked; no k3s or VM restart. |
| `apply-kubelet` | Requires `maintenance_ack=true`. Restarts Monolith logind and k3s to load the files; verifies the node is Ready, effective configz durations and a live kubelet inhibitor. Brief API/service disruption is expected. |
| `test-construct` | Requires `maintenance_ack=true`. Stops and starts only Construct from Monolith's independent runner, checks the graceful helper's successful exit and a changed guest boot ID, SSH and DNS recovery. Attempts to restore Construct even if the stop check fails. Saves acceptance tied to the installed helper hash. Active guest sessions disconnect. |
| `activate` | Read-only Watchtower preflight, then Monolith verification and secondary activation, then primary activation/timer arming. Requires OL with no OB/LB/FSD, at least 900 seconds estimated runtime, guest acceptance, live kubelet settings, and both persistent NUT monitors logged in. Unmanaged QEMU guests block arming pending review; their files are preserved. |
| `disarm` | On stable mains only, stops primary policy/monitor first, then masks the secondary. Removes arming markers but preserves telemetry/configuration. Does not cancel a committed FSD. |

These are staged operations, not a distributed transaction. A failed activation
can leave the secondary enabled while the primary remains unarmed. Review the job
results and complete or disarm the partial activation; do not call that state
ready for the full UPS test. No workflow automatically unplugs power or dispatches
FSD as a test.

Configuration files alone do not establish that the kubelet loaded the settings.
K3s 1.32+ is required for the managed kubelet configuration directory. Unsupported
versions, competing priority-based shutdown settings, insufficient logind limits,
or absent inhibitors fail validation rather than being treated as configured.

## Secrets, network and ownership

The existing shared Ansible Vault entry `vault_nut_monitor_password` is required
(non-placeholder, at least 12 characters). It is used as a secret seed with distinct
SHA-256 domain labels to produce separate primary/secondary credentials. The seed
is not rendered to either host. Only the relevant monitor credential is installed
on Monolith; Watchtower stores both in upsd.users. Files are root:nut 0640 and
secret-bearing tasks suppress output. Vault changes require a planned credential
rotation while disarmed, followed by preparation and revalidation on both hosts.

The existing Actions vault password unlocks the repository vault through a temporary
0600 runner-local file removed at step exit. No new plaintext repository secret,
GitHub secret, private-key transfer, or encrypted-artifact exchange is introduced.
Missing/placeholder vault data blocks preparation before configuration changes.

Runner identities remain Monolith `gh-runner`, Watchtower `speddling`; both use their
own existing SSH keys to log in as `speddling` with sudo. Neither requires the other
runner's SSH private key. The Monolith runner alone reaches Construct via port 2222.

NUT listens on 127.0.0.1 and 192.168.30.11, with UFW allowing TCP 3493 from Monolith
192.168.30.10. Preparation requires UFW already active; it does not replace the
broader firewall policy. NUT protocol authentication on this trusted Infra path is
not TLS-encrypted. The localhost primary credential stays on Watchtower; the
secondary has no primary/FSD authority.

`/etc/nut/lwa-coordinated` replaces the telemetry-only ownership marker; the old
telemetry workflow then refuses to overwrite the setup. `nut_enabled: false`
continues to disable the legacy Watchtower role and is not the new activation flag.
Do not enable that legacy role. `/etc/nut/lwa-shutdown-armed` and live service state
are the new activation evidence. Preparation refuses an armed or running monitor.

## Weekend mains-disconnection test — only after readiness is confirmed

1. Complete the guest acceptance and both-host activation checks. Save work, ensure
   local physical access and fresh backups for important data, and record OL,
   load, charge and runtime. Allow for service interruption and manual server power-on.
2. Disconnect the UPS **mains input**, leaving the UPS switched on and equipment
   plugged into battery-backed outlets. Do not disconnect its battery or USB cable.
3. Verify OB is reported. A short restoration before five minutes should cancel
   the timer. For the full test, continue on battery beyond five minutes only while
   sufficient runtime remains; low reserve can intentionally cause earlier shutdown.
4. Expect the shutdown request at approximately five minutes, plus polling and NUT
   coordination delay. Actual host poweroff takes additional time for workloads and
   filesystems. SSH/DNS/services will disappear as their hosts stop. Do not interpret
   the first lost SSH session as proof every filesystem has finished shutting down.
5. If shutdown does not begin near the expected time, restore mains and investigate;
   do not wait for battery exhaustion to force the test to finish. Once FSD begins,
   allow shutdown to complete even if mains is restored.
6. Restore mains and start Watchtower, then Monolith as needed. Verify DNS, k3s node
   Ready, applications/PVCs, Construct login, OL telemetry and both monitors. The
   monitors are enabled and arming markers persist across normal reboots.
7. Review previous-boot journals for `nut-monitor`, `lwa-ups-policy`, `k3s` and
   `construct`, recording timer and shutdown durations and any forced fallback.
   Mark full protection verified only after successful recovery; reset the runtime
   expectations after the PSU/GPU upgrade.

References: [NUT monitor semantics](https://networkupstools.org/docs/man/upsmon.conf.html),
[Kubernetes graceful node shutdown](https://kubernetes.io/docs/concepts/cluster-administration/node-shutdown/),
[K3s kubelet configuration](https://docs.k3s.io/installation/configuration),
[NUT authentication protocol](https://networkupstools.org/historic/v2.8.1/docs/developer-guide.chunked/net-protocol.html).
