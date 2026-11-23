# Experimental TWRP ZIP

A native TWRP `update-binary` installer is implemented for the measured **SM-G980F,
8 GB / 128 GB, bootloader G980FXXSNHYB7** profile. It is tested with independent
file-backed partitions and has **not been run on the phone**. Its manifest remains
`installer_validated: false`. A controlled hardware trial and rescue tests are
required before an end-user release.

## Does it repartition the phone?

**No PIT/GPT changes or partition resizing are required for the current measured
layout.** The installer uses the existing physical partitions:

| Existing partition | Installation use |
|---|---|
| `super` | Writes system APFS at byte 0, at most 4 GiB; saves Android's original 1 MiB partition map in the last 2 MiB (for the restore ZIP); leaves the rest of the tail alone |
| `userdata` | HFSX persistent data; initialized in fresh mode after its 45-second cancel window |
| `recovery` | Full runtime image, replacing TWRP |
| `boot` | Matching Android/Samsung boot head, committed last |

This replaces Android's contents and dynamic-partition metadata in the written
super range; it does not preserve Android or provide dual boot. Reformatting
userdata as HFSX is not the same operation as repartitioning a physical disk.
No EFS/sec_efs, modem, bootloader, DTBO, VBMETA, param or PIT/GPT writer exists in
this backend. An Android stock restore needs the exact stock firmware and may
require wiping data; retaining the table does not itself supply a rollback slot.

## From an Android ROM or from iOS

The same ZIP installs from TWRP whatever the phone runs now:

- **Android ROM (ExtremeROM, UN1CA, LineageOS, stock):** TWRP maps the ROM's
  logical partitions and mounts `/data`. After the Volume Up confirmation the
  installer unmounts exactly the mounts on `super`/`userdata`, removes the
  device-mapper entries stacked only on them (by name, never `remove_all`) and
  checks that nothing holds them any more. A mapping that also uses another disk,
  or a busy mount, stops the install (busy: TWRP *Mount > Disable MTP*). No lazy
  unmounts. Before writing iOS, it saves the ROM's partition map (first 1 MiB of
  `super`, checksummed) at `super - 2 MiB`.
- **Jesvi iOS:** recovery holds the iOS runtime, so first put TWRP back with
  Odin (AP = TWRP tar), boot it, and flash. `choose` mode keeps iOS data.

The ZIP itself must not be on internal storage: microSD, USB-OTG or `adb sideload`.

## Back to Android: Jesvi-iOS-Restore

```sh
./build.sh restore --device x1slte --output dist/restore.zip [--experimental]
# or: ./build.sh release --set OUTPUTS=restore
```

Flash it in TWRP. It refuses a `super` that still holds Android partitions or
holds neither iOS nor an Android map. Otherwise it writes a valid, **empty**
Android partition map at the head of `super` (the copy saved at install time
with its partitions dropped, or the measured stock layout from `android.json`),
reads it back, and zeroes the HFSX headers (first and last MiB) on `userdata`.
BOOT, recovery (TWRP) and every protected partition are untouched. Then, without
rebooting: *Wipe > Format Data* and flash any Android ROM ZIP. UN1CA-based ROM
ZIPs (ExtremeROM too) start their `dynamic_partitions_op_list` with
`remove_all_groups`, but the updater must first load a valid map, which is what
the restore puts back. The encoder is checked byte-for-byte against the S20's real
pre-iOS super head (`JESVI_SUPER_HEAD=... go test`). Running it twice is a no-op.

## Build the ZIP

From an already built/verified candidate:

```sh
# Read-only preflight package: device checks and full image validation, no partition writes.
./build.sh twrp --bundle dist/local-validation \
  --output dist/s20-preflight.zip

# Enable the experimental writer: fresh by default, proceeds after 45 seconds unless cancelled.
./build.sh twrp --bundle dist/local-validation \
  --output dist/s20-experimental.zip --experimental
```

Or build inputs/images/ZIP with one command (no duplicate transport tar):

```sh
./build.sh local --output dist/s20-001 --experimental
```

TWRP is the default local output (`--no-twrp` requests a transport tar).
Without `--experimental`, the ZIP is preflight-only even if selected in TWRP.
Existing output paths are refused. The builder uses a checksum-pinned Go toolchain
(no third-party Go modules), cross-compiles a static Linux/AArch64 executable,
verifies recovery AVB with the reviewed AOSP tool/public test key, packages images
without extracting the large system image to RAM, runs native read-only APFS checks and checks an HFSX seed reconstructed in a
private sparse virtual image (attached read-only, never mounted, then detached),
checks ZIP CRCs, then runs the
same payload validators on the host before publishing the ZIP. Companion files
are `.zip.sha256` and `.zip.build.json` (installer source identity, original
candidate identity, toolchain, archive checksum and qualification state).

The earlier `.tar` transport package remains **unsuitable for Odin/TWRP flashing**.
Use the separate `.zip` produced by this command. These private ZIPs are unsigned;
external trusted checksums do not replace authenticated public release signing.

## Recovery preparation for a controlled trial

An existing iOS-only phone no longer has TWRP in recovery. Temporarily installing
TWRP is itself a separate recovery-partition write and requires the tested rescue
path and explicit device/reboot authorization; this ZIP builder does not do it.

1. Preserve verified **off-device** personal-data/EFS backups, a known-good port
   candidate, exact-device stock firmware and a tested Download Mode/TWRP rescue.
   Backups are prepared separately; the installer does not create or authenticate
   them. Its cancel window does not establish that a backup exists.
2. Use the exact qualified recovery build during testing. Keep the ZIP on a
   microSD/USB-OTG volume or use TWRP sideload. Do not keep its only copy on internal
   `/data`: targets must be unmounted and fresh install destroys userdata.
3. Disable automatic reboot. Unmount userdata and all super-backed filesystems;
   disable MTP if it keeps those volumes busy. Existing device-mapper holders must
   be released using a reviewed exact-recovery procedure. The installer **refuses**
   mounted/held targets; it does not run a generic `dmsetup remove_all`, edit
   metadata or blindly kill processes. The specific recovery's cleanup procedure
   remains a hardware qualification item.
4. Start with the preflight ZIP. It must pass root/TWRP, exact model/product/SoC,
   bootloader/unlock evidence, partition aliases/labels/capacities, mount/holder,
   archive location and battery checks. Missing/ambiguous evidence is a failure;
   record it and fix the profile/backend through review rather than bypassing it.
5. Only in the approved hardware trial, select the experimental ZIP. The UI shows
   the planned data policy and a **45-second cancel window**. Installation, including
   userdata erasure in fresh mode, proceeds automatically when it expires. Volume
   Down/Power cancels; hold Volume Up for three seconds to proceed early. Restore
   still requires an explicit Volume Up hold and cancels on timeout. Read-only
   preflight ZIPs never enter the cancel window or write partitions.
6. Copy `/tmp/jesvi-install.log` and TWRP's log to the host before leaving recovery.
   The installer never requests a reboot. A failed installation is not success;
   preserve the log and use the prepared rescue procedure. Coordinate the shared
   phone and obtain explicit reboot permission before an agent changes its state.

Battery must report at least 50% and temperature within 0–45 °C. Unknown battery,
bootloader or mount evidence is not accepted. The package is about 2.5 GiB; the
specific TWRP build's ZIP/ZIP64 and sideload handling still need a real test.
Signature-verification settings and authenticated distribution also need to be
resolved as part of release qualification; do not label this a signed release.

## Fresh versus update policy

Default `--mode fresh` erases existing userdata, including existing iOS data, after
the 45-second cancel window. Use `--mode update` for a preserving update.

Optional `--mode choose` inspects the existing data header:

- A valid HFSX header with the exact userdata geometry selects **update**. Userdata
  is held read-only/exclusive; keybags and all existing data remain untouched.
- A recognizable but damaged HFS/HFSX header **aborts**. Corruption is not permission
  to format, and it must not silently turn an update into a fresh install.
- A non-HFS data partition selects the **fresh-install cancel window**.

`--mode update` refuses missing/damaged data. `--mode fresh` explicitly selects the
fresh flow and destroys existing data after the cancel window (or an early Volume Up hold). Fresh mode
writes and checks the trusted HFS kit's metadata/data/zero extents, including both
volume headers. It is **not a secure erase of every previous free block**. Normal
boot never formats data and still halts on an unavailable persistent volume.

## Write and reuse behavior

All ZIP image sizes/hashes, Android/Samsung table geometry, APFS windows, recovery
layout and HFS kit CRC/extents/headers are checked before device writes. The binary
is bound to the exact installer configuration digest; all destinations and
capacities are allowlisted again in the device backend.

The backend claims targets exclusively, checks their kernel identities and
mount/holder state again, then proceeds:

1. Verify existing system bytes; skip if its full image-range hash already matches,
   otherwise write, fsync, invalidate cached block pages and verify disk readback.
2. For confirmed fresh install only, initialize and read back HFSX userdata extents.
3. Verify/skip or write/read back the runtime recovery image.
4. Verify/skip or write/read back BOOT last.

BOOT is never intentionally committed after an earlier failure. A non-A/B layout
still has interruption windows and no atomic rollback. A host build-cache hit is
not used as evidence of installed bytes; skips require hashing the device range.
The small boot/recovery images (about 70 MiB combined) are verified and retained
in memory before writing begins, so their final commits do not depend on a live
sideload transport. The multi-GB system image is streamed; none of it is unpacked
to `/tmp` or staged on the data being initialized.

The format-kit CRC, AVB structure checks and host-side public-test-key verification
are integrity/layout checks,
not cryptographic release authentication. Native host APFS and reconstructed
HFSX filesystem checks are now required by the ZIP builder; live filesystem mount
and hardware behavior remain separate tests.
The final boot head/AVB behavior, first-install filesystem mount, repeated cold
boot, preservation of passcode/keychain data, failure interruption and independent
rescue still need hardware acceptance.

## Implementation and host checks

- `tools/recovery/`: standard-library-only native recovery entry point, validation,
  physical-key confirmation, Linux block backend and transaction tests.
- `tools/release/twrp_package.py`: ZIP assembly and host validation.
- `tools/release/go_toolchain.py`: pinned compiler download and isolated caches.
- `bash ci/check-recovery.sh`: file-backed tests, Go vet and static ARM64 cross-build;
  also runs in source CI. It does not connect to a phone.

Sources: [AOSP recovery ZIP layout](https://source.android.com/docs/core/ota/nonab/inside_packages),
[official S20 Exynos TWRP](https://twrp.me/samsung/samsunggalaxys20.html),
[Go downloads/checksums](https://go.dev/dl/),
[Go runtime requirements](https://go.dev/wiki/MinimumRequirements).

For previous iOS candidate restoration and stock Android return, see
[rollback](rollback.md). The [ExtremeROM comparison](extremerom-review.md) records
which source details were used and why S10 repartition steps are not copied.
