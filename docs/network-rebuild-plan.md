# Network Rebuild Plan

The flat `192.168.0.0/24` network is being replaced with a segmented design built around five VLANs, a managed Omada switch, and a single-source-of-truth security policy that lives on the ER605.

This document is the **design** — the what and why. The [Network Migration Runbook](network-migration-runbook.md) covers the **how** — the cutover-day sequence.

---

## Goals & Principles

- **Best practice** over convenience where the two diverge
- **Single point of truth** for every concern: routing/firewall on ER605, DNS on watchtower (AdGuard), wireless config in OC200, network topology in this document
- **Default deny inter-VLAN**, with explicit allows captured below
- **Generous subnet allocation** (/24 per VLAN) so segments can grow without re-IP'ing
- **VLAN ID = third octet of subnet** so the mapping is self-documenting
- **Reserve VLAN 1** — never used for production traffic; trunk ports use a dedicated blackhole VLAN as their native

---

## Hardware

### Switch — TP-Link Omada SG2218P

Selected from the JetStream Smart Managed line. Key spec match:

| Need | SG2218P provides |
|---|---|
| Native PoE+ for APs, OC200, cameras | 16× 802.3at PoE+ ports, 150W budget |
| Omada SDN integration with existing OC200 | Native L2+ smart managed |
| SNMP for Prometheus | v1/v2c/v3 |
| 802.1Q VLANs | Up to 4094 |
| Quiet enough for the home office closet | **Fanless** passive cooling |
| Long lifecycle | Current-rev (UPC 840030709500), 5-year warranty |

PoE budget consumed: ~51W of 150W. Plenty of headroom.

**Not chosen and why:**
- SG2428P — louder (two fans, well-documented complaints), more ports than needed
- SG3428X — non-PoE, would require injectors; SG3428XMP price/value didn't justify the 10G uplinks once the Mac Mini M4 10GbE firmware issues came to light
- SG2210MP — too few ports for realistic 2-year growth

### Router

ER605 v2.0 retained. Continues handling WAN, DHCP, inter-VLAN routing, and all firewall policy.

### APs

Three APs total:

- **EAP245 — Downstairs Hall** (v3.0, indoor ceiling/wall mount, previously labeled Foyer)
- **EAP245 — Upstairs Hall** (v3.0, indoor ceiling/wall mount, previously labeled Yarn Studio — relocated upstairs for second-floor coverage near daughter's bedroom)
- **EAP225-Outdoor — Balcony** (v3, IP65 weatherproof, mounted above the master suite balcony slider on the back-NW corner of the house). Wi-Fi 5 AC1200, 802.3af PoE, detachable omnidirectional antennas. Selected over Wi-Fi 6 outdoor alternatives because the marginal benefit doesn't justify the price delta given the SG2218P is 1 Gbps and outdoor use cases don't have density problems.

---

## VLAN Architecture

Five segments organized by trust class:

| VLAN ID | Name | Subnet | Gateway | Trust class |
|---|---|---|---|---|
| 10 | Management | 192.168.10.0/24 | .10.1 | Network infrastructure only |
| 20 | LAN | 192.168.20.0/24 | .20.1 | Trusted users & their personal devices |
| 30 | Homelab | 192.168.30.0/24 | .30.1 | Trusted infrastructure / compute |
| 40 | IoT | 192.168.40.0/24 | .40.1 | Low-trust networked devices |
| 50 | Guest | 192.168.50.0/24 | .50.1 | Untrusted / school-managed |
| 999 | Blackhole | none | none | Trunk native VLAN; any untagged frame is dropped |

VLAN IDs are multiples of 10 to leave room for future segments (e.g., a `Lab` VLAN at 25, a `Storage` VLAN at 35) without renumbering.

### DHCP scope layout (per VLAN)

- `.1` — gateway (ER605)
- `.2–.99` — static reservations
- `.100–.200` — DHCP dynamic pool
- `.201–.254` — reserved for future static needs

Guest VLAN uses `.50–.200` for DHCP (more dynamic capacity, less static need).

---

## Static IP Plan

### Management (192.168.10.0/24)

| IP | Device |
|---|---|
| .10.1 | ER605 management interface |
| .10.2 | SG2218P |
| .10.3 | OC200 |
| .10.4 | EAP245 — Downstairs Hall |
| .10.5 | EAP245 — Upstairs Hall |
| .10.6 | EAP225-Outdoor — Balcony |

### Homelab (192.168.30.0/24)

| IP | Device |
|---|---|
| .30.10 | monolith |
| .30.11 | watchtower |
| .30.12 | Obelisk (Win11 VM on monolith) |
| .30.20 | Lore — Ollama inference server *(future)* |
| .30.21 | Data — production LLM build *(future)* |

### IoT (192.168.40.0/24)

| IP | Device |
|---|---|
| .40.10 | Big Brother NVR |
| .40.11 | Reolink camera #1 (door-focused, porch) |
| .40.12 | Reolink camera #2 (PTZ, road/driveway) |
| .40.20 | Brother HL-L3290CWD printer |

### LAN (192.168.20.0/24)

Pure DHCP. All LAN-class devices are wireless — no wired clients on this VLAN today (apex is WiFi-only; watchtower with a monitor and keyboard is the wired admin/recovery path). Optional DHCP reservation for apex if you ever want predictable RDP-source filtering.

### Guest (192.168.50.0/24)

Pure DHCP. Daughter's school Chromebook gets a reservation once its randomized MAC is captured on first connection.

---

## Switch Port Plan

SG2218P, 16× 1G PoE+ ports + 2× SFP slots.

| Port | Device | Mode | Native VLAN | Tagged VLANs | PoE |
|---|---|---|---|---|---|
| 1 | ER605 uplink | Trunk | 999 | 10, 20, 30, 40, 50 | off |
| 2 | monolith | Trunk | 30 | — *(add tags as VMs land on other VLANs)* | off |
| 3 | watchtower | Access | 30 | — | off |
| 4 | Lore *(future)* | Access | 30 | — | off |
| 5 | Data *(future)* | Access | 30 | — | off |
| 6 | spare — Homelab | Access | 30 | — | off |
| 7 | Big Brother NVR | Access | 40 | — | off *(wall powered)* |
| 8 | Reolink cam #1 | Access | 40 | — | **PoE+ on** |
| 9 | Reolink cam #2 | Access | 40 | — | **PoE+ on** |
| 10 | reserved — Chicken run/coop | Access | 40 | — | on *(ready for future outdoor PoE device at the coop)* |
| 11 | OC200 | Access | 10 | — | **PoE on** |
| 12 | EAP245 — Downstairs Hall | Trunk | 10 | 20, 40, 50 | **PoE+ on** |
| 13 | EAP245 — Upstairs Hall | Trunk | 10 | 20, 40, 50 | **PoE+ on** |
| 14 | EAP225-Outdoor — Balcony | Trunk | 10 | 20, 40, 50 | **PoE on** *(802.3af)* |
| 15 | spare — LAN | Access | 20 | — | off |
| 16 | unused | **shutdown** | — | — | off |
| SFP1 | reserved | — | — | — | n/a |
| SFP2 | reserved | — | — | — | n/a |

**Trunk semantics:**
- Port 1 (ER605 uplink) carries all five active VLANs tagged; native VLAN 999 drops any stray untagged frames.
- Port 2 (monolith) is a trunk with native = Homelab so the host interface sees untagged Homelab traffic as expected. Additional VLAN tags added later if VMs need to live on other segments.
- Ports 12, 13, & 14 (APs) have native = Management so the APs reach the OC200 untagged. The three tagged VLANs carry the wireless SSIDs (LAN, IoT, Guest).
- Port 10 is **reserved** for the future chicken-run/coop cable. Cable terminates in a weatherproof junction box at the coop end and stays unused until needed; the port is pre-configured for IoT VLAN so a future camera, outdoor AP, or sensor hub can plug in without reconfiguring the switch.

**PoE budget:** ~59W active draw of 150W. Reserved capacity (port 10 chicken run) leaves ample headroom for future outdoor PoE devices.

**Unused ports** are administratively shut down. No accidental plug-ins gain network access.

---

## Firewall Rules

**Default policy:** all inter-VLAN traffic **denied**, all WAN-outbound **allowed**, all WAN-inbound **denied** (WireGuard handled separately). Rules below are explicit allows on top of that. The ER605 firewall is stateful — return traffic is permitted automatically.

### From LAN (192.168.20.0/24)

| Destination | Port / Protocol | Purpose |
|---|---|---|
| Homelab .30.12 (Obelisk) | TCP 3389 | RDP from apex |
| Homelab .30.11 (watchtower) | TCP/UDP 53 | DNS via AdGuard |
| Homelab .30.10 (monolith) | TCP 445, 139 | Samba (wife laptop, daughter iPad) |
| Homelab .30.20 (Lore) *(future)* | TCP 11434 | Ollama from apex |
| Homelab .30.21 (Data) *(future)* | TCP 11434 | Ollama from apex |
| IoT .40.20 (printer) | TCP 631, 9100; UDP 5353 | Print + mDNS discovery |
| Management (all) | TCP 22, 80, 443 | Admin access to router/switch/APs/OC200 |

### From Guest (192.168.50.0/24)

| Destination | Port / Protocol | Purpose |
|---|---|---|
| IoT .40.20 (printer) | TCP 631, 9100; UDP 5353 | Print (Chromebook + visitors) |
| WAN | * | Internet only |

**No DNS allow to Homelab.** Guest DNS is pushed via DHCP as `1.1.1.1` and `9.9.9.9` — guests resolve externally, AdGuard query logs stay clean.

### From Homelab (192.168.30.0/24)

| Destination | Port / Protocol | Purpose |
|---|---|---|
| Management (all) | UDP 161, ICMP | watchtower SNMP scrapes + ping monitoring |
| WAN | * | Updates, container pulls, ArgoCD, ntfy |

No allow to LAN or Guest. Homelab does not initiate to user devices.

### From IoT (192.168.40.0/24)

| Destination | Port / Protocol | Purpose |
|---|---|---|
| WAN | * | Cameras phone home, printer firmware updates, NTP |

No allow to any internal VLAN. NVR ↔ cameras is intra-VLAN (no rule needed). Printer is a destination, never a source.

### From Management (192.168.10.0/24)

| Destination | Port / Protocol | Purpose |
|---|---|---|
| WAN | * | OC200 cloud access, firmware updates |

Default deny everything else. Management devices initiate nowhere internal.

---

## SSID Plan

| SSID | VLAN | Notes |
|---|---|---|
| `LittleWolfAcres` | 20 (LAN) | Main household SSID. Existing name retained so family devices reconnect transparently after cutover. |
| `LittleWolfAcres-IoT` | 40 (IoT) | Printer and any future IoT WiFi devices |
| `LittleWolfAcres-Guest` | 50 (Guest) | Daughter's school Chromebook, visitor devices |

No Homelab SSID — Homelab is wired-only by design.

All three APs (Downstairs Hall, Upstairs Hall, Balcony) broadcast all three SSIDs. Band steering and roaming between APs handled by Omada.

---

## DNS Strategy

**Split-horizon via AdGuard on watchtower (.30.11):**
- All internal VLANs (Management, LAN, Homelab, IoT) receive `.30.11` as their primary DNS via DHCP from the ER605.
- AdGuard handles `*.littlewolfacres.com` rewrites for internal service hostnames and filters/forwards external queries.
- Guest VLAN receives `1.1.1.1` and `9.9.9.9` via DHCP, bypassing AdGuard entirely.

**Service naming convention:** internal services live at `<service>.littlewolfacres.com` with AdGuard rewrites pointing to private IPs. Future externally-exposed services (Navidrome, etc.) go through a reverse proxy as a separate concern.

---

## Remote Access Architecture

Single source of truth for "how do I reach the homelab from outside": **WireGuard on the ER605**.

- One inbound UDP port (51820) on the WAN, no per-service port forwards
- WireGuard clients land in their own subnet with full reach into LAN, Homelab, IoT (similar trust level to LAN)
- New self-hosted services don't require firewall changes — they just become reachable over the tunnel
- Public service exposure (Navidrome when traveling, possibly Data) handled through a reverse proxy or Cloudflare Tunnel at a later phase, not port forwards

---

## Deferred / Open

- **WireGuard configuration** — subnet allocation, client policy, key rotation procedure
- **Reverse proxy / Cloudflare Tunnel** — for selective WAN-exposed services
- **Mermaid network topology diagram** — to be added as `docs/network-topology.md`
- **VLAN-aware Proxmox bridge on monolith** — required before any VM lands on a non-Homelab VLAN
- **PR fallback for WAN-side RDP** — only if WireGuard proves insufficient for some use case; source-IP-restricted port forward as fallback only

---

## Decisions captured for posterity

| Decision | Outcome | Rationale |
|---|---|---|
| Inter-VLAN routing location | ER605 (router), not switch | Single source of truth for security policy; ER605 is already the WAN boundary |
| Management VLAN split? | Yes, separate from Homelab | Tighter ACLs around admin interfaces; clean isolation if LAN is ever compromised |
| Obelisk placement | Homelab VLAN | Same VLAN as its host (monolith) and DNS/monitoring (watchtower) |
| Printer placement | IoT VLAN, not standalone | Single-device VLAN is overkill; IoT trust class fits |
| School Chromebook | Guest VLAN | School-managed device the user does not control; access pattern matches guest |
| Guest DNS | External (1.1.1.1) | Cleanest isolation, no Homelab punchthrough, no AdGuard log noise |
| 10G uplinks | Skipped | Mac Mini M4 10GBASE-T firmware issues + can be added later as a separate concern |

---

## More things to consider

### Apex needs a DHCP reservation — not optional

The plan lists a DHCP reservation for apex as "optional," but the Monolith UFW role allows SSH specifically from `ip_apex` (`192.168.0.19`). After migration, apex is a wireless device that lands somewhere in the `192.168.20.100–200` DHCP pool. Without a reservation, the firewall rule silently breaks and the primary admin SSH path from apex to Monolith is lost. Capture apex's MAC before cutover and create a DHCP reservation at a `.20.x` static address. Update `ip_apex` in `ansible/vars/main.yml` to that address in the IaC PR.

### Studio has no place in the new IP plan

`ip_studio: "192.168.0.109"` is in shared vars and has a corresponding SSH allow rule in the Monolith UFW role. Studio does not appear anywhere in the new VLAN static IP tables. Determine whether studio is wired or wireless, which VLAN it belongs to, and what its new IP will be. If it's a LAN-class device on WiFi, add a DHCP reservation in the LAN VLAN and update the var. If it's being retired or renamed, remove the UFW rule.

### Monolith UFW role needs a VLAN-aware rewrite, not a find-and-replace

The current firewall rules use `192.168.0.0/24` as a single catch-all for "internal LAN." After migration, that range doesn't exist, and different VLANs have different trust levels. The UFW role needs to be updated to reflect the actual post-migration access policy:

- **HTTP/HTTPS (80/443)** and **Samba (445/139)** — allow from `192.168.20.0/24` (LAN VLAN) only, not a broad internal range
- **ArgoCD NodePort fallback and Obelisk RDP** — LAN VLAN only (`192.168.20.0/24`)
- **node_exporter, ArgoCD metrics, kube-state-metrics** — watchtower only at its new IP (`192.168.30.11`)
- **Synapse MCP** — apex only at its new reserved IP
- **SSH** — apex and studio at their new IPs

Simply replacing `192.168.0.0/24` with a new range would grant LAN trust to the wrong VLANs. Each rule class should reference the correct VLAN subnet explicitly. Plan for this to be the most time-intensive part of the IaC PR.

### AdGuard rewrite sequencing: DNS must update before the IaC PR deploys

Prometheus scrape jobs target Monolith via `fqdn_monolith` (`monolith.littlewolfacres.com`). If the IaC PR's Ansible run fires before AdGuard's local rewrites are updated to point that name to `192.168.30.10`, every `fqdn_monolith`-based scrape job fails with a connection error. The runbook has AdGuard prep in Phase 1 and the IaC PR in Phase 5 — make sure the rewrite list is actually pushed to AdGuard before the IaC deploy runs, not just prepared. Verify with `dig monolith.littlewolfacres.com @192.168.30.11` from a Homelab device before triggering the workflow.

### Prometheus scrape job names should be updated in the IaC PR

Once the OC200 rename of "Yarn Studio" → "Upstairs Hall" happens, the Prometheus job name `snmp-eap-yarn-studio` will be a permanent inconsistency in Grafana and the scrape config. Rename it to `snmp-eap-upstairs-hall` in the IaC PR while everything else is being touched. No functional impact — just clarity.

### Blackbox ICMP probe targets are var-referenced — handled automatically

The `blackbox-icmp` probe in `prometheus.yml.j2` targets `ip_monolith` and `ip_watchtower` directly (currently `192.168.0.20` and `192.168.0.21`). These are pulled from `ansible/vars/main.yml` rather than being hardcoded strings, so updating those vars in the IaC PR will update the probe targets automatically. No separate action needed — just confirming these are covered.

### "VLAN-aware Proxmox bridge" doc correction

The deferred item reads "VLAN-aware Proxmox bridge on monolith." Monolith runs bare-metal k3s, not Proxmox. This should read "VLAN-aware Linux bridge on monolith" — the concept is identical (create a VLAN-tagged bridge interface so future VMs can reach non-Homelab VLANs) but the tooling is a netplan/networkd config, not a Proxmox interface. Update this note before it causes confusion during implementation.

### ER605 syslog destination will need updating post-migration

When AT&T Internet Air WAN2 is added, the ER605 is configured to send syslog to Watchtower at `192.168.0.21:1514` for Promtail ingestion. After the VLAN migration, Watchtower moves to `192.168.30.11`. Remember to update the ER605 syslog destination in that same IaC cutover window, or the WAN event log stream will break silently.

### AT&T Internet Air gateway lives outside the VLAN architecture

The AT&T CGW450 connects to the ER605 WAN2 port and sits entirely outside the internal VLAN structure. Its LAN-side IP (typically `192.168.1.1`) is only visible to the ER605's WAN2 interface — no internal VLAN or firewall rule touches it. The `ip_att_gateway` var and the commented-out `snmp-att-cgw450` scrape job in `prometheus.yml.j2` are WAN-side concerns only. No VLAN planning is needed for the AT&T gateway.
