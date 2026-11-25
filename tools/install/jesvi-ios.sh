#!/bin/bash
# jesvi-ios.sh — one command from nothing to Jesvi iOS on your Galaxy S20 (SM-G980F).
#   curl -fsSL <raw url of this file> | bash        or        bash tools/install/jesvi-ios.sh [--no-flash]
# 1. gets (or updates) the source into ~/Jesvi-iOS (JESVI_DIR)
# 2. iOS 16.5's files straight from Apple (sysimage/fetch.sh), the other inputs (tools/install/get-inputs.sh:
#    AOSP's AVB tool, our UEFI, Samsung's DT table from YOUR phone in TWRP), then checks this Mac (make doctor)
# 3. builds the TWRP install ZIP (make release; the first time about an hour)
# 4. if the phone is in TWRP over USB: offers a full backup, then installs the ZIP (twrp-install.sh)
# Your phone's own firmware files are pulled from TWRP the first time (tools/s20-firmware.sh --adb).
#   --no-flash   stop after building        JESVI_BACKUP_DIR=...   where the backup goes
set -euo pipefail
case "${1:-}" in -h|--help) sed -n '2,9s/^# \{0,1\}//p' "$0" 2>/dev/null || true; exit 0;; --no-flash|"") ;;
	*) echo "unknown option: $1 (try --help)"; exit 2;; esac
REPO=${JESVI_REPO:-https://github.com/jesvi-eulah/Jesvi-iOS.git}
DIR=${JESVI_DIR:-$HOME/Jesvi-iOS}
flash=1; [ "${1:-}" = --no-flash ] && flash=0
B=$'\033[1m' G=$'\033[32m' R=$'\033[31m' N=$'\033[0m'; [ -t 1 ] || B= G= R= N=
say() { printf '\n%s==> %s%s\n' "$B" "$*" "$N"; }
ok() { printf '%s  ok%s  %s\n' "$G" "$N" "$*"; }
die() { printf '\n%s  x %s%s\n' "$R" "$*" "$N" >&2; exit 1; }
printf '%sJesvi iOS installer%s  (Galaxy S20, SM-G980F)\n' "$B" "$N"

say "1/4 source"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only -q; else git clone -q --depth 1 "$REPO" "$DIR"; fi
cd "$DIR"; ok "$DIR at $(git log --oneline -1 | cut -c1-60)"

say "2/4 checking this computer"
if [ ! -d sysimage/rootfs ]; then
	echo "iOS 16.5's files are not here yet: downloading them from Apple (about 7 GB, once)"
	(cd sysimage && ./fetch.sh) || die "the iOS download stopped; run this again to continue"
fi
tools/install/get-inputs.sh || die "the build inputs are not complete (above); see docs/release/building.md, then run this again"
make doctor || die "this computer is missing what is listed above: see docs/release/building.md, then run this again"
ok "ready to build"

phone() { adb get-state 2>/dev/null | grep -q recovery; }
if [ ! -d fw-wifi ] && phone; then say "your phone's firmware files (first time only)"; tools/s20-firmware.sh --adb; fi

say "3/4 building (the first time about an hour)"
make release
zip=$(ls -t dist/release/Jesvi-iOS_*_x1s.zip | head -1)
ok "built: $zip"

[ $flash = 1 ] || { echo; echo "install later with:  tools/install/twrp-install.sh $zip"; exit 0; }
say "4/4 install"
if ! phone; then
	echo "Boot the phone into TWRP (Volume Down+Power, then Volume Up+Power), plug it straight into this computer,"
	echo "then run:  tools/install/twrp-install.sh $zip"; exit 0
fi
read -r -p "Make a full backup of the phone first? (strongly recommended) [Y/n] " a
case "$a" in n|N) ;; *) tools/install/twrp-backup.sh ${JESVI_BACKUP_DIR:+"$JESVI_BACKUP_DIR"};; esac
tools/install/twrp-install.sh "$zip"
