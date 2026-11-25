#!/usr/bin/env bash
# fetch-boot-dtb.sh OUTDIR: write the shared Exynos 990 stock boot trees
# (stock-boot-dtb.img, stock-boot-dtbh.img) pinned in devices/exynos990/platform.conf.
# Used by CI for every target and by developers locally. Fails on any checksum mismatch.
set -euo pipefail
out=${1:?usage: fetch-boot-dtb.sh OUTDIR}
root=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=/dev/null
. "$root/devices/exynos990/platform.conf"
sha() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
mkdir -p "$out"
curl --fail --silent --show-error --location --proto '=https' --retry 3 \
  --output "$out/stock-boot-dtb.img" "$PLATFORM_BOOT_DTB_URL"
[ "$(sha "$out/stock-boot-dtb.img")" = "$PLATFORM_BOOT_DTB_SHA256" ] || { echo "boot DTB checksum mismatch" >&2; exit 1; }
{ printf '%s' "$PLATFORM_BOOT_DTBH_HEADER" | xxd -r -p; cat "$out/stock-boot-dtb.img"; } > "$out/stock-boot-dtbh.img"
[ "$(sha "$out/stock-boot-dtbh.img")" = "$PLATFORM_BOOT_DTBH_SHA256" ] || { echo "boot DTBH checksum mismatch" >&2; exit 1; }
echo "boot trees OK in $out"
