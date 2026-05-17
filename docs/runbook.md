# Little Wolf Acres — Homelab Runbook
> Operational reference for day-to-day tasks, troubleshooting, and maintenance.
> Last updated: 2026-05-14

---

## Navidrome

### Music Library — Mounting on Studio

Navidrome reads from `/mnt/hdd-c/music-library` on Monolith via a k3s hostPath volume. To add new music or edit metadata from Studio, mount the `music-library` Samba share. **This is a one-time manual setup on Studio** — there is no Ansible automation for it.

```bash
# 1. Install CIFS support
sudo apt install cifs-utils

# 2. Create the credentials file (root-only, never world-readable)
sudo tee /etc/samba/studio-music-creds > /dev/null <<'EOF'
username=james
password=<vault_james_password>
EOF
sudo chmod 600 /etc/samba/studio-music-creds

# 3. Create the mount point
sudo mkdir /music-library

# 4. Add to /etc/fstab
echo '//192.168.0.20/music-library  /music-library  cifs  credentials=/etc/samba/studio-music-creds,uid=1000,gid=1000,file_mode=0664,dir_mode=0775,vers=3.0,_netdev,x-systemd.automount  0  0' | sudo tee -a /etc/fstab

# 5. Mount now without rebooting
sudo systemctl daemon-reload
sudo mount /music-library
```

> **Password:** retrieve from `ansible/vars/vault.yml` on apex:
> `ansible-vault view ~/homelab/ansible/vars/vault.yml --vault-password-file=~/homelab/.vault_pass`

After mounting, `/music-library` behaves like a local directory. New files and edited tags written here are picked up by Navidrome on its next scheduled scan (default: every hour).

### Forcing a Navidrome Rescan

```bash
# Trigger a full library rescan immediately
curl -u admin:<password> -X POST https://navidrome.littlewolfacres.com/rest/startScan?apiKey=<key>

# Or via the web UI
# Navidrome → ⚙ Settings → Library → Start Full Scan
```

### Health Check

```bash
# Check pod status
sudo k3s kubectl get pods -n navidrome

# Tail logs
sudo k3s kubectl logs -n navidrome deployment/navidrome --tail=50 -f

# Verify music hostPath is mounted inside the pod
sudo k3s kubectl exec -n navidrome deployment/navidrome -- ls /music | head -20
```

### Restarting Navidrome

```bash
sudo k3s kubectl rollout restart deployment/navidrome -n navidrome
sudo k3s kubectl rollout status deployment/navidrome -n navidrome
```

---

## Service Health Checks

### Watchtower (run on watchtower)

```bash
# All core services at once
systemctl status prometheus alertmanager grafana-server netdata AdGuardHome unbound

# Individual services
systemctl status prometheus
systemctl status alertmanager
systemctl status grafana-server
systemctl status AdGuardHome
systemctl status unbound
systemctl status node_exporter
systemctl status blackbox_exporter
systemctl status snmp_exporter
systemctl status adguard_exporter
systemctl status netdata
```

### Monolith (run on monolith)

```bash
# k3s node and all pods
sudo k3s kubectl get nodes
sudo k3s kubectl get pods -A

# Specific namespace
sudo k3s kubectl get pods -n navidrome
sudo k3s kubectl get pods -n minecraft

# Pod logs
sudo k3s kubectl logs -n navidrome deployment/navidrome --tail=50
sudo k3s kubectl logs -n minecraft deployment/minecraft --tail=50
```

---

## Live Log Tailing

### Watchtower

```bash
journalctl -fu prometheus
journalctl -fu alertmanager
journalctl -fu grafana-server
journalctl -fu AdGuardHome
journalctl -fu unbound
journalctl -fu adguard_exporter
journalctl -fu snmp_exporter
```

---

## DNS

### Testing

```bash
# Test Unbound directly (recursive resolver)
dig @127.0.0.1 -p 5335 google.com

# Test AdGuard Home (DNS frontend)
dig @127.0.0.1 google.com

# Test local rewrites
dig monolith.littlewolfacres.com
dig grafana.littlewolfacres.com

# Test short hostname resolution (search domain)
dig monolith
dig grafana

# Test from apex against watchtower
dig @192.168.0.21 monolith.littlewolfacres.com
```

### Adding a Local Rewrite

1. Open AdGuard Home → `http://watchtower:3000`
2. Filters → DNS rewrites → Add rewrite
3. Domain: `hostname.littlewolfacres.com` → IP address
4. Update `homelab-state.md` DNS rewrites table
5. Commit via `docs/*` branch

### Omada DHCP Settings

Search domain and other DHCP options are at:
**Omada Cloud Portal → Settings → Wired Networks → LAN → Edit → DHCP Server**

- Domain Name: `littlewolfacres.com` (pushes search domain to all DHCP clients)
- DNS Server: `192.168.0.21` (Watchtower)

---

## SNMP Testing (run on watchtower)

```bash
# Test ER605
snmpwalk -v2c -c littlewolfacres 192.168.0.1 1.3.6.1.2.1.1.1.0

# Test EAP245 Yarn Studio
snmpwalk -v2c -c littlewolfacres 192.168.0.5 1.3.6.1.2.1.1.1.0

# Test EAP245 Foyer
snmpwalk -v2c -c littlewolfacres 192.168.0.2 1.3.6.1.2.1.1.1.0

# Test SNMP exporter directly
curl "http://localhost:9116/snmp?module=if_mib&auth=littlewolfacres_v2&target=192.168.0.1"
```

---

## Prometheus

```bash
# Validate config
promtool check config /etc/prometheus/prometheus.yml

# Validate alert rules
promtool check rules /etc/prometheus/alert_rules.yml

# Check active alerts
curl -s http://192.168.0.21:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"'

# Check all targets and health
curl -s http://192.168.0.21:9090/api/v1/targets | python3 -m json.tool | grep -E "job|health"

# Check storage size
du -sh /var/lib/prometheus

# Restart after config change
sudo systemctl restart prometheus
```

---

## Alertmanager

```bash
# Check health
curl -s http://192.168.0.21:9093/-/healthy

# Check active alerts
curl -s http://192.168.0.21:9093/api/v2/alerts

# Restart
sudo systemctl restart alertmanager
```

---

## Ansible (run from apex)

```bash
cd ~/homelab/services/watchtower/ansible

# Run individual playbooks
ansible-playbook -i inventory.ini playbooks/dns.yml --vault-password-file=~/homelab/.vault_pass
ansible-playbook -i inventory.ini playbooks/monitoring.yml --vault-password-file=~/homelab/.vault_pass
ansible-playbook -i inventory.ini playbooks/exporters.yml --vault-password-file=~/homelab/.vault_pass

# Dry run
ansible-playbook -i inventory.ini playbooks/monitoring.yml --check --vault-password-file=~/homelab/.vault_pass

# Vault operations
ansible-vault edit group_vars/all/vault.yml --vault-password-file=~/homelab/.vault_pass
ansible-vault view group_vars/all/vault.yml --vault-password-file=~/homelab/.vault_pass
```

### Monolith Ansible

```bash
cd ~/homelab/services/monolith/ansible
ansible-playbook -i inventory.ini playbooks/monitoring.yml
```

---

## Terraform (run from apex)

```bash
# Watchtower
cd ~/homelab/terraform/watchtower
terraform init && terraform plan
terraform apply

# Monolith
cd ~/homelab/terraform/monolith
terraform init && terraform plan
terraform apply
```

---

## UFW

```bash
# Check rules
sudo ufw status numbered

# Reload after changes
sudo ufw reload
```

---

## k3s Storage

```bash
# Check PVCs
sudo k3s kubectl get pvc -A

# Check storage classes
sudo k3s kubectl get storageclass

# Check disk usage on mounts
df -h | grep mnt
```

---

## Grafana API

```bash
# List provisioned alert rules
curl -s -u 'admin:PASSWORD' 'http://192.168.0.21:3001/api/v1/provisioning/alert-rules' | python3 -m json.tool

# Import dashboard by ID — do via UI: Dashboards → Import → Enter ID
```

---

## NUT — When UPS Arrives

1. Connect CyberPower CP1500PFCLCD via USB to Watchtower
2. Run monitoring playbook — NUT role will activate automatically
3. Verify: `systemctl status nut-server nut-monitor`
4. Check UPS status: `upsc cyberpower@localhost`

---

## Git Workflow

```bash
# Start new work
cd ~/homelab
git checkout -b feature/description

# Commit and push
git add .
git commit -m "feat: description"
git push -u origin feature/description

# Open PR
gh pr create --title "feat: description" --body "What and why"

# Merge via GitHub UI after validate passes
# Deploy triggers automatically on merge to master

# Manual workflow trigger
gh workflow run deploy-watchtower.yml
```

### Branch conventions

| Prefix | Use |
|---|---|
| `feature/*` | New capabilities |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation only — no deploy triggered |
| `chore/*` | Maintenance, dependency updates |
