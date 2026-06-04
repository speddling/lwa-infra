# Minecraft Bedrock Server — K3s Homelab Reference

## Overview

A Bedrock-only Minecraft server for 2 LAN players, running on Monolith via k3s.
Managed by ArgoCD. World data is persisted via a PersistentVolumeClaim with
optional import from a `.mcworld` backup triggered via the `#zombatron` Slack channel.

Players: `MamaKittaly` and `Makamakamelon` (both operators)
Server address: `zombatron.littlewolfacres.com:30132`

---

## Stack

| Layer | Tool |
|---|---|
| Container runtime | k3s |
| Server image | `itzg/minecraft-bedrock-server:latest` |
| GitOps | ArgoCD (auto-sync, prune, selfHeal) |
| World import | Zombatron Importer (Slack bot on apex) |
| Config management | Ansible |
| CI/CD | GitHub Actions (self-hosted runner on Monolith) |

---

## Networking

| Detail | Value |
|---|---|
| Protocol | UDP |
| Internal port | 19132 |
| NodePort | 30132 |
| Service type | NodePort (LoadBalancer is broken for UDP in k3s) |
| LAN DNS | `zombatron.littlewolfacres.com` → 192.168.0.20 (AdGuard rewrite) |
| Public DNS | `zombatron.littlewolfacres.com` → WAN IP (Cloudflare A record, DNS only) |
| Client connection | `zombatron.littlewolfacres.com` port `30132` |

> ⚠️ k3s ServiceLB does not reliably handle UDP — always use NodePort for UDP services.
> Cloudflare cannot proxy UDP game traffic — the zombatron A record must be DNS only (grey cloud).

---

## Directory Structure

```
lwa-homelab/
├── services/
│   └── minecraft/
│       ├── ansible/
│       │   ├── inventory.ini              ← monolith: 192.168.0.20
│       │   └── playbooks/
│       │       └── import-world.yml       ← stages .mcworld on Monolith (manual path)
│       ├── kubernetes/
│       │   ├── namespace.yaml
│       │   ├── pvc.yaml
│       │   ├── configmap.yaml
│       │   ├── deployment.yaml
│       │   └── service.yaml
│       └── files/
│           └── .gitkeep                   ← .mcworld files go here, gitignored
├── services/
│   └── apex/
│       └── zombatron-importer/
│           ├── importer.py                ← Slack bot service
│           └── requirements.txt
└── .github/
    └── workflows/
        ├── import-minecraft-world.yml     ← manual import (Ansible + pod bounce)
        └── slack-minecraft-import.yml     ← bot-triggered (marker clear + pod bounce only)
```

---

## Kubernetes Manifests

### `namespace.yaml`
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: minecraft
```

### `pvc.yaml`
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minecraft-data
  namespace: minecraft
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi
```

### `configmap.yaml`
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: minecraft-config
  namespace: minecraft
data:
  EULA: "TRUE"
  LEVEL_NAME: "littlewolfacres"
  GAMEMODE: "survival"
  DIFFICULTY: "normal"
  MAX_PLAYERS: "2"
  SERVER_NAME: "Little Wolf Acres"
  ALLOW_CHEATS: "true"
  ONLINE_MODE: "true"
  OPS: "Makamakamelon,MamaKittaly"
```

### `deployment.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minecraft-bedrock
  namespace: minecraft
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minecraft-bedrock
  template:
    metadata:
      labels:
        app: minecraft-bedrock
    spec:
      initContainers:
        - name: world-import
          image: busybox
          command:
            - sh
            - -c
            - |
              WORLD_DIR="/data/worlds/littlewolfacres"
              MARKER="/data/worlds/.imported"

              if [ -f "$MARKER" ]; then
                echo "World already imported, skipping."
                exit 0
              fi

              if [ -f "/world-import/realm.mcworld" ]; then
                echo "Importing realm backup..."
                mkdir -p "$WORLD_DIR"
                unzip /world-import/realm.mcworld -d "$WORLD_DIR"
                touch "$MARKER"
                echo "Import complete."
              else
                echo "No .mcworld file found, starting fresh world."
              fi
          volumeMounts:
            - name: minecraft-data
              mountPath: /data
            - name: world-import
              mountPath: /world-import
      containers:
        - name: minecraft-bedrock
          image: itzg/minecraft-bedrock-server:latest
          envFrom:
            - configMapRef:
                name: minecraft-config
          ports:
            - containerPort: 19132
              protocol: UDP
          volumeMounts:
            - name: minecraft-data
              mountPath: /data
          resources:
            requests:
              memory: "1Gi"
              cpu: "500m"
            limits:
              memory: "3Gi"
              cpu: "2000m"
      volumes:
        - name: minecraft-data
          persistentVolumeClaim:
            claimName: minecraft-data
        - name: world-import
          hostPath:
            path: /opt/minecraft/import
            type: DirectoryOrCreate
```

### `service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: minecraft-bedrock
  namespace: minecraft
spec:
  type: NodePort
  selector:
    app: minecraft-bedrock
  ports:
    - port: 19132
      targetPort: 19132
      nodePort: 30132
      protocol: UDP
```

---

## World Import

Two paths depending on how the file arrives.

### Via Slack (normal path — Zombatron Importer)

1. Drop a `.mcworld` file into `#zombatron` in the Little Wolf Acres Slack
2. The bot downloads it, SCPs it to `/opt/minecraft/import/realm.mcworld` on Monolith, and asks for confirmation
3. Reply `yes` → bot triggers `slack-minecraft-import.yml` → pod bounces → initContainer imports the world
4. Reconnect to `zombatron.littlewolfacres.com:30132` after ~60 seconds

Reply `no` to cancel — current world is left untouched.

### Manual path (GitHub Actions)

1. Place `.mcworld` at `services/minecraft/files/realm.mcworld` (gitignored)
2. Run **Actions → Import Minecraft World** → type `yes` to confirm
3. Ansible stages the file on Monolith, clears the import marker, bounces the pod

### How the initContainer works

On every pod start, the `world-import` initContainer checks for `/data/worlds/.imported`:
- **Marker present** → skip (protects against accidental re-import on crash/restart)
- **Marker absent + `realm.mcworld` exists** → unzip into `/data/worlds/littlewolfacres/`, write marker
- **Marker absent + no file** → start fresh world

To force a re-import, the marker must be cleared first — both import paths handle this automatically.

---

## Zombatron Importer (Slack Bot)

Python service running as a launchd agent on apex. Connects to Slack via Socket Mode — no inbound port forwarding required.

| Detail | Value |
|---|---|
| Source | `services/apex/zombatron-importer/importer.py` |
| Runtime | Python venv at `~/.venv/zombatron-importer` |
| Service manager | launchd — `com.littlewolfacres.zombatron-importer` |
| Log | `~/Library/Logs/zombatron-importer.log` |
| Slack channel | `#zombatron` (private, 3 members) |
| Channel ID | `C0B5C20R1SB` |
| Vault variables | `vault_slack_zombatron_bot_token`, `vault_slack_zombatron_app_token` |
| GitHub PAT | `vault_github_actions_pat` (Actions: Read & Write, homelab repo) |
| Deploy | `deploy-zombatron-importer.yml` — auto-triggers on push to `services/apex/**` |

### Bot behaviour

| Event | Action |
|---|---|
| `.mcworld` file shared in `#zombatron` | Download, SCP to Monolith, ask for confirmation |
| Any other file type | Ignore |
| `yes` reply | Trigger `slack-minecraft-import.yml`, report when done |
| `no` reply | Cancel, confirm world is untouched |
| Message in any other channel | Ignore |

---

## GitHub Actions Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `slack-minecraft-import.yml` | Bot dispatch (GitHub API) | Clears import marker, bounces pod — file already staged by bot |
| `import-minecraft-world.yml` | Manual (`workflow_dispatch`, confirm: yes) | Stages via Ansible, clears marker, bounces pod |
| `deploy-zombatron-importer.yml` | Push to `services/apex/**` or manual | SSHs to apex, runs Ansible playbook on-host |

---

## Key Gotchas

| Gotcha | Detail |
|---|---|
| **UDP + k3s = NodePort only** | k3s ServiceLB silently fails for UDP — always use NodePort |
| **`LEVEL_NAME` must match** | ConfigMap value must match the world directory name exactly (`littlewolfacres`) |
| **Marker file prevents overwrites** | `/data/worlds/.imported` — deleted automatically by both import workflows before bounce |
| **Marketplace content won't transfer** | License-locked to Xbox accounts, not the world file |
| **Both players are ops** | `MamaKittaly` and `Makamakamelon` — can use all commands in-game |
| **`.mcworld` is gitignored** | `services/minecraft/files/*.mcworld` — world data stays out of version control |
| **Cloudflare A record must be DNS only** | UDP traffic cannot be proxied — grey cloud, no orange cloud |
| **No automatic backups yet** | Consider a k8s CronJob to tarball the PVC — see Pending Work |

---

## Quick Reference

```bash
# Pod status
kubectl get pods -n minecraft

# Follow server logs
kubectl logs -n minecraft deploy/minecraft-bedrock -f

# Check initContainer import logs
kubectl logs -n minecraft <pod-name> -c world-import

# Restart the server
kubectl delete pod -n minecraft -l app=minecraft-bedrock

# Check service / NodePort
kubectl get svc -n minecraft

# Manually clear import marker (both import workflows do this automatically)
kubectl exec -n minecraft deploy/minecraft-bedrock -- rm -f /data/worlds/.imported

# Check Zombatron Importer logs on apex
tail -f ~/Library/Logs/zombatron-importer.log

# Restart Zombatron Importer on apex
launchctl unload ~/Library/LaunchAgents/com.littlewolfacres.zombatron-importer.plist
launchctl load ~/Library/LaunchAgents/com.littlewolfacres.zombatron-importer.plist
```

---

## Pending

- **Automated PVC backups** — k8s CronJob to tarball `/data` nightly to `/mnt/hdd-c`
- **Realm cancellation** — export world from Realm, import via `#zombatron`, then cancel $8/month subscription
