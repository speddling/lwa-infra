# Network Documentation

## Static IP Reservations

All static assignments are DHCP MAC-bound in the ER605. Do not set static IPs at the OS level.

| IP | Hostname | Role |
|---|---|---|
| 192.168.0.4 | Big Brother | Reolink NVR / Camera Controller |
| 192.168.0.7 | OC200 | Omada Network Controller |
| 192.168.0.19 | Apex | MacBook Pro — Primary Workstation |
| 192.168.0.20 | Monolith | k3s Node — Primary Server |
| 192.168.0.21 | Watchtower | Ansible / DNS / Network Services (pending) |
| 192.168.0.109 | Studio | Ubuntu Studio — DAW / KDE Workstation |

All other devices use dynamic DHCP leases.

---

## Notes

- DNS resolution via hostname is pending Watchtower build — use IPs until then
- When Watchtower DNS is live, all fstab and Ansible inventory files referencing IPs should be updated to hostnames
- ER605 manages routing and firewall at the network boundary

---

## SSH Aliases (Apex ~/.zshrc)

```bash
# Lab hosts
alias monolith='ssh speddling@192.168.0.20'
alias watchtower='ssh speddling@192.168.0.21'
alias studio='ssh speddling@192.168.0.109'
```

---

*Last updated: 2026-04-24*

