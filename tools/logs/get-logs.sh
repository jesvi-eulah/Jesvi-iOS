#!/usr/bin/env bash
# Jesvi iOS: collect the phone's logs into one ZIP on the Desktop (macOS / Linux).
#   Phone: hold a volume key at the iOS logo -> "Log access (USB)" -> plug in the cable.
#   Computer: curl -fsSL https://raw.githubusercontent.com/jesvi-eulah/Jesvi-iOS/main/tools/logs/get-logs.sh | bash
# Downloads Google's platform-tools if fastboot is missing. Reads logs only; writes nothing to the phone.
set -euo pipefail
say() { printf '\n==> %s\n' "$*"; }
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
fb=$(command -v fastboot || true)
if [ -z "$fb" ]; then
  case $(uname -s) in Darwin) os=darwin;; Linux) os=linux;; *) echo "Unsupported system"; exit 1;; esac
  say "Downloading fastboot (Google platform-tools)"
  curl -fsSL -o "$work/pt.zip" "https://dl.google.com/android/repository/platform-tools-latest-$os.zip"
  unzip -q "$work/pt.zip" -d "$work"
  fb="$work/platform-tools/fastboot"
fi
say "Waiting for the phone (menu -> Log access (USB), cable plugged in)"
for i in $(seq 1 120); do
  "$fb" devices 2>/dev/null | grep -q fastboot && break
  [ "$i" = 120 ] && { echo "Phone not found. Check the menu shows Log access and try another cable/port."; exit 1; }
  sleep 1
done
out="$work/jesvi-logs"; mkdir -p "$out"
grab() {  # grab NAME COMMAND...: stage something on the phone, then download it
  local name=$1; shift
  if "$fb" "$@" >/dev/null 2>&1 && "$fb" get_staged "$out/$name.bin" >/dev/null 2>&1; then
    LC_ALL=C tr -d '\000' < "$out/$name.bin" > "$out/$name.txt"; rm -f "$out/$name.bin"; echo "   got $name"
  else
    echo "   (no $name)"
  fi
}
say "Reading logs"
grab last-run oem lastlog
grab loader  oem log
"$fb" oem memmap >/dev/null 2>&1 || true
grab memory-map oem log
"$fb" getvar all > "$out/phone-info.txt" 2>&1 || true
dest="$HOME/Desktop"; [ -d "$dest" ] || dest="$HOME"
zip="$dest/jesvi-logs-$(date +%Y%m%d-%H%M%S).zip"
(cd "$work" && zip -qr "$zip" jesvi-logs)
say "Done: $zip"
echo "Send this file to the Jesvi iOS group. It holds logs only: no IMEI, accounts or photos."
