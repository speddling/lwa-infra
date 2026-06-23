# LWA Infra -- Network Migration Runbook
> Last updated: 2026-06-16

Operational sequence for moving from the flat `192.168.0.0/24` network to the 5-VLAN segmented design defined in the [Network Rebuild Plan](network-rebuild-plan.md).

**Design principle:** nothing breaks until the very last step, and that step has a one-click rollback.

**Maintenance window:** ~60 minutes total. Family gets a 30-minute warning before takedown.

---

## Phase 1 — Pre-cutover (week before switch arrives)

Work that can be done while the existing flat network keeps running.

### OC200 staging

- [ ] Create VLANs 10, 20, 30, 40, 50, and 999 (blackhole) in OC200
- [ ] Define DHCP scopes per VLAN, but **do not activate** the networks yet
- [ ] Pre-create static reservations for known IPs:
  - `.30.10` monolith, `.30.11` watchtower, `.30.12` Obelisk
  - `.40.10` Big Brother, `.40.11–.12` Reolinks, `.40.20` printer
  - `.10.1–.6` infrastructure including the future `.10.6` Balcony AP (controller will mostly auto-assign these via Omada discovery)
  - `.20.2` apex, `.20.3` Studio — capture both MAC addresses before cutover, and disable WiFi MAC address randomization for the `LittleWolfAcres` SSID on both devices first (this is the one thing that can quietly break a MAC-bound reservation)
- [ ] Pre-stage the EAP245 rename in OC200: Foyer → **Downstairs Hall**, Yarn Studio → **Upstairs Hall**
- [ ] Plan the physical relocation of the Upstairs Hall EAP245 (formerly Yarn Studio) to its new mounting location upstairs near daughter's bedroom — can be done before or after cutover, independent of the VLAN work
- [ ] Pre-create new SSIDs (`LittleWolfAcres-IoT`, `LittleWolfAcres-Guest`) mapped to their VLANs, marked **disabled**
- [ ] Plan to retain the existing `LittleWolfAcres` SSID name on the new LAN VLAN — family devices reconnect transparently
- [ ] Check Controller and ER605 firmware versions, then configure the mDNS Repeater (Settings → Services → mDNS) for LAN → IoT and Guest → IoT, scoped to the printer's Bonjour service — see [Network Rebuild Plan → mDNS / Bonjour cross-VLAN discovery](network-rebuild-plan.md#mdns--bonjour-cross-vlan-discovery-printer) for why the `UDP 5353` firewall rule alone doesn't make auto-discovery work

### AdGuard prep

- [ ] Export current local DNS rewrites
- [ ] Prepare an updated rewrite list mapping every `*.littlewolfacres.com` entry to its new IP
- [ ] Confirm AdGuard listener is bound to `0.0.0.0` (not a specific interface) so it answers on the new VLAN gateway

### IaC prep (parallel PR branch)

- [ ] `grep -rn '192.168.0.' .` across the repo — list every occurrence, group by file
- [ ] Stage changes in Ansible vars, K8s manifests, monitoring configs, `homelab-state.md`, `network.md`
- [ ] Hold the PR until post-cutover so it can land atomically with verified-working IPs

### Backups

- [ ] OC200 config export
- [ ] ER605 config export
- [ ] AdGuard config snapshot
- [ ] Current Ansible vault encrypted to a tagged commit (rollback reference)

### Logistics

- [ ] Confirm 30-minute warning channel for the family (text? in-person? sign on the closet door?)
- [ ] Pick the maintenance window — late evening or weekend morning, low usage
- [ ] Have a monitor and keyboard at watchtower for wired recovery access during cutover — apex is WiFi-only, so if WiFi reconnection has any hiccup, watchtower is the wired admin path

---

## Phase 2 — Hardware swap (low risk, no config change yet)

Estimated time: 15 minutes. Network is briefly down during the swap.

1. Issue 30-minute family warning
2. Power down TL-SG1210P; unplug all cables
3. Mount/place SG2218P; power on; let it boot
4. Plug ER605 uplink into any SG2218P port (still flat network)
5. Wait for OC200 to discover the new switch on the flat network
6. Adopt the SG2218P into OC200
7. Update SG2218P firmware via OC200 if newer is available
8. Reconnect cables one at a time **into the planned port positions** from the [Network Rebuild Plan](network-rebuild-plan.md#switch-port-plan). Verify each device gets DHCP and works on the still-flat network as you go.

**Checkpoint:** all devices are on the new switch but still on flat `192.168.0/24`. AdGuard still works. Internet works. Samba works. If anything is broken at this stage, the problem is hardware, not config — pull the SG2218P and revert to the TL-SG1210P.

---

## Phase 3 — VLAN activation (the actual cutover)

Estimated time: 15–20 minutes. Devices will reconnect with new IPs.

1. **Snapshot OC200 config now** — this is the rollback point
2. In OC200, enable the new networks (10/20/30/40/50/999). The ER605 begins listening on the new VLAN gateways simultaneously
3. Push the SG2218P port plan: trunks, native VLANs, tagged VLANs as designed. The moment you push, ports change behavior
4. Update static-IP devices that don't get their config from Omada:
   - **watchtower** — change static config from `.0.21` to `.30.11` (or convert to DHCP reservation, then reboot)
   - **monolith** — `.0.20` to `.30.10`
   - **NVR** — `.0.4` to `.40.10` (via NVR's web UI)
   - **Reolinks** — `.40.11` and `.40.12` (via Reolink app)
5. Update AdGuard's local DNS rewrites with the new IPs (paste the prepared list from Phase 1)
6. Enable the new SSIDs in OC200; keep `LittleWolfAcres` broadcasting on the new LAN VLAN

---

## Phase 4 — Verification

Per-VLAN smoke test. Don't skip any of these.

### DHCP

- [ ] LAN device gets `192.168.20.x`, gateway `.20.1`, DNS `.30.11`
- [ ] IoT device gets `192.168.40.x`, gateway `.40.1`, DNS `.30.11`
- [ ] Guest device gets `192.168.50.x`, gateway `.50.1`, DNS `1.1.1.1` and `9.9.9.9`
- [ ] Homelab device gets `192.168.30.x`, gateway `.30.1`, DNS `.30.11`
- [ ] Management interfaces visible at `.10.x` from a Homelab device

### DNS

- [ ] `dig monolith.littlewolfacres.com` from a LAN device returns `192.168.30.10`
- [ ] AdGuard query log shows queries from the LAN VLAN's subnet
- [ ] AdGuard query log shows **no** queries from the Guest VLAN's subnet (proves split-horizon DNS is working)

### Inter-VLAN rules

- [ ] RDP from apex → Obelisk works
- [ ] RDP from Studio → Obelisk is **blocked** (deliberate exception — confirms the deny rule is ordered correctly ahead of the general LAN allow)
- [ ] Samba from Studio → monolith works (needed for the upcoming music-library metadata work)
- [ ] Samba from wife's laptop → monolith works
- [ ] Print job from any LAN device → printer succeeds
- [ ] Print job from the Guest VLAN → printer succeeds
- [ ] If relying on auto-discovery (AirPrint, etc.) rather than a manually-added printer IP: confirm the printer actually *appears* in the device's printer list without manual IP entry — a successful print via manual IP doesn't prove the mDNS Repeater rule is working
- [ ] LAN device cannot reach Homelab on any port other than the allowed ones (try SSH to monolith from a LAN device — should fail)
- [ ] IoT device cannot reach LAN or Homelab (try `ping .30.10` from the NVR's debug shell — should fail)
- [ ] Guest device cannot reach anything internal except the printer (try `ping .30.11` from a guest device — should fail)

### Monitoring

- [ ] Prometheus targets all green in Grafana
- [ ] SNMP scrapes return data for ER605, SG2218P, both EAP245s
- [ ] node_exporter scrapes succeed for monolith and watchtower

### Services

- [ ] NVR recording continues on both switch-connected Reolinks
- [ ] Internet works from a device on every VLAN
- [ ] ArgoCD on watchtower reaches GitHub
- [ ] Synapse (`monolith.littlewolfacres.com:30800`) reachable from apex; UFW restriction still effective

---

## Phase 5 — Cleanup & commit

- [ ] Disable VLAN 1 on all switch ports (replaced by VLAN 999 as the native blackhole)
- [ ] Confirm unused ports (port 16, both SFPs) are administratively shut down
- [ ] Confirm port 10 is configured as Access/VLAN 40 (IoT) with PoE on, but disabled until the chicken-run/coop cable is pulled
- [ ] Land the IaC PR with all `192.168.0.x` → new subnet replacements
- [ ] Update `docs/network.md` static IP table with the new VLAN layout
- [ ] Update `docs/homelab-state.md` to reflect the new addressing
- [ ] Take a fresh OC200 config backup as the new baseline
- [ ] Decommission the TL-SG1210P or label it as cold spare for the SG2218P
- [ ] Capture daughter's Chromebook MAC after first connection to the Guest SSID; add as a DHCP reservation in OC200

---

## Rollback

Triggered if Phase 3 verification reveals a critical failure that can't be debugged inside the maintenance window.

1. In OC200, restore the snapshot taken at the start of Phase 3
2. ER605 reverts to flat network gateway
3. SG2218P drops back to no-VLAN behavior; all ports become access ports on default VLAN
4. APs revert to broadcasting only the original SSID
5. Devices re-DHCP back into `192.168.0.x`

Static-IP devices that were changed in Phase 3 step 4 need to be reverted to their old addresses manually (this is why the OC200 snapshot alone isn't a complete rollback — keep a note of which devices got touched).

**Estimated rollback time:** 5–10 minutes from decision to fully reverted.

---

## Post-cutover follow-ups

Tracked separately from this runbook:

- **EAP225-Outdoor — Balcony install:** mount above the master suite balcony slider, run outdoor cable through the duct chase from the basement, add inline Ethernet surge protector at the basement entry, plug into switch port 14, AP self-adopts to `.10.6`
- **Future front-east AP** (orchard coverage): same install pattern through the chimney facade chase, second EAP225-Outdoor when the orchard is in
- **Chicken-run/coop cable:** pulled when the power-to-coop project happens, terminated in a weatherproof junction box at the coop end, lands on switch port 10
- WireGuard configuration on the ER605
- Reverse proxy or Cloudflare Tunnel for any externally-exposed services
- Mermaid topology diagram (`docs/network-topology.md`)
- VLAN-aware bridge enable on monolith (deferred until a VM needs a non-Homelab VLAN)
