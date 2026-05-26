# Little Wolf Acres — Architecture Overview
> Generated 2026-05-26 · Source of truth is README.md and homelab-state.md

---

## Network Topology

```
Internet
    │
    ├── T-Mobile FAST 5688W (5G WAN)
    └── [secondary WAN]
            │
        ER605 v2 (192.168.0.1)
        Multi-WAN VPN Router
            │
        TL-SG1210P (unmanaged PoE switch)
            │
    ┌───────┼───────────────────────────┐
    │       │                           │
EAP245   EAP245                    Wired LAN
(Foyer)  (Yarn Studio)
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              apex (.19)         monolith (.20)      watchtower (.21)
         MacBook Air M4        AMD Ryzen 7 5700G     Asus VM40B
         16GB unified          32GB DDR4             8GB DDR3
         Primary WS            k3s node              DNS + Monitoring

                                                  studio (.109)
                                             Dell Precision 5560
                                             DAW / KDE workstation
```

---

## Control Plane Flow

```
apex (author)
    │
    ├── git push → GitHub (speddling/homelab)
    │       │
    │       ├── GitHub Actions (self-hosted runners on monolith + watchtower)
    │       │       ├── deploy-watchtower.yml  → Ansible → watchtower
    │       │       ├── deploy-monolith.yml    → Ansible → monolith
    │       │       └── rotate-argocd-credentials.yml → monolith
    │       │
    │       └── ArgoCD (monolith) watches master
    │               └── reconciles k8s workloads from repo
    │
    └── Ansible (manual, apex-local)
            ├── services/apex/ansible/     → localhost (apex services)
            └── services/monolith/ansible/ → monolith (via SSH)
```

---

## Monolith — k3s Cluster

```
monolith (192.168.0.20)
│
├── Traefik (ingress, TLS termination)
│       ├── argocd.littlewolfacres.com   → ArgoCD
│       └── navidrome.littlewolfacres.com → Navidrome
│
├── cert-manager (Let's Encrypt via Cloudflare DNS-01)
│
├── ArgoCD (GitOps controller)
│       Manages: navidrome · minecraft · synapse · cert-manager · kube-state-metrics
│
├── Navidrome (music streaming)          namespace: navidrome
├── Minecraft Bedrock                    namespace: minecraft   NodePort :30132 UDP
├── Synapse MCP                          namespace: synapse     NodePort :30800 TCP
│
├── kube-state-metrics                   → Prometheus on watchtower
│
└── Samba (bare-metal, not k8s)
        ├── vault          → /mnt/ssd-b/vault
        ├── studio-archive → /mnt/lab-backups/studio-archive
        └── music-library  → /mnt/hdd-c/music-library  ← Navidrome source
```

### Monolith Storage

```
/           512GB NVMe  (Samsung PM9A1)   OS + k3s
/mnt/ssd-a  500GB SSD   (Crucial)         k8s local-path provisioner (PVCs)
/mnt/ssd-b  256GB SSD   (Crucial)         Obelisk workspace (reserved) + vault share
/mnt/hdd-c  3.6TB HDD   (Seagate)         Music library + bulk storage
/mnt/hdd-d  1.8TB HDD   (Hitachi)         Mirror of hdd-c (nightly rsync 02:00)
```

---

## Watchtower — DNS + Monitoring Stack

```
watchtower (192.168.0.21)
│
├── DNS
│       AdGuard Home (:53, :3000)
│           └── Unbound (:5335) → Root DNS servers
│
└── Monitoring
        Prometheus (:9090)
            ├── scrapes: watchtower · monolith · argocd · kube-state-metrics
            ├── scrapes: snmp_exporter (ER605, EAP245×2)
            ├── scrapes: blackbox_exporter (HTTP/ICMP probes)
            ├── scrapes: adguard_exporter · tmobile_exporter · reolink_exporter
            └── fires alerts → Alertmanager (:9093) → Slack #sentinel

        Grafana (:3001)  [display only — Alertmanager owns alerting]
            Dashboards: Node Exporter Full · Blackbox Probes · k3s Cluster
                        SNMP Interfaces · T-Mobile 5G Gateway · Reolink NVR

        Netdata (:19999)  real-time host observability
```

---

## DNS Resolution Chain

```
LAN client
    │
    └── AdGuard Home (watchtower :53)
            ├── Local rewrites (*.littlewolfacres.com → LAN IPs)
            ├── Ad/tracker blocking
            └── Unbound (watchtower :5335)
                    └── Root DNS servers (recursive, no upstream forwarder)

Public DNS: Cloudflare
    ├── Authoritative for littlewolfacres.com
    ├── LAN fallback if AdGuard unreachable
    └── DNS-01 challenge provider for cert-manager (Let's Encrypt)
```

---

## AI / MCP Layer

```
Claude (apex)
    │
    ├── Synapse MCP (monolith :30800)  ← read-only
    │       k3s pod state · Prometheus metrics · Alertmanager alerts · monolith filesystem
    │
    ├── Scribe MCP (apex :8765)        ← write (git only)
    │       branch · stage · commit · push · open PRs
    │       branch protection + path allowlist enforced at server level
    │
    └── Argus MCP (watchtower :9800)   ← read-only
            Alertmanager config · Prometheus config · systemd state · journald logs

B-4 (apex ~/B-4/)
    └── Ollama (Metal backend, 16GB unified)
            ├── gemma4     (~12GB)  Claude Code integration
            └── llama3.2:3b (~2GB)  direct chat

Lore (planned — Mac Mini M4 Pro 48GB / 10GbE)
    └── Ollama headless → API served to LAN
```

---

## CI/CD Pipelines

| Workflow | Trigger | Runner | Target |
|---|---|---|---|
| `deploy-watchtower.yml` | Push to master (`services/watchtower/**`) | watchtower | Ansible → watchtower |
| `deploy-monolith.yml` | Push to master | monolith | Ansible → monolith |
| `deploy-fileserver.yml` | Manual | monolith | Ansible → monolith |
| `deploy-synapse.yml` | Push to master | monolith | Ansible → monolith |
| `bootstrap-argocd.yml` | Manual (once) | monolith | cert-manager + ArgoCD install |
| `provision-k3s.yml` | Manual | monolith | k3s cluster init |
| `rotate-argocd-credentials.yml` | Manual + quarterly | monolith | PAT rotation |
| `import-minecraft-world.yml` | Manual (`confirm: yes`) | monolith | Ansible + pod bounce |
| `slack-minecraft-import.yml` | Zombatron Importer (GitHub API) | monolith | Clear marker + pod bounce |

> Apex services (Scribe, Zombatron Importer) deploy manually from apex — no inbound SSH, no CI runner.

---

## Secrets Management

```
ansible/vars/vault.yml          ← Ansible Vault (AES-256)
    │   All IPs, ports, passwords, tokens, community strings
    │
    ├── .vault_pass             ← local file on apex (gitignored)
    └── GitHub Actions secrets  ← VAULT_PASSWORD injected at runtime

ArgoCD repo secret (homelab-repo)
    └── Fine-grained GitHub PAT — managed out-of-band, never via ArgoCD sync
        Rotation: rotate-argocd-credentials.yml (quarterly + manual)
```

---

## Planned Additions

| Item | Target | Notes |
|---|---|---|
| Loki | watchtower | Log aggregation |
| NUT | watchtower | UPS monitoring — role ready, waiting on hardware |
| JetStream switch | network | Replaces unmanaged TL-SG1210P, enables per-port SNMP |
| Minecraft PVC backups | monolith | Nightly CronJob → /mnt/hdd-c |
| Obelisk | monolith | Isolated client workspace on /mnt/ssd-b |
| VLAN design | network | IoT · LAN · homelab · guest segments |
| Lore | new node | Mac Mini M4 Pro 48GB — dedicated LAN inference |
| Navidrome HTTPS | monolith | cert-manager annotation already understood — just needs applying |
