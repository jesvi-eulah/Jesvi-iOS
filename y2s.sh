#!/bin/bash
# y2s.sh: host-side helper for the Exynos 990 Galaxy S20+ 5G (SM-G986B, y2s).
#
#   ./y2s.sh                show this help
#   ./y2s.sh ulog           pull the last run's log over USB ("Log access (USB)" in the loader menu)
#   ./y2s.sh log            alias for ulog
#   ./y2s.sh fresh          initialize iOS userdata from userland/hfs-kit.bin (needs the hfskit loader)
#   ./y2s.sh rflash         from Log access: flash and verify boot + recovery only
#   ./y2s.sh tflash         from Log access: flash and verify boot, recovery and system.apfs
#   ./y2s.sh uflash FILE    stage FILE and write it to recovery (low-level)
#   ./y2s.sh wflash FILE PART [HEXOFFSET]
#                           stage FILE and write it to PART (recovery, boot, super)
#   ./y2s.sh lflash FILE PART [HEXOFFSET]
#                           alias for wflash (Log access flash)
#   ./y2s.sh sflash FILE    write an APFS system image to super in chunks (low-level)
#   ./y2s.sh uboot          leave Log access and let the loader start iOS
#
# All flashing done here goes through the loader's Log access fastboot server;
# this is the ONLY supported update path. The separate first-install TWRP ZIP is
# fresh-only and erases userdata; do not reflash it over an existing iOS install.
# Set VERBOSE=0 to silence the step-by-step lines; otherwise every chunk prints
# a percentage after the loader has written it and read it back.
#
# The log is saved to out/y2s/xnulog.bin (raw, NUL padded) and
# out/y2s/xnulog.txt (NULs removed, printable), then printed.
#
# Unlike x1slte.sh, `oem lastlog` is optional here: on SM-G986B it can return
# "FAILED (remote: '')" while the staged log is still available via get_staged.
# We try it, ignore that failure, then read the staged log.
set -euo pipefail
cd "$(dirname "$0")"

FASTBOOT=${FASTBOOT:-fastboot}
OUT=out/y2s
LOG_BIN=$OUT/xnulog.bin
LOG_TXT=$OUT/xnulog.txt
HFSKIT=${HFSKIT:-userland/hfs-kit.bin}
VERBOSE=${VERBOSE:-1}
BLOCK=4096
CHUNK_BLOCKS=${Y2S_CHUNK_BLOCKS:-4096}      # 16 MiB per progress step
FLASH_TMP=

die() { echo "y2s.sh: $*" >&2; exit 1; }
note() { [ "$VERBOSE" = 1 ] && printf 'y2s.sh: %s\n' "$*" >&2 || true; }
progress() {
	local pct=$1; shift
	[ "$VERBOSE" = 1 ] && printf 'y2s.sh: [%3d%%] %s\n' "$pct" "$*" >&2 || true
}
cleanup() { [ -z "$FLASH_TMP" ] || rm -f "$FLASH_TMP"; }
trap cleanup EXIT

usage() {
	awk 'NR == 2 { on = 1 } on && /^#/ { sub(/^# ?/, ""); print; next } on { exit }' "$0"
}

fb_wait() {
	local i
	note "waiting up to 60 s for the loader's fastboot device"
	for i in $(seq 1 60); do
		"$FASTBOOT" devices 2>/dev/null | grep -q fastboot && { note "fastboot device found"; return 0; }
		sleep 1
	done
	# Some loader builds answer get_staged without showing up in `devices` on the first try.
	echo "y2s.sh: no fastboot device listed; trying the loader anyway" >&2
}

fb_prepare() {
	command -v "$FASTBOOT" >/dev/null 2>&1 || die "fastboot not found (set FASTBOOT=/path/to/fastboot)"
	fb_wait
	local product
	product=$("$FASTBOOT" getvar product 2>&1 |
		awk -F'product:' '/product:/ { gsub(/^[ \t]+|[ \t\r]+$/, "", $2); print $2; exit }') || true
	[ "$product" = xnuloader ] ||
		die "expected the JesviOS loader in Log access (product xnuloader), got '${product:-nothing}'"
	note "JesviOS loader confirmed; flashing through Log access"
}

blocks_of() {
	local size
	size=$(wc -c < "$1" | tr -d ' ')
	[ $((size % BLOCK)) -eq 0 ] || die "$1 is not a multiple of $BLOCK bytes"
	echo $((size / BLOCK))
}

# Stage one chunk and write it to the partition at BYTEOFF. The loader writes
# through its DMA-safe scratch buffer and reads the same chunk back before OKAY.
fb_write_range() {
	local file=$1 part=$2 byteoff=$3 size blocks blk=0 this pct reply
	size=$(wc -c < "$file" | tr -d ' ')
	[ $((size % BLOCK)) -eq 0 ] || die "$file is not a multiple of $BLOCK bytes"
	blocks=$((size / BLOCK))
	[ "$CHUNK_BLOCKS" -gt 0 ] || die "Y2S_CHUNK_BLOCKS must be positive"
	[ "$CHUNK_BLOCKS" -le 24320 ] || die "Y2S_CHUNK_BLOCKS is larger than the loader's 95 MiB stage"

	FLASH_TMP=$(mktemp "${TMPDIR:-/tmp}/y2s-flash.XXXXXX")
	note "$file: $((size / 1048576)) MiB, $blocks blocks of $BLOCK; ${part}+0x$(printf '%x' "$byteoff")"
	while ((blk < blocks)); do
		this=$(( blocks - blk < CHUNK_BLOCKS ? blocks - blk : CHUNK_BLOCKS ))
		dd if="$file" of="$FLASH_TMP" bs="$BLOCK" skip="$blk" count="$this" status=none
		pct=$(((blk + this) * 100 / blocks))
		note "staging ${file##*/} chunk at $part+0x$(printf '%x' "$((byteoff + blk * BLOCK))")"
		"$FASTBOOT" stage "$FLASH_TMP" >/dev/null 2>&1 ||
			die "could not stage chunk at $part+$((byteoff + blk * BLOCK))"
		note "flashing $part+0x$(printf '%x' "$((byteoff + blk * BLOCK))") from ${file##*/}"
		reply=$("$FASTBOOT" oem write "$part" "$(printf '%x' "$((byteoff + blk * BLOCK))")" 2>&1) ||
			die "write failed at $part+$((byteoff + blk * BLOCK)): $reply"
		case "$reply" in
			*"written and read back"*) ;;
			*) die "unexpected write reply at $part+$((byteoff + blk * BLOCK)): $reply" ;;
		esac
		progress "$pct" "$part+0x$(printf '%x' "$((byteoff + blk * BLOCK))") written and read back"
		blk=$((blk + this))
	done
	rm -f "$FLASH_TMP"
	FLASH_TMP=
	progress 100 "$file -> $part+0x$(printf '%x' "$byteoff") verified by loader readback"
}

flash_image() {
	local file=$1 part=$2 max=$3 size maxval
	[ -f "$file" ] || die "no such file: $file"
	size=$(wc -c < "$file" | tr -d ' ')
	[ $((size % BLOCK)) -eq 0 ] || die "$file is not a multiple of $BLOCK bytes"
	# y2s.conf records the windows as 0x... strings; bash arithmetic handles both hex and decimal.
	maxval=$((max))
	[ "$maxval" -eq 0 ] || [ "$size" -le "$maxval" ] ||
		die "$file is $size bytes, larger than $part's $maxval-byte window"
	fb_write_range "$file" "$part" 0
}

cmd_ulog() {
	fb_prepare
	note "creating $OUT if needed"
	mkdir -p "$OUT"
	note "asking the loader to stage the last log (an 'unavailable' reply is normal)"
	"$FASTBOOT" oem lastlog >/dev/null 2>&1 ||
		echo "y2s.sh: 'oem lastlog' unavailable; reading the staged log directly" >&2
	note "downloading the staged log to $LOG_BIN"
	rm -f "$LOG_BIN"
	"$FASTBOOT" get_staged "$LOG_BIN" >/dev/null 2>&1 ||
		die "get_staged failed: choose \"Log access (USB)\" in the loader menu and plug the cable in"
	[ -s "$LOG_BIN" ] || die "staged log is empty (no saved run?)"
	note "stripping NUL padding into $LOG_TXT"
	python3 - "$LOG_BIN" "$LOG_TXT" <<'PY'
import sys
src, dst = sys.argv[1:3]
data = open(src, 'rb').read().replace(b'\0', b'').decode('utf-8', 'replace')
open(dst, 'w').write(data)
print(data, end='\n' if not data.endswith('\n') else '')
PY
	note "log saved to $LOG_TXT"
}

cmd_fresh() {
	local reply loader_version blocks_hex blocks chunk done this pct wrote_hex wrote
	[ -f "$HFSKIT" ] || die "no HFSX kit at $HFSKIT"
	fb_prepare
	loader_version=$("$FASTBOOT" getvar version 2>&1) ||
		die "could not read the loader version: $loader_version"
	printf '%s\n' "$loader_version" | grep -Eq 'version: 0\.6' ||
		die "this loader has no chunked hfsinfo/hfsnext ($loader_version). Run ./y2s.sh rflash, power off, re-enter Log access, then retry fresh"
	note "staging $HFSKIT"
	"$FASTBOOT" stage "$HFSKIT" >/dev/null 2>&1 ||
		die "could not stage $HFSKIT to the loader"
	note "asking the loader to validate the kit"
	reply=$("$FASTBOOT" oem hfsinfo 2>&1) ||
		die "the loader refused the kit: $reply"
	blocks_hex=$(printf '%s\n' "$reply" | awk '{ for (i = 1; i <= NF; i++) if ($i == "blocks") { print $(i + 1); exit } }')
	[ -n "$blocks_hex" ] || die "loader did not report a block count: $reply"
	blocks=$((16#$blocks_hex))
	[ "$blocks" -gt 0 ] || die "the loader reported zero hfskit blocks"
	chunk=${Y2S_HFSKIT_CHUNK_BLOCKS:-256}      # 1 MiB per progress step
	[ "$chunk" -gt 0 ] || die "Y2S_HFSKIT_CHUNK_BLOCKS must be positive"
	note "userdata: $blocks blocks of $BLOCK; $chunk blocks per progress step"
	done=0
	while ((done < blocks)); do
		this=$(( blocks - done < chunk ? blocks - done : chunk ))
		reply=$("$FASTBOOT" oem hfsnext "$(printf '%x' "$this")" 2>&1) ||
			die "hfsnext chunk failed at block $done: $reply"
		case "$reply" in
			*FAIL*) die "hfsnext chunk failed at block $done: $reply" ;;
			*OKAY*) ;;
			*) die "unexpected hfsnext reply at block $done: $reply" ;;
		esac
		wrote_hex=$(printf '%s\n' "$reply" | awk '{ for (i = 1; i <= NF; i++) if ($i == "wrote") { print $(i + 1); exit } }')
		[ -n "$wrote_hex" ] || die "loader did not confirm an hfsnext chunk at block $done: $reply"
		wrote=$((16#$wrote_hex))
		[ "$wrote" -gt 0 ] && [ "$wrote" -le "$this" ] ||
			die "loader reported $wrote hfskit blocks at block $done, wanted $this"
		done=$((done + wrote))
		pct=$((done * 100 / blocks))
		progress "$pct" "userdata: $done / $blocks blocks written and read back"
	done
	progress 100 "userdata initialized from $HFSKIT and verified by loader readback"
	echo "y2s.sh: iOS userdata initialized"
}

cmd_uflash() {
	[ -n "${2:-}" ] || die "usage: ./y2s.sh uflash FILE"
	# shellcheck disable=SC1091
	. common/devices/y2s.conf
	fb_prepare
	flash_image "$2" recovery "$RECOVERY_PARTITION_SIZE"
	echo "y2s.sh: recovery written and read back from Log access"
}

cmd_wflash() {
	[ -n "${3:-}" ] || die "usage: ./y2s.sh wflash FILE PART [HEXOFFSET]"
	local file=$2 part=$3 off=${4:-0}
	[ -f "$file" ] || die "no such file: $file"
	case "$off" in
		0x*|0X*) off=$((off)) ;;
		*) off=$((16#$off)) ;;
	esac
	fb_prepare
	fb_write_range "$file" "$part" "$off"
	echo "y2s.sh: $file written to $part+0x$(printf '%x' "$off") and read back"
}

cmd_sflash() {
	[ -n "${2:-}" ] || die "usage: ./y2s.sh sflash FILE [PART]"
	local file=$2 part=${3:-super} max=0
	# shellcheck disable=SC1091
	. common/devices/y2s.conf
	[ "$part" = super ] && max=$ROOT_SUPER_LEN
	fb_prepare
	flash_image "$file" "$part" "$max"
	echo "y2s.sh: $file written to $part and read back in chunks"
}

cmd_rflash() {
	# shellcheck disable=SC1091
	. common/devices/y2s.conf
	fb_prepare
	note "full boot/recovery update from Log access (system.apfs untouched)"
	flash_image out/y2s/y2s-recovery.img recovery "$RECOVERY_PARTITION_SIZE"
	flash_image out/y2s/y2s-boot.img boot "$BOOT_PARTITION_SIZE"
	echo "y2s.sh: boot + recovery updated from Log access; run ./y2s.sh uboot to start iOS"
}

cmd_tflash() {
	# shellcheck disable=SC1091
	. common/devices/y2s.conf
	fb_prepare
	note "full update from Log access: system.apfs, then recovery, then boot"
	flash_image userland/system.apfs super "$ROOT_SUPER_LEN"
	flash_image out/y2s/y2s-recovery.img recovery "$RECOVERY_PARTITION_SIZE"
	flash_image out/y2s/y2s-boot.img boot "$BOOT_PARTITION_SIZE"
	echo "y2s.sh: full update flashed from Log access; run ./y2s.sh uboot to start iOS"
}

cmd_uboot() {
	fb_prepare
	note "asking the loader to leave Log access and start iOS"
	"$FASTBOOT" oem boot >/dev/null 2>&1 || true
	echo "y2s.sh: iOS is starting"
}

case "${1:-help}" in
	ulog|log) cmd_ulog ;;
	fresh) cmd_fresh ;;
	uflash) cmd_uflash "$@" ;;
	wflash|lflash) cmd_wflash "$@" ;;
	sflash) cmd_sflash "$@" ;;
	tflash) cmd_tflash ;;
	rflash) cmd_rflash ;;
	uboot) cmd_uboot ;;
	help|-h|--help) usage ;;
	*) echo "y2s.sh: unknown command '$1'" >&2; usage >&2; exit 2 ;;
esac
