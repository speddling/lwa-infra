# UPS shutdown implementation status

Updated 2026-09-13. Use [the coordinated shutdown runbook](ups-shutdown-runbook.md)
for the current implementation, workflow actions and weekend test procedure.

Owner policy: CP1000PFCLCD on Watchtower USB; all data-connected equipment remains
battery-backed. Allow five minutes for typical two-to-three-minute outages, with
an earlier shutdown for critical battery/reserve conditions. Reassess after the
planned Monolith PSU/GPU upgrade. Additional battery capacity is only a future option.

## Verified live

- [Inspection 34629066497](https://github.com/speddling/lwa-infra/actions/runs/34629066497):
  USB identifies CP1000PFCLCDa (`0764:0601`); NUT was then absent on both hosts.
- [Telemetry deployment 34660864596](https://github.com/speddling/lwa-infra/actions/runs/34660864596):
  Watchtower NUT driver/server active, monitor masked/inactive; OL, 22% load,
  100% charge and 1700 seconds estimated runtime. This was not an endurance test.
- [Construct lifecycle deployment 34663861718](https://github.com/speddling/lwa-infra/actions/runs/34663861718):
  graceful SSH stop handler installed; process identity and restricted SSH probe
  passed without changing the running QEMU PID. Shutdown/recovery later passed run 34723605172.

## Deployed and active

Activation passed run 34723961571. Physical outage simulation was owner-completed
on 2026-09-13; recovery inspection passed, previous-boot host-log review is pending.

The coordinated workflow implements both host monitors, Watchtower's five-minute
policy, Monolith's kubelet shutdown configuration, a guest acceptance test, and
staged activation/disarming. It replaces the earlier upssched proposal with a
single polling service whose monotonic timer survives service restarts within a
boot. NUT still handles primary/secondary FSD coordination and native emergencies.

Commissioning order (already completed): `prepare`, acknowledged `apply-kubelet`, acknowledged
`test-construct`, then `activate`. Preparation keeps monitors masked and the policy
in observation mode. It uses the existing shared vaulted NUT secret and each host's
own runner identity. Activation requires live kubelet/inhibitor evidence, guest
acceptance, both monitors connected and sufficient current runtime. No real mains
outage is part of a workflow.

The timer requests shutdown at 300 seconds observed on battery, or sooner when
remaining runtime is at or below 600 seconds or low battery is reported. The minimum
runtime for activation is 900 seconds. These budgets need validation under actual
load. Monolith's 120-second Kubernetes grace and Construct's bounded stop fallback
are accounted for; they are not measured shutdown timings yet.

NUT does not command UPS output power off, allowing Monolith to finish after
Watchtower shuts down. Servers may require manual power-on after mains restoration.
The legacy `nut_enabled` remains false; it must not be used to activate this setup.
Do not mark the full weekend test ready until the staged live checks pass.
