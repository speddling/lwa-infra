# NUT shutdown implementation plan

Owner decision, 2026-09-11: CyberPower CP1000PFCLCD installed, USB connected to
Watchtower. Watchtower and Monolith must begin orderly shutdown after five minutes
continuously on battery. This is desired behavior, not a deployed capability.
`nut_enabled: false` remains in force.

The owner confirms all data-connected equipment, including the network between
both servers, is battery-backed. The five-minute grace period is deliberate:
usual outages last only two to three minutes. Available runtime is an owner
estimate, not a measured shutdown budget. Read UPS load/runtime telemetry and
allow time for orderly shutdown; reassess this budget after Monolith's planned
PSU replacement and GPU addition.

## Live discovery and next deployment

[Inspection run 34629066497](https://github.com/speddling/lwa-infra/actions/runs/34629066497)
completed successfully on both hosts, 2026-09-11. Watchtower reports USB product
`CP1000PFCLCDa` (`0764:0601`). Neither host has NUT installed; load/runtime readings
are unavailable. Monolith's live Construct unit uses `kill -9`, and its running
QEMU has no QMP/monitor control arguments.

The separate `deploy-ups-telemetry.yml` workflow prepares local telemetry only;
see `../services/ups/README.md`. It does not activate the five-minute shutdown
policy. Telemetry deployment run 34660864596 succeeded on 2026-09-12: mains (`OL`),
22% load, 100% charge and 1700 seconds estimated runtime. The monitor was verified
masked/inactive. This is a telemetry estimate at the sampled load, not an endurance test.

The next prepared change uses the existing SSH forward for graceful Construct
shutdown, avoiding a QMP retrofit/restart; see `construct-shutdown.md`. Installation
is nondisruptive, but a real guest shutdown acceptance test still needs an outage window.

## Agreed implementation order

1. Construct: install and probe the restricted SSH stop handler, then test guest
   shutdown/recovery in an agreed window.
2. Monolith: install its NUT client and coordinate k3s workloads with guest shutdown.
3. Watchtower: configure primary coordination and the five-minute timer; activate
   only after the two preceding shutdown paths are verified.

The owner approved this ordering work and confirms the network remains on battery.
The planned GPU/PSU upgrade will require a new load/runtime assessment. Disconnecting
from services does not establish that background inference has stopped. Plan explicit
inference suspension when that workload is deployed; do not assume it already exists.
The owner may add battery capacity if needed; no additional UPS is presently verified.

## Proposed behavior

- Watchtower owns the USB driver, NUT server and primary monitor. Monolith runs
  a secondary monitor against Watchtower's Infra address, `192.168.30.11`.
- An ONBATT event starts a 300-second upssched timer; ONLINE cancels it. On
  expiry, recheck current UPS status and initiate NUT forced shutdown if still
  on battery. A later outage starts a fresh timer.
- Critical low battery retains NUT's earlier emergency shutdown behavior; five
  minutes is not a reason to exhaust the battery before shutting down.
- Monolith receives the shutdown state and begins stopping workloads. Watchtower
  coordinates through NUT's primary/secondary mechanism. HOSTSYNC acknowledges
  monitor disconnection, not completion of every guest or filesystem shutdown.
- Shutdown is committed once forced shutdown begins; restored mains at that
  point must not be presented as a guaranteed cancellation.

Timer semantics: [NUT upssched.conf](https://networkupstools.org/docs/man/upssched.conf.html).
Coordination semantics: [NUT upsmon.conf](https://networkupstools.org/docs/man/upsmon.conf.html).
Use directives supported by the installed Ubuntu package version, not newer
directives merely because they appear in upstream documentation.

## Read-only discovery

After merging the inspection workflow, run **Inspect UPS and shutdown prerequisites**
(`inspect-ups.yml`) from `master`. It runs on each host's existing runner:
Monolith process user `gh-runner`, Watchtower process user `speddling`. Both use
that runner's existing SSH key and strict host trust to log in remotely as
`speddling`, then use noninteractive sudo for inspection.

The workflow reports installed package versions, NUT service state, USB model/IDs,
available UPS status/load/runtime telemetry, and Construct shutdown/control
configuration. It installs nothing, reads no vault or NUT credential files, and
sends no power-control commands. Missing tools or unavailable telemetry appear
explicitly in the JSON report; a green workflow means inspection completed, not
that shutdown protection is working. Review each command's exit status/error.
The two inspection jobs can run independently; neither requires cross-host SSH
from Construct. PR validation executes only Python compilation on a hosted runner.

## Gaps to resolve before activation

1. Network battery coverage is owner-confirmed. Inspect USB detection and
   `upsc` status/model/load/runtime read-only;
   do not unplug mains or invoke forced shutdown as an inspection step.
2. Replace the incorrect CP1500PFCLCD template description. Establish vaulted
   credentials and the missing password mapping; separate the Monolith secondary
   account from Watchtower's primary authority. Protect rendered files and logs.
3. Add Monolith's client and narrowly allow TCP 3493 from Monolith to Watchtower.
   Watchtower's normal deploy does not apply its firewall playbook, so deployment
   order must explicitly include this rule and verify reachability.
4. Replace the notification-only upssched script with a validated timer handler,
   with narrowly scoped permission to initiate shutdown. Slack failures must not
   block or delay shutdown. Protect the timer pipe/lock directory.
5. Verify graceful k3s and VM shutdown. Construct's declared unit currently uses
   `ExecStop=/bin/kill -9 $MAINPID`; fix and test guest shutdown before enabling
   host automation. Do not run the destructive Construct provisioning role to
   deploy that change. Preserve all Obelisk disks and redeployment artifacts.
6. Validate exporter release, checksum and flags independently of the shutdown
   path. The existing unpinned download and credentials in command arguments need
   review. Monitoring success does not establish shutdown correctness.

## Validation and rollout

Prepare implementation on a branch and require human PR merge. Keep activation
disabled until USB and network checks pass on both hosts. Test timer start,
restoration cancellation, repeated outages, expiry, low battery, stale/lost
communications and notification failure with simulated events and stub shutdown
commands. Verify no test can call a real shutdown command or consume live UPS
events. Validate configuration against the target NUT package version.

Deploy the secondary client and firewall before enabling the primary timer.
Verify service state and authentication without displaying secrets. A real power
loss/shutdown acceptance test needs a scheduled outage window: it will stop
Construct, both CI runners, cluster services and DNS. Do not dispatch it from an
ordinary monitoring check. Record timings, filesystem/guest recovery and UPS
power-return behavior before marking automatic protection verified.
