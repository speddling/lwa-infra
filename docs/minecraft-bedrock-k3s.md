# Minecraft Bedrock Server — K3s Homelab Reference

## Overview

A Bedrock-only Minecraft server for 2–3 LAN players, running on the `amd-tower` (Monolith) worker node via K3s. World data is imported from a Realm backup and persisted via a PersistentVolumeClaim.

---

## Stack

| Layer | Tool |
|---|---|
| Container runtime | K3s (k3s.io) |
| Server image | `itzg/minecraft-bedrock-server:latest` |
| IaC | Terraform |
| Config management | Ansible |
| CI/CD | GitHub Actions (self-hosted runner on Monolith) |
| OS | Ubuntu Server 24.04 LTS |

---

## Networking

| Detail | Value |
|---|---|
| Protocol | **UDP** (not TCP) |
| Port | `19132` |
| Service type | `LoadBalancer` (k3s servicelb) |
| Client connection | Node LAN IP on port `19132` |

> ⚠️ The UDP protocol must be explicitly declared in the Service manifest — k3s servicelb supports it but defaults to TCP.

---

## Directory Structure

```
homelab/
├── services/
│   └── minecraft/
│       ├── ansible/
│       │   ├── inventory.ini
│       │   └── playbooks/
│       │       └── import-world.yml
│       ├── kubernetes/
│       │   ├── namespace.yaml
│       │   ├── pvc.yaml
│       │   ├── configmap.yaml
│       │   ├── deployment.yaml
│       │   └── service.yaml
│       └── files/
│           └── .gitkeep          ← .mcworld files go here, gitignored
└── .github/
    └── workflows/
        └── deploy-minecraft.yml
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
  LEVEL_NAME: "my-realm"        # must match extracted world folder name
  GAMEMODE: "survival"
  DIFFICULTY: "normal"
  MAX_PLAYERS: "3"
  SERVER_NAME: "Homelab SMP"
  ALLOW_CHEATS: "false"
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
              WORLD_DIR="/data/worlds/my-realm"
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
                echo "No .mcworld file found, starting fresh."
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
            path: /opt/minecraft/import   # Ansible stages the .mcworld here
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
  type: LoadBalancer
  selector:
    app: minecraft-bedrock
  ports:
    - port: 19132
      targetPort: 19132
      protocol: UDP
```

---

## Ansible

### `import-world.yml`
```yaml
---
- name: Stage Minecraft world import
  hosts: monolith
  become: true

  vars:
    import_dir: /opt/minecraft/import
    mcworld_local_path: "{{ playbook_dir }}/../../files/realm.mcworld"

  tasks:
    - name: Create import staging directory
      ansible.builtin.file:
        path: "{{ import_dir }}"
        state: directory
        mode: "0755"

    - name: Copy .mcworld file to node
      ansible.builtin.copy:
        src: "{{ mcworld_local_path }}"
        dest: "{{ import_dir }}/realm.mcworld"
        mode: "0644"

    - name: Confirm file staged
      ansible.builtin.debug:
        msg: "realm.mcworld staged at {{ import_dir }} — deploy the manifest to trigger import"
```

---

## GitHub Actions

### `deploy-minecraft.yml`
```yaml
name: Deploy Minecraft

on:
  workflow_dispatch:
    inputs:
      import_world:
        description: "Stage a new .mcworld import?"
        type: boolean
        default: false

jobs:
  deploy:
    runs-on: self-hosted
    labels: [monolith]

    steps:
      - uses: actions/checkout@v4

      - name: Stage world import (optional)
        if: ${{ inputs.import_world }}
        run: |
          ansible-playbook \
            -i services/minecraft/ansible/inventory.ini \
            services/minecraft/ansible/playbooks/import-world.yml

      - name: Apply Kubernetes manifests
        run: |
          kubectl apply -f services/minecraft/kubernetes/namespace.yaml
          kubectl apply -f services/minecraft/kubernetes/pvc.yaml
          kubectl apply -f services/minecraft/kubernetes/configmap.yaml
          kubectl apply -f services/minecraft/kubernetes/deployment.yaml
          kubectl apply -f services/minecraft/kubernetes/service.yaml
```

---

## Realm World Import Process

### One-time setup steps

1. **Export from Realm** — In-game → Settings → Download World → saves a `.mcworld` file
2. **Place the file** at `services/minecraft/files/realm.mcworld`
3. **Run the workflow** with `import_world: true`
   - Ansible copies the file to `/opt/minecraft/import/` on Monolith
4. **Pod starts** — init container checks for a `.imported` marker file
   - Not found → unzips `.mcworld` into `/data/worlds/my-realm/`
   - Found → skips (protects against accidental overwrites on restart)
5. **Main container starts** — `LEVEL_NAME` in ConfigMap points to the imported world

### To load a new world later

Delete the marker file and re-run with `import_world: true`:
```bash
kubectl exec -n minecraft deploy/minecraft-bedrock -c world-import -- rm /data/worlds/.imported
```
Then re-run the workflow with `import_world: true`.

---

## Key Gotchas

| Gotcha | Detail |
|---|---|
| **`LEVEL_NAME` must match folder name** | BDS is strict — the ConfigMap value must match the extracted world directory name exactly |
| **Marker file prevents overwrites** | `/data/worlds/.imported` is created after first import — delete it intentionally to re-import |
| **Marketplace content won't transfer** | License-locked to accounts, not the world file |
| **Behavior/resource packs** | Must be copied separately into `behavior_packs` / `resource_packs` and re-linked in `world_behavior_packs.json` |
| **Single node = no HA** | Fine for LAN — pod restarts automatically on crash |
| **No automatic backups** | Consider adding a K3s `CronJob` to tarball the PVC data |
| **`.mcworld` is gitignored** | `services/minecraft/files/*.mcworld` — keep world data out of version control |


---

## Quick Reference Commands

```bash
# Check pod status
kubectl get pods -n minecraft

# Watch logs
kubectl logs -n minecraft deploy/minecraft-bedrock -f

# Check init container logs (import troubleshooting)
kubectl logs -n minecraft deploy/minecraft-bedrock -c world-import

# Get the LAN IP players connect to
kubectl get svc -n minecraft

# Restart the server
kubectl rollout restart deploy/minecraft-bedrock -n minecraft

# Delete marker to force re-import on next deploy
kubectl exec -n minecraft deploy/minecraft-bedrock -- rm /data/worlds/.imported
```
