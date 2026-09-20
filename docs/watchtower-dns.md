# Watchtower DNS helper investigation

The UPS recovery inspections recorded a failed `unbound-resolvconf.service` on
Watchtower while DNS queries still succeeded. That finding is separate from the
completed UPS recovery work. Its precise cause has not yet been established.

The repository's DNS roles configure AdGuard Home as the client-facing resolver
and Unbound on `127.0.0.1:5335`. The Unbound role disables systemd-resolved's stub
listener but does not explicitly manage the package's resolvconf integration.
Inspect the live resolver owner and helper error before changing that integration.

Run **Inspect Watchtower DNS** on master after merge. The runner is
`watchtower/speddling`, and SSH also uses `speddling` with its existing trusted
key and sudo. The diagnostic reads unit state, the helper's current-boot journal,
resolver configuration, package versions, listeners, and the package helper
script. It probes Unbound, AdGuard, and the host resolver independently. It does
not read AdGuard's credential-bearing configuration, restart services, reset
failed units, change resolvers, or alter NUT. Nonzero check results remain visible
in the report; workflow success alone does not establish healthy DNS.

Direct Argus access from Construct timed out on 2026-09-15. Its documented
firewall boundary still allows Apex only. Use the existing runner path for this
investigation; moving Argus access is a separate development migration item.

## Diagnosis and repair

Inspection `35543850424` on 2026-09-20 found the helper failed with:
`Failed to set DNS configuration: Link lo is loopback device.` Unbound was
running and valid on `127.0.0.1:5335`; AdGuard was running on `*:53`; direct
queries to both, and host resolution through systemd-resolved, returned NOERROR.
The helper is therefore an obsolete package integration, not a DNS outage.

The repair masks and stops `unbound-resolvconf.service` in the Unbound role and
ensures it is not enabled again. It leaves systemd-resolved, AdGuard, Unbound,
`/etc/resolv.conf`, listeners, and NUT unchanged. After merging, deploy the
Watchtower configuration and rerun the inspection. Acceptance requires the
helper to be masked/inactive, Unbound and AdGuard active, all three DNS probes
successful, and no failed units attributable to this helper.

The first post-deployment inspection `35544331895` confirmed the mask and all
DNS probes, but systemd still listed the historical failure in `systemctl
--failed`. The follow-up clears that stale result with `systemctl reset-failed`
after masking. This does not start, reload, or otherwise change the helper.
