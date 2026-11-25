# Repository, CI and retained images

## Repository initialization and migration

The current project is already a Git repository. Do not run `git init` at
`ios-port-research/`: that directory contains private device dumps, backups and
many unrelated clones. Keep `upstream` for attribution; create publication `origin`
only when the final owner/repository is chosen. Suggested name: `ios-exynos990`,
display name Jesvi iOS.

Keep a private preservation copy of the complete research history. Before making
any remote public, scan **all history**, not only HEAD, for secrets, personal data,
firmware and unlicensed artifacts. `tools/release/audit.py` is a tracked-tree triage
report, not a secret scanner or license verdict. Use a dedicated full-history
scanner with redaction and review embedded firmware tables manually.

After that review, either publish the audited history or prepare a separate clean
release repository with documented upstream source revisions and notices. Do not
force-push rewritten history over the active development branch. A fresh public
repository is a reasonable option if the research history contains private device
data, but the clean snapshot itself must still be audited. GitHub's automatically
generated source archives include everything tracked at the tag.

Keep source and small configuration in Git. Generated SDKs, UEFI outputs, image
files, dumps and caches stay outside tracked paths. LFS is not an image-build cache
and does not resolve redistribution/privacy or history issues. Preserve licenses
and contributor attribution; clean directories do not justify replacing them.

## Concrete GitHub settings to apply on the final repository

These are prepared settings, **not remotely applied**; this checkout has no origin.

| Setting | Value |
|---|---|
| Default branch | `main` for the audited release source |
| Description | Experimental iOS/XNU port for Samsung Exynos 990; SM-G980F developer preview |
| Topics | `exynos990`, `galaxy-s20`, `xnu`, `darwin`, `ios-port` |
| Merge policy | PRs, squash or merge with attribution; delete merged feature branches |
| Main ruleset | Require PR + one review; resolve conversations; block force pushes/deletions |
| Required checks | `checks`, `kernel` after their first successful workflow runs |
| Maintainer changes | Dismiss stale reviews; require a fresh review after source changes |
| Tags `v*` | Restrict creation/deletion to maintainers/release role |
| Actions | Read-only default GITHUB_TOKEN; explicit allowed actions; SHA pins |
| Fork PRs | Hosted disposable workers only; no private inputs/secrets; approve first-time external jobs |
| Release environment | Named `release`, protected with reviewers where plan supports it |
| Private image environment | Separate PRIVATE repository, protected `private-images` environment |
| Features | Issues enabled; Discussions useful for device maintainers; wiki optional |
| Security | Enable supported secret/push scanning and private vulnerability reports |
| Artifact retention | Source CI artifacts 7 days; research audit 7 days; upstream report 30 days |

Add CODEOWNERS only after actual maintainer handles are known. A placeholder owner
would give a false sense of enforced review. Device profiles intentionally have
empty maintainer arrays until owners volunteer.

## Workflows included

- **CI:** all pushes/PRs/dispatches → registry, unit tests and shell syntax → macOS
  source kernel. Recovery CI also runs file-backed transaction tests, Go vet and
  static Linux/ARM64 cross-compilation with a pinned toolchain. Exact compiler/OS/architecture/source cache key; no fallback key.
  Cache writes only on non-PR runs. Only source-built kernel/provenance/checksums are
  uploaded. Job permissions are read-only; checkout credentials are not persisted.
- **Upstream watch:** weekly/manual read-only `ls-remote` against the input lock and `ci/upstream-watch.json` for HakiOS upstream.
  Reports changes; never merges or silently updates the build inputs. Dependabot
  opens reviewed action-version changes. "Auto pull" means check out the triggering
  commit for builds; upstream source updates remain reviewed lock changes.
- **Private TWRP release:** manual dispatch, default branch only, gated by
  `ENABLE_PRIVATE_IMAGE_BUILDS=true`. `runner=hosted` uses GitHub's `macos-15`
  compute, `runner=macos-26` selects GitHub’s macOS 26 image, and
  `runner=self-hosted` uses the provisioned `exynos990-private` worker.
  Both call **the same `./build.sh release` and `release.conf` as local builds**.
  Only tool/input setup and retention differ. Each attempt uses a fresh output
  directory, verifies ZIP checksums, and uploads an artifact for seven days.
  `writes=true` creates an installable ZIP; `mode=update` preserves installed data.
  No workflow flashes a phone. Ordinary CI's Restore ZIP is not the iOS installer.
- **Draft source release:** disabled unless `ENABLE_DRAFT_RELEASES=true`. A `v*`
  tag runs strict publication inventory and host checks, then creates a **draft**
  behind the release environment. Initial inventory deliberately blocks this
  until the publication review is resolved. It does not publish automatically.

Action pins were resolved from official action repositories during this review.
`actionlint` 1.7.12 validates the YAML, including the configured custom runner label.
Inspect current repository visibility and run status rather than treating configuration as proof of execution.

## GitHub-hosted full builds

1. Check the account's Actions billing/usage first. Private repositories draw from
   the plan's included allowance; additional compute and artifact storage can cost
   money. Standard macOS compute is not unlimited free compute. A billing rejection
   prevents even the configuration job from starting.
2. Prepare the small board/bootstrap archive from an isolated, reviewed checkout:
   `python3 tools/release/hosted_inputs.py pack --root /path/to/clean-checkout --output /private/staging/board-inputs.tar.gz`.
   It verifies the selected inputs against their existing private-input lock,
   includes firmware (including fingerprint), board/tool files, HFS kits and the
   reviewed bootstrap, and rejects personal Wi-Fi configuration. It does not include
   built images, Apple extraction, SSH settings or the development workspace.
3. For a public build repository, encrypt `board-inputs.tar.gz` with age and upload
   `board-inputs.tar.gz.age` as a release asset. Set
   `HOSTED_BOARD_INPUTS_AGE_KEY` in the `private-images` environment to the age
   identity. A private build repository can also use the plaintext asset without
   the age secret. Use a non-version release tag such as `private-build-inputs-YYYYMMDD`.
   Set `PRIVATE_INPUTS_TAG` to that tag and `PRIVATE_INPUTS_SHA256` to the archive's
   checksum. The hosted job checks the settings and confirms the asset exists
   before installing build tools. The input archive follows repository visibility; it is input storage, not a product release.
4. Set `ENABLE_PRIVATE_IMAGE_BUILDS=true`. Public repositories also require
   explicit `ENABLE_PUBLIC_IMAGE_BUILDS=true` authorization for public image artifacts. Dispatch **Build Jesvi iOS for Galaxy S20 (TWRP)** with `runner=hosted` and `outputs=twrp`.
   For `target=y2s`, the workflow first calls `y2s-firmware.yml` on Ubuntu ARM64: set either
   `Y2S_STOCK_FIRMWARE_URL` (a verified SM-G986B XSG stock ZIP, checked against its published
   MD5) or `Y2S_FUS_IMEI` in the `private-images` environment so the pinned stock boot tree can
   be fetched. `HOSTED_BOARD_INPUTS_AGE_KEY` encrypts both that handoff and the shared board
   inputs; the macOS job installs `age` and verifies `SHA256SUMS` before building. With the
   default `writes=from-release.conf`, y2s produces a flashable first-install ZIP (`MODE=fresh`,
   `IOS_DATA_GB=all`, `WRITES=true`); choose `writes=false` for a preflight-only ZIP.

`ci/setup-hosted-images.sh` only runs on disposable GitHub-hosted macOS machines.
It retains the selected Xcode, removes unused Xcode versions/simulator data,
installs tools and checks for at least 45 GiB free after setup. GitHub's documented
standard runner free-space allowance alone is insufficient; if reclamation does
not leave enough room, the job stops. It never cleans the local Mac.

The SHA-pinned archive is extracted with path/type/symlink checks, then its content
hashes are verified. The shared release build fetches Apple extraction and the
Touch ID library from Apple, builds the kernel and userland from source, assembles
images and packages them. There is no fallback to a previously built local image.
Hosted execution remains unverified until a full run passes. Local tests cannot
prove hosted capacity, external downloads or runtime performance.

## Private worker setup

Never register the active development Mac as this worker. Use a disposable VM/host
identity with no phone attached. Provision compiler/build tools and adequate disk
space for SDK, Mesa, extraction, input copies and several image copies (plan at
least 60–100 GB free, measure actual usage). The workflow label is
`exynos990-private`; access must be restricted to the private build repository.

Provision two restricted volumes outside the checkout:

- `PRIVATE_INPUTS_ROOT`: a reviewed immutable snapshot with exactly the path layout
  in [building](building.md), including `inputs/private-inputs.lock.json` and the HFSX format kit for the
  configured data size.
- `PRIVATE_STORE_ROOT`: retained image objects/candidate manifests. Set the Actions
  variables to these local mount paths. The separate system cache path defaults
  in the workflow to `/var/cache/exynos990/private-images`.

The supplied `private_store.py stage` copies only allowlisted private paths,
refuses checkout/source overlap and verifies their content lock. It does not import
shell configuration, private SSH folders or a second checkout. `retain` verifies
candidate files and stores each image under its SHA-256, writing candidate metadata
only after objects exist. Interrupted uploads may leave unreferenced objects but
cannot create a candidate pointing at a not-yet-uploaded image.

No automatic garbage collector is shipped: accidental deletion of still-referenced
multi-GB images is worse than temporary extra disk use. A future GC must mark all
objects referenced by retained candidate manifests, retain a safety grace period
and delete only unreferenced objects. Until then monitor space and manually prune
known-expired cache entries/candidates with a backup; never evict retained releases
just because a build cache is full.

An authenticated object store/CDN can later replace the local persistent volume.
Keep the same `sha256 -> bytes` and `candidate -> manifest` contracts. Upload objects
first, verify, then publish the manifest atomically. Public redistribution remains
a separate decision; making the bucket private is not license clearance.

## Cache boundaries

| Layer | Key material | Storage | On miss |
|---|---|---|---|
| Source kernel | Exported source, scripts/dependency lock, compiler, host OS/arch | Public Actions cache: kernel outputs only | Build from pinned source |
| SDK/firmware/extraction | Source locks + verified private input inventory | Private input snapshot | Fetch/provision reviewed inputs |
| system.apfs | Actual extraction, executables, firmware/apps/bootstrap, image recipe/tool sources | Private system cache | Force system rebuild |
| root/recovery | Rebuilt using current sources/options and private inputs | Local candidate | Assemble and validate |
| Retained images | SHA-256 of complete file | Private durable object store/volume | Store object once |
| Candidate | Manifest SHA-256 | Separate retained metadata | Publish metadata after objects |

A changed Git commit alone does not invalidate the system image. A changed local
firmware byte does, even if Git and mtimes are unchanged. Different devices must
not share a private input snapshot without an explicit common-content provenance
contract. Caches are disposable acceleration; retained release artifacts are the
recovery/distribution record.

GitHub's [cache reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
and [secure-use guide](https://docs.github.com/en/actions/reference/security/secure-use)
explain cache visibility, immutable keys, least privilege and action pinning.

## Retrieving the final TWRP ZIP

Open the successful **Full TWRP release** run and follow its summary download
link (`jesvi-ios-<run-id>-<attempt>` artifact). GitHub wraps the output files in an
outer artifact ZIP. Extract that, verify the inner `Jesvi-iOS_*.zip` using its
`.sha256` file, and install the **inner ZIP**, not the outer GitHub artifact ZIP.

The shared `release.conf` version determines names for both local and hosted
packages. No product release or version tag is created by this workflow. Public repositories expose the artifacts publicly.

Apple-framework passcode tests run on macOS. Full private builds run source and
recovery checks before assembly. Workflow lint and host tests are local evidence,
not proof of a successful GitHub full image build. In the 2026-11-21 investigation,
GitHub rejected the latest CI jobs before execution with an account payment or
spending-limit error; no hosted full ZIP was produced.

The owner made Jesvi-iOS public on 2026-11-21 and explicitly authorized a public
full installer ZIP. The workflow keeps a separate public-output opt-in so a future
visibility change alone does not publish full images.
