# Little Wolf Acres — Homelab Runbook
> Operational reference for day-to-day tasks, troubleshooting, and maintenance.
> Last updated: 2026-06-15

---

## ArgoCD

### Access

| Method | URL | When to use |
|---|---|---|
| Primary | https://argocd.littlewolfacres.com | Normal operations |
| Fallback | http://monolith.littlewolfacres.com:30880 | DNS unstable or cert issue |

> **CLI tip:** if every `argocd` command errors needing `--grpc-web` after a fresh
> `argocd login`, pass it at login time instead —
> `argocd login argocd.littlewolfacres.com --grpc-web` — the CLI persists this as
> the default for that server context, so subsequent commands don't need it.

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
### Recovering from a Stuck or Corrupted Database (Full PVC Wipe)

**When to use:** `data.db` is corrupted (e.g. after a power outage) and a normal
`kubectl rollout restart` doesn't fix it — or you're locked out and need a
genuinely fresh database. This wipes **all** Navidrome metadata: user accounts,
playlists, favorites, ratings, play history. Music files on
`/mnt/hdd-c/music-library` are untouched (separate hostPath mount) and get
re-imported by the next scan.

**Why the naive approach fails:** ArgoCD's `Automated (Prune)` / `Self-Heal`
policy will race a manual `kubectl delete pvc` — it can recreate the PVC before
`local-path-provisioner` finishes deleting the old directory, leaving you with a
"new" PVC that's still bound to the old data (no migration run, old users still
present, saved passwords stop working, no "Create Admin" prompt). The
`argocd.argoproj.io/skip-reconcile` annotation prevents this race.

#### 1. Freeze the ArgoCD Application

```bash
kubectl annotate application navidrome -n argocd argocd.argoproj.io/skip-reconcile="true" --overwrite
```

#### 2. Scale down and delete the PVC

```bash
kubectl scale deployment navidrome --replicas=0 -n navidrome
kubectl delete pvc navidrome-db -n navidrome
```

#### 3. Checkpoint — confirm it's actually gone

**Do not skip this.** Its absence is what let a stale database survive a "wipe"
last time.

```bash
kubectl get pvc navidrome-db -n navidrome
kubectl get pv | grep navidrome
```

Both should return empty/`NotFound` within ~30-60s. If the PVC hangs in
`Terminating`, stop and check `kubectl describe pvc navidrome-db -n navidrome` for
stuck finalizers before continuing.

#### 4. Unfreeze and force a sync

```bash
kubectl annotate application navidrome -n argocd argocd.argoproj.io/skip-reconcile-
argocd app sync navidrome --grpc-web
```

#### 5. Checkpoint — confirm a genuinely fresh database

```bash
kubectl get pods -n navidrome
kubectl logs -n navidrome <new-pod-name> | head -60
```

Look for the fresh-DB bootstrap sequence:

```
level=info msg="Creating DB Schema"
...
level=info msg="Running initial setup"
level=info msg="Creating new JWT secret, used for encrypting UI sessions"
```

If instead you see `goose: no migrations to run. current version: ...` with no
preceding `OK <migration>.sql` lines, the database was **not** wiped — go back to
step 3.

#### 6. Watch for OOM during the initial scan

A fresh DB means every folder is "new" (`updated=N` for every folder in the scan
log, not just changed ones) — a cold full-library scan is far more memory-hungry
than the normal hourly incremental scan. As of 2026-06-15, `deployment.yaml` sets
`request: 512Mi` / `limit: 2Gi` specifically to cover this; monolith has plenty of
headroom (16 cores / 32GB+) to go higher if needed.

If the pod still crash-loops:

```bash
kubectl get pod -n navidrome -o wide   # check RESTARTS
kubectl get pod -n navidrome -o jsonpath='{.status.containerStatuses[0].lastState}'
```

`"reason":"OOMKilled"`, `"exitCode":137` → bump the memory limit further.

#### 7. Create the admin account

Once stable, visit `https://navidrome.littlewolfacres.com/app/` — you should land
on **Create Admin Account**. If the page won't load even though the pod is
healthy, see "Browser Can't Reach *.littlewolfacres.com" under the DNS section
below.

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

### Browser Can't Reach *.littlewolfacres.com (DNS Resolves Fine)

Two client-side issues that both present as a generic "Unable to connect" — neither
is a cluster/DNS problem despite appearances:

**1. Firefox's DNS-over-HTTPS bypasses AdGuard.** Firefox enables DoH by default,
sending queries straight to a public resolver instead of the network's
DHCP-assigned DNS server. Since the public Cloudflare record for
`*.littlewolfacres.com` is DNS-only (grey cloud) pointing at the WAN IP — not
port-forwarded — Firefox resolves to an address it can't reach.
- Fix: `about:preferences#privacy` → "DNS over HTTPS" → **Off**, fully restart
  Firefox, clear the cache on `about:networking#dns`.
- Verify: `about:networking#dns` should resolve `*.littlewolfacres.com` to
  `192.168.0.20`.

**2. macOS "Local Network" permission (Sonoma+).** Even when DNS resolves
correctly to `192.168.0.20`, macOS requires per-app permission to connect to
devices on the local network — separate from internet access entirely. Without it,
a browser resolves the hostname fine but the TCP connection silently fails, even
for a raw `http://192.168.0.20:<port>` with no hostname or TLS involved.
- Fix: **System Settings → Privacy & Security → Local Network** → enable the
  toggle for the affected browser, then fully quit and relaunch it.
- This is the one to check first if DNS already looks correct and the failure is
  browser-specific (e.g. Chrome works, Firefox doesn't) on the same machine.

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
