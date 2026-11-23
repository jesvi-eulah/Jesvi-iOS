# Flashing, recovery and delivery

For package verification and the user-facing process, read the
[installation guide](install.md).

## Current answer

For a first release, qualify **TWRP for first installation**, **Odin/Download Mode
for bootstrap and rescue**, and **a host helper for input verification, progress,
backups and readback**. A `.sh` file is an interface, not a flashing protocol.
The [experimental TWRP backend](twrp.md) implements this transaction, but is not
yet qualified on hardware; `./build.sh verify|plan` only verifies files and
prints an offline plan. Do not turn the research `x1slte.sh` flash functions into
public one-click instructions without the tests below.

| Method | Good use | Project-specific limitation | Decision |
|---|---|---|---|
| TWRP ZIP / sideload | Root access, partition discovery, streamed writes, user-facing progress | Runtime consumes the recovery partition; final installation replaces TWRP. `/data` is a future raw HFS partition | Preferred first-install environment, pending qualification |
| Odin `.tar` / `.tar.md5` | Samsung Download Mode bootstrap and rescue; familiar on Windows | Tar packaging does not validate model/geometry or manage first-boot formatting. Full raw/sparse `super` behavior needs testing. MD5 is not release authentication | Use for separately validated TWRP/rescue packages initially |
| Host `./build.sh verify|plan` + adb in TWRP | Read-only probe, model checks, external backups, streaming, hashes | Needs a working recovery and cable; Windows needs a native Python/PowerShell wrapper or an explicitly tested environment | Build toward a common host backend; current helper is offline only |
| Heimdall | Open Download Mode transport | Project notes record handshake/session failures and preference for one partition per session | Optional tested rescue alternative, not default multi-partition automation |
| Stock fastboot/fastbootd | Android bootloader/logical-partition workflows where provided | Samsung Download Mode is not generic fastboot. The custom loader implements its own protocol | Never publish `fastboot flash` commands copied from Qualcomm instructions |
| Custom loader updater | Potential fast small updates after installation | Current commands are development tools; recovery holds a live log and kernel/root slots | Later, after protocol/version/readback/interruption qualification |

The official [S20 Exynos TWRP page](https://twrp.me/samsung/samsunggalaxys20.html)
describes Odin installation and dynamic-partition behavior. It does not validate
writing this port's APFS layout. The port overwrites the physical `super` partition;
it is not installing an Android logical `system` image through fastbootd.

## Actual layout and why it matters

```text
Samsung bootloader
  boot: Android v2 boot head, Samsung DT table, shim + UEFI + XNU loader
  recovery:
    head          shim + UEFI + payload / AVB metadata
    16 MiB        runtime log (8 MiB)
    32 MiB        XNU (loader reads at most 16 MiB)
    52 MiB        small root.apfs
    final 64 B    AVB footer
  super + 0       system.apfs (maximum 4 GiB)
  super tail      separate loader log window
  userdata        HFS+ /private/var (whole measured partition)
```

`out/x1slte-embed.img` is not a validated BOOT image: its raw FDT caused recorded
Samsung DT table rejection. The legacy standalone path takes the corrected head
from packed recovery. The new candidate packager computes that head's length from
the Android v2 header instead of copying a fixed offset; **the resulting boot head
still needs device validation**, including sboot/AVB behavior.

The existing AVB footer hashes only the boot head, deliberately excluding mutable
log/kernel/root slots. An AVB footer or valid hash alone does not authenticate the
whole runtime. The package therefore hashes every complete file. Before shipping,
verify the footer with the pinned AOSP avbtool and implement authenticated release
metadata; these are different checks.
[AOSP boot image format](https://source.android.com/docs/core/architecture/bootloader/boot-image-header).

## First-install transaction to implement and qualify

1. **Before touching storage:** identify exactly one device by explicitly selected
   transport; verify model, Exynos SoC, product/board revision, approved bootloader,
   root recovery environment, unlock state and required tools. Match partition
   names and byte capacities from the device, not hardcoded `/dev/block/sdaNN`.
2. **Offline rescue:** retain verified exact-device TWRP and stock firmware on the
   host. Demonstrate Download Mode and a TWRP restore before destructive trials.
   Back up EFS/sec_efs and essential stock partitions to encrypted/private host
   storage; verify hashes and sizes. Never place the only backups on userdata.
3. **Payload validation:** verify signed manifest, exact device/layout, every chunk
   and full-file SHA-256, decompressed length, boot DT table and APFS geometry.
   Check sufficient power and host storage. Reject sparse/compressed images unless
   that exact decoder/write path is implemented and tested.
4. **Destructive scope shown explicitly:** Android in super is replaced; all user
   data will be lost when HFS is initialized; TWRP is replaced. The installer must
   require deliberate confirmation from the actual person installing it.
5. **No mount conflicts:** unmount super logical partitions and userdata, ensure
   device-mapper holders do not retain them. Refuse ambiguous/missing mount evidence.
   A root shell alone is not evidence that partitions are safe to write.
6. **Stream from host/sideload or external storage:** do not stage a multi-GB ZIP
   on the userdata partition that is about to be reformatted. Avoid FAT32's 4 GB
   file limit; use tested USB/SD filesystem or chunked streaming. ZIP64 support in
   the specific recovery must be tested if a monolithic ZIP is offered.
7. **Write and read back system**, then **runtime recovery**, then **BOOT last**.
   Initialize/validate data for an explicitly confirmed fresh install before
   committing BOOT. Writing BOOT last reduces premature entry into an incomplete
   port but is not atomic rollback. Verify complete intended ranges and exact byte counts. Do
   not zero the rest of super: its tail is reserved for loader logs.
8. **Initialize data only on an explicit fresh install.** Normal init now only mounts an existing HFSX volume. An absent/damaged header,
   read failure or failed mount halts persistent-data boot without formatting.
   The experimental offline initializer and its fresh-install cancel window
   are implemented; hardware qualification remains. Updates must preserve userdata.
9. **Only after successful readback:** record the installed version/layout marker,
   save the log on the host, then reboot. Do not reboot on failure or falsely claim
   success. Recovery has already been overwritten, so rescue must remain possible
   through Download Mode independently of the runtime.

No installer may write EFS/sec_efs, modem/radio, bootloader, param/up_param, DTBO,
VBMETA or a PIT/GPT. Any necessary prerequisite for a specific bootloader must be
documented and qualified separately; don't ship generic "disable verification" or
repartition actions as part of an all-device installer.

## Offline tools provided now

After assembling a private candidate:

```sh
./build.sh verify --bundle dist/my-candidate
./build.sh plan --bundle dist/my-candidate --device-report /private/path/device-report.json
```

A tester-supplied report has this shape. This example is not a live device probe
and does not prove unlock state, backups or transport identity:

```json
{
  "model": "SM-G980F",
  "product": "x1s",
  "bootloader": "G980FXXSNHYB7",
  "environment": "twrp",
  "root": true,
  "mounted_targets": [],
  "partitions": {
    "boot": 61865984,
    "recovery": 69009408,
    "super": 9437184000,
    "userdata": 116253523968
  }
}
```

The verifier rejects wrong geometry, altered files, raw FDT, missing AVB footer,
missing/truncated APFS, unknown image destinations and mismatched boot/recovery
heads. HFS kit capacity, extents and CRC are checked before packaging. These are
structural checks; `apfsck`, AVB signature verification, boot tests and authenticated
release manifests remain separate qualification gates. The planner always emits
`executable: false` and lists missing qualifications.

## Updates and rollback

Initial policy: **no OTA promise, no dirty-update promise, no automatic downgrade**.
The current non-A/B layout has no second system slot and writes in place. A
"skip unchanged system" optimization is safe only when the installed image's
identity is independently verified; a file with a familiar name is insufficient.
A cache hit on the build host says nothing about what is currently on the phone.

Test update compatibility of root, system and data schema as a set. Keep previous
project-built inputs/manifests, but do not imply old software can boot newer data.
A failed iOS install may need Download Mode → exact-device TWRP or stock restore.
An Android stock restore overwrites the port and may require a data wipe. Never
relock the bootloader with custom images installed; keep that outside this installer.

## Delivery format

Public release initially: source tag, notices, audited project-built kernel/tools,
release notes, exact model table, known issues and checksums. Public OS/firmware
redistribution is not enabled. Users/developers assemble private images from their
own inputs. `dist/<candidate>` is local-only and explicitly marked private.

If redistribution is later cleared, use a small installer/bootstrap plus an
immutable, authenticated manifest pointing to content-addressed image objects.
Download changed objects only; verify complete compressed and expanded size/hash;
resume downloads, not partially verified writes. Host objects/chunks on an approved
store/CDN, with mirrored signed manifests and retained versions. GitHub release
assets must each be under 2 GiB, so a multi-GB system image needs a different store
or a tested chunk format.
[GitHub release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## Hardware acceptance matrix

Before enabling any writer: pristine supported firmware → first install; wrong
model/SoC/bootloader/capacity rejection before writes; corrupt/truncated image;
low host space; multiple devices; mounted target; USB disconnect during each
stage; recovery write failure; BOOT failure; power loss; successful Download Mode
rescue; existing HFS data; corrupt HFS; same-version reinstall; update; downgrade
refusal; cold boot; charging; storage integrity; private-data persistence; exact
release feature checklist. Record logs and hashes with the candidate/source commit.
