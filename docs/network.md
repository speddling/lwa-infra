# Network Documentation

## Static IP Reservations

All static assignments are DHCP MAC-bound in the ER605. Do not set static IPs at the OS level.

| IP            | Hostname           | Role                                       |
| ------------- | ------------------ | ------------------------------------------ |
| 192.168.0.4   | Big Brother        | Reolink NVR / Camera Controller            |
| 192.168.0.7   | OC200              | Omada Network Controller                   |
| 192.168.0.19  | Apex               | MacBook Air M4 — Primary Workstation       |
| 192.168.0.20  | Monolith           | k3s Node — Primary Server                  |
| 192.168.0.21  | Watchtower         | DNS / Monitoring Stack                     |
| 192.168.0.109 | Studio             | Ubuntu Studio — DAW / KDE Workstation      |
| 192.168.0.1   | ER605 v2.0         | Gigabit Multi-WAN VPN Router               |
| 192.168.0.2   | EAP245-Foyer       | Access Point / Mesh                        |
| 192.168.0.5   | EAP245-Yarn-Studio | Access Point / Mesh                        |

All other devices use dynamic DHCP leases.

---

## Workspaces

Named k3s namespaces and logical environments on Monolith with reserved identities.

| Name | Namespace | Host | Purpose | Status |
|---|---|---|---|---|
| Synapse | `synapse` | monolith | MCP/AI tooling — Claude's interface to the homelab and coursework | ✅ Active |
| Obelisk | `obelisk` | monolith (`/mnt/ssd-b`) | Client workspace — isolated environment | 🔜 Reserved |

- **Synapse** is accessible at `http://monolith.littlewolfacres.com:30800/sse` (apex only, UFW restricted)
- **Obelisk** will be isolated at the namespace, storage, and network level when built

---

## Notes

- When Watchtower DNS is live, all fstab and Ansible inventory files referencing IPs should be updated to hostnames
- ER605 manages routing and firewall at the network boundary

---

**Network**  

- ER605 interface traffic (in/out bytes, packets, errors per interface)
- EAP245 Foyer interface stats
- EAP245 Yarn Studio interface stats
- Sagemcom FAST5688W (5G cell internet)— signal quality (RSRP, RSRQ, SINR), band, temperature, uptime, throughput

**DNS**  

- AdGuard Home — query rate, block rate, blocked domains, client counts, upstream latency
- Unbound — cache hit rate, query types

**Compute — Watchtower (Asus VM40b)**  

- CPU usage, load average
- Memory usage
- Disk usage and I/O
- Network throughput
- All systemd service states

**Compute — Monolith (old workstation, now Kubernetes lab)**  

- CPU, memory, disk, network (same as Watchtower via node_exporter)

**Uptime / Reachability**  

- Blackbox exporter probing endpoints (HTTP, ICMP, TCP)

**Power — UPS (pending budget for a** CP1500PFCLCD**)**  

- Battery charge, runtime remaining, load percentage, input voltage, on-battery status

**Security Cameras — NVR (planned)**  

- HDD health and capacity
- Channel online/offline status
- Detection event counts

---
*Last updated: 2026-05-14*
