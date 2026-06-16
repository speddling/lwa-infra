# Obelisk — Windows 11 VM Runbook

**Host:** monolith (`192.168.0.20`)
**Guest:** Windows 11 Pro (Build 26200)
**RDP:** `192.168.0.20:33389`
**VNC:** `192.168.0.20:5900` (install/recovery only)
**Accounts:** `speddling` (admin), `obelisk` (admin)

---

## Current State

Manually installed and configured. QEMU/KVM process on monolith, not managed by KubeVirt. Systemd service pending.

---

## How It's Running

Plain QEMU/KVM process on monolith. No Kubernetes involvement in VM lifecycle.

```bash
sudo qemu-system-x86_64 \
  -enable-kvm \
  -m 8192 \
  -smp 4 \
  -machine q35 \
  -cpu host \
  -bios /usr/share/ovmf/OVMF.fd \
  -drive file=/mnt/ssd-b/obelisk-disk/disk.img,if=ide,index=0,format=qcow2 \
  -drive file=/mnt/ssd-b/obelisk-win11-iso/disk.img,media=cdrom,index=1,readonly=on \
  -drive file=/mnt/ssd-b/obelisk-autounattend/disk.img,media=cdrom,index=2,readonly=on \
  -netdev user,id=net0,hostfwd=tcp::33389-:3389 \
  -device e1000e,netdev=net0 \
  -vnc 0.0.0.0:0,password=on \
  -monitor unix:/tmp/obelisk-monitor.sock,server,nowait \
  -daemonize \
  -pidfile /tmp/obelisk.pid
```

**TODO:** wrap in systemd service for clean lifecycle management.

---

## Storage

All on `/mnt/ssd-b` (234G SSD, ~214G free at time of setup):

| Path | Size | Purpose |
|---|---|---|
| `obelisk-disk/disk.img` | 100G qcow2 | Windows OS disk |
| `obelisk-win11-iso/disk.img` | 7.9G | Win11 25H2 ISO — permanent artifact |
| `obelisk-autounattend/` | ~50KB | autounattend ISO — vault passwords injected |
| (reserved) | ~100G | Second Windows instance — not yet provisioned |

**Overflow:** hdd-c available as a second virtual disk if bulk storage needed inside the VM. Attach as additional `-drive` argument.

---

## Install History

### What Worked
- QEMU/KVM directly on monolith — no KubeVirt
- OVMF UEFI (`/usr/share/ovmf/OVMF.fd`)
- SATA disk (`if=ide`), e1000e network
- Manual install from ISO — UEFI shell required (`fs0:\EFI\BOOT\BOOTX64.EFI`)
- TPM/SecureBoot bypass via regedit during install (`HKLM\SYSTEM\Setup\LabConfig`)

### TPM/SecureBoot Bypass Registry Keys
```
HKEY_LOCAL_MACHINE\SYSTEM\Setup\LabConfig
  BypassTPMCheck     REG_DWORD  1
  BypassSecureBootCheck  REG_DWORD  1
```

### What Failed (KubeVirt — do not repeat)
- CDI HTTP import of Win11 ISO — Microsoft URLs are session-authenticated, 403 every time
- virtio disk bus — OVMF cannot enumerate virtio-blk at boot, "no bootable device"
- EFI NVRAM not persistent by default — boot entries lost on VM restart
- autounattend not picked up when booting via UEFI shell — bypasses CD autodetection

---

## Post-Install Configuration

### Win11Debloat
Ran [Win11Debloat](https://github.com/Raphire/Win11Debloat) as `speddling` on 2026-05-29.

**Selected options / what ran:**
- 119 apps removed (full list in transcript)
- Dark mode enabled
- Telemetry, diagnostic data, activity history, app-launch tracking, targeted ads disabled
- Copilot disabled and removed
- Windows Recall disabled
- Click to Do disabled
- Bing web search and Copilot in Windows Search disabled
- Widgets disabled and removed
- Tips, tricks, suggestions and ads throughout Windows disabled
- Game Bar and Xbox screen recording disabled
- Animations and visual effects disabled
- Transparency effects disabled
- Taskbar buttons aligned left
- Search icon hidden from taskbar
- Start menu recommended section disabled
- All pinned apps removed from start menu
- OneDrive and Gallery hidden from File Explorer nav pane
- Hidden files, folders, drives unhidden
- File extensions for known types enabled
- End Task option enabled in taskbar right-click
- Phone Link disabled
- AI service prevented from starting automatically
- Edge ads, suggestions, MSN news feed disabled
- Windows update fast-ring disabled
- Auto-restart after updates while signed in disabled
- Common folders added back to This PC

**Transcript:** `docs/obelisk-win11debloat-transcript-20260529.txt` (TODO: commit)

### RDP
Enabled manually via PowerShell before Win11Debloat:
```powershell
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f
netsh advfirewall firewall add rule name="RDP" protocol=TCP dir=in localport=3389 action=allow
```

---

## TODO

> **Client contract compliance items** (MFA, connection encryption, access logging, breach notification, certificate of destruction on termination) tracked in `docs/homelab-todo.md` → "Client Contract — Security & Compliance". The "inbound RDP from internet" item below should wait until those are done.

- [ ] Systemd service for QEMU process (start/stop/restart lifecycle)
- [ ] windows_exporter install (port 9182 — Prometheus scrape target)
- [ ] Firewall rule for windows_exporter (9182)
- [ ] Prometheus scrape config on watchtower for obelisk
- [ ] AdGuard rewrite: `obelisk.littlewolfacres.com` → `192.168.0.20:33389`
- [ ] UFW rule on monolith: tighten 5900 (VNC) to LAN only, close after install confirmed stable
- [ ] Second Windows instance on remaining ~100G of ssd-b
- [ ] Fix autounattend boot detection for future reinstalls (UEFI shell bypass issue)
- [ ] Investigate TPM emulation (`swtpm`) for future installs with SecureBoot on
- [ ] Document Swiss client RDP access procedure
- [ ] inbound RDP from internet — after VLAN work, open cleanly through Traefik or dedicated firewall rule

---

## Connect

```bash
# RDP (daily use)
open rdp://192.168.0.20:33389

# VNC (recovery / install observation only)
open vnc://192.168.0.20:5900

# Stop VM
sudo kill $(sudo cat /tmp/obelisk.pid)

# Check running
ps aux | grep qemu
```
