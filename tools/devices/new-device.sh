#!/usr/bin/env bash
# new-device.sh CODENAME MODEL "NAME": start support for another Exynos 990 phone.
#   tools/devices/new-device.sh c2s SM-N986B "Galaxy Note20 Ultra 5G"
# Creates devices/exynos990/CODENAME/{target.conf,device.json,README.md} (status unmaintained)
# and lists it in devices/manifest.conf. Everything shared (kernel, platform drivers,
# boot-args, the stock boot DTB, userland, release tooling) comes from the platform layer;
# the new folder holds only what is unique to the phone. See docs/porting/new-device.md.
set -euo pipefail
code=${1:?usage: new-device.sh CODENAME MODEL \"NAME\"}; model=${2:?model, e.g. SM-G988B}; name=${3:?display name}
[[ $code =~ ^[a-z0-9]+$ ]] || { echo "codename: lowercase letters/digits (Samsung board id, e.g. z3s)"; exit 2; }
root=$(cd "$(dirname "$0")/../.." && pwd); dir=$root/devices/exynos990/$code
if [ -e "$dir/target.conf" ]; then echo "$code already exists: edit $dir/target.conf"; exit 1; fi
mkdir -p "$dir"
cat > "$dir/target.conf" <<CONF
# $name ($model). Unmeasured: fill in from your own phone (docs/porting/new-device.md).
# Everything not set here comes from devices/exynos990/platform.conf.
TARGET_NAME="$name"
TARGET_CODENAME="$code"
TARGET_STATUS="unmaintained"
TARGET_ASSERT_MODEL="$model"
TARGET_ASSERT_BOOTLOADER=""
TARGET_RECOVERY_PRODUCTS="$code"
# Closest supported phone whose settings you start from (x1slte or y2s); delete if none.
#TARGET_INHERIT="x1slte"
TARGET_RAM_GB=""
TARGET_STORAGE_GB=""
TARGET_DISPLAY_RESOLUTION=""
TARGET_DISPLAY_REFRESH_RATES="60"
TARGET_PANEL=""
TARGET_TOUCH=""
TARGET_MODEM="lte"
TARGET_WIFI_CHIP=""
TARGET_FINGERPRINT=""
# Extra boot-args only this phone needs (drivers that differ from the platform).
TARGET_BOOTARGS=""
TARGET_DISABLE_MODS=""
CONF
cat > "$dir/device.json" <<JSON
{
  "schema": 1,
  "id": "$code",
  "name": "$name",
  "platform": "exynos990",
  "status": "unmaintained",
  "maintainers": [],
  "models": ["$model"],
  "recovery_products": ["$code"],
  "bootloaders": [],
  "installer_validated": false,
  "partitions": {},
  "layout": {},
  "evidence": null
}
JSON
cat > "$dir/README.md" <<MD
# $name ($code)

Status: **unmaintained**, no build has booted on this phone yet. Maintainer: wanted.

Start with [docs/porting/new-device.md](../../../docs/porting/new-device.md).
MD
grep -q "^device $code\$" "$root/devices/manifest.conf" || printf '\ndevice %s\n\tpath        devices/exynos990/%s\n' "$code" "$code" >> "$root/devices/manifest.conf"
echo "created $dir: fill in target.conf, then follow docs/porting/new-device.md"
