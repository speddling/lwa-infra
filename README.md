# Little Wolf Acres — Home Lab

Personal Kubernetes homelab built with production-grade IaC discipline. Everything is code, nothing is clicked.

## Hardware

| Node              | Hostname     | Specs                        | Role                                |
| ----------------- | ------------ | ---------------------------- | ----------------------------------- |
| MacBook Air M4    | `apex`       | 16GB, 256GB                  | Primary workstation / control plane |
| AMD Ryzen 7 5700G | `monolith`   | 32GB DDR4, Fractal Define R4 | k3s worker node                     |
| Asus VM40B        | `watchtower` | 8GB RAM, 1TB SSD             | DNS + monitoring (always-on)        |

## Network

TP-Link Omada ecosystem — fully managed, SNMP-monitored.

| Device | Role |
|---|---|
| ER605 v2 | Multi-WAN VPN router |
| OC200 | Omada network controller |
| TL-SG1210P | Unmanaged PoE switch |
| 2× EAP245 | Access points (Foyer + Yarn Studio) |

DNS chain: **AdGuard Home → Unbound → root** (recursive, no upstream forwarder dependency)

## Stack

- **Kubernetes** — k3s
- **IaC** — Terraform Cloud
- **Automation** — GitHub Actions + Ansible (modular role structure, Ansible Vault for secrets)
- **Monitoring** — Prometheus · Grafana · node_exporter · blackbox_exporter · snmp_exporter
- **OS** — Ubuntu Server 24.04 LTS (monolith + watchtower)

## CI/CD

GitHub Actions pipelines run on self-hosted runners and handle:
- K3s cluster provisioning via Terraform
- Service deployment via `kubectl apply`
- Ansible playbook execution (DNS, monitoring, exporters)
- Secrets managed via Ansible Vault

## Services

| Service | Stack | Status |
|---|---|---|
| Navidrome | Kubernetes (PVC + Ingress) | ✅ Online — ~1TB FLAC/MP3 library |
| Watchtower DNS + Monitoring | Ansible roles, Prometheus, Grafana, AdGuard, Unbound | ✅ Online |
| Samba file share | Ansible | ✅ Online — family backups |
| Minecraft server | Kubernetes (optional world import workflow) | ✅ Online |

## Custom Tooling

**T-Mobile Home Internet Exporter** — custom Python Prometheus exporter for T-Mobile gateway metrics. Deployed as a hardened systemd service via Ansible, scraped by Prometheus on Watchtower.

## In Progress

- Closet rewire + Omada network reconfiguration

## Planned

- Private client jumpbox / VPN ingress
- Offsite mirror for music library and family file shares