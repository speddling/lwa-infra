# Little Wolf Acres — Homelab Roadmap
> Future plans, upgrades, and aspirational builds. Current state lives in `homelab-state.md`. Operational debt and one-off tasks live in `homelab-todo.md`.
> Last updated: 2026-05-30

---

## AI Node Progression

The AI stack follows a three-tier naming and capability progression. Each node has a distinct role — they are not redundant, they are additive.

| Node | Host | Role | Status |
|---|---|---|---|
| B-4 | apex (MacBook Air M4) | Daily driver, experimentation, fast iteration | ✅ Active |
| Lore | Mac Mini or Mac Studio (TBD) | Dedicated headless inference — always-on, silent, LAN API | 🕐 Planned |
| Data | Custom Linux build (TBD) | Production-parity environment, CUDA, fine-tuning, MLOps | 🕐 Aspirational |

---

## Lore — Dedicated Inference Node

Headless Mac Mini or Mac Studio serving Ollama over LAN. Closet-mounted, silent, always on. Replaces B-4 for sustained inference so apex stays free for development.

### Target Spec

| Item | Target |
|---|---|
| Hardware | Mac Mini M5 Pro or Mac Studio M5 (maxed chip, maxed RAM, smallest SSD) |
| Memory | Maximum available unified memory for the chosen config |
| Storage | Smallest internal SSD — model weights live on external Thunderbolt NVMe |
| Network | 10 Gigabit Ethernet — future-proofs beyond current gigabit LAN |
| Hostname | `lore` (reserved in AdGuard Home and DHCP) |
| IP | TBD — DHCP MAC-bound on arrival |
| Software | Ollama headless, MLX for native Apple Silicon inference |
| API | `http://lore.littlewolfacres.com:11434` (planned) |

### Timing

Waiting on M5 Mac Mini / Mac Studio refresh. M5 chip brings ~30% memory bandwidth improvement over M4 and introduces Neural Accelerators per GPU core — meaningful for inference throughput. Expected mid-to-late 2026.

> **Decision point on arrival:** Mac Mini M5 Pro (maxed) vs Mac Studio M5 depending on final specs and pricing. Mac Studio if memory ceiling or bandwidth justifies the premium. Either way: max chip, max RAM, smallest storage.

### Notes

- Edu pricing applies via `.edu` email — check Apple Education Store at purchase time
- External Thunderbolt 5 NVMe enclosure for model storage (keeps internal SSD clean)
- Initial setup requires a monitor for ~20 minutes to enable SSH and headless mode — borrow, don't buy
- Use MLX (`mlx-lm`) as primary inference runtime, Ollama as API compatibility layer

---

## Data — Linux Production-Parity AI Workstation

Custom Linux build targeting production-parity with cloud ML environments. CUDA, PyTorch, vLLM, fine-tuning pipelines, Kubernetes GPU workloads. The environment that maps to what enterprise AI infrastructure actually runs on.

> **Status:** Aspirational — not on current roadmap. Component choices below reflect research as of May 2026. Expect GPU, RAM pricing, and available models to shift before purchase.

### Target Spec

| Component | Target | Est. Price (May 2026) |
|---|---|---|
| Case | Fractal Design Define 7 Compact | ~$120 |
| CPU | AMD Ryzen 9 9950X (16c/32t, Zen 5, AM5) | ~$520 |
| Motherboard | ASRock B650E Steel Legend WiFi or MSI PRO B850-P WiFi (ATX, AM5) | ~$180–230 |
| RAM | 128 GB DDR5-5600 (4×32 GB, EXPO, CL36–40) | ~$280–320 |
| GPU | NVIDIA RTX 5080 16 GB GDDR7 | ~$999–1,099 |
| OS Drive | 1–2 TB PCIe 4.0 NVMe (Samsung 990 Pro or WD Black SN850X) | ~$90–150 |
| Model Drive | 4 TB PCIe 4.0 NVMe (Seagate FireCuda 530 or Samsung 990 Pro 4TB) | ~$280–350 |
| PSU | 850W 80+ Gold SFX-L or ATX modular | ~$120–150 |
| CPU Cooler | 280mm AIO | ~$80–120 |
| **Total** | | **~$2,700–3,000 (excl. peripherals)** |

### Key Decisions and Rationale

**Why AMD + Linux over Intel + Windows:**
Production ML infrastructure runs overwhelmingly on Linux. CUDA, PyTorch, Kubernetes GPU operators, vLLM — all target Linux first. Building on this stack from day one means every skill transfers directly.

**Why RTX 5080 over 5090:**
The 5080 (16 GB GDDR7) fits in the Define 7 Compact without thermal compromise, draws 250W vs 575W, and handles 34B models comfortably with quantization. The 5090 (32 GB) offers more VRAM headroom but doubles power draw and cost. Upgrade path is a GPU swap — the board, CPU, and RAM all carry forward.

**Why 128 GB system RAM:**
Enables partial CPU offloading of 70B+ models at usable speeds (6–8 tok/s) alongside the GPU. With 16 GB VRAM, large models spill to system RAM — more RAM means less quantization compromise. Fill all four DIMM slots at purchase to avoid a full kit replacement later.

**Why Define 7 Compact over SFF:**
Direct lineage from Monolith's Define R4. Sound dampening, proper ATX PSU support, 360mm GPU clearance, room for 280mm AIO. Sized for a 24/7 inference server, not a gaming burst load. Familiar tooling.

**Why two NVMe drives:**
OS and model storage should be separate. Models are large, frequently swapped, and re-downloaded often. A dedicated 4 TB model drive keeps the OS volume clean and prevents fragmentation from 40 GB files appearing and disappearing. The Define 7 Compact has two M.2 slots plus additional SATA bays.

### Hostname

`data` (reserved) — reflects its role as the production-parity data and ML platform.

---

## Monolith — Pending Hardware

| Item | Priority | Notes |
|---|---|---|
| RAM — 2×16 GB DDR4-3200 | High | Bring to 64 GB. ~2 weeks out. |

> After RAM: hardware freeze. No GPU, no PSU, no case fans. Monolith's role is k3s and household services — AI workloads belong to Lore and Data.

---

## Network — Pending Hardware

| Item | Priority | Notes |
|---|---|---|
| JetStream managed switch | Low | Replaces unmanaged TL-SG1210P — enables per-port SNMP stats in Grafana |
| UPS — CyberPower CP1500PFCLCD | Low | NUT Ansible role is written and tested — waiting on hardware budget |
