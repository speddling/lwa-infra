# LWA Infra — Network Migration Runbook
> Last updated: 2026-06-23

Operational sequence for moving from the flat `192.168.0.0/24` network to the 5-VLAN segmented design.

**Design principle:** nothing breaks until cutover, and cutover has a one-click rollback.

**Maintenance window:** ~60 minutes. Family gets a 30-minute warning before takedown.

---

## VLAN Reference

| VLAN | Name | Subnet | Gateway | Trust |
|------|------|--------|---------|-------|
| 10 | Mgmt | 192.168.10.0/24 | .10.1 | Network infrastructure only |
| 20 | Users | 192.168.20.0/24 | .20.1 | Trusted users & personal devices |
| 30 | Infra | 192.168.30.0/24 | .30.1 | Trusted infrastructure / compute |
| 40 | IoT | 192.168.40.0/24 | .40.1 | Low-trust networked devices |
| 50 | Guest | 192.168.50.0/24 | .50.1 | Untrusted / school-managed |
| 999 | Pit | none | none | Trunk native — untagged frames dropped |

**DHCP pool layout (all VLANs except Guest and Pit):**
- `.1` — gateway (ER605)
- `.2–.99` — static reservations
- `.100–.200` — dynamic pool
- `.201–.254` — reserved

**Guest exception:** dynamic pool is `.50–.200` (more DHCP capacity, fewer statics).

---

## Static IP Plan

### Mgmt (192.168.10.0/24)
| IP | Device |
|----|--------|
| .10.1 | ER605 management interface |
| .10.2 | SG2218P |
| .10.3 | OC200 |
| .10.4 | EAP245 — Downstairs Hall |
| .10.5 | EAP245 — Upstairs Hall |
| .10.6 | EAP225-Outdoor — Balcony *(future)* |

### Infra (192.168.30.0/24)
| IP | Device |
|----|--------|
| .30.10 | monolith |
| .30.11 | watchtower |
| .30.12 | Obelisk (Win11 VM on monolith) |
| .30.20 | Lore — Ollama inference *(future)* |
| .30.21 | Data — production LLM build *(future)* |

### IoT (192.168.40.0/24)
| IP | Device |
|----|--------|
| .40.10 | Big Brother NVR |
| .40.11 | Reolink camera #1 (porch) |
| .40.12 | Reolink camera #2 (driveway PTZ) |
| .40.20 | Brother HL-L3290CWD printer |

### Users (192.168.20.0/24)
| IP | Device | Notes |
|----|--------|-------|
| .20.2 | apex | MAC-bound reservation. Disable WiFi MAC randomization for `LittleWolfAcres` SSID before cutover. |
| .20.3 | Studio | MAC-bound reservation. Same — disable randomization. |

All other Users devices are pure DHCP.

### Guest (192.168.50.0/24)
Pure DHCP. Capture daughter's Chromebook MAC on first connection and add as a reservation.

---

## Switch Port Map

See [`switch-port-map.svg`](switch-port-map.svg) for a visual reference.

| Port | Device | Mode | Native VLAN | Tagged VLANs | PoE |
|------|--------|------|-------------|--------------|-----|
| 1 | ER605 uplink | Trunk | 999 (Pit) | 10, 20, 30, 40, 50 | off |
| 2 | monolith | Trunk | 30 (Infra) | *(add tags as VMs need other VLANs)* | off |
| 3 | watchtower | Access | 30 (Infra) | — | off |
| 4 | Lore *(future)* | Access | 30 (Infra) | — | off |
| 5 | Data *(future)* | Access | 30 (Infra) | — | off |
| 6 | spare — Infra | Access | 30 (Infra) | — | off |
| 7 | Big Brother NVR | Access | 40 (IoT) | — | off *(wall powered)* |
| 8 | Reolink cam #1 | Access | 40 (IoT) | — | **PoE+ on** |
| 9 | Reolink cam #2 | Access | 40 (IoT) | — | **PoE+ on** |
| 10 | reserved — coop/run | Access | 40 (IoT) | — | on *(pre-staged, disabled until cable pulled)* |
| 11 | OC200 | Access | 10 (Mgmt) | — | **PoE on** |
| 12 | EAP245 — Downstairs Hall | Trunk | 10 (Mgmt) | 20, 40, 50 | **PoE+ on** |
| 13 | EAP245 — Upstairs Hall | Trunk | 10 (Mgmt) | 20, 40, 50 | **PoE+ on** |
| 14 | EAP225-Outdoor — Balcony *(future)* | Trunk | 10 (Mgmt) | 20, 40, 50 | **PoE on** *(802.3af)* |
| 15 | spare — Users | Access | 20 (Users) | — | off |
| 16 | unused | **shutdown** | — | — | off |
| SFP1 | reserved | — | — | — | n/a |
| SFP2 | reserved | — | — | — | n/a |

---

## Pre-Cutover Checklist

Work that can be done while the flat network keeps running.

### OC200

- [x] Create VLANs 10, 20, 30, 40, 50, 999 in OC200
- [x] Flip each VLAN to **Interface** purpose and define DHCP scopes (pool, DNS) with DHCP Server on — networks not yet active
- [x] Rename EAP245s: Foyer → **Downstairs Hall**, Yarn Studio → **Upstairs Hall**
- [ ] Pre-create static reservations:
  - Infra: `.30.10` monolith, `.30.11` watchtower, `.30.12` Obelisk
  - IoT: `.40.10` Big Brother NVR, `.40.11–.12` Reolinks, `.40.20` printer
  - Mgmt: `.10.1–.6` infrastructure (controller auto-assigns most via Omada discovery)
  - Users: `.20.2` apex, `.20.3` Studio — capture MACs first; **disable WiFi MAC randomization for `LittleWolfAcres` on both devices before cutover**
    - macOS: Settings → Wi-Fi → Details → Private Wi-Fi Address → off (per network)
    - Windows: Settings → Wi-Fi → [network] → Random hardware addresses → off
- [ ] Pre-create SSIDs `LittleWolfAcres-IoT` (VLAN 40) and `LittleWolfAcres-Guest` (VLAN 50), marked **disabled**
- [ ] Retain existing `LittleWolfAcres` SSID — it moves to VLAN 20 (Users) at cutover; family devices reconnect transparently
- [ ] Configure mDNS Repeater: Settings → Services → mDNS → enable on the Gateway (ER605), add forwarding rules Users→IoT and Guest→IoT scoped to the printer's Bonjour/IPP service
  - Requires Controller 5.6+ (have 5.14.x ✓) and matching ER605 firmware (have 2.2.3 ✓)
  - Fallback if auto-discovery is troublesome: add printer manually by IP (`.40.20`) on each device — works regardless of mDNS Repeater state

### AdGuard

- [ ] Export current local DNS rewrites (backup)
- [ ] Prepare updated rewrite list mapping every `*.littlewolfacres.com` entry to its new IP
- [ ] Confirm AdGuard listener is bound to `0.0.0.0` (not a specific interface) so it answers across all VLANs post-cutover

### IaC Prep

- [ ] `grep -rn '192.168.0.' .` across the repo — list every occurrence, group by file
- [ ] Stage all changes (Ansible vars, K8s manifests, monitoring configs, `homelab-state.md`, `network.md`) in a parallel PR branch — **hold until post-cutover**
- [ ] Rename Prometheus job `snmp-eap-yarn-studio` → `snmp-eap-upstairs-hall` in that PR
- [ ] Rewrite UFW rules on monolith — `192.168.0.0/24` catch-all must be split by VLAN:
  - HTTP/HTTPS, Samba → `192.168.20.0/24` (Users) only
  - node_exporter, ArgoCD metrics → watchtower `192.168.30.11` only
  - Synapse MCP → apex `192.168.20.2` only
  - SSH → apex and Studio at their reserved IPs
- [ ] Update ER605 syslog destination `192.168.0.21:1514` → `192.168.30.11:1514` in the IaC PR

### Backups

- [ ] OC200 config export
- [ ] ER605 config export
- [ ] AdGuard config snapshot
- [ ] Ansible vault committed and tagged (rollback reference)

### Logistics

- [ ] Confirm 30-minute family warning channel
- [ ] Pick maintenance window — late evening or weekend morning
- [ ] Stage monitor and keyboard at watchtower for wired recovery during cutover

---

## Cutover

Issue **30-minute family warning** before starting.

1. **Snapshot OC200 config** — this is your rollback point
2. In OC200, **enable the new networks** (VLANs 10/20/30/40/50/999). ER605 immediately begins listening on the new VLAN gateways
3. **Push the SG2218P port plan** — trunks, native VLANs, tagged VLANs per the switch port table above. Ports change behavior immediately
4. Update static-IP devices that don't pull config from Omada:
   - **watchtower** — change static config `.0.21` → `.30.11` (or convert to DHCP reservation and reboot)
   - **monolith** — `.0.20` → `.30.10`
   - **Big Brother NVR** — `.0.4` → `.40.10` (via NVR web UI)
   - **Reolink cam #1** — → `.40.11` (via Reolink app)
   - **Reolink cam #2** — → `.40.12` (via Reolink app)
5. **Push AdGuard DNS rewrites** — paste the prepared list. Verify: `dig monolith.littlewolfacres.com @192.168.30.11` from an Infra device
6. **Enable new SSIDs** in OC200 (`LittleWolfAcres-IoT`, `LittleWolfAcres-Guest`). Move `LittleWolfAcres` to VLAN 20 (Users)

---

## Post-Cutover Verification

Per-VLAN smoke test. Don't skip any of these.

### DHCP
- [ ] Users device gets `192.168.20.x`, gateway `.20.1`, DNS `.30.11`
- [ ] IoT device gets `192.168.40.x`, gateway `.40.1`, DNS `.30.11`
- [ ] Guest device gets `192.168.50.x`, gateway `.50.1`, DNS `1.1.1.1` / `9.9.9.9`
- [ ] Infra device gets `192.168.30.x`, gateway `.30.1`, DNS `.30.11`
- [ ] Mgmt interfaces visible at `.10.x` from an Infra device

### DNS
- [ ] `dig monolith.littlewolfacres.com` from a Users device returns `192.168.30.10`
- [ ] AdGuard query log shows queries from the Users VLAN subnet
- [ ] AdGuard query log shows **no** queries from the Guest VLAN subnet (confirms split-horizon DNS)

### Inter-VLAN Rules
- [ ] RDP from apex → Obelisk (`.30.12`) works
- [ ] RDP from Studio → Obelisk is **blocked** (Studio deny rule is ordered above the general LAN allow)
- [ ] Samba from Studio → monolith works
- [ ] Samba from wife's laptop → monolith works
- [ ] Print job from any Users device → printer succeeds
- [ ] Print job from Guest → printer succeeds
- [ ] If relying on AirPrint auto-discovery: printer *appears* in device's list without manual IP entry — a successful print via manually-added IP does not confirm the mDNS Repeater is working
- [ ] Users device cannot reach Infra on non-allowed ports (try SSH from Users → monolith — should fail)
- [ ] IoT device cannot reach Users or Infra (`ping 192.168.30.10` from NVR debug shell — should fail)
- [ ] Guest device cannot reach anything internal except the printer (`ping 192.168.30.11` from guest device — should fail)

### Monitoring
- [ ] Prometheus targets all green in Grafana
- [ ] SNMP scrapes return data for ER605, SG2218P, both EAP245s
- [ ] node_exporter scrapes succeed for monolith and watchtower

### Services
- [ ] NVR recording continues on both Reolinks
- [ ] Internet works from a device on every VLAN
- [ ] ArgoCD on watchtower reaches GitHub
- [ ] Synapse (`monolith.littlewolfacres.com:30800`) reachable from apex; UFW restriction effective

---

## Cleanup & Commit

- [ ] Disable VLAN 1 on all switch ports (replaced by VLAN 999 Pit as native blackhole)
- [ ] Confirm ports 16, SFP1, SFP2 are administratively shut down
- [ ] Confirm port 10 is Access/VLAN 40, PoE on, disabled until coop cable is pulled
- [ ] Land the IaC PR — all `192.168.0.x` → new subnet replacements
- [ ] Update `docs/homelab-state.md` to reflect new addressing
- [ ] Take a fresh OC200 config backup as the new baseline
- [ ] Decommission TL-SG1210P or label as cold spare for the SG2218P
- [ ] Capture daughter's Chromebook MAC after first Guest SSID connection; add DHCP reservation in OC200

---

## Rollback

Triggered if verification reveals a critical failure that can't be debugged within the window.

1. In OC200, **restore the snapshot** taken at step 1 of cutover
2. ER605 reverts to flat network gateway
3. SG2218P drops back to no-VLAN behavior; all ports become access on default VLAN
4. APs revert to original SSID only
5. Devices re-DHCP back to `192.168.0.x`

**Note:** static-IP devices changed in cutover step 4 must be manually reverted — the OC200 snapshot alone doesn't cover those. Keep a note of which devices were touched and their old IPs before starting.

**Estimated rollback time:** 5–10 minutes from decision to fully reverted.

---

## Post-Cutover Follow-Ups

Not part of the maintenance window — tracked separately.

- **Balcony AP (EAP225-Outdoor):** mount above master suite balcony slider, run outdoor cable through duct chase from basement, inline Ethernet surge protector at basement entry, plug into port 14 — AP self-adopts to `.10.6`
- **Coop/run cable:** pulled when power-to-coop project happens; terminates in weatherproof junction box at coop end, lands on port 10
- **WireGuard on ER605:** subnet allocation, client policy, key rotation
- **Reverse proxy / Cloudflare Tunnel:** for selectively WAN-exposed services
- **Mermaid topology diagram:** `docs/network-topology.md`
- **VLAN-aware Linux bridge on monolith:** netplan/networkd config required before any VM lands on a non-Infra VLAN
