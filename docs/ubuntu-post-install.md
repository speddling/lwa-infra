# Ubuntu Server — Post-Install Hardening Runbook
> For headless Ubuntu Server 24.04 LTS nodes joining the Little Wolf Acres homelab.
> Run through this checklist on first SSH session after OS install.
> Last updated: 2026-05-20

---

## 0. Before You Begin

You need from the install:
- IP address of the new node (temporary DHCP or set statically during install)
- The username and password set during install
- Your SSH public key ready to deploy (`~/.ssh/id_ed25519.pub` on apex)

Once this runbook is complete the node will:
- Accept SSH key auth only (no passwords)
- Have a locked root account
- Have UFW active with a minimal rule set
- Apply security patches automatically
- Be registered in the homelab — DNS, monitoring, Ansible

---

## 1. First Login and System Update

```bash
# Log in with password (last time you'll need it)
ssh <user>@<ip>

# Full system update before anything else
sudo apt update && sudo apt full-upgrade -y
sudo apt autoremove -y
```

Set the hostname if the installer didn't:
```bash
sudo hostnamectl set-hostname <newname>
```

Set timezone:
```bash
sudo timedatectl set-timezone America/New_York
timedatectl status
```

---

## 2. Install Base Tools

> **Note:** The install command below is split into groups for readability.
> Run it as a single block — bash does not allow inline comments (`#`) inside
> a multi-line `apt install` command. Strip the group headers if copying
> line by line, or run each group as a separate `apt install` call.

```bash
sudo apt install -y \
  dmidecode htop ncdu iotop net-tools dnsutils traceroute mtr nmap tcpdump \
  curl wget git rsync unzip jq tree \
  ufw fail2ban unattended-upgrades apt-listchanges \
  lsof sysstat \
  vim tmux bash-completion
```

What each group covers:

| Package(s) | Purpose |
|---|---|
| `dmidecode` | Read hardware info (RAM, BIOS, chassis) from DMI/SMBIOS |
| `htop` | Interactive process viewer |
| `ncdu` | Interactive disk usage analyser |
| `iotop` | I/O usage by process |
| `net-tools` | `ifconfig`, `netstat`, `route` |
| `dnsutils` | `dig`, `nslookup` |
| `traceroute`, `mtr` | Network path tracing |
| `nmap` | Port scanning and host discovery |
| `tcpdump` | Packet capture |
| `curl`, `wget` | HTTP clients |
| `git` | Version control |
| `rsync` | Efficient file sync and backup |
| `unzip`, `jq`, `tree` | Archive handling, JSON processing, directory visualisation |
| `ufw` | Firewall management frontend |
| `fail2ban` | Brute force protection |
| `unattended-upgrades`, `apt-listchanges` | Automatic security patching |
| `lsof` | List open files and sockets |
| `sysstat` | `iostat`, `mpstat`, `sar` — system performance stats |
| `vim` | Terminal editor |
| `tmux` | Terminal multiplexer — persistent sessions over SSH |
| `bash-completion` | Tab completion for common commands |

---

## 3. Create Admin User (if install created root only)

If the install created a root-only system:
```bash
# Create user
sudo adduser <username>

# Add to sudo group
sudo usermod -aG sudo <username>

# Switch to new user and verify sudo works
su - <username>
sudo whoami   # should return: root
```

If the install already created your user, skip to section 4.

---

## 4. Deploy SSH Key

From **apex** — push your public key to the new node:
```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<ip>
```

Then verify key auth works before locking down passwords:
```bash
# Open a second terminal on apex and test key login
ssh -i ~/.ssh/id_ed25519 <user>@<ip>
```

**Do not proceed to section 5 until you have confirmed key login works.**

---

## 5. SSH Hardening

```bash
sudo vim /etc/ssh/sshd_config
```

Set or confirm these values:
```
# Disable password authentication — keys only
PasswordAuthentication no
PubkeyAuthentication yes

# Disable root login entirely
PermitRootLogin no

# Reduce attack surface
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
AllowTcpForwarding no
MaxSessions 4

# Idle timeout — disconnect inactive sessions after 15 min
ClientAliveInterval 300
ClientAliveCountMax 3

# Restrict to specific users (add all accounts that need SSH)
AllowUsers <username>
```

**On port:** changing the default SSH port (22) has marginal security value but
meaningfully reduces log noise from automated scanners. It's a trade-off. If you
change it, update UFW, ER605 firewall rules, and all Ansible inventories.
For LWA nodes this is not standard practice — left as a decision for the operator.

Apply changes:
```bash
sudo systemctl restart ssh

# Verify from apex (keep current session open as fallback)
ssh <user>@<ip>
```

---

## 6. UFW Firewall

```bash
# Set defaults
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH — restrict to apex IP if this is a homelab-only node
sudo ufw allow from 192.168.0.19 to any port 22 proto tcp

# If SSH from studio is also needed
sudo ufw allow from 192.168.0.109 to any port 22 proto tcp

# Enable — you will be asked to confirm
sudo ufw enable

# Verify
sudo ufw status verbose
```

Additional ports are added later once the node's role is defined.
For Monolith-pattern nodes see `docs/homelab-state.md` UFW rules.
All Monolith UFW rules are managed declaratively via the `ufw` Ansible role
in `services/monolith/ansible/roles/ufw/` — do not add rules manually once
Ansible management is active.

---

## 7. Unattended Security Updates

```bash
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

Edit the config to confirm security-only updates and set reboot policy:
```bash
sudo vim /etc/apt/apt.conf.d/50unattended-upgrades
```

Ensure these are set:
```
// Apply security updates automatically
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};

// Remove unused dependencies automatically
Unattended-Upgrade::Remove-Unused-Dependencies "true";

// Reboot if required (e.g. kernel update) — set time to low-traffic window
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:00";

// Email on errors (optional — requires mail configured)
// Unattended-Upgrade::Mail "you@example.com";
// Unattended-Upgrade::MailReport "on-change";
```

Enable the timer:
```bash
sudo systemctl enable --now unattended-upgrades
sudo systemctl status unattended-upgrades
```

---

## 8. fail2ban

Protects SSH against brute force attempts:

```bash
# Create local jail config (never edit jail.conf directly — gets overwritten on upgrade)
sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 3
backend  = systemd

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s
EOF

sudo systemctl enable --now fail2ban
sudo systemctl status fail2ban

# Verify SSH jail is active
sudo fail2ban-client status sshd
```

---

## 9. sysctl Hardening

```bash
sudo tee /etc/sysctl.d/99-hardening.conf > /dev/null <<'EOF'
# ── Network hardening ─────────────────────────────────────────────────────

# Disable IP forwarding (re-enable only if this node routes traffic, e.g. k3s)
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Ignore ICMP broadcast requests (Smurf attack mitigation)
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Ignore bogus ICMP error responses
net.ipv4.icmp_ignore_bogus_error_responses = 1

# SYN flood protection
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# Disable source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# Disable ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0

# Enable reverse path filtering (anti-spoofing)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Log martian packets (packets with impossible source addresses)
net.ipv4.conf.all.log_martians = 1

# ── Memory hardening ──────────────────────────────────────────────────────

# Restrict ptrace to parent processes only
kernel.yama.ptrace_scope = 1

# Restrict dmesg access to root
kernel.dmesg_restrict = 1

# Disable magic SysRq key
kernel.sysrq = 0

# Randomise memory layout (ASLR) — 2 = full randomisation
kernel.randomize_va_space = 2
EOF

# Apply immediately
sudo sysctl -p /etc/sysctl.d/99-hardening.conf
```

> **k3s note:** if this node will run k3s, `net.ipv4.ip_forward` must be `1`.
> k3s sets this automatically, but adding it here will conflict. Either omit
> the ip_forward lines or set them to `1` for k3s nodes.

---

## 10. Secure Shared Memory

```bash
# Add to /etc/fstab to mount /run/shm with restrictive options
echo 'tmpfs /run/shm tmpfs defaults,noexec,nosuid,nodev 0 0' \
  | sudo tee -a /etc/fstab

sudo mount -o remount /run/shm 2>/dev/null || true
```

---

## 11. Disable Unused Services

Review what's running and disable anything not needed:
```bash
# See all enabled services
systemctl list-unit-files --state=enabled --type=service

# Common ones to disable on a headless server if present
sudo systemctl disable --now avahi-daemon   # mDNS — not needed if using proper DNS
sudo systemctl disable --now cups           # Printing
sudo systemctl disable --now bluetooth      # If no BT hardware
sudo systemctl disable --now whoopsie       # Ubuntu crash reporting
sudo systemctl disable --now apport         # Ubuntu crash reporting
```

---

## 12. Verify Hardening

```bash
# Confirm SSH rejects password auth
ssh -o PasswordAuthentication=yes <user>@<ip>
# Expected: Permission denied (publickey)

# Confirm root login rejected
ssh root@<ip>
# Expected: Permission denied

# UFW status
sudo ufw status numbered

# fail2ban status
sudo fail2ban-client status

# sysctl values applied
sudo sysctl net.ipv4.tcp_syncookies
sudo sysctl kernel.randomize_va_space

# Check for any listening services that shouldn't be
sudo ss -tlnp
```

---

## 13. LWA Homelab Registration

Once the node is hardened, register it in the homelab:

### ER605 — DHCP MAC Reservation
- Omada Controller → Settings → Wired Networks → LAN → DHCP → Add Static Assignment
- Enter MAC address and desired IP
- Reboot node or release/renew DHCP to pick up reserved IP

### AdGuard Home — DNS Rewrite
Add to `services/watchtower/ansible/roles/adguard/templates/AdGuardHome.yaml.j2`:
```yaml
- domain: <hostname>.littlewolfacres.com
  answer: <ip>
```
Then PR → merge → run **Deploy Watchtower Config**.

### Cloudflare DNS
Add an A record in Cloudflare for `<hostname>.littlewolfacres.com → <ip>`.
Set to DNS only (gray cloud — private IP, can't be proxied).

### Ansible Inventory
Add the node to the relevant Ansible inventory file.
Update `ansible/vars/main.yml` with the new IP and FQDN variables.

### node_exporter
Install node_exporter on the new node and add a scrape job to
`services/watchtower/ansible/roles/prometheus/templates/prometheus.yml.j2`.
PR → merge → run **Deploy Watchtower Config**.

### homelab-state.md
Add a hardware table and services section for the new node.
Document UFW rules, IaC layer, and any running services.

---

## 14. Reboot and Final Check

```bash
sudo reboot
```

After reboot:
```bash
# Reconnect via key auth
ssh <user>@<ip>

# Confirm all hardening survived reboot
sudo ufw status
sudo fail2ban-client status
sudo sysctl net.ipv4.tcp_syncookies
systemctl status unattended-upgrades
systemctl status fail2ban
```

If everything looks good, the node is ready for its role-specific configuration.

---

## Notes and Known Issues

**k3s nodes:** `net.ipv4.ip_forward = 1` is required. k3s sets this at startup,
but if the sysctl hardening file sets it to `0` it may cause issues depending on
service startup order. Set it to `1` in `99-hardening.conf` for k3s nodes, or
omit that line entirely and let k3s manage it.

**Watchtower/DNS nodes:** `net.ipv4.ip_forward` should remain `0` — Watchtower
routes nothing, it only listens.

**fail2ban + UFW:** fail2ban uses its own `iptables`/`nftables` chains alongside
UFW. They coexist without conflict on Ubuntu 24.04.

**Ubuntu 24.04 and nftables:** UFW on 24.04 uses nftables as the backend.
`sudo nft list ruleset` shows the full firewall state if you need to debug
at a lower level than `ufw status`.
