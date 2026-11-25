# Install, update and remove Jesvi iOS

For the **Galaxy S20 LTE (SM-G980F)** with bootloader **G980FXXSNHYB7**. The installer checks both before it writes
anything; another model or bootloader is refused.

## Before you start

- **Back up** anything you want to keep. Installing over Android wipes the data partition; going back to Android wipes iOS's.
- Battery **at least 10 %**: the installer refuses below that.
- **TWRP 3.7.1 or newer** for the S20. The official TWRP 3.7.0 (2022) is too old for current bootloaders: its USB drops
  out. ExtremeROM's TWRP (unified Exynos 990 build, 3.7.1_12) works.
- For the computer method: `adb` and this repository, and the cable **straight into the computer**. Through a USB hub
  TWRP's connection kept vanishing.
- Get the release files: `Jesvi-iOS_<version>_x1s.zip` (on GitHub in two parts: join them with
  `cat <zip>.part1 <zip>.part2 > <zip>` and check `shasum -a 256 -c <zip>.sha256`) and
  `Jesvi-iOS-Restore_<version>_x1s.zip`.

Booting TWRP on an S20: phone off or in Download Mode, hold **Volume Down + Power** until the screen goes black, then
at once **Volume Up + Power** until TWRP appears.

**From a phone running Jesvi iOS, no buttons:** `tools/install/flash-twrp.sh` (cable in). It sends the phone to
Download Mode, writes TWRP into recovery and lets the phone restart, which then starts TWRP by itself (Jesvi iOS keeps
the "boot into recovery" flag set). Without the script: Odin → AP: TWRP, then let it restart.

**Two ways to confirm an install:**
- **From the computer** (`twrp-install.sh`): you type `yes` there once, before anything is copied (`ERASE` for
  anything that erases data, with `--erase`). Then it runs by itself, with **no key presses on the phone**, shows
  each step on the computer and on TWRP's screen, and restarts the phone into iOS when done (`--no-reboot` to stay).
- **On the phone** (TWRP → *Install*): write-enabled installs proceed after a **10-second cancel window**. Press Volume Up to start straight away. Volume Down or Power cancels. Fresh installs erase existing data.

## A. From Android (ExtremeROM or any ROM) to iOS

1. Boot TWRP.
2. Either
   - **with a computer:** `tools/install/twrp-install.sh --erase Jesvi-iOS_<version>_x1s.zip` and type `ERASE`
     (this erases the phone's data), or
   - **without one:** put the ZIP on a **microSD card or USB-C stick** (never internal storage: it is about to be
     wiped), then TWRP → *Install* → pick the ZIP, and watch the 10-second cancel window. Fresh mode erases existing userdata when the window expires.
3. Before it writes iOS, the installer saves your ROM's partition map at the end of `super` (used by the way back).
4. It also puts iPhone's pictures into Samsung's power-on screens (the Apple logo, the charging and battery-empty
   screens), keeping Samsung's own for the way back.
5. Reboot (the script does it): the Apple logo from power-on, then iOS's first setup.
   After the install TWRP re-reads its Android partitions and may print **"Failed to mount '/system_root'"** and
   similar errors: they are expected (iOS now holds those partitions) and can be ignored.

## B. Update an S20 that already runs Jesvi iOS

Use a ZIP explicitly built with `MODE=update` (or `MODE=choose`) to keep data, apps
and settings. The default `MODE=fresh` ZIP erases them, including on an existing iOS phone.

1. `tools/install/flash-twrp.sh` (iOS lives where TWRP was; this puts TWRP back and boots it, no buttons).
2. `tools/install/twrp-install.sh Jesvi-iOS_<version>_x1s.zip` (cable straight into the computer), type `yes`.
3. It installs, checks every byte and restarts into iOS by itself.

The ZIP's iOS data size must match the phone's: a 64 GB package (`IOS_DATA_GB=64`) refuses a phone whose iOS data
uses all of userdata, and the other way round. It stops before writing anything; use the matching package, or a fresh
install (erases data).

On a phone running iOS, TWRP's own *Install* button and *ADB Sideload* do not work: Install stops before the ZIP runs
("Unable to find partition for path '/system_root'": there is no Android system any more), and Sideload streams
2.6 GB over a connection that can drop. The script copies the ZIP into TWRP's memory, checks it and runs the
installer there, so after the copy the cable no longer matters.

## C. Back to Android (ExtremeROM or any ROM)

Nothing was resized or repartitioned: the same partitions only held iOS's contents. EFS, modem, bootloader and the
partition table were never touched.

1. `tools/install/flash-twrp.sh` (or **Odin → AP: TWRP**: iOS's runtime took recovery's place). Boot TWRP.
2. Run the restore ZIP **with the script** (on an iOS phone TWRP's Install button refuses every ZIP):
   `tools/install/twrp-install.sh Jesvi-iOS-Restore_<version>_x1s.zip`, wait for the checks, then press **Volume Up** on the phone to restore.
   Press Volume Down or Power to cancel, or let the 45-second prompt expire.
   Restore puts the saved Android partition map back into `super` (or Samsung's stock layout if none was saved), clears
   the iOS data headers and puts Samsung's own power-on pictures back. BOOT and recovery are left alone.
3. Without rebooting: TWRP → *Wipe → Format Data* → type `yes`.
4. Flash the ROM ZIP (ExtremeROM etc.) as usual. It rebuilds system/vendor/product inside `super` and writes its own boot.
5. Reboot into Android. From here it is a normal Android phone for any ROM.

## D. If something goes wrong

| You see | Do |
|---|---|
| The installer stopped with a message | Nothing was written unless it said "Writing". Fix what it says (battery, model) and run it again. |
| It stopped after "Writing ..." | Run the same ZIP again: every write is checked by reading it back. |
| The Samsung logo forever, or our loader's menu after an install | Download Mode, Odin → AP: TWRP, boot TWRP, run the install again (B). |
| No TWRP any more and no iOS | Download Mode (Volume Down + Volume Up, plug the cable in), flash TWRP with Odin (AP), then A or C. |
| Want the exact previous state | Keep your own `recovery`/`boot` backups from TWRP (*Backup*) or, on iOS, from the developer tools. |

## Troubleshooting

- **Computer does not see the phone in TWRP:** cable straight into the computer, another port or cable; in TWRP
  *Mount → Enable MTP*; unplug and plug again.
- **"battery must report at least 10 percent":** charge in TWRP and run it again.
- **"physical confirmation timed out"**: run Restore again and press Volume Up within the 45-second confirmation window.
- **"the iOS data here is damaged or a different size than this package":** the package's iOS data size
  (`IOS_DATA_GB`) differs from the phone's; nothing was written. Use the matching package.
- **"unqualified recovery product" or "model/bootloader mismatch":** not an SM-G980F on G980FXXSNHYB7: not supported.
- **The phone runs hot in TWRP:** let it cool; TWRP has none of iOS's thermal control.

## Build it yourself

One command from a fresh Mac: `tools/install/jesvi-ios.sh` (clone, iOS 16.5 from Apple, inputs, check, build,
backup, install). The board inputs are fetched or cut from your own phone by `tools/install/get-inputs.sh`: AOSP's
AVB tool, our UEFI, and Samsung's device tree table from your phone's boot partition (phone in TWRP). Details:
[building](building.md) and [local build](local-build.md).

---

## Background: design and earlier plan

Status: **a local build produces a verified private image package, but this branch
has no qualified install command yet.** The package manifest deliberately says
`installer_validated: false`. `./build.sh verify|plan` supports offline `verify` and `plan` only.
A successful build/cache check does not establish that this exact candidate boots.

An [experimental TWRP ZIP](twrp.md) is now implemented, including a preflight-only
mode and an explicitly enabled writer. It still needs controlled hardware
qualification; the guide below describes the transaction and the older tar archive.

The current measured target is **SM-G980F, Exynos 990, 8 GB / 128 GB**, bootloader
`G980FXXSNHYB7`. The development profile is `x1slte`; recovery may identify its
family as `x1s`. Read [device evidence](device-evidence.md). This is not a general
S20/S20+/Ultra/Note20 installer and does not provide dual boot.

## What you can run now

From the release checkout on a prepared Mac:

```sh
./build.sh local --output dist/s20-001
./build.sh verify --bundle dist/s20-001
```

The retained local validation candidate is at `dist/local-validation/`. The
redundant transport tar was removed during authorized cleanup; its TWRP ZIP is
retained. New local builds generate a TWRP ZIP by default. See [local build](local-build.md) for
one-time inputs, host tools, caching and logs.

Verify a newly built ZIP from its parent directory before any TWRP trial:

```sh
(cd dist && shasum -a 256 -c s20-001.zip.sha256)
./build.sh verify --bundle dist/s20-001
```

Use the checksum received through a trusted channel when distributing packages;
a hash supplied by the same untrusted sender does not authenticate a release.

The archive contains:

| File | Intended use after qualification |
|---|---|
| `boot.img` | Validated Android/Samsung boot head; BOOT written last |
| `recovery.img` | Loader, kernel and small root APFS; replaces TWRP |
| `system.apfs` | iOS system in the measured `super + 0` window |
| `manifest.json` | Exact target, image sizes/hashes and source/input identities |
| `SHA256SUMS` | Full-file checksums |

**Do not select this archive in Odin's AP slot or install it as a TWRP ZIP.** It is
an ordinary transport tar, with no Odin layout or TWRP update-binary. Renaming it
`.tar.md5` or `.zip` does not create an installer. `system.apfs` is not an Android
logical-system image, and generic `fastboot flash system` instructions do not apply.

## Fresh installation from Android: intended transaction

The following is the installation design, **not executable flashing instructions**.
There are deliberately no raw block-write commands until the writer and recovery
path are tested against the actual device.

1. Record exact model, bootloader, board and physical partition geometry. Confirm
   unlock state and the explicitly selected transport/device. Reject mismatches.
2. Prepare exact-device stock firmware and TWRP on the host. Demonstrate Download
   Mode rescue independently of the iOS runtime. Store verified EFS/sec_efs,
   important partition backups and personal-data backups off the phone.
3. Enter the qualified TWRP/root recovery environment. Verify package identity,
   every full-image hash and expected sizes. Confirm adequate power and host space.
4. Show the destructive scope and the 10-second cancel window before fresh installation:
   Android in `super` is replaced, userdata is initialized for HFSX and TWRP is
   overwritten. Keep the package/backup on the host or suitable external storage;
   its only copy must not be on userdata.
5. Unmount all targets and release device-mapper holders. Verify those conditions
   rather than assuming a root recovery shell is sufficient.
6. Write/read back the system range, retaining the separate super log tail.
   Explicitly initialize and validate HFSX userdata **only for fresh install**;
   Android/TWRP's ordinary Format Data is not this project's HFSX initializer.
7. Write/read back the runtime recovery image. Commit BOOT **last**, only after
   system, data initialization and runtime verification succeed. This is an
   in-place layout, not an atomic/A-B transaction.
8. Save the installation record and logs off-device. After successful checks and
   deliberate reboot authorization, boot the candidate and run acceptance tests:
   cold boot, storage/persistence, passcode/relocking, charging/thermals and the
   exact declared feature set. Record a successful rescue test as well.

TeamWin's [official S20 Exynos page](https://twrp.me/samsung/samsunggalaxys20.html)
provides its own Odin/TWRP installation guidance and explains dynamic partitions.
It does **not** qualify this port's physical-super/APFS installation scheme.

No installer in this design changes EFS/sec_efs, modem, bootloader, PIT/GPT,
param/up_param, DTBO or VBMETA. Any actual prerequisite must be separately tested
and documented for the exact device/bootloader. Never relock with custom images.

## Updating the existing iOS phone

Do not repeat the fresh-install data initialization. Preserve userdata, keychains
and saved software passcode bags; updates must never format on a failed read/mount.
This branch's init mounts existing HFSX and halts if persistent data is unavailable.

Before a controlled update, preserve a known-good package, stock/TWRP rescue and
private backups. Compare the installed image identities with the candidate to
choose writes; a build-host cache hit does not identify the bytes on the phone.
Check root/system/data-schema compatibility as a set. A system change requires its
write/readback; a loader/kernel/root change requires the appropriate recovery and
BOOT checks. No OTA, dirty-update or downgrade compatibility is promised yet.

Retain `softpasscode=1`, `autounlock=0`, native keybagd, the guarded pre-launchd
restore and repeat-lock bridge. Do not clear keybags to recover from a failed
update. See [passcode traps and recovery](../devices/x1slte/passcode.md#traps-and-recovery).

The legacy `x1slte.sh` and workspace phone-update tools were used for development.
They can write/reboot, contain historical assumptions and are not a substitute
for the release installer. The current guide does not authorize phone operations;
coordinate the shared phone and explicit reboot permission before any trial.

## What remains before an install command can be published

- Qualify the implemented device probe, readback writer and physical confirmations.
- Qualify offline HFSX initialization; prepare and verify backups separately.
- Verify complete APFS integrity, actual AVB/BOOT behavior and release authenticity.
- Test first install, preserving updates, wrong-target rejection, interrupted
  writes, corrupt data, power loss and independent Download Mode rescue.
- Record hardware acceptance for the exact candidate, then enable the installer
  through a reviewed code change; flipping the profile boolean is insufficient.

See [flashing design](flashing.md), [validation](validation.md) and the
[release checklist](checklist.md). Until these gates close, the package is for
controlled developer qualification rather than an end-user installation release.

[Rollback / return to stock Android](rollback.md) covers the separate recovery
paths. Restoring BOOT alone is not an Android restoration.
