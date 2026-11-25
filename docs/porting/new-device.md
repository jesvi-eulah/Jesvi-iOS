# Adding another Exynos 990 phone

Jesvi iOS is one **common base** plus a small folder per phone. If you own a phone that is
not supported yet, you only add what is unique to it.

| Layer | Where | Who changes it |
|---|---|---|
| Kernel (XNU + Exynos 990 drivers) | `xnu-src/`, `xnu/` | shared, every phone |
| Platform settings + boot-args | `devices/exynos990/platform.conf` | shared, every phone |
| Stock boot device tree | pinned in `platform.conf`, fetched by `tools/devices/fetch-boot-dtb.sh` | shared, every phone |
| Platform mods / optional mods | `devices/exynos990/patches/`, `devices/exynos990/mods/` | shared |
| Userland, release tooling, TWRP/Restore ZIPs | `userland/`, `tools/release/`, `build.sh` | shared |
| **The phone** | `devices/exynos990/<codename>/` | **you** |

## Phones

| Codename | Phone | Status |
|---|---|---|
| x1slte | Galaxy S20 (SM-G980F) | validated, daily driver |
| y2s | Galaxy S20+ 5G (SM-G986B) | development, boot-tested, CI builds |
| x1s | Galaxy S20 5G (SM-G981B) | unmaintained, inherits x1slte |
| y2slte | Galaxy S20+ (SM-G985F) | unmaintained, inherits y2s |
| z3s | Galaxy S20 Ultra (SM-G988B) | unmaintained |
| c1s | Galaxy Note20 (SM-N980F/N981B) | unmaintained |
| c2s | Galaxy Note20 Ultra (SM-N985F/N986B) | unmaintained |
| r8s | Galaxy S20 FE (SM-G780F) | unmaintained |

`python3 tools/release/targets.py` prints the live list.

## No firmware hunting for the boot tree

The device tree inside the stock `boot.img` is the generic Exynos 990 tree. It is byte-identical
on the S20, S20+ and S20 Ultra (SHA-256 `ffcad4d6…`). Model-specific hardware sits in `dtbo`,
which Jesvi iOS never uses. So every phone shares one pinned copy: no Samsung firmware
download and no IMEI. If your phone's stock boot tree turns out different, extract it with
`tools/y2s/stock-info.py boot-trees <boot.img> <dir>` and open an issue with its SHA-256.

## Steps

1. **Create the folder:** `tools/devices/new-device.sh <codename> <model> "<name>"`. If your phone
   already has a folder (x1s, z3s, c1s, c2s, r8s), skip this.
2. **Measure your phone** while it still runs Android, and fill in `target.conf`: RAM, storage,
   panel, touch, modem, Wi-Fi chip. Set `TARGET_INHERIT` to the closest working phone
   (`x1slte` for S20-like boards, `y2s` for the 5G S20+). Write down where each fact came from.
   Never post IMEI, serials or EFS.
3. **Partitions:** record the partition sizes and layout in `device.json` from your phone's PIT /
   by-name map (see `docs/release/device-evidence-y2s.md` for a worked example). The installer
   refuses to write until `installer_validated` is true.
4. **Boot-args:** add only what differs from the platform to `TARGET_BOOTARGS` (touch controller,
   haptics, sensor hub, Wi-Fi). Turn off mods that break your phone with `TARGET_DISABLE_MODS`.
5. **Build:** `./build.sh release --dry-run --set TARGETS=<codename>`, then a preflight
   (`WRITES=false`) ZIP. Flash only after the preflight passes on your phone.
6. **Report:** open a PR with your folder and evidence. Status goes `unmaintained` →
   `development` (boots) → `validated` (installer proven, daily use). Add yourself to
   `maintainers` in `device.json`.

Never touch EFS, modem, bootloader or param partitions (`PLATFORM_PROTECTED_PARTITIONS`).
