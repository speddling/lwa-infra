
# LWA VLAN Cutover — Take 3 Runbook

## What Failed in Take 2 (and why)

1. **Port 11 (OC200) and port 1 (ER605 trunk) flipped simultaneously.** OC200 lost its
   flat-network DHCP lease before the ER605 had initialized VLAN 10 interfaces and before
   the Mgmt DHCP scope was serving. OC200 went unreachable and took switch management with it.

2. **No staged port sequencing.** All 16 ports applied in one shot — no window to verify
   DHCP was serving between the gateway flip and everything else.

3. **Apex was WiFi-only upstairs.** When the EAP ports (12/13) flipped, WiFi dropped and
   apex lost management access entirely.

4. **UFW was not pre-flighted.** After PR #183 merged (ip_* vars to VLAN addresses), the
   firewall playbooks would lock SSH to VLAN IPs that the servers didn't have yet.

---

## What's Different in Take 3

- **Switch ports now apply in two phases** — port 1 (ER605 trunk) alone first, then
  everything else. Port 11 (OC200) is permanently excluded from automation.
- **Preflight playbook** adds VLAN subnet UFW rules before any switch ports flip,
  so both servers remain reachable throughout the transition.
- **OC200 port 11 is manual, always** — flip it in the OC200 UI after everything
  else is stable and verified.

---

## Pre-Cutover Checklist (do this before the window)

- [ ] Console access staged: KVM or keyboard/monitor on monolith AND watchtower
- [ ] Apex has wired ethernet into an "All" port (port 15 or direct into ER605)
- [ ] OC200 reachable and vault updated: vault_omada_api_base matches current OC200 IP
- [ ] Dry-run all three Omada playbooks clean (reservations, vlans, switch_ports)
- [ ] inventory.cutover.ini updated with current flat-network IPs:
      ssh speddling@<monolith-ip> ip addr show enp8s0 | grep 'inet '
      ssh speddling@<watchtower-ip> ip addr show enp3s0 | grep 'inet '

---

## Cutover Sequence

All commands run from apex in ~/lwa-homelab.

### Step 0 — Verify current state
All commands run from apex in ~/lwa-homelab.

### Step 0 — Verify current state

    cd services/omada/ansible
    ansible-playbook -i inventory.ini playbooks/reservations.yml
    ansible-playbook -i inventory.ini playbooks/vlans.yml
    ansible-playbook -i inventory.ini playbooks/switch_ports.yml

All three dry-runs must be clean before proceeding.

### Step 1 — Apply DHCP reservations

    ansible-playbook -i inventory.ini playbooks/reservations.yml -e omada_apply=true

### Step 2 — Apply VLAN/DHCP scope config

    ansible-playbook -i inventory.ini playbooks/vlans.yml -e omada_apply=true

### Step 3 — Pre-flight UFW

    ansible-playbook -i inventory.cutover.ini playbooks/cutover_preflight.yml \
      --vault-password-file ~/lwa-homelab/.vault_pass

Adds VLAN subnet rules alongside flat-network rules on both servers.

### Step 4 — Phase 1: ER605 trunk port only

    ansible-playbook -i inventory.ini playbooks/switch_ports.yml \
      -e omada_apply=true -e cutover_phase=1

Wait 60 seconds then verify ER605 VLAN routing:

    ping -c 2 192.168.10.1
    ping -c 2 192.168.20.1
    ping -c 2 192.168.30.1
    ping -c 2 192.168.40.1

All four must respond before Phase 2.

### Step 5 — Phase 2: Everything else (except OC200)

    ansible-playbook -i inventory.ini playbooks/switch_ports.yml \
      -e omada_apply=true -e cutover_phase=2

Ports 2-10, 12-15 flip. WiFi drops briefly. Verify within 60 seconds:

    ping 192.168.30.10
    ping 192.168.30.11
    ssh speddling@192.168.30.11
    ssh speddling@192.168.30.10

### Step 6 — Manual: OC200 port 11

In OC200 UI: switch -> Ports -> Port 11 -> set profile to Mgmt.
OC200 comes up at 192.168.10.2. Update vault:

    ansible-vault edit ansible/vars/vault.yml
    # Change vault_omada_api_base to https://192.168.10.2:443

### Step 7 — Post-cutover cleanup

    cd ~/lwa-homelab/services/monolith/ansible
    ansible-playbook -i inventory.ini playbooks/firewall.yml \
      --vault-password-file ~/lwa-homelab/.vault_pass

    cd ~/lwa-homelab/services/watchtower/ansible
    ansible-playbook -i inventory.ini playbooks/firewall.yml \
      --vault-password-file ~/lwa-homelab/.vault_pass

    ansible-playbook -i inventory.ini playbooks/dns.yml \
      --vault-password-file ~/lwa-homelab/.vault_pass

### Step 8 — Verify

    dig grafana.littlewolfacres.com @192.168.30.11
    dig monolith.littlewolfacres.com @192.168.30.11
    curl -k https://grafana.littlewolfacres.com
    curl -k https://argocd.littlewolfacres.com

---

## Rollback

1. In OC200 UI set all switch ports back to All profile manually
2. Servers pick up flat-network DHCP leases within 60 seconds
3. SSH back in using flat-network IPs
4. UFW preflight rules are additive — flat-network rules still work

---

## IP Reference

| Device      | Post-cutover  | VLAN    |
|-------------|---------------|---------|
| ER605       | 192.168.0.1   | Default |
| OC200       | 192.168.10.2  | Mgmt    |
| apex        | 192.168.20.2  | Users   |
| studio      | 192.168.20.3  | Users   |
| monolith    | 192.168.30.10 | Infra   |
| watchtower  | 192.168.30.11 | Infra   |
| Big Brother | 192.168.40.10 | IoT     |
