# release.conf: one file for every release build

`release.conf` at the repository root says what to build, like UN1CA's target
selection. `./build.sh release` reads it on a Mac; GitHub Actions reads the same file.

```sh
./build.sh release --dry-run                    # show the plan and file names
./build.sh release                              # build everything it asks for
./build.sh release --set WRITES=true --set OUTPUTS="twrp restore"
JESVI_TARGETS="x1slte y2s" ./build.sh release   # environment override
```

| Key | Meaning |
|---|---|
| `NAME`, `VERSION` | File names: `NAME_VERSION_YYYYMMDD_target.zip`, `NAME-Restore_...zip`; explicit modes add `_fresh` or `_update` before the target; `_preflight` is added when writes are off |
| `TARGETS` | Device ids from `devices/exynos990/`. Targets without a measured profile are listed as SKIP |
| `OUTPUTS` | `twrp` (iOS installer), `preflight` (check-only), `restore` (back to Android), `tar` (images for developers) |
| `MODE` | `fresh` (default; erases existing userdata), `choose` (preserve valid iOS data, else fresh), `update` (requires existing iOS data) |
| `WRITES` | `true`: installs proceed after a 45-second cancel window; restore requires a Volume Up hold. `false` (default): every ZIP only checks the phone |
| `BUNDLE` | Existing verified candidate to package. Empty: full local build first (macOS, private Apple inputs, ~25 GiB free) |
| `OUT` | Output directory inside `dist/` |

Each ZIP gets `.sha256` and `.build.json` (source commit, Go version, install mode, writes flag).

For an explicit first installation, build with:

```sh
./build.sh release --set MODE=fresh --set WRITES=true --set OUTPUTS=twrp
```

A dispatched `target=y2s` build always sets `MODE=fresh`, `IOS_DATA_GB=all` and
(unless `writes=false` is chosen explicitly) `WRITES=true`, so its artifact is a
flashable first-install TWRP ZIP rather than a preflight. This erases existing
userdata after a 45-second cancel window, even on an existing iOS installation.
Volume Down/Power cancels; holding Volume Up for three seconds proceeds early.
Read-only preflights do not enter this window. Use off-device
backups first. `MODE=update` requires matching existing iOS userdata and cannot
initialize an Android phone. Unmounting or wiping Android cache does not change
an update-only ZIP's mode; rebuild the ZIP. Optional `MODE=choose` selects fresh
on non-HFS userdata, preserves valid iOS data, and refuses damaged or differently
sized iOS data. The dry-run/build plan prints the mode and whether writes are enabled.

## GitHub Actions

| Workflow | Runner | Output |
|---|---|---|
| `ci.yml` | public | tests, Go recovery checks, kernel, and **restore ZIPs** for every measured target (artifact `restore-zips-<sha>`) |
| `private-images.yml` | hosted or self-hosted macOS with private Apple inputs | everything `release.conf` asks for (`mode`/`writes`/`outputs` inputs override it); artifact `jesvi-ios-<sha>-<run>` |
| `y2s-firmware.yml` | hosted Ubuntu ARM64 | called by `private-images.yml` for `target=y2s`: extracts the pinned stock SM-G986B tree, builds `Mu-y2s.img`, and hands it to the macOS job as an age-encrypted artifact |
| `draft-release.yml` | public, on `v*` tags | draft release with the restore ZIPs attached |

The restore ZIP carries no Apple or Samsung files, so public runners can build it.
iOS ZIPs contain Apple-derived images and stay in private runs.

## Targets and mods

Per-phone settings, boot-args and mods: see [targets](targets.md).
