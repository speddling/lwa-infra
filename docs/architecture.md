# LWA Infra — Architecture

Documentation audit: 2026-09-11. This describes repository declarations and dated
operator confirmations, not a new live survey. See `homelab-state.md` for addressing
and migration status; verify addresses against fresh Omada evidence before changes.

## Hosts and failure domains

- **Monolith:** Ubuntu, Ryzen 5700G, 64 GB RAM. Single k3s node, Samba, Construct
  and the unused Obelisk Windows VM. Its CI runner process runs as `gh-runner`.
- **Watchtower:** Ubuntu, Celeron mini-PC, 8 GB RAM. DNS and monitoring remain
  outside k3s. Its CI runner process runs as `speddling`.
- **Apex:** M4 MacBook Air client workstation; former host for development and local AI tooling. All development work has moved to Construct.
- **Studio:** Dell Precision workstation/DAW. WiFi on Users; wired dock on Mgmt
  provides a separate emergency access path.
- **Construct:** Debian 12 QEMU/KVM VM on Monolith, systemd lifecycle, 8 vCPUs,
  16 GB RAM and 80 GB disk. All development authoring now happens here (owner confirmed 2026-09-11). Herdr is
  installed separately from the retired-in-design wmux browser terminal.
- **Obelisk:** QEMU/KVM Windows VM still present, unused and no longer needed
  according to the owner (2026-09-11). Decommissioning awaits retention review.

The UPS is installed and USB-connected to Watchtower (owner confirmation,
2026-09-11). NUT's role is disabled; working monitoring and shutdown behavior have
not been established. Which equipment uses battery-backed outlets needs confirmation.

## Network and DNS

T-Mobile FAST 5688W and AT&T CGW450 cellular WANs terminate on the Omada ER605.
The SG2218P provides managed switching/PoE, OC200 control, and two EAP245s WiFi.
EAP225-Outdoor is installed (owner confirmed 2026-09-11); its live address and monitoring remain unverified. The old unmanaged switch is decommissioned.

Documented VLAN state: Mgmt 10, Users 20 and wired Infra 30 are stable; IoT 40
has the NVR; Guest 50 and blackhole/native 999 remain planned. Router policy is
managed manually today: the Omada role only exports sites/device inventory.

LAN DNS: AdGuard Home on Watchtower → Unbound → recursive root resolution.
AdGuard rewrites are Ansible-managed. Cloudflare is authoritative for
`littlewolfacres.com` and supplies DNS-01 challenges. Public DNS-only records
for internal services may intentionally point to LAN addresses; records do not
create network access. Do not assume every service is publicly exposed.

Construct's QEMU NAT network uses guest `10.0.2.15` with host port 2222 forwarded
to guest SSH port 22. Apex/Studio access `monolith:2222`; a client SSH alias can
name this `construct`. A dedicated guest LAN IP is deferred. Removal of Tailscale
on both hosts and wmux on Construct is pending successful retirement workflow
execution. ER605 WireGuard remains a separate deferred design.

## Authoring through production

```text
Construct: inspect → branch → edit → validate → PR
                                           │
                                    human review/merge
                                           │
                                  GitHub master revision
                                  /                    \
              path-filtered Actions                 ArgoCD reconciliation
              Ansible / kubectl                     root apps → children
              host config / bootstrap               Kubernetes resources
                                  \                    /
                              verify deployed behavior
```

No staging/promotion environment is declared. Merge can deploy to production
immediately. Scribe is a documented git mechanism; the branch/PR/human-merge
workflow is the requirement, not permanent use of that mechanism.

| Context | Local process | Remote login / privilege |
|---|---|---|
| Monolith runner | `gh-runner` | Main Ansible inventory: SSH `speddling`, then sudo |
| Watchtower runner | `speddling` | Main Ansible inventory: SSH `speddling`, then sudo |
| Retirement on Monolith runner | `gh-runner` | SSH `speddling` to Monolith LAN and Construct loopback forward, then sudo |
| Synapse image build | GitHub-hosted runner | Builds/pushes GHCR image; Monolith handles deployment |

Known-hosts files and client private keys belong to the local runner process
user. `authorized_keys` belongs to the remote login account. Do not conflate
these with root privileges used by individual tasks. Some PR validation jobs
install packages and write vault-password files on the production runners.

## Kubernetes and deployment ownership

The root ArgoCD Application watches `kubernetes/apps/` on `master`. Ten child
Applications declare Navidrome, Jellyfin, Kavita, Minecraft, Synapse, Firecrawl,
Plane, kube-state-metrics, cert-manager configuration and ArgoCD configuration.
Automated pruning/self-healing and Application deletion finalizers are enabled.
Deleting manifests can delete live resources; manual changes can be reverted.

Traefik handles ingress/TLS. Bootstrap pins ArgoCD v3.3.0 and cert-manager
v1.20.2 controller/CRD installations; the cert-manager Application owns local
configuration such as ClusterIssuers, not the upstream installation itself.

Direct Actions applies remain for media applications, Synapse, Firecrawl and
kube-state-metrics. Plane uses a remote Helm chart with generated secrets and
a separately bootstrapped Certificate. That Certificate is also inside the root
Application's watched directory, so bootstrap-only ownership is not established.
Plane's `WEB_URL` and ArgoCD repo-secret data have deliberate ignore-difference
exceptions; preserve those until their original causes are resolved.

Monolith Terraform declares a k3s-installing `null_resource` using `local-exec`.
Watchtower Terraform has only its cloud backend. Verify Terraform execution
placement and the existing datastore arguments before reusing provisioning.

## Storage and recovery

- NVMe: host OS and Construct's `/vm/construct` LV (`ubuntu-vg`).
- `/mnt/ssd-a`: k3s local-path PVCs, tied to Monolith.
- `/mnt/ssd-b`: Obelisk artifacts and Samba vault share.
- `/mnt/hdd-c`: music/media and bulk data.
- `/mnt/hdd-d`: nightly rsync mirror with `--delete`, smaller than the source.

Shared variables currently place the Studio archive at `/mnt/lab-backups`,
while historical docs place it on HDD-C. Treat that discrepancy as unresolved.
No complete off-host/versioned recovery chain for VMs, PVCs and Plane secrets is
established here. The deleting mirror does not supply historical recovery.

Construct provisioning is destructive even with the documented cloud-init tag.
Use the separate retirement playbook for access changes; do not invoke bootstrap
against a VM that must be preserved. Obelisk is not managed by KubeVirt/ArgoCD;
the legacy KubeVirt workflow remains dispatchable but references deleted manifests.

## Observability

Watchtower runs Prometheus, Alertmanager, Grafana, Loki, Promtail, Netdata and
exporters as systemd services. Kubernetes object/ArgoCD metrics are exposed via
NodePorts on Monolith. SNMP covers router, switch and AP interfaces; custom
exporters cover T-Mobile and Reolink. Endpoint probes add reachability checks.

Prometheus evaluates alerts; Alertmanager routes to Slack and an external
healthchecks.io watchdog. A separate systemd timer sends morning/evening summaries
and pings its own healthcheck. Grafana alerting is disabled and unmanaged dashboards
are purged during deployment. The Loki datasource still requires manual provisioning.
Promtail declares Watchtower journal collection and UDP network syslog on 1514;
live device forwarding must be checked before claiming logs are arriving.

## Secrets and AI boundaries

Ansible Vault holds encrypted shared secrets; Actions injects its password into
runner-local files. Other credentials come from GitHub secrets, generated cluster
Secrets (Plane), and workstation-local MCP configuration. Firecrawl includes
literal Secret `stringData` in git, so not all credential-shaped values are vaulted.
Bootstrap logs and rendered secret-bearing files require separate review.

Synapse has read-only Kubernetes RBAC, logs and mounted filesystem reads. Argus
has read-only monitoring APIs, config/journal access and a dedicated service user.
These read surfaces can expose sensitive data. Documentation's apex-only Argus
boundary conflicts with the LAN-wide UFW source currently declared.

Scribe guards git branches and paths but uses its process user's credentials.
Its current location/use and Zombatron's location/use await operator confirmation:
the repo contains Apex launchd deployment, not their asserted Construct migration.
Atlas uses a Plane account token with broad mutation permissions. Plane records
obligations and incidents; the repository declares infrastructure configuration.

B-4/Ollama on Apex is documented, but no reproducible local inference deployment
or current model inventory is managed by this repo. Do not infer that all earlier
model names or endpoints are still active.

See `construct-development-migration.md` for surviving Apex tooling and the
Construct paths, identities and access dependencies that still need migration.
