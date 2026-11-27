# Jesvi iOS 16.5

Jesvi iOS runs iOS 16.5 (20F66) on the Exynos 990 **Galaxy S20 LTE** x1slte and includes a development port for other **Galaxy S20 Series Devieces** with the exynos 990 SoC. The project builds the XNU 8796.121.2 kernel, UEFI loader, drivers and device services. The iOS system image comes from Apple's iPhone X firmware.

[![Latest Release](https://img.shields.io/github/v/release/jesvi-eulah/Jesvi-iOS?label=Download&style=flat-square&logo=github&color=brightgreen)](https://github.com/jesvi-eulah/Jesvi-iOS/releases/latest)
![Model](https://img.shields.io/badge/Model-SM--G980F%20%7C%20x1slte-555555?style=flat-square)
![iOS](https://img.shields.io/badge/iOS-16.5-007AFF?style=flat-square&logo=apple&logoColor=white)
![Status](https://img.shields.io/badge/Status-Beta-orange?style=flat-square)
[![Telegram](https://img.shields.io/badge/Telegram-@eulah__rom-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://t.me/eulah_rom)

[![Jesvi iOS running on a Galaxy S20. Watch the demo on YouTube.](docs/IMG_5690%202.jpg)](https://www.youtube.com/watch?v=-4pcSUe0ny0)

## Feature status

The following features are reported for the **S20 LTE**.

| Area | Status on S20 LTE |
|---|---|
| Display | QHD/FHD+ @ 60/120 Hz,  True Tone, auto-brightness and AOD |
| Graphics | Metal acceleration on Mali-G77 and OpenGL ES through Mesa |
| Cellular | LTE data, VoLTE calls and carrier SMS |
| Connectivity | Dual-band Wi-Fi, Bluetooth, BL-Audio and Hotspot, USB |
| Cameras | Front and all three rear cameras |
| Audio | Speaker, earpiece and microphone |
| Sensors | Motion, Gyro, compass, proximity, ambient light, GPS, haptics and flashlight |
| Power | USB PD charging and thermal management |
| Storage | Persistent Full Speed UFS storage and exFAT microSD in Files, Max-Ram |
| USB | USB networking, serial console and Finder file access |
| Security | Passcode and Touch ID enrolment (Fingerprint matching incomplete, shitty driver by samsung). Apple ID setup works but currently requires a companion Hackintosh. |

App Store downloads wont work due to apple's Fairplay-DRM check, iMessage and FaceTime remain unavailable. Others bugs & stutters..

[Device configuration](devices/exynos990/x1slte/device.conf) · [Development log](docs/SHIPPING.md)

## [Download and install](https://github.com/jesvi-eulah/Jesvi-iOS/releases/latest)

1. Match the **model number** in the [device list](#tested-devices) to the target in the ZIP name. Get the package.
 For a development build, extract the artifact from a successful [TWRP workflow run](https://github.com/jesvi-eulah/Jesvi-iOS/actions/workflows/private-images.yml).
2. Choose the procedure for your phone below. **Fresh install erases existing Android or iOS userdata.** Write-enabled installers built from current main start after a 10-second cancel window when launched from TWRP's Install screen. Press Volume Down or Power during that window to cancel & **Volume Up to continue**.

Use TWRP 3.7.1 or newer. With the phone connected directly to your computer, run one of the following commands, substituting the actual path to the verified ZIP. A preserving update requires an existing iOS data volume of the matching size.

```sh
# First install or deliberate erase
tools/install/twrp-install.sh --erase /path/to/fresh_x1s.zip

# Preserve an existing installation
tools/install/twrp-install.sh /path/to/update_x1s.zip
```

The computer helper asks for approval before copying an install ZIP.

**Back to Android:** Use the Restore ZIP for your device. It checks the phone, then waits for a **Volume Up** press before erasing iOS data. Press **Volume Down** or **Power**, or let the prompt time out, to stop after the checks. The Restore code is shared across devices, and each ZIP contains the partition layout for its own target. [Install guide](docs/release/install.md) · [Rollback guide](docs/release/rollback.md)

## Build

For the default S20 LTE target on a prepared macOS checkout:

```sh
make doctor    # Check tools and inputs
make check     # Run source checks and host tests
make kernel    # Build the x1slte kernel
make release   # Package the outputs selected in release.conf
```

The checked-in configuration selects fresh mode, a 64 GB iOS data volume and read-only packages. To build a writable S20 LTE installer, run:

```sh
./build.sh release --set TARGETS=x1slte --set MODE=fresh --set WRITES=true --set OUTPUTS=twrp
```

## Repository layout

| Path | Contents |
|---|---|
| [`xnu/`](xnu) | Kernel patches and board drivers for Apple's XNU 8796.121.2 |
| [`xnuloader/`](xnuloader) | UEFI loader that starts XNU |
| [`userland/`](userland) and [`sysimage/`](sysimage) | Native services, injected libraries, first-boot defaults, and system-image assembly |
| [`devices/`](devices) | Shared Exynos 990 settings and per-device profiles |
| [`tools/`](tools) | Install, release, camera, cellular, Touch ID, and S20+ build tools |
| [`docs/`](docs) | Install and build guides, device evidence, and development notes |
| [`build.sh`](build.sh), [`Makefile`](Makefile), and [`x1slte.sh`](x1slte.sh) | Build entry points and the S20 LTE developer flash loop |

## Tested devices

### x1s · Galaxy S20

- **SM-G980F** (LTE, `x1slte`) — **Tested | Fully Stable**
- **SM-G981B** (5G, `x1s`) — **Untested.** 

### y2s · Galaxy S20+

- **SM-G985F** (LTE, `y2slte`) — **Tested** 
- **SM-G986B** (5G, `y2s`) — **Tested.**

Larger storage models (256/512 GB) install too: iOS uses the first 116 GB of userdata for now and the rest stays unused.

### z3s · Galaxy S20 Ultra

- **SM-G988B** (5G, `z3slte`) — **Tested**


**Own another Exynos 990 phone** (Note20, Note20 Ultra, S20 FE, S20 5G)? The shared base does most of the work: see [Adding another Exynos 990 phone](docs/porting/new-device.md). It is 98% compatible, if you do get it booted or working, create a merge request and get it into the repository.

## Credits and licenses

[Jesvi Jonathan](https://jesvi.net) for Jesvi-iOS for the S20 series. 
[Android-Artisan](https://github.com/Android-Artisan) for her contribution in y2s port.
The project builds on [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel), Apple's open-source XNU (APSL 2.0), Mu-Silicium and Mesa. 

The project is AI friendly & do feel free to contribute & use for further developement, <br>Please credit Jesvi iOS and its contributors when building on this work. 

This project (Jesvi iOS) is independent of Apple and Samsung. 

[Notices](NOTICE) · [Third-party licenses](docs/legal/THIRD_PARTY_LICENSES.md) · [Legal information](docs/legal/LEGAL.md)
