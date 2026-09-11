# Development migration: Apex to Construct

Owner clarification, 2026-09-11: Apex previously hosted development and its tooling;
all development work now happens on Construct. Existing Apex services must be
explicitly migrated or retired. Moving the repository does not move their services,
credentials, client configuration or network access.

## Evidence from Construct

Read-only inspection on 2026-09-11 found:

- Checkout: `/home/speddling/lwa-infra`.
- Git, GitHub CLI, Python, Node 22, uv/uvx and Herdr available on PATH.
- `ansible-playbook`, Terraform and kubectl not on PATH. Temporary Ansible used
  for validation is not an installed development environment.
- No standard outbound `~/.ssh/id_ed25519` or `~/.ssh/known_hosts`.
- No `.vault_pass` in this checkout or `~/lwa-homelab`.
- No `~/.venv/scribe`, `~/.venv/zombatron-importer`, or matching units in
  `/etc/systemd/system` and `~/.config/systemd/user`.

These are observations of specific locations, not proof that no alternate
installation or credential exists. Do not print credential contents during inventory.

The Monolith runner process is `gh-runner`; the Watchtower runner process is
`speddling`. Main SSH inventories target `speddling`, then use sudo. Construct's
development identity and outbound key are separate from both runner identities.

## Service and dependency inventory

| Component | Existing source/assumption | Required Construct work |
|---|---|---|
| Scribe | `services/apex/scribe/`; launchd role, MacPorts Python, `/Users/speddling/...` repo allowlist | Confirm retention. If kept: Linux venv/service, explicit Construct repo allowlist, approved GitHub identity, process credentials and local MCP transport/access. Preserve branch/path guards. |
| Zombatron Importer | `services/apex/zombatron-importer/`; launchd role, Slack Socket Mode, SSH/SFTP to Monolith, GitHub workflow dispatch | Confirm retention. If kept: systemd service, protected environment file, its own verified Monolith SSH path/key and authorized staging permissions, Slack/GitHub credentials, and coordinated cutover from the old bot. |
| Atlas / Plane MCP | Configured in Apex's Claude Desktop as a stdio subprocess using `uvx` and a Plane token | Configure the actual Construct agent client if retained; establish token ownership and DNS/API reachability. No systemd service is implied for stdio. Do not copy macOS client JSON verbatim. |
| Synapse | Cluster service; host UFW rule allows Apex; NodePort 30800 | Verify reachability from Construct and the source address observed after QEMU NAT before changing allow rules. Keep read-only RBAC. |
| Argus | Watchtower service; docs say Apex-only while the current UFW role is LAN-wide | Verify actual firewall and Construct reachability, then document/implement the intended narrow access. Do not assume docs prove enforcement. |
| B-4 / Ollama | Historically Apex with Metal and unified memory | Decide whether to retain Apex as an inference endpoint or retire this setup. Construct is not an equivalent Metal host; do not transfer old resource/model assumptions. |
| Git/GitHub | Existing user authentication on Construct; separate GitHub login was only considered | Keep branch → PR → human merge. Decide service/account identities before configuring Scribe or changing credentials. |
| Ansible authoring | Current CI stays on Monolith/Watchtower; many configs assume `~/lwa-homelab/.vault_pass` | Prefer CI deployment. If local Ansible execution is needed, provision its environment, vault-password access and SSH authorization deliberately; do not assume they migrated. |
| Terraform | Monolith resource executes the k3s installer with `local-exec` | Do not move `terraform apply` to Construct until execution location is established. It must not accidentally install k3s in the dev VM. |
| Kubernetes administration | Historical workstation kubeconfig/API access | Decide whether Construct needs direct kubectl access; establish credentials and source firewall policy before enabling it. Existing Actions still handle deployment. |
| Herdr | Installed independently on Construct | Keep it independent of retired wmux; no reinstall is required for this access migration. |

## Cutover boundaries

1. Resolve the runner-to-Construct SSH authorization prerequisite and complete the
   already-reviewed Tailscale/wmux removal through the ordinary SSH forward.
2. Choose which legacy integrations remain in use. Prepare separate reviewable
   changes for retained services, including Linux deployment and client setup.
3. Establish each identity and secret's owner. A developer account, a CI runner,
   a bot dispatch token and a Plane account need not share credentials.
4. Validate service startup and read-only connectivity first. For Zombatron,
   starting a second live bot can consume channel events and dispatch jobs; stop
   the old instance before activating the replacement. A real world import remains
   a separate explicit confirmation because it changes family game data.
5. Update runtime location/status only after verification. Retire obsolete Apex
   launch agents and credentials as part of each completed cutover, not by assuming
   that unused-looking files are safe to delete.

The preserved `services/apex/` code is migration source, not a reason to continue
hosting development on Apex. Current macOS playbooks must not be run on Construct.
No new inbound WAN ports or dedicated Construct LAN IP are part of this plan.

## Open decisions

- Retain or retire Scribe and Zombatron; which agent client should consume retained MCPs?
- Keep B-4/Ollama on Apex as a reachable inference service, or retire it?
- Use the existing GitHub account on Construct or create a separate identity?
- Is local privileged Ansible/kubectl administration needed, or should production
  changes remain dispatched through the existing self-hosted runners?

Separately, EAP225-Outdoor is installed, but its address/name and monitoring need
controller verification. Obelisk retention and NUT activation/shutdown policy remain
separate decisions; moving development does not authorize deleting client data or
turning on an unverified power shutdown policy.
