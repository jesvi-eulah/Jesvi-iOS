# Targets: one folder per phone (UN1CA / ExtremeROM style)

Each Exynos 990 phone has its own camera, panel, touch, modem (LTE/5G), Wi-Fi,
sensors, S Pen and so on. The port runs one shared XNU kernel, and every board
driver is selected by **boot-args** (`haptic_chip=cs40l25`, `cam_s20=1`,
`wifi_pcie=4`...). A target is the set of facts, boot-args and mods for one phone.

```
devices/exynos990/
  platform.conf              PLATFORM_*: SoC, XNU/iOS build, shared boot-args   ExtremeROM: platform/exynos990
  patches/<mod>/             mods every 990 phone gets                           platform/exynos990/patches
  mods/<mod>/                optional features (island, softpasscode)            unica/mods
  <target>/target.conf       TARGET_*: identity, display, camera, modem, chips   target/<dev>/config.sh
  <target>/patches/<mod>/    mods only this phone gets                           target/<dev>/patches
  <target>/device.json       measured partitions/layout for the installer
  <target>/android.json      measured stock super layout for Jesvi-iOS-Restore
common/devices/<board>.conf  loader memory map, UEFI, DTB (TARGET_BOARD_CONF)
```

```sh
./build.sh target                          # table of all targets
./build.sh target x1slte                   # merged config (bash-sourceable)
./build.sh target x1slte --format bootline # the boot line the image gets
./build.sh target x1slte --format mods     # mods in application order
```

**Config order:** `platform.conf`, then `TARGET_INHERIT` (e.g. `x1s` inherits
`x1slte` and changes modem/RAM), then the target. Later values win; unknown keys,
`$`, backticks and backslashes are rejected. `TARGET_STATUS` must equal
`device.json`'s status, and a buildable target's models/bootloaders/products/super
size must agree with `device.json`.

**Boot line:** `PLATFORM_BOOTARGS` + words derived from hardware
(`TARGET_HAPTIC_CHIP` → `haptic_chip=`, `TARGET_TORCH_CHIP` → `torch_chip=`,
`TARGET_CAMERA=s20` → `cam_s20=1`) + `TARGET_BOOTARGS` + each active mod's
`bootargs`. A later word replaces an earlier one with the same key. Limit: 550
characters (the S20 uses 539). The S20's generated line equals `x1slte.cmdline`
(test); `x1slte.sh` and day-to-day development still use that file.

**Mods:** a folder with `module.prop` (`id=` folder name, `name=`, `description=`,
optional `targets="c1s c2s"`, `requires="TARGET_HAS_SPEN"`), and any of
`bootargs`, `root/` (copied into root.apfs), `system/` (into system.apfs),
`customize.sh` (bash, run with the merged config plus `STAGE`, `DEST`, `MODPATH`),
`disable`. Order: platform patches → inherited target patches → target patches →
mods, each by name. `release.conf` `MODS_DISABLE="island"` drops optional mods.
`userland/build.sh` applies them when `JESVI_TARGET` is set (release builds).

**LTE and 5G:** ExtremeROM keeps one target per phone and picks the LTE DTBO by
bootloader. Here the S20 LTE (`x1slte`, measured) and S20 5G (`x1s`, inherits it)
are separate because the modem driver and RAM differ; S20+, Note20 and Note20
Ultra use `TARGET_MODEM="auto"` until a phone of each is measured.

**Status today:** `x1slte` and `y2s` have development profiles. See the [S20+ build and update guide](../../tools/y2s/README.md). The others hold public facts (from
ExtremeROM's targets and Samsung specs) and are skipped as `unmaintained`.

## Bringing up a new phone

1. Dump it (by-name sizes, `super` head, getprop, live FDT): `device/dump/*`.
2. `common/new-device.sh <board> <fdt>` → board `.conf` (memory map, GIC, UEFI).
3. Fill `target.conf` (hardware, boot-args for its chips), `device.json`
   (partition bytes, layout), `android.json` (slot 0 of its super metadata).
4. Device-only fixes go into `<target>/patches/<mod>/`.
5. Set `TARGET_STATUS="development"` in both files; `./build.sh target`, tests,
   `./build.sh release --set TARGETS=<target>`.
