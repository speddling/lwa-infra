# ufw

Manages UFW firewall rules on Monolith (Ubuntu 24.04). Default deny inbound, allow outbound.

## Ports managed

| Port | Service | Allowed From |
|---|---|---|
| 22   | SSH              | apex (192.168.20.2), studio (192.168.20.3), studio wired dock (192.168.10.7), temporarily LAN-wide |
| 80   | Traefik HTTP     | LAN |
| 443  | Traefik HTTPS    | LAN |
| 139/445 | Samba         | LAN |
| 9100 | node_exporter   | watchtower |
| 30132 | Minecraft UDP  | LAN |
| 30800 | Synapse MCP     | apex only |
| 30880 | ArgoCD NodePort | LAN |
| 30885 | ArgoCD controller | watchtower |
| 30883 | ArgoCD server   | watchtower |
| 30900 | kube-state-metrics | watchtower |
| 2222 | Construct SSH   | apex (192.168.20.2), studio (192.168.20.3) |
| 33389 | Obelisk RDP    | LAN |
| 39182 | Obelisk windows_exporter | watchtower |

## Run

Via workflow: `Actions → Deploy Monolith → Run workflow`
Manual: `ansible-playbook -i inventory.ini playbooks/firewall.yml --vault-password-file ~/.vault_pass`

> Do not add rules manually on Monolith — edit this role and push to master.
