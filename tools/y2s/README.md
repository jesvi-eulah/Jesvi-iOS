# y2s board-probe helpers

Tools for bringing up the Exynos 990 Galaxy S20+ (`y2s`, SM-G986B) from a phone
that is still running Android/a custom ROM with a root shell.

## `extract-firmware.sh`

```sh
./tools/y2s/extract-firmware.sh ~/Downloads/SM-G986B_..._fac.zip
./tools/y2s/extract-firmware.sh --with-vendor ~/Downloads/SM-G986B_..._fac.zip
```

Unpacks only the boot-chain pieces (`boot`, `dtbo`, `vbmeta`, `param`, PIT) from
a stock Samsung package into `inputs/y2s/firmware/extracted/`, locally. Use
`--with-vendor` when you need the module firmware/NVRAM files (several GiB).
This is the source for the boot header, DTB/DTBO, and board-part evidence that
cannot be guessed from the shared Exynos 990 code. Use these stock images for
**every offset and image-geometry value**. The ROM dumps gathered by `probe.sh`
are useful cross-checks only, because the donor ROM can repack boot/dtbo and
change logical-partition layout.

## `pit.py` and `stock-info.py`

```sh
python3 tools/y2s/pit.py inputs/y2s/firmware/extracted/images/*.pit
python3 tools/y2s/stock-info.py dtbo inputs/y2s/firmware/extracted/images/dtbo.img
python3 tools/y2s/stock-info.py dtb inputs/y2s/firmware/extracted/images/boot.img
python3 tools/y2s/stock-info.py super inputs/y2s/firmware/extracted/images/super.raw.img
```

`pit.py` prints the physical partition map. `stock-info.py` cuts the board DTB
from the stock `boot.img`, lists the stock DTBO overlays, and derives the stock
`super` LP extents and 1 MiB-aligned free tail. The `super` subcommand takes the
raw (unsparse) image produced by `simg2img super.img super.raw.img`. These are
the authoritative sources for every y2s offset; see
`docs/release/device-evidence-y2s.md` for the derived values.

## `probe.sh`

```sh
adb devices
./tools/y2s/probe.sh                  # writes inputs/y2s/probe-<UTC timestamp>/
Y2S_PROBE_OUT=inputs/y2s/probe-1 ./tools/y2s/probe.sh
```

Requirements: USB debugging authorized, `su` available on the phone. The script
is read-only with respect to the phone's user data. It:

- records model/bootloader/build props, kernel version and kernel command line;
- records `/proc/device-tree` memory nodes, reserved memory, chosen bootargs;
- records exact byte sizes of `boot`, `recovery`, `super`, `userdata`, `dtbo`,
  etc., plus UFS logical/physical sector sizes;
- records display, touch, Wi-Fi, audio, charging, sensor and camera evidence
  from `dmesg` and sysfs;
- copies the small boot-chain partitions (`boot`, `recovery`, `dtbo`, `dtb`,
  `vbmeta*`) into `inputs/y2s/.../dumps/` for offline DTB/DTBH inspection.

It deliberately does **not** record serial numbers, IMEI/IMSI, Wi-Fi MAC
addresses, network configuration, or anything from the Android userdata
partition. `inputs/` is gitignored: dumps and reports are local evidence only,
never release artifacts.

Use the report to fill `docs/release/device-evidence-y2s.md`, then mirror only
stock-verified geometry in `devices/exynos990/y2s/target.conf`,
`devices/exynos990/y2s/device.json`, and `common/devices/y2s.conf`. The ROM
dumps are only cross-checks; do not widen the model/bootloader allowlists to
make a check pass.

## Development build chain (not a release)

The y2s UEFI is built from upstream Mu-Silicium plus the checked-in y2s overlay:

```sh
git clone https://github.com/Project-Silicium/Mu-Silicium.git <work>/Mu-Silicium
cd <work>/Mu-Silicium
git submodule update --init --depth 1
cp -R <checkout>/devices/exynos990/y2s/legacy/uefi-y2s/Platforms/Samsung/y2sPkg Platforms/Samsung/
cp <checkout>/devices/exynos990/y2s/legacy/uefi-y2s/Resources/Configs/y2s.toml Resources/Configs/
cp <checkout>/inputs/y2s/stock-boot-dtb.img Resources/DTBs/y2s.dtb
cp <checkout>/devices/exynos990/y2s/legacy/uefi-y2s/BootManagerLib/XnuLoader.{c,h} \
   Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/
git apply <checkout>/devices/exynos990/y2s/legacy/uefi-y2s/y2s.patch
python3 build_uefi.py -d y2s -r RELEASE
```

Linux is required for the EDK2/NuGet toolchain (the build was done in Ubuntu
24.04 arm64). The outputs are `Build/y2sPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`
and `Mu-y2s.img`; the build recipe and generated artifact hashes are recorded in
`out/y2s/build.json`. They are development artifacts only: y2s's device profile
is `development` with measured stock geometry, but `installer_validated` stays
`false`.

After the GICv2 kernel build, prepare y2s's **own** sysimage tree. The shared
`sysimage/` stays small so x1slte and the release pipeline are untouched;
`sysimage-y2s/` uses the default debloated selector (~3.1 GB extracted, 2.4 GB
`system.apfs`), which fits TWRP's 5.3 GB `/tmp`. It keeps y2s's IconState overlay
and the downloaded root DMG. The old all-apps/all-languages tree is available as
`Y2S_FULL_ROOT=1 ./tools/y2s/fetch-full-root.sh`, but is diagnostic only and is
not used by the installer.

```sh
./tools/y2s/fetch-full-root.sh
```

Then produce the userland images from the checkout root. Use the y2s GPU wrapper
with the camera-enabled x1slte userland profile: plain
`DEVICE=y2s ./userland/build.sh` omits the camera profile and the Mesa/Redwood
GL layer, which gives black wallpaper and stutter. The wrapper already defaults
`IOS_INPUT_DIR=../sysimage-y2s` and `VAR_OVERLAY=var-y2s`; the explicit settings
below are only reminders. `7zz` (or `7z`) must be on `PATH`.

```sh
LDID=${LDID:-ldid} CAMERA_LDID=${CAMERA_LDID:-ldid} \
  OPENH264=${OPENH264:-../third-party/openh264} REST=1 \
  JESVI_TARGET=x1slte IOS_INPUT_DIR=../sysimage-y2s ./userland/build-gpu-y2s.sh
```

The wrapper defaults `ACCOUNT_RELAY=0` for y2s. The inherited x1slte job points
at `/var/jb/bin/sh` and account dylibs that y2s does not ship, so leaving it
installed only made launchd retry a missing interpreter and petrify the job at
every boot. This removes that failure; it does **not** by itself make Apple ID
or App Store sign-in work.

App Store connectivity remains a separate, unresolved problem. Full
connect/sign-in needs FairPlay, an Apple-rooted Secure Enclave/activation
identity and the private Store AMD/anisette stack, none of which are in this
checkout. Do not add a `/var/jb/bin/sh` shim or re-enable the relay as a “fix”:
the relay script still exits on its missing private dylibs, and a `/var/jb`
tweak has already been shown to crash-loop SpringBoard. x1slte's default is
unchanged.

Then run:

```sh
./tools/y2s/build-image.sh
```

It rebuilds `xnuloader/loader.efi` with `GIC_V2=1`, `Y2S_LOG_FLASH=1`, the stock
super tail `0x217000000`, and the stock system/userdata write windows; then it creates an
XNUP payload, splices it into `out/y2s/Mu-y2s.img`, and packs
`out/y2s/y2s-recovery.img` with the full stock DT table
(`inputs/y2s/stock-boot-dtbh.img`, magic `d7b7ab1e`) and an AVB hash footer.
`inputs/y2s/stock-boot-dtb.img` is the inner raw FDT for Mu-Silicium and is not
valid as the Android boot header's DTB section. Nothing here flashes the phone
or qualifies the installer.

Once `userland/system.apfs` exists, assemble a standard private candidate and a
flashable TWRP ZIP. The y2s profile is `development` (measured stock geometry)
but `installer_validated` stays false: no hardware EXIT=0 run has qualified it.

```sh
./build.sh lock-inputs                       # once, when private inputs change
./build.sh package --device y2s --output dist/y2s-fresh-candidate
./build.sh verify --bundle dist/y2s-fresh-candidate
./build.sh twrp --bundle dist/y2s-fresh-candidate \
  --output dist/Jesvi-iOS_0.1.3_YYYYMMDD_y2s.zip --mode fresh --experimental
```

The ZIP is **first install only**. `installer.json` pins `mode: fresh`, so it
erases Android/iOS data, initializes a clean HFSX userdata volume, then flashes
`super`, `recovery`, `boot` and the power-on logo. It never rewrites the
partition table and does not reboot. Push it to TWRP `/tmp` (2.5 GB, under the
5.3 GB tmpfs) and flash with `adb twrp install`. Do not use it for updates.

`tools/y2s/package-candidate.py` remains as a read-only legacy manifest for the
full-root diagnostic image; it is not an installer input.

## Flashing from Log access

`./y2s.sh` is the y2s-only host helper; do not use `x1slte.sh` for this phone.
Power on, hold a volume key to open the JesviOS menu, choose **Log access (USB)**,
and plug the cable into the Mac. The loader's fastboot server writes boot,
recovery and `super` directly; this is the **only** supported update path after
a first install. No TWRP or Download Mode step is needed for updates. The helper
reports each stage/flash/readback with percentages and 16 MiB chunks:

```sh
./y2s.sh rflash        # boot + recovery (root.apfs lives in recovery)
./y2s.sh tflash        # system.apfs, then recovery, then boot
./y2s.sh fresh         # initialize /private/var from userland/hfs-kit.bin, with progress
./y2s.sh ulog          # pull the last iOS log
./y2s.sh uboot         # leave Log access and start iOS
```

Every `oem write` is performed through the loader's DMA-safe scratch buffer and
read back before it replies OKAY. `rflash`/`tflash` refuse a device that does not
report the JesviOS loader (`product: xnuloader`), so an unrelated fastboot device
cannot be flashed by mistake. Neither flashes userdata; only `fresh` deliberately
reinitializes the iOS data volume. Use `rflash` for a runtime/root change and
`tflash` when `system.apfs` changed; never reflash the first-install TWRP ZIP
over an existing iOS install, because it would erase userdata again.

`fresh` uses the same chunked progress: loader 0.6 validates the staged kit with
`oem hfsinfo`, writes 1 MiB at a time with `oem hfsnext`, and the host prints a
percentage after each verified chunk. Set `Y2S_HFSKIT_CHUNK_BLOCKS` to change the
step. The host checks `getvar version` first: an older 0.5 loader treats any
`oem hfskit*` name as a full one-shot write, so `fresh` refuses to run until you
flash the new boot/recovery with `rflash` and **power-cycle back into Log access**.

Camera bring-up uses `cam=5 cam_s20=1 cam_s20_y2s=1`. The last boot arg is
y2s-only: it turns on the CSIS PMU domain and S2MPS22 LDO5S/LDO6S rails that y2s
leaves cold, then restores them after each session. x1slte does not set it.

Keep the board-driver args in `y2s.cmdline` (`touch_ts=1 haptic=5 shub=6 torch=3
wifi_pcie=4 wifi_nvram=1 wifi_pcie_wait=3`). The shared `softpasscode` mod is
disabled for y2s in `target.conf` and by the userland wrapper: y2s has no
software bag on existing data volumes, and `softpasscode=1` hangs SpringBoard
at the Apple logo. x1slte keeps its default.

The x1s-style Dynamic Island is enabled by the `island=1` mod in
`devices/exynos990/y2s/target.conf`; `devices/exynos990/y2s/y2s.cmdline` is the
generated boot line, checked against the target by CI. The loader maps the
device subtype to 2556 and drops the home button. If a status bar cannot read
IOKit early enough, `libredwood`/`libredwood-sb` fall back to the boot arg, but
only when `cam_s20_y2s=1` is also present, so x1slte is unaffected. y2s loader
builds also print the generated `/product artwork-device-subtype` and
`/buttons home-button-type` in the saved log. Only boot/recovery need reflashing.

Safari's app bundle was already in `system.apfs`; the missing piece was a home
screen icon. y2s uses `userland/var-y2s/mobile/Library/SpringBoard/IconState.plist`
instead of changing the shared x1slte layout. The overlay is copied only while
the data volume is first initialized; an existing volume keeps whatever layout
the user already has. Do not force-refresh a live IconState: on y2s the full
widget/folder layout hung SpringBoard at the Apple logo and then a black screen,
so the old `init.c` refresh and its `redwood-app-icons-v3` marker were removed.
A `./y2s.sh rflash` is enough to pick up root changes; `system.apfs` is unchanged.
