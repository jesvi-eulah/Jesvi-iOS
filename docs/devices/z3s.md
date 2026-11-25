# Galaxy S20 Ultra (SM-G988B, z3s)

Status: **development, first-boot profile, untested on a phone by this project.**

## What the build is

The S20 Ultra is built on the S20+ (y2s) image path. It boots the same Exynos 990 kernel, the
Mu-y2s UEFI loader and the shared stock boot device tree, with its own board config
(`common/devices/z3s.conf`), boot line (`devices/exynos990/z3s/z3s.cmdline`) and TWRP ZIP
(`Jesvi-iOS_<version>_<date>_fresh_z3s.zip`).

Why this is expected to boot:

| | S20 Ultra | Source |
|---|---|---|
| Boot DTB | byte-identical to S20/S20+ (`ffcad4d6…`) | N1709/z3sios, our backups |
| super / boot / recovery | 9437184000 / 61865984 / 69009408, same as S20+ | ExtremeROM `target/z3s`, installer checks on the phone |
| RAM / memory map | 12 GB, same as S20+ | Samsung specs |
| Panel | s6e3hab family, 1440x3200, like the S20+ | ExtremeROM, z3sios |
| Touch, Wi-Fi, gauge | sec_ts, BCM4375, MAX77705 | z3sios (display, touch, Wi-Fi, GPU worked there) |

## First-boot profile

On: display, touch, GPU/Metal, storage, battery/charging, USB, Wi-Fi, Bluetooth, audio path, CPU/thermal.
Off until confirmed on a z3s: **camera** (108 MP HM1 + periscope need their own profile), **flash**,
**sensor hub** (auto-brightness, rotation), **haptics**.

16 GB RAM models (512 GB storage) use a different memory map and are not covered yet.

## Testing

1. TWRP, unlocked bootloader, Android backed up (fresh install erases userdata).
2. Flash the `z3s` ZIP. It refuses any phone that is not an SM-G988B, or whose boot, recovery or
   super partition differs.
3. Report: does the loader menu appear, does iOS reach the lock screen, what works. Logs: [one command](../release/install.md#sending-logs-freezes-crashes).
   The loader's *Log access (USB)* gives the boot log.
4. Back to Android: flash the `z3s` Restore ZIP, then Format Data and an Android ROM.

To turn a feature on, add its boot argument to `devices/exynos990/z3s/z3s.cmdline` and
`TARGET_BOOTARGS` in `target.conf` (they must match; `ci/check.sh` tests that), then open a PR.
