#!/bin/bash
# tools/y2s/probe.sh -- read-only board facts for the SM-G986B (y2s) port.
#
# Run against the phone's *current* ROM (rooted shell, USB debugging on):
#   ./tools/y2s/probe.sh
#   Y2S_PROBE_OUT=inputs/y2s/probe-1 ./tools/y2s/probe.sh
#
# Writes a sanitized report plus small, local-only partition dumps under
# inputs/y2s/ (gitignored). It never writes to userdata and never records
# serial numbers, IMEI/IMSI, Wi-Fi MAC addresses, the phone's network config
# or anything from the Android user data partition.
set -euo pipefail
cd "$(dirname "$0")/../.."

OUT=${Y2S_PROBE_OUT:-inputs/y2s/probe-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT/dumps"

adb wait-for-device
if ! adb shell 'id' | grep -q uid=0; then
	adb root > /dev/null 2>&1 || true
fi
if ! adb shell 'su -c id' 2>/dev/null | grep -q uid=0; then
	echo "probe: no root shell on the phone (need 'su' access)" >&2
	exit 1
fi
echo "probe: root shell confirmed; collecting facts -> $OUT"

DEVICE_SCRIPT=/data/local/tmp/y2s-probe-device.sh
cat > "$OUT/device-probe.sh" <<'EOS'
#!/system/bin/sh
# Everything here is read-only. Keep the report free of device identities.
R=/data/local/tmp/y2s-probe-report.txt
: > "$R"
say() { printf '%s\n' "$*" >> "$R"; }
section() { printf '\n===== %s =====\n' "$*" >> "$R"; }
show() { say "$1: $(cat "$2" 2>/dev/null || echo '<unavailable>')"; }

section identity
for p in \
  ro.product.model ro.product.device ro.product.board ro.product.name \
  ro.product.vendor.model ro.product.vendor.device ro.product.odm.model \
  ro.boot.bootloader ro.bootloader ro.boot.hardware ro.hardware \
  ro.board.platform ro.boot.revision ro.boot.boot_revision \
  ro.boot.mode ro.boot.slot_suffix ro.boot.dynamic_partitions \
  ro.build.version.release ro.build.version.sdk ro.build.id \
  ro.build.display.id ro.build.PDA ro.build.version.incremental \
  ro.build.type ro.build.tags ro.zygote; do
  say "$p=$(getprop "$p" 2>/dev/null)"
done
show kernel /proc/version
# /proc/cmdline carries androidboot.serialno and similar identities on Samsung ROMs: strip them.
say "cmdline=$(sed -E 's/androidboot\.serialno=[^ ]+/androidboot.serialno=<redacted>/g; s/androidboot\.ap_serial=[^ ]+/androidboot.ap_serial=<redacted>/g; s/androidboot\.em\.did=[^ ]+/androidboot.em.did=<redacted>/g' /proc/cmdline 2>/dev/null)"
show meminfo_total_etc /proc/meminfo
grep -i '^MemTotal:\|^MemAvailable:\|^SwapTotal:' /proc/meminfo >> "$R" 2>/dev/null || true

section device_tree
ls -1 /proc/device-tree/ 2>/dev/null >> "$R" || true
for f in model compatible name; do show "dt/$f" "/proc/device-tree/$f"; done
for d in /proc/device-tree/memory@*; do
  [ -d "$d" ] || continue
  say "dt/${d##*/}/device_type=$(cat "$d/device_type" 2>/dev/null)"
  say "dt/${d##*/}/reg=$(od -An -tx1 -v "$d/reg" 2>/dev/null | tr -d ' \n')"
done
if [ -d /proc/device-tree/reserved-memory ]; then
  for d in /proc/device-tree/reserved-memory/*; do
    [ -d "$d" ] || continue
    reg=$(od -An -tx1 -v "$d/reg" 2>/dev/null | tr -d ' \n')
    say "reserved/${d##*/}: reg=$reg compatible=$(cat "$d/compatible" 2>/dev/null | tr '\0' ' ')"
  done
fi
show dt/chosen-bootargs /proc/device-tree/chosen/bootargs
show dt/aliases /proc/device-tree/aliases

section storage
ls -l /dev/block/by-name/ 2>/dev/null >> "$R" || true
for p in boot recovery dtbo dtb vbmeta vbmeta_system super userdata metadata misc up_param param odm product system vendor; do
  b=/dev/block/by-name/$p
  [ -e "$b" ] || continue
  sz=$(blockdev --getsize64 "$b" 2>/dev/null || echo '?')
  bs=$(blockdev --getss "$b" 2>/dev/null || echo '?')
  say "partition $p: bytes=$sz logical_sector=$bs link=$(readlink "$b")"
done
for b in /sys/block/sd*; do
  [ -e "$b/queue/logical_block_size" ] || continue
  say "block ${b##*/}: logical=$(cat "$b/queue/logical_block_size") physical=$(cat "$b/queue/physical_block_size") size=$(cat "$b/size")"
done
df -h /data /system /vendor 2>/dev/null >> "$R" || true
cat /proc/partitions 2>/dev/null >> "$R" || true

section display
ls -l /dev/graphics /dev/dri /sys/class/drm /sys/class/display /sys/class/backlight 2>/dev/null >> "$R" || true
for f in /sys/class/drm/card*/modes /sys/class/display/*/modes /sys/class/backlight/*/max_brightness; do
  [ -f "$f" ] || continue
  say "$f=$(cat "$f" 2>/dev/null | tr '\n' ' ')"
done
dmesg 2>/dev/null | grep -iE 'panel|hubble|s6e3|lcd|decon|dsi|drm|fps|refresh|display' | tail -100 >> "$R" || true

section touch_and_buttons
ls -l /sys/bus/i2c/devices/ 2>/dev/null >> "$R" || true
dmesg 2>/dev/null | grep -iE 'sec_ts|tsp_|touchscreen|goodix|synaptics|ilitek|key.(power|volume)' | tail -80 >> "$R" || true

section wireless
ls -1 /vendor/firmware /vendor/firmware_mnt 2>/dev/null | grep -iE 'bcm|nvram|wifi|ath|bt' >> "$R" || true
dmesg 2>/dev/null | grep -iE 'bcmdhd|ath11k|wlan|wifi|nvram|bluetooth' | tail -80 >> "$R" || true

section audio_haptics_sensors_camera
dmesg 2>/dev/null | grep -iE 'max77705|fuel|charger|battery|cs40l25|haptic|sensorhub|bcm_sensorhub|is_sensor|cam_|s5k|imx|sensors' | tail -100 >> "$R" || true
ls -1 /vendor/etc/camera /vendor/etc/sensors 2>/dev/null | head -60 >> "$R" || true

section firmware_files
ls -l /vendor/firmware 2>/dev/null | head -100 >> "$R" || true
for p in boot recovery dtbo dtb vbmeta vbmeta_system; do
  b=/dev/block/by-name/$p
  [ -e "$b" ] || continue
  dd if="$b" of="/data/local/tmp/y2s-$p.img" bs=1M 2>/dev/null || true
done
ls -l /data/local/tmp/y2s-*.img 2>/dev/null >> "$R" || true
say DONE
EOS

adb push "$OUT/device-probe.sh" "$DEVICE_SCRIPT" > /dev/null
adb shell "su -c 'sh $DEVICE_SCRIPT'" > /dev/null
adb pull /data/local/tmp/y2s-probe-report.txt "$OUT/report.txt" > /dev/null
for p in boot recovery dtbo dtb vbmeta vbmeta_system; do
	adb pull "/data/local/tmp/y2s-$p.img" "$OUT/dumps/$p.img" > /dev/null 2>&1 || true
done
adb shell "su -c 'rm -f $DEVICE_SCRIPT /data/local/tmp/y2s-probe-report.txt /data/local/tmp/y2s-boot.img /data/local/tmp/y2s-recovery.img /data/local/tmp/y2s-dtbo.img /data/local/tmp/y2s-dtb.img /data/local/tmp/y2s-vbmeta.img /data/local/tmp/y2s-vbmeta_system.img'" > /dev/null 2>&1 || true

echo "probe: report at $OUT/report.txt"
echo "probe: partition dumps at $OUT/dumps/ (local only; do not commit or publish)"
grep -E '^(ro.product.model|ro.boot.bootloader|ro.bootloader|ro.build.PDA|kernel|partition (boot|recovery|super|userdata)|dt/model)' "$OUT/report.txt" || true
