> **Step by step for users:** [Install guide, section C "Back to Android"](install.md#c-back-to-android-extremerom-or-any-rom). This page is the background.

# Rollback and returning to Android

There are two different recovery paths. Neither is an undo of erased personal
data, and neither is hardware-qualified for the new installer yet. Prepare the
required firmware/backups and demonstrate Download Mode rescue **before** installing.
The phone and other agents are not accessed by the tools below.

## Return to a previous compatible iOS build

Keep a complete known-good candidate directory with its manifest and checksums,
not just a loose kernel or BOOT image. Use only a previous build explicitly known
to support the current data/keybag format; arbitrary downgrade compatibility is
not inferred from an HFS header. Back up persistent data off-device first.

Wrap that candidate with the current installer in **update-only** mode:

```sh
./build.sh twrp --bundle /private/path/previous-candidate \
  --output dist/ios-rollback-preflight.zip --mode update

# After reviewed compatibility and the controlled hardware-test prerequisites:
./build.sh twrp --bundle /private/path/previous-candidate \
  --output dist/ios-rollback-experimental.zip --mode update --experimental
```

Without `--experimental` this is read-only preflight. Update-only mode refuses
missing/damaged HFSX and never initializes userdata. The installer checks and
restores the candidate's system/recovery/BOOT as a set, skips identical installed
image ranges only after hashing them, verifies written ranges and commits BOOT
last. It does not request reboot or restore keybags from another device.

TWRP is replaced by the runtime during installation. An existing iOS-only phone
may therefore require a separately approved Download Mode/TWRP bootstrap before
using this ZIP. The full candidate and an independent rescue path must remain on
the host. Do not assume a partially failed write leaves the previous OS bootable;
this is an in-place, non-A/B installation with no atomic rollback slot.

## Return to an Android custom ROM (TWRP only)

Flash TWRP with Odin and run the `Jesvi-iOS-Restore_*.zip` for your device.
Restore checks the phone first. Press **Volume Up** within
45 seconds to proceed. Press **Volume Down** or **Power** to cancel.
After Restore completes, use *Format Data* and flash the Android ROM ZIP.
[Restore steps](install.md#c-back-to-android-extremerom-or-any-rom)
No PC firmware download is needed. For stock Samsung firmware use the Odin path below.

## Return to stock Android

Our installer does not resize or rewrite PIT/GPT. It does replace Android logical
metadata and contents at the start of physical `super`, replace BOOT/recovery, and
initialize HFSX userdata on fresh installs. **Restoring BOOT alone cannot undo
those changes.** TWRP's Android Format Data also cannot restore a missing Android
system image.

The intended stock recovery path is:

1. Retain private/off-device backups and the exact model's genuine full stock
   firmware. Confirm the current bootloader revision independently. Use the same
   supported revision or a separately qualified compatible newer one; never force
   a bootloader downgrade or assume returning stock restores Knox state.
2. Use hardware Download Mode and the qualified Odin procedure on a supported host.
   Restore the matching **BL, full AP, CP and CSC** set. AP must restore stock
   boot/recovery and the complete Android super contents/logical metadata. A
   boot-only patched AP or a port's system image is not a full stock restore.
3. Use **CSC**, not **HOME_CSC**, for this cross-filesystem clean restoration.
   Boot the restored stock recovery and perform its factory reset so userdata and
   encryption metadata are recreated for Android. This destroys iOS data/keybags;
   do not promise data preservation across HFSX-to-Android conversion.
4. Verify Android cold boot, filesystem capacity, storage access and required
   radios/features. Preserve logs/backups and keep bootloader relocking outside
   this process. Do not manually enable generic repartition/PIT options or flash a
   borrowed PIT; any actual OEM-table repair must have its own exact-device evidence.

The matching CSC archive may contain a PIT. Its presence is reported, not treated
as proof of its layout or permission for a generic repartition operation. Stock
flashing software behavior, restoring Android metadata, the actual filesystem
reset and successful rescue still need a controlled test. On macOS, do not assume
that an untested Odin port or Heimdall session is equivalent to the tested host.

### Read-only firmware-set inspection

For the initially recorded `G980FXXSNHYB7` revision, inspect your own extracted
firmware set without extracting its images or contacting a phone:

```sh
python3 tools/release/stock_return.py \
  --firmware /private/path/stock-firmware \
  --output out/return-to-stock-plan.json
```

The directory must contain exactly one `BL_`, `AP_`, `CP_` and `CSC_` TAR/TAR.MD5
for SM-G980F. The inspector checks model/revision names, complete AP member names,
archive structure, Odin MD5 trailers where present, whole-file SHA-256 identities,
and embedded PIT names. It rejects HOME_CSC-only sets, boot-only APs, mismatches,
links/traversal and corrupt/truncated archive structure. It does **not** validate
Samsung signatures, compressed image contents or PIT topology, acquire firmware,
run Odin, format a device or prove restore success. JSON says `executable: false`.
The exact-revision restriction avoids guessing Samsung anti-rollback encoding;
other firmware needs review instead of bypassing that check.

## Required qualification before public installation

Record both paths separately: previous compatible iOS candidate restoration with
keybags preserved, and full stock Android restoration with a fresh Android data
filesystem. Include interrupted writes, wrong firmware/model, corrupt data,
recovery replacement and successful independent Download Mode rescue. Keep the
previous installer code/candidate manifests and hardware evidence with the release.

See [TWRP process](twrp.md), [installer acceptance](flashing.md#hardware-acceptance-matrix)
and the [ExtremeROM comparison](extremerom-review.md).
