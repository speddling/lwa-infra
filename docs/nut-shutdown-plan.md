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
