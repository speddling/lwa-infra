# LWA Infra — Architecture Overview
> Last verified: 2026-06-21 · Source of truth is README.md and homelab-state.md
> This is a structure doc: what's deployed and how it connects. Roadmap and in-flight work live in Plane (`LWA Infra` project), not here.

---

## Network Topology

```
Internet
    │
    ├── T-Mobile FAST 5688W (5G WAN)
    └── AT&T CGW450 (5G WAN2 — in progress, separate cellular network)
            │
        ER605 v2 (192.168.0.1)
        Multi-WAN VPN Router
            │
        TL-SG1210P (unmanaged PoE switch — being replaced by SG2218P, in progress)
            │
    ┌───────┼───────────────────────────┐
    │       │                           │
EAP245   EAP245                    Wired LAN
(Foyer)  (Yarn Studio)
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              apex (.19)         monolith (.20)      watchtower (.21)
         MacBook Air M4        AMD Ryzen 7 5700G     Asus VM40B
         16GB unified          64GB DDR4             8GB DDR3
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
    ├── git push → GitHub (speddling/lwa-homelab)
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
├── KubeVirt + CDI (bootstrapped, not yet used — Obelisk still runs as a bare QEMU/KVM process below, not a KubeVirt VirtualMachine)
│
├── Navidrome (music streaming)          namespace: navidrome
├── Minecraft Bedrock                    namespace: minecraft   NodePort :30132 UDP
├── Synapse MCP                          namespace: synapse     NodePort :30800 TCP
│
├── kube-state-metrics                   → Prometheus on watchtower
│
└── Bare-metal (not k8s)
        ├── Obelisk (Win11 VM)          QEMU/KVM process, RDP :33389, metrics :39182
        └── Samba
                ├── vault          → /mnt/ssd-b/vault
                ├── studio-archive → /mnt/hdd-c/studio-archive
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
            ├── scrapes: watchtower · monolith · argocd-app-controller · argocd-server · kube-state-metrics
            ├── scrapes: snmp_exporter (ER605, EAP245×2)
            ├── scrapes: blackbox_exporter (HTTP/ICMP probes)
            ├── scrapes: adguard_exporter · tmobile_exporter · reolink_exporter
            ├── scrapes: loki · promtail
            └── fires alerts → Alertmanager (:9093) → Slack #sentinel + healthchecks.io watchdog

        Loki (:3100) + Promtail (:9080)
            ├── sources: Watchtower systemd journal
            └── sources: ER605 syslog on :1514 (not yet wired — pending ER605 config)

        Grafana (:3001)  [display only — Alertmanager owns alerting]
            Dashboards: Node Exporter Full · Blackbox Probes · k3s Cluster
                        SNMP Interfaces · T-Mobile 5G Gateway · Reolink NVR
            Loki datasource added manually (not Ansible-provisioned)

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
```

---

## CI/CD Pipelines

| Workflow | Trigger | Runner | Target |
|---|---|---|---|
| `deploy-watchtower.yml` | Push to master (`services/watchtower/**`, `terraform/watchtower/**`, `ansible/vars/**`) | watchtower | Ansible → watchtower |
| `deploy-monolith.yml` | Push or PR to master (`services/monolith/ansible/**`, `ansible/vars/**`) | monolith | Ansible → monolith |
| `deploy-fileserver.yml` | Manual | monolith | Ansible → monolith |
| `deploy-synapse.yml` | Push to master | monolith | Ansible → monolith |
| `deploy-k3s-manifests.yml` | Push to master (`kubernetes/manifests/**`) | monolith | kubectl → k3s manifests |
| `deploy-navidrome.yml` | Manual | monolith | Ansible/kubectl → Navidrome |
| `deploy-mirror.yml` | Push to master (`services/monolith/ansible/roles/mirror-hdd/**`) | monolith | Ansible → hdd-c/hdd-d mirror systemd timer |
| `deploy-reolink-exporter.yml` | Push to master or manual (`services/watchtower/ansible/roles/reolink_exporter/**`) | watchtower | Ansible → reolink_exporter |
| `deploy-tmobile-exporter.yml` | Push to master or manual (`services/watchtower/ansible/roles/tmobile_exporter/**`) | watchtower | Ansible → tmobile_exporter |
| `bootstrap-argocd.yml` | Manual (once) | monolith | cert-manager + ArgoCD install |
| `bootstrap-kubevirt.yml` | Manual (once, unrun) | monolith | KubeVirt + CDI install, provisions Obelisk as a KubeVirt VM |
| `bootstrap-plane.yml` | Push to master (`kubernetes/apps/plane.yaml`) or manual | monolith | Generates Plane secrets; idempotent no-op if they already exist |
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
