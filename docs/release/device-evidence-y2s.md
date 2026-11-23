# SM-G986B measured evidence (y2s bring-up)

Status: **board measured; development images boot on the owner's phone; installer
unqualified**. This is the evidence record for the `y2s` development target
(Galaxy S20+ 5G, SM-G986B). Nothing here is an installer qualification.

Stock Samsung firmware and the stock PIT are authoritative for every offset and
image geometry value. The phone used for the measurements runs a ported S24+
ROM, so its `boot.img`, `dtbo.img`, `lpdump` layout and by-name map are useful
cross-checks only. Do not feed ROM-derived offsets into `android.json`,
`device.json`, `target.conf`, xnuloader, or the flash plan.

Measurements were taken on 2026-11-22 with `tools/y2s/probe.sh` (read-only root
shell), `lpdump`, `/proc/device-tree`, and the extracted stock firmware. Private
dumps and logs stay under `inputs/y2s/` and `out/y2s/` (gitignored); only
sanitized measurements belong in this document.

## Identity

| Field | Observation | Source |
|---|---|---|
| Hardware model | `SM-G986B` | `ro.product.vendor.model`, `ro.product.odm.model`, `androidboot.em.model` |
| Board / device | `y2s`, DT `Samsung Y2S EUR OPEN 21 based on EXYNOS990` | `ro.product.vendor.device`, `/proc/device-tree/model` |
| DT compatible | `samsung,armv8samsung,exynos990` | `/proc/device-tree/compatible` |
| SoC | Exynos 990 (`universal990`, `exynos990`) | `ro.board.platform`, `ro.hardware` |
| Bootloader | `G986BXXSNHYB1` | `ro.boot.bootloader` |
| Board revision | 22 | `ro.boot.revision` |
| CSC / carrier | `EUX`, `XSG` | `sales_code`, `androidboot.carrierid` |
| Running ROM | ported S24+ image: `SM-S926B`, `S926BXXSHDZI1`, Android 16 (`BP4A.251205.006`); its `ro.product.model` is spoofed | probe report |
| ROM kernel | `Linux 4.19.325-cip119-st3-ArtisanKRNL-v4.0.1` (custom) | `/proc/version` |
| AVB | `androidboot.verifiedbootstate=orange`; `vbmeta` and `vbmeta_samsung` present | cmdline, partition map |

Do not put `SM-S926B` or `S926BXXSHDZI1` in the y2s allowlist. They belong to
the donor ROM. The measured model is `SM-G986B`. Recovery warns on other matching G986 model/firmware combinations and checks the Exynos SoC and partition sizes;
`SM-G985F` (LTE S20+) and `z3s` remain separate, unmeasured targets.

## Boot chain, memory and reservations

| Field | Observation | Source |
|---|---|---|
| Framebuffer / Display Reserved | `0xF1000000` (`s3cfb.bootloaderfb=0xf1000000`) | kernel cmdline |
| Panel ID | `8458500` (`lcdtype`, `mcd-panel.boot_panel_id`) | kernel cmdline |
| DTBO index | 7 (`androidboot.dtbo_idx=7`) | kernel cmdline |
| Loader payload window | `0xE8100000` + `0x80000` in xnuloader (`FD_BASE + 0x100000`) | `xnuloader/loader.c` |
| GIC | GICv2: distributor `0x10101000`, CPU IF `0x10102000` | `xnuloader/loader.c` |
| CPU topology | 4× A55, 2× A76, 2× M5 (loader MPIDRs) | `xnuloader/loader.c` |
| RAM | 12 GB: `ddr_size=12`, `dram_info=...12G`, MemTotal 11,155,868 kB. Ignore `corememsize=8G` (stale ROM arg). | cmdline, `/proc/meminfo` |
| Low memory banks | `0x80000000`+`0x3AB00000`, `0xC1200000`+`0x1EE00000`, `0xE1900000`+`0x1E700000` | DT `memory@*` |
| High memory banks | 20 banks `0x880000000` … `0xAE0000000`, each `0x20000000`; total 11.875 GiB | DT `memory@*` |
| `el2_earlymem` | `0xAFE800000` + `0x1800000` (24 MiB) | DT reserved-memory |
| `abox_rmem` | `0xF8000000` + `0x2A00000` (42 MiB, below 4 GiB) | DT reserved-memory |
| `cp_rmem` | `0xF0000000` + `0x800000` (8 MiB) | DT reserved-memory |
| `cp_rmem_2` | `0xD0000000` + `0x4000000` (64 MiB) | DT reserved-memory |

The 12 GB QSPR/LPDDR layout and the 8 MB `cp_rmem` at `0xF0000000` are the
concrete reasons the x1slte (8 GB) memory map cannot be copied unchanged. The
legacy 16 MB `PAYLOAD_BASE=0xF0000000` is not used by y2s.

## Storage geometry

Partition sizes are from the stock PIT and live block devices. The LP extents
and super tail are from stock `super.img`; the running ROM's `lpdump` is a
cross-check only.

| Field | Value |
|---|---:|
| `boot` | 61,865,984 bytes |
| `recovery` | 69,009,408 bytes |
| `dtbo` | 8,388,608 bytes |
| `vbmeta` | 65,536 bytes (`vbmeta_samsung` also present) |
| `super` | 9,437,184,000 bytes |
| `userdata` | 116,253,523,968 bytes |
| UFS sector size | 4096 logical and physical; LP metadata counts 512-byte sectors |
| `super` group | `group_basic`, max 9,432,989,696 bytes |

Stock `super.img` LP extents, in bytes from the start of `super`:

| Partition | Start | End |
|---|---:|---:|
| `system` | `0x100000` | `0x174194000` |
| `vendor` | `0x174200000` | `0x1cb4a1000` |
| `product` | `0x1cb500000` | `0x216a77000` |
| `odm` | `0x216b00000` | `0x216f26000` |

The last logical partition ends at `0x216f26000`; the 1 MiB-aligned free tail
starts at **`0x217000000`** and leaves 440 MiB before the end of `super`. This
is the value used for `SUPER_TAIL_START`. The ROM's `0x1EA584000`, x1slte's
`0x1E8B04000` and the legacy `0x184B00000` are all inside stock logical
partitions and must not be reused.

The iOS root is staged into `super[0..0x174200000)` (the stock system extent
rounded to the next 1 MiB boundary). This is a development image window, not an
installer profile.

## Board parts

The DTBO evidence below is from stock DTBO index 7, whose compatible string is
`samsung,Y2S EUR OPEN 21` / `samsung,EXYNOS990` (`dtbo-hw_rev=0x15`). It matches
the phone's active overlay on the listed points.

| Field | Observation |
|---|---|
| Panel | `s6e3hab_hubble2_a3_s0_default_osc_96_5m_rev03`; ID `0x811104` / decimal `8458500`; 1440×3200@60 plus 1080×2400 and 720×1600 modes |
| Backlight | `/sys/class/backlight/panel`, max 48600 |
| Touch | `sec_ts` at I²C bus 7, address `0x48`; firmware `tsp_sec/y79a_y2.bin` |
| Wi-Fi | Broadcom BCM4375 over PCIe (`133b0000.pcie`), `bcmdhd_sta.bin_b1` |
| Bluetooth | `bcm4375B1_murata.hcd`, `bcm4375B1_semco.hcd` |
| Charger / gauge | MAX77705 charger, fuel gauge and wireless charging |
| Haptic | Cirrus `cs40l25a@40`; `cs40l25a.wmfw`, `cs40l25a_cal.wmfw`, `cs40l20.bin`, `vts.bin` |
| Audio | ABox with `cs35l41_l` / `cs35l41_r` / `vts`; `abox_tplg.bin`, `abox_tplg.conf` |
| Sensor hub | SSP `BCM4773@0` |
| Torch / flash | `s2mpb02` PMIC torch node, `torch-sec1` on `gpp4-4`, flash on `gpp4-0` |
| Cameras | `S5K2LD`, `SAK3J1`, `S5KGW2`, `S5K2LA`, `IMX516`, `IMX518`; nine supported camera IDs |
| Fingerprint | Unclaimed: no module was identified in the runtime or DTBO evidence |

## y2s-specific implementation notes

- The boot line lives in `devices/exynos990/y2s/y2s.cmdline` and is generated
  from `target.conf` by `tools/release/targets.py`; a CI test prevents drift.
  It carries `cam=5 cam_s20=1 cam_s20_y2s=1 island=1`. `cam_s20_y2s` powers the
  CSIS PMU domain and S2MPS22 LDO5S/LDO6S rails that y2s leaves cold at boot,
  then restores them after each session. x1slte does not set this arg.
- The status-bar island fallback and the home-screen layout refresh are gated
  on `cam_s20_y2s`; x1slte's defaults and first-boot behavior are unchanged.
  The shared `softpasscode` mod is disabled for y2s: its `softpasscode=1` boot
  arg hangs SpringBoard on data volumes with no software bag. The boot-tested
  line keeps the board-driver args (`touch_ts`, `haptic`, `shub`, `torch`,
  `wifi_pcie`/`wifi_nvram`) and omits `softpasscode`.
- y2s uses its own sysimage tree with the default debloated selector and its own
  `IconState.plist` overlay. The shared `sysimage/` and `userland/var/` trees
  keep their x1slte contents. The 2.4 GB `system.apfs` fits TWRP's `/tmp`.
- `ACCOUNT_RELAY=0` keeps the inherited account-store relay out of y2s images.
  It pointed at `/var/jb/bin/sh` and private account dylibs that y2s does not
  ship. This removes a boot-time launchd failure; it is not an App Store
  sign-in fix. Full App Store connectivity still needs private FairPlay,
  activation and store components absent from this checkout.
- The first install uses a y2s-only TWRP ZIP pinned to `mode: fresh`; it erases
  Android/iOS data, initializes a clean HFSX userdata volume and flashes
  `super`, `recovery`, `boot` and the power-on logo. It does not delete local
  backups or touch the partition table.
- Updates are flashed **only** from the loader's Log access (USB) fastboot
  server with `./y2s.sh rflash` or `./y2s.sh tflash`. Do not reflash the TWRP
  ZIP over a running iOS install: it is a fresh-install image, not an update.
  There is no Download Mode step in the y2s path.

Generated images, candidate bundles, extracted firmware and logs are local,
ignored artifacts. They are deliberately not listed here because their hashes
change with every development rebuild and some contain private device data.

## Still required before qualification

- Authenticated device report.
- Hardware validation of display, touch, storage, charging, modem and camera
  against the release candidate.
- A recorded installer `EXIT=0` qualification before changing
  `installer_validated` from `false` or promoting `status` beyond `development`.
