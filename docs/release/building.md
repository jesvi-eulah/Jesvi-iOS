# Build Jesvi iOS

## Quick start (macOS)

1. Xcode Command Line Tools, Homebrew, ~25 GB free. `make doctor` lists what is missing.
2. **iOS 16.5 is fetched for you:** the build downloads only the parts it needs of the 20F66 firmware from Apple's
   servers, checks them and caches them. You never handle an IPSW.
3. **What you supply once** (Samsung's and board files cannot be in the repository). `tools/install/get-inputs.sh`
   does all of the `inputs/` rows for you, checked against known hashes (phone in TWRP over USB for the DT table):

   | Input | How |
   |---|---|
   | `fw-wifi`, `fw-sound`, `fw-haptic`, `fw-sensors` | from your own phone on Android or TWRP: `tools/s20-firmware.sh --adb` |
   | `inputs/x1slte/Mu-x1slte.img` | the UEFI: the `x1slte-uefi` artifact of the g980f-uefi repository |
   | `inputs/x1slte/boot-dtb.img` | Samsung's DT table, cut from your phone's `boot` partition (or `JESVI_BOOT_IMG=boot.img`) |
   | `inputs/tools/avbtool.py`, `inputs/tools/testkey_rsa4096.pem` | AOSP `external/avb`, pinned commit `76117860` |
   | `inputs/toolchain.json` | this computer's compiler and the inputs' hashes (written by get-inputs.sh) |

4. `make check`, then `make release` → `dist/release/Jesvi-iOS_<version>_<date>_x1s.zip` and the restore ZIP.
5. Install as in the [install guide](install.md).

Settings are in `release.conf` (`./build.sh release --set KEY=value` for one run). Developer loop on a connected
phone: `./x1slte.sh` (see `docs/devices/x1slte/`).

---

# Building and verifying

## Fresh source checkout

Clone the eventual public `ios-exynos990` repository into an empty directory without
spaces. Do not clone into the research collection root or overlay two Git indexes
into one directory. `common/setup.sh` is a historical two-repository overlay helper;
it is not part of this release workflow.

```sh
./build.sh devices
./build.sh validate
bash ci/check.sh
```

Host checks require Git, Bash and Python 3.9+. No phone or proprietary firmware is
needed. A device marked `unmaintained` deliberately has no usable build adapter.

## Source kernel (macOS)

Install Xcode Command Line Tools. Homebrew is a convenient way to install GNU
utilities: `coreutils gnu-tar gnu-sed findutils bison m4`; an equivalent provisioned
toolchain also works. `common/macos-env.sh` adds Homebrew GNU tool paths when present.

```sh
./build.sh doctor --device x1slte
./build.sh kernel --device x1slte --jobs 4
(cd out/kernel && shasum -a 256 -c SHA256SUMS)
```

This applies `xnu/redwood.patch` and `xnu/files` to pinned XNU in a private
`.cache/release-kernel/<source-key>` tree. It fetches/builds dependencies, uses
`GIC_V2=1`, rebuilds the dependency libraries against the selected headers, requires
successful `make ... build`, strips local symbols and enforces the loader's 16 MiB
limit. It does not call `xnu/export.sh`, use `prebuilt/mach...` or touch a phone.

`out/kernel/build.json` records source commit/dirty state, compiler, dependency lock,
size and hash. The artifact is a **development kernel**, not a BOOT/RECOVERY image.
A cache hit retains the original build provenance, even when a docs-only commit
requests it again. CI artifact names identify the requesting workflow commit.

The iOS SDK Git revision is locked in `ci/sources.lock.json`. This kernel recipe
also fetches dependency commits in `xnu-deps/setup.sh`; the old macOS SDK archive
URL and toolchain packages still need checksum/version tightening before claiming
fully reproducible releases. Native local compilation was tested; the new workflows
have not been run on GitHub yet. Hosted `macos-14` is not the exact local host version.

## Local private image assembly

Do this in a **dedicated, isolated checkout**. Never symlink `rootfs`/`cryptex` into
another agent's extraction: the legacy image builder rearranges files. Do not
borrow live `fw-*`, `jb`, SSH material or active build directories. The wrapper
refuses top-level shared input links, symlinks inside firmware/tool inputs, and personal network/SSH inputs.

Required inputs include:

| Local path | Contents/provenance |
|---|---|
| `sysimage/` | Own selected iOS 16.5 / 20F66 extraction, manifest, var skeleton and dyld parts; the existing `sysimage/fetch.sh` is the fetch/extract recipe |
| `inputs/x1slte/Mu-x1slte.img` | UEFI for the exact measured board, pinned wrapper/Mu source revisions and verified hash |
| `inputs/x1slte/boot-dtb.img` | Samsung DT table extracted from the target's stock boot image, not a raw FDT |
| `inputs/tools/avbtool.py` | Pinned AOSP AVB tool from a reviewed source |
| `inputs/tools/testkey_rsa4096.pem` | AOSP's public test key used by the existing packer; not a secret production signing key |
| `inputs/toolchain.json` | Builder-maintained tool versions/source identities/hashes, including UEFI overlay and firmware provenance |
| `fw-*` | Own exact-device firmware; no `fw-wifi/network` or other personal credentials |
| `jb/` (optional) | Reviewed package/bootstrap inputs, locked locally; never a personal installed-device snapshot |
| `userland/hfs-kit.bin` | Generated HFS kit for **116253523968 bytes**, verified against the profile |

The HFS kit can be generated on a compatible macOS host with
`tools/mk-var-hfs.sh 116253523968`. This uses a host sparse image and temporary loop
attachment; it is not a phone formatter. Review the command/environment first and
never pass a phone block device. The existing script uses macOS ASIF/diskutil APIs,
so the private builder's OS version must support them or supply an already qualified
kit. The hosted kernel job does not need ASIF.

```sh
./build.sh doctor --device x1slte --images
./build.sh lock-inputs
HACKIOS_IMAGE_CACHE=/private/build-cache/system \
  ./build.sh images --device x1slte --development
./build.sh package --output dist/rc1-private
./build.sh verify --bundle dist/rc1-private
```

`lock-inputs` hashes the actual local files; it does not grant redistribution rights
or prove their origin. Review origins/hashes independently. It is local-only and
must be regenerated deliberately after input changes. `SHARE=1` is set for image
assembly, but this is not a guarantee that arbitrary firmware/bootstrap input trees
are sanitized. Never copy personal device trees wholesale.

The image adapter invokes the existing GPU/userland builder and x1slte embed,
payload and pack stages. It never invokes flash, ship, standalone or reboot. It
builds a fresh source kernel first. Full private assembly has not been tested in
this worktree because the audited private input snapshot has not been provisioned.
The legacy userland build can use prebuilts and optional components: do not call
this a qualified all-source release until every required binary and firmware input
has a manifest/provenance entry and a clean build has been demonstrated.

The newer calls recipe can extract a missing `callservicesd` into rootfs. Prepare
that extraction and the matching call-provider/tweak inputs **before** creating the
private input lock. If a build changes locked inputs, the final verification fails
instead of silently retaining a candidate from a different snapshot. Calls/runtime
components still need explicit clean-image qualification.

The candidate packager checks geometry, Android v2/Samsung DT table, footer bounds,
Mach-O/APFS presence and HFS kit CRC/capacity, then writes exactly `boot.img`,
`recovery.img`, `system.apfs`, `manifest.json` and `SHA256SUMS` to a new directory.
It labels the bundle private/unqualified. The manifest cannot enable flashing.

## System image reuse

The cache hook in `userland/build.sh` runs after the system's executables are
compiled. It hashes actual file content, including nested input changes, and forces
a rebuild on misses. Kernel/boot-line-only changes reuse system.apfs. Changes to
stage0, LocalFilesHost, extraction, firmware, apps/bootstrap or image tools rebuild
it. The entire image recipe is conservatively included; an unrelated edit in that
file can invalidate the system image, which is safer than silently omitting a dependency.

Set `HACKIOS_IMAGE_CACHE` to a private persistent directory. Without it, the legacy
builder's mtime behavior remains available. `SYSTEM=1` forces a fresh system build
even on a cache hit; immutable existing entries are not overwritten. No fallback cache key is used for
final images. Restore verifies full-file SHA-256. Corrupt cache entries fail and
must be quarantined/removed deliberately. Pending writes never become visible
entries. Hashing costs a read of large inputs; no timestamp shortcut is used.

`system.apfs` is cached independently; `root.apfs` and recovery are rebuilt because
they contain frequently changing code/options and runtime-dependent contents.
The private candidate store still deduplicates **any byte-identical image** across
runs. The current APFS/root build includes timestamps and other changing fields,
so identical source does not yet promise byte-for-byte identical fresh builds.
Do not advertise reproducible images until `SOURCE_DATE_EPOCH`, filesystem UUIDs,
ordering and all toolchain inputs are controlled and demonstrated.

## Failure and debugging

- `BLOCKED` from doctor means missing/unsafe inputs or an unsupported board; it is
  not a reason to bypass exact model or capacity checks.
- A nonzero compiler exit is failure. No stale artifact fallback is accepted.
- `ios165/` exists only in historical developer layouts. New builds use `sysimage/`;
  a deliberate legacy invocation can set `IOS_INPUT_DIR`.
- Existing research flashing helpers still contain workspace-specific operations.
  They are outside this no-phone release entry point.
- Never clean or rebuild another agent's directory. Preserve its pending work;
  merge/cherry-pick the reviewed release commits into the final source branch.

### Source-only development builds

`images --development` disables the legacy userland prebuilt fallback and builds
OpenH264 from its reviewed commit into `.cache/release-deps/openh264-source`.
Mesa/AIR is compiled locally with at most four workers by default (`JOBS` overrides).
The full image build requires a freshly prepared, reviewed extraction matching the
current selection recipe. Do not change `.done-rootfs` timestamps to bypass that
check. Host validation also needs a C compiler for the data-mount policy test.
Normal boot has no data formatter; a first-install initializer remains unqualified.

For preparation through verified archive generation with one command, see
[Local package build](local-build.md).
