# UPS commissioning and coordinated shutdown

Coordinated shutdown is active (run 34723961571). Construct's graceful stop/recovery
and Monolith's live Kubernetes/logind checks passed. The owner completed the physical
outage simulation on 2026-09-13; recovery checks passed, with previous-boot host-log
review still pending. See [the operational runbook](../../docs/ups-shutdown-runbook.md).

The telemetry-only workflow below is the historical initial commissioning path.
Coordinated configuration now owns `/etc/nut`; telemetry-only preparation refuses
to overwrite it. Do not run preparation over the active shutdown configuration.

## Telemetry phase

After human merge, dispatch **Deploy UPS telemetry only** (`deploy-ups-telemetry.yml`)
from `master`. Merge itself does not deploy. It runs on Watchtower as runner user
`speddling`, connects by strict-key SSH as `speddling`, then uses sudo. No vault
password or new credentials are needed; existing Ansible must be available.

The playbook installs distribution `nut-server`/`nut-client` packages, uses the
identified USB HID device, and enables the distribution driver enumerator/server.
The server listens only on `127.0.0.1:3493`. There are no authenticated control
users, no LAN firewall change and no exporter download. The automatic shutdown
monitor is masked before installation and remains stopped/disabled afterward.

Existing NUT configuration is accepted only with `/etc/nut/lwa-telemetry-only`;
an active monitor or `nut_enabled: true` blocks this commissioning playbook.
Remove the marker during the future coordinated-shutdown migration so this
workflow cannot overwrite that deployment. Do not enable the old Watchtower NUT
role to advance to the next phase; it lacks the agreed shutdown behavior.

Validation waits for an actual successful `upsc ... ups.status` response. Optional
model/load/charge/runtime fields are reported as unavailable if unsupported.
A successful telemetry deployment is not automatic shutdown protection and does
not prove battery health or full-load endurance. Rerun **Inspect UPS and shutdown
prerequisites** for named readings and installed versions after commissioning.

If commissioning fails, the monitor stays masked. Inspect the driver/server logs
and USB access before rerunning; never use `upsdrvctl shutdown`, `upscmd`, or
`upsmon -c fsd` to diagnose telemetry. No outage test is part of this workflow.

Driver selection follows [NUT usbhid-ups documentation](https://networkupstools.org/docs/man/usbhid-ups.html).
See [the shutdown plan](../../docs/nut-shutdown-plan.md) for the five-minute timer,
Monolith client, graceful guest shutdown and acceptance-test work still required.
