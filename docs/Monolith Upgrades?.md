# ASRock AB350 Pro4 — Upgrade Summary
**Use case:** k3s Kubernetes lab · Navidrome audio server · LAN fileshare/backup

---

## System Context

| Item | Detail |
|---|---|
| Motherboard | ASRock AB350 Pro4 (AM4, B350 chipset) |
| Current CPU | Ryzen 3 1200 (Summit Ridge / "A10" — Raven Ridge APU) |
| Max RAM | 64GB DDR4 (4 slots) |
| Max RAM speed | DDR4-3200 (native, no OC needed with Zen 3) |
| OS | Ubuntu (headless) |
| Orchestration | k3s |

---

## ⚠️ Critical: BIOS Update Sequence

Before installing any Ryzen 5000 (Vermeer) CPU, you **must** update the BIOS incrementally using your existing CPU. Skipping steps risks a non-booting system or bricked BIOS.

**Required update path:**
```
3.40 → 5.40 → 7.00 → 8.02
```

- Download each version from the [ASRock AB350 Pro4 BIOS page](https://www.asrock.com/mb/AMD/AB350%20Pro4/)
- Do **not** skip intermediate versions — the BIOS chip is small and updates are incremental by design
- Complete all updates with your **current CPU in place**, then swap

> The B350 chipset officially supports up to Matisse (Ryzen 3000). Ryzen 5000 (Vermeer) works on BIOS 8.02 but is community-confirmed, not officially listed by ASRock for this board.

---

## Planned Upgrade: Ryzen 5 5600G + 64GB DDR4

### CPU: AMD Ryzen 5 5600G
| Spec            | Value                                  |
| --------------- | -------------------------------------- |
| Architecture    | Zen 3 (Cezanne)                        |
| Cores / Threads | 6c / 12t                               |
| Base / Boost    | 3.9 GHz / 4.4 GHz                      |
| TDP             | 65W                                    |
| iGPU            | Radeon Vega 7 (no discrete GPU needed) |
|                 |                                        |


---

## RAM: 64GB DDR4-3200 CL16

**Configuration:** 4×16GB across all 4 slots (preferred over 2×32GB)

**Kits:**
- G.Skill RipjawsV 4×16GB DDR4-3200 CL16
- Kingston Fury Beast 4×16GB DDR4-3200 CL16 
- Corsair Vengeance LPX 4×16GB DDR4-3200 CL16 

> **Note:** DDR4-3200 is the official rated speed for Zen 3 on this board. No XMP/overclocking needed — it just works at spec.

---

## Workload Fit Assessment

| Workload                       | CPU demand           | RAM demand | Notes                                           |
| ------------------------------ | -------------------- | ---------- | ----------------------------------------------- |
| k3s base overhead              | Low                  | ~1–2GB     | k3s is much lighter than full k8s               |
| Navidrome                      | Very low             | ~256MB     | Basically idle                                  |
| LAN fileshare/backup (3 users) | Very low (I/O bound) | Low        | Network and disk are the bottleneck, not CPU    |
| Python coursework              | Low–Medium           | Low        | Bursts during script runs                       |
| Front-end dev (upcoming)       | Low                  | Low        | Node/npm dev servers are light                  |
| Back-end + DB (upcoming)       | Medium               | Medium     | Multiple containers — where 64GB earns its keep |
| Small ML school projects       | Medium (bursts)      | Medium     | CPU inference only; no GPU compute needed       |
|                                |                      |            |                                                 |

---

## Quick Checklist

- [ ] Download BIOS versions 3.40, 5.40, 7.00, and 8.02 from ASRock before ordering CPU
- [ ] Update BIOS incrementally with current CPU installed
- [ ] Order CPU + RAM kit
- [ ] Set iGPU VRAM to 512MB in BIOS after install (Option 1 only)
- [ ] Verify DDR4-3200 is detected correctly in BIOS (should be automatic with Zen 3)
- [ ] Enjoy the upgrade
