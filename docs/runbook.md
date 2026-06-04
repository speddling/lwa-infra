# Little Wolf Acres — Homelab Runbook
> Operational reference for day-to-day tasks, troubleshooting, and maintenance.
> Last updated: 2026-05-23

---

## ArgoCD

### Access

| Method | URL | When to use |
|---|---|---|
| Primary | https://argocd.littlewolfacres.com | Normal operations |
| Fallback | http://monolith.littlewolfacres.com:30880 | DNS unstable or cert issue |

### Rotating Repository Credentials

ArgoCD pulls manifests from `speddling/lwa-homelab` using a GitHub fine-grained PAT
stored in `ansible/vars/vault.yml` as `vault_argocd_github_token`.

**Normal rotation procedure:**

```bash
# 1. Generate a new fine-grained PAT at:
#    GitHub → Settings → Developer Settings → Fine-grained tokens → Generate new token
#    Repository: speddling/lwa-homelab only
#    Permission: Contents → Read
#    Expiration: No expiration (preferred)

# 2. Update the vault on apex
ansible-vault edit ansible/vars/vault.yml \
  --vault-password-file ~/lwa-homelab/.vault_pass
# Update vault_argocd_github_token with the new PAT value

# 3. Commit the encrypted vault change
git checkout -b fix/rotate-argocd-pat
git add ansible/vars/vault.yml
git commit -m "fix: rotate ArgoCD GitHub PAT"
git push -u origin fix/rotate-argocd-pat
gh pr create --title "fix: rotate ArgoCD GitHub PAT" --body "Routine PAT rotation."

# 4. After merge — run the rotation workflow
gh workflow run rotate-argocd-credentials.yml
```

**Emergency rotation (PAT compromised or expired, can't wait for PR merge):**

```bash
# Run the playbook directly from apex against the current vault
cd services/monolith/ansible
ansible-playbook -i inventory.ini playbooks/argocd-credentials.yml \
  --vault-password-file ~/lwa-homelab/.vault_pass

# Then update the vault and open the PR as above
```

**Verify rotation succeeded:**

```bash
kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-repo-server
kubectl get applications -n argocd
# All apps should show Synced / Healthy within ~60s
```

### Health Checks

```bash
# All ArgoCD pods
kubectl get pods -n argocd

# All managed applications
kubectl get applications -n argocd

# Certificate status
kubectl get certificate -n argocd

# Traefik routing (look for argocd-server ingress)
kubectl get ingress -A
```

### Common Operations

```bash
# Force ArgoCD to re-sync an app immediately
kubectl patch application navidrome -n argocd \
  --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'

# Check why an app is OutOfSync
kubectl describe application navidrome -n argocd

# Restart ArgoCD server (e.g. after ConfigMap change)
kubectl rollout restart deployment/argocd-server -n argocd
kubectl rollout status deployment/argocd-server -n argocd --timeout=120s
```

### Insecure Mode (Traefik TLS termination)

ArgoCD runs with `server.insecure: "true"` in `argocd-cmd-params-cm`. This disables
ArgoCD's internal TLS so Traefik can terminate TLS at the ingress and forward plain
HTTP to argocd-server:8080. Without this flag, ArgoCD returns 307 redirects.

To verify the flag is set:
```bash
kubectl get configmap argocd-cmd-params-cm -n argocd -o yaml | grep insecure
```

If missing, patch and restart:
```bash
kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge -p '{"data":{"server.insecure":"true"}}'
kubectl rollout restart deployment/argocd-server -n argocd
```

### Adding a New Service to GitOps

1. Create `kubernetes/apps/<service>.yaml` — ArgoCD Application manifest
2. Add `<hostname>.littlewolfacres.com` to AdGuard Home rewrite table in
   `services/watchtower/ansible/roles/adguard/templates/AdGuardHome.yaml.j2`
3. Add matching A record in Cloudflare DNS:
   - Type: `A`, Name: `<hostname>`, Value: WAN IP, Proxy: **DNS only (grey cloud)**
   - UDP services (e.g. Minecraft) **cannot** use the orange Cloudflare proxy — grey cloud only
4. Update `homelab-state.md` DNS rewrites table
5. PR → merge → ArgoCD auto-syncs, `deploy-watchtower` applies the AdGuard rewrite — done

### cert-manager / TLS

```bash
# Check all certificates
kubectl get certificates -A

# Check why a cert isn't issuing
kubectl describe certificate argocd-tls -n argocd
kubectl describe certificaterequest -n argocd
kubectl describe challenge -n argocd

# Force cert retry (deletes stuck challenge, recreates automatically)
kubectl delete challenge -n <namespace> --all
# If still stuck, delete the CertificateRequest too:
kubectl delete certificaterequest -n <namespace> --all

# Check ClusterIssuers
kubectl get clusterissuer
```

The Cloudflare API token for DNS-01 challenges lives in:
`kubectl get secret cloudflare-api-token -n cert-manager`

It is managed out-of-band (bootstrap workflow) and excluded from ArgoCD sync.
Do not commit it to the repo. Rotate it in Cloudflare → update GitHub secret
`CLOUDFLARE_API_TOKEN` → re-run bootstrap or patch directly:
```bash
kubectl create secret generic cloudflare-api-token \
  --namespace cert-manager \
  --from-literal=api-token='<NEW_TOKEN>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## Navidrome

### Music Library — Mounting on Studio

Navidrome reads from `/mnt/hdd-c/music-library` on Monolith via a k3s hostPath volume.
To add new music or edit metadata from Studio, mount the `music-library` Samba share.
**One-time manual setup on Studio — no Ansible automation.**

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
echo '//192.168.0.20/music-library  /music-library  cifs  credentials=/etc/samba/studio-music-creds,uid=1000,gid=1000,file_mode=0664,dir_mode=0775,vers=3.0,_netdev,x-systemd.automount  0  0' \
  | sudo tee -a /etc/fstab

# 5. Mount now without rebooting
sudo systemctl daemon-reload
sudo mount /music-library
```

> **Password:** retrieve from vault on apex:
> `ansible-vault view ~/lwa-homelab/ansible/vars/vault.yml --vault-password-file=~/lwa-homelab/.vault_pass`

### Health Check

```bash
kubectl get pods -n navidrome
kubectl logs -n navidrome deployment/navidrome --tail=50 -f
kubectl exec -n navidrome deployment/navidrome -- ls /music | head -20
```

### Restarting Navidrome

```bash
kubectl rollout restart deployment/navidrome -n navidrome
kubectl rollout status deployment/navidrome -n navidrome
```

---

## Service Health Checks

### Watchtower

```bash
systemctl status prometheus alertmanager grafana-server netdata AdGuardHome unbound \
  node_exporter blackbox_exporter snmp_exporter adguard_exporter
```

### Monolith — k3s workloads

```bash
# All pods across all namespaces
kubectl get pods -A

# Specific namespace
kubectl get pods -n navidrome
kubectl get pods -n minecraft
kubectl get pods -n argocd
kubectl get pods -n cert-manager

# Pod logs
kubectl logs -n navidrome deployment/navidrome --tail=50
kubectl logs -n argocd deployment/argocd-server --tail=50

# Node status
kubectl get nodes
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
# Test from apex against watchtower
dig @192.168.0.21 monolith.littlewolfacres.com
dig @192.168.0.21 argocd.littlewolfacres.com

# Test Unbound directly (run on watchtower)
dig @127.0.0.1 -p 5335 google.com

# Test AdGuard Home (run on watchtower)
dig @127.0.0.1 google.com

# Flush Unbound cache (run on watchtower)
sudo unbound-control flush_zone littlewolfacres.com
```

### Adding a Local DNS Rewrite

**Do not add rewrites via the AdGuard Home UI** — they will be overwritten on the
next deploy-watchtower run. All rewrites are managed in:
`services/watchtower/ansible/roles/adguard/templates/AdGuardHome.yaml.j2`

Process:
1. Add entry to `AdGuardHome.yaml.j2` under `filtering.rewrites`
2. Add matching A record in Cloudflare DNS:
   - Type: `A`, Name: `<hostname>`, Value: WAN IP, Proxy: **DNS only (grey cloud)**
   - UDP services (e.g. Minecraft/Zombatron) cannot use Cloudflare proxy — grey cloud only
3. PR → merge → `deploy-watchtower` applies the AdGuard rewrite automatically
4. Update `homelab-state.md` DNS rewrites table

---

## SNMP Testing (run on watchtower)

```bash
snmpwalk -v2c -c littlewolfacres 192.168.0.1 1.3.6.1.2.1.1.1.0
snmpwalk -v2c -c littlewolfacres 192.168.0.5 1.3.6.1.2.1.1.1.0
snmpwalk -v2c -c littlewolfacres 192.168.0.2 1.3.6.1.2.1.1.1.0
curl "http://localhost:9116/snmp?module=if_mib&auth=littlewolfacres_v2&target=192.168.0.1"
```

---

## Prometheus

```bash
# Validate config and rules (run on watchtower)
promtool check config /etc/prometheus/prometheus.yml
promtool check rules /etc/prometheus/alert_rules.yml

# Check active alerts
curl -s http://192.168.0.21:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"'

# Check all targets and health
curl -s http://192.168.0.21:9090/api/v1/targets | python3 -m json.tool | grep -E "job|health"

# Check storage size
du -sh /var/lib/prometheus

# Restart after config change (run on watchtower)
sudo systemctl restart prometheus
```

---

## Alertmanager

```bash
curl -s http://192.168.0.21:9093/-/healthy
curl -s http://192.168.0.21:9093/api/v2/alerts
sudo systemctl restart alertmanager
```

---

## Ansible (run from apex)

### Watchtower

```bash
cd ~/lwa-homelab/services/watchtower/ansible

ansible-playbook -i inventory.ini playbooks/dns.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass
ansible-playbook -i inventory.ini playbooks/exporters.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass

# Dry run
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --check --vault-password-file=~/lwa-homelab/.vault_pass

# Vault operations
ansible-vault edit group_vars/all/vault.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass
ansible-vault view group_vars/all/vault.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass
```

### Apex

Apex is a workstation with no inbound SSH — GitHub Actions cannot deploy to it.
All apex services (Scribe, Zombatron Importer) are deployed manually from apex itself.
Run from `services/apex/ansible/` so `ansible.cfg` is picked up correctly.

```bash
# Scribe
cd ~/lwa-homelab/services/apex/ansible
ansible-playbook --vault-password-file ~/lwa-homelab/.vault_pass \
  -i inventory.ini playbooks/scribe.yml

# Zombatron Importer
cd ~/lwa-homelab/services/apex/ansible
ansible-playbook --vault-password-file ~/lwa-homelab/.vault_pass \
  -i inventory.ini playbooks/deploy-zombatron-importer.yml
```

### Monolith

```bash
cd ~/lwa-homelab/services/monolith/ansible

# Firewall rules
ansible-playbook -i inventory.ini playbooks/firewall.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass

# Monitoring agents (node_exporter etc.)
ansible-playbook -i inventory.ini playbooks/monitoring.yml \
  --vault-password-file=~/lwa-homelab/.vault_pass
```

---

## Terraform (run from apex)

```bash
# Watchtower
cd ~/lwa-homelab/terraform/watchtower
terraform init && terraform plan
terraform apply

# Monolith
cd ~/lwa-homelab/terraform/monolith
terraform init && terraform plan
terraform apply
```

---

## UFW (run on the relevant host)

```bash
# Check rules
sudo ufw status numbered

# Reload after changes
sudo ufw reload
```

**Do not add UFW rules manually on Monolith** — all rules are managed by the `ufw`
Ansible role in `services/monolith/ansible/roles/ufw/`. Add rules there and run the
**Deploy Monolith Config** workflow.

---

## k3s Storage

```bash
kubectl get pvc -A
kubectl get storageclass
df -h | grep mnt
```

---

## Grafana API

```bash
# List provisioned alert rules
curl -s -u 'admin:PASSWORD' \
  'http://192.168.0.21:3001/api/v1/provisioning/alert-rules' | python3 -m json.tool
```

**Do not import dashboards via the Grafana UI** — the monitoring playbook purges any
dashboard not in the managed UID set. Add new dashboards to the Ansible grafana role.

---

## NUT — When UPS Arrives

1. Connect CyberPower CP1500PFCLCD via USB to Watchtower
2. Run monitoring playbook — NUT role activates automatically (`nut_enabled: true` in vars)
3. Verify: `systemctl status nut-server nut-monitor`
4. Check UPS status: `upsc cyberpower@localhost`

---

## Git Workflow

```bash
cd ~/lwa-homelab
git checkout -b feat/description-of-change

git add <explicit paths>
git commit -m "feat: description"
git push -u origin feat/description-of-change

gh pr create --title "feat: description" --body "What and why"

# After merge — sync local repo
git checkout master && git pull

# Manual workflow trigger
gh workflow run deploy-watchtower.yml
gh workflow run deploy-monolith.yml
```

### Branch conventions

| Prefix | Use |
|---|---|
| `feat/*` | New capabilities |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation only — no deploy triggered |
| `chore/*` | Maintenance, dependency updates |

### Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `deploy-watchtower.yml` | Push to master (watchtower paths) | DNS, monitoring, exporters |
| `deploy-monolith.yml` | Push to master (monolith paths) | Firewall, monitoring agents |
| `deploy-fileserver.yml` | Manual | Samba config |
| ~~`deploy-zombatron-importer.yml`~~ | Deleted — apex has no inbound SSH. Deploy manually from apex. |
| `import-minecraft-world.yml` | Manual (confirm: yes) | Stage world via Ansible + bounce pod |
| `slack-minecraft-import.yml` | Zombatron Importer bot | Clear import marker + bounce pod |
| `bootstrap-argocd.yml` | Manual (once) | cert-manager + ArgoCD install |
| `provision-k3s.yml` | Manual | k3s cluster init |
