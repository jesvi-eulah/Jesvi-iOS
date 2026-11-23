#!/bin/bash
# tools/y2s/extract-firmware.sh -- unpack the small, relevant parts of a stock SM-G986B
# Samsung firmware package for local, offline inspection. Nothing here is ever committed.
#
#   ./tools/y2s/extract-firmware.sh path/to/SM-G986B_..._fac.zip [outdir]
#
# Default output: inputs/y2s/firmware/extracted/ (gitignored). It extracts only the
# boot-chain images needed to measure the y2s port (boot/dtbo/vbmeta/param/PIT).
# Add --with-vendor to also extract vendor.img (needs several GiB) for module firmware.
set -euo pipefail
cd "$(dirname "$0")/../.."

WITH_VENDOR=0
if [ "${1:-}" = --with-vendor ]; then WITH_VENDOR=1; shift; fi
ZIP=${1:-}
if [ -z "$ZIP" ] || [ ! -f "$ZIP" ]; then
	sed -n '2,8p' "$0"; exit 2
fi
BASE=${2:-inputs/y2s/firmware/extracted}
mkdir -p "$BASE/tars" "$BASE/images"

echo "extract-firmware: listing $ZIP"
unzip -l "$ZIP" | tail -n +4 | sed -e '$d' -e '$d' | awk '{print $4}' | grep -v '^$' > "$BASE/zip-contents.txt" || true
cat "$BASE/zip-contents.txt"

unzip -o -q "$ZIP" -d "$BASE/tars"

shopt -s nullglob nocaseglob
for t in "$BASE"/tars/*.tar.md5 "$BASE"/tars/*.tar; do
	name=$(basename "$t" .tar.md5); name=${name%.tar}
	echo "extract-firmware: reading $name"
	mkdir -p "$BASE/tars/$name.d"
	patterns=(boot.img recovery.img dtbo.img vbmeta super.img 'param*' '*.pit' 'up_param*')
	[ "$WITH_VENDOR" = 1 ] && patterns+=(vendor.img)
	args=()
	while IFS= read -r member; do
		case "$member" in
			boot.img*|recovery.img*|dtbo.img*|vbmeta*.img*|super.img*|param*|*.pit|up_param*|vendor.img*) args+=("$member") ;;
		esac
	done < <(tar -tf "$t" 2>/dev/null || true)
	[ ${#args[@]} -gt 0 ] && tar -xf "$t" -C "$BASE/tars/$name.d" "${args[@]}" 2>/dev/null || true
done

for f in "$BASE"/tars/*/*.lz4; do
	[ -f "$f" ] || continue
	lz4 -df -q "$f" "${f%.lz4}" 2>/dev/null || echo "extract-firmware: could not decompress ${f##*/}"
done

find "$BASE" -type f \( -name '*.img' -o -name '*.pit' -o -name '*.bin' \) \
	-not -path '*/tars/*' -exec cp -n {} "$BASE/images/" \; 2>/dev/null || true
find "$BASE/tars" -type f \( -name 'boot.img' -o -name 'recovery.img' -o -name 'dtbo.img' -o -name 'vbmeta*.img' -o -name 'super.img' -o -name '*.pit' -o -name 'vendor.img' \) \
	-exec cp -n {} "$BASE/images/" \; 2>/dev/null || true

echo "extract-firmware: images:"
ls -lh "$BASE/images" 2>/dev/null || true
echo "extract-firmware: local evidence only; do not commit $BASE"
