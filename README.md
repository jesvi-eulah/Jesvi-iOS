# Jesvi iOS

iOS 16.5 running natively on the **Samsung Galaxy S20 (SM-G980F, Exynos 990)**. The XNU kernel,
loader, drivers and user-space glue are built from this tree; the iOS system files come from an IPSW
you download yourself. Built on [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel) and laid out
the same way: a common tree, plus one directory per device.

> Experimental. It replaces Android on the phone. Read [Install](docs/release/install.md) and
> [Rollback](docs/release/rollback.md) before you start.

## Device support

| Build | Measured hardware | Installation |
|---|---|---|
| x1slte | Galaxy S20 LTE, SM-G980F | TWRP fresh install or explicit update |
| y2s | Galaxy S20+ 5G, SM-G986B | Development port. Fresh TWRP install only. Use the loader for subsequent updates. [Board evidence](docs/release/device-evidence-y2s.md) · [Build and update guide](tools/y2s/README.md) |

Other G980 and G986 regional variants can try the corresponding build when the model and firmware agree, the SoC is Exynos 990, and the partition sizes match. Recovery warns about untested combinations. The G985 S20+ LTE has no measured board profile here.

## What works on the S20

| | |
|---|---|
| Display | FHD+ up to 120 Hz (real ProMotion), auto-brightness, Always-On Display |
| Graphics | Metal on the Mali-G77; OpenGL ES games through Mesa |
| Cellular | 4G data, VoLTE calls both ways, SMS in Messages |
| Cameras | front + three rear lenses by zoom, photo and video with sound |
| Connectivity | Wi-Fi 2.4/5 GHz, Bluetooth audio, USB networking, Finder file access |
| System | touch, buttons, vibration, charging, sensors and compass, passcode, persistent data, thermal control |
| Not yet | fingerprint, full GPS, App Store purchases |

The full status per part is in [`devices/exynos990/x1slte/device.conf`](devices/exynos990/x1slte/device.conf),
and every change is logged in [SHIPPING.md](docs/SHIPPING.md).

## Install

Everything is in the **[install guide](docs/release/install.md)**: before you start, then

- **A. From Android** (ExtremeROM, UN1CA, stock...): TWRP 3.7.1+, then the install ZIP from microSD/USB-C or with
  `tools/install/twrp-install.sh` from a computer; the write-enabled installer proceeds after 45 seconds unless cancelled.
- **B. Update** an x1slte already on Jesvi iOS (use an explicit update ZIP to keep data): `tools/install/twrp-install.sh <zip>` in TWRP.
  Tested on the phone 2026-11-18.
- **C. Back to Android:** Odin TWRP, the restore ZIP, *Format Data*, flash any ROM. Nothing is repartitioned.
- **D. If something goes wrong**, and troubleshooting.

## Build

On macOS, with your own iOS 16.5 IPSW and the phone's firmware:

```sh
make doctor          # what this Mac is still missing
make check           # source checks and tests (what CI runs)
make kernel          # the kernel        -> out/kernel/mach.x1slte
make release         # TWRP + restore ZIPs -> dist/release/
```

`./build.sh --help` lists every command; settings live in [`release.conf`](release.conf).
Guides: [building](docs/release/building.md), [one-command local build](docs/release/local-build.md),
[CI and releases](docs/release/operations.md).

## Layout

| Path | What |
|---|---|
| `build.sh`, `Makefile`, `release.conf` | the entry points and release settings |
| `devices/` | `manifest.conf`; `exynos990/` = SoC layer (`soc.conf`) and one directory per phone (`x1slte/`: `device.conf`, boot line, partition profile) |
| `xnu/` | the kernel: patch against Apple's `xnu-8796.121.2` plus our own files (`xnu/files/`) |
| `xnuloader/` | the UEFI loader that starts XNU |
| `userland/` | the system image: daemons, injected libraries, boot jobs, defaults |
| `prebuilt/` | binaries the image takes when they are not rebuilt |
| `tools/` | per-subsystem tools (`camera/`, `cellular/`, `recovery/`, `release/`, ...) |
| `x1slte.sh` | the S20 developer loop: payload, pack, flash over USB |
| `docs/` | `release/` install and build, `devices/x1slte/` per-feature notes, `dev/` and `research/` |
| `ci/`, `.github/` | checks and workflows |

## More devices

The Exynos 990 layer is shared, so the S20 Ultra (`z3s`) and Note20 (`c1s`/`c2s`) can be
added as directories next to `x1slte`. See [porting](docs/release/porting.md).

## Credits and licenses

[Android-Artisan](https://github.com/Android-Artisan) contributed the S20+ 5G port, stock partition measurements, loader updates and build tools in [PR #7](https://github.com/jesvi-eulah/Jesvi-iOS/pull/7).

HakiOS (oosexgang), Apple's open-source XNU (APSL 2.0), Mu-Silicium, Mesa and the other components
in [NOTICE](NOTICE) and [THIRD_PARTY_LICENSES.md](docs/legal/THIRD_PARTY_LICENSES.md). Nothing of Apple's or
Samsung's is in this repository: the build takes it from your own IPSW and phone. Jesvi iOS is not
affiliated with Apple or Samsung. [LEGAL.md](docs/legal/LEGAL.md).
