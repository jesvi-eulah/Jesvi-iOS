#!/bin/bash
# Build y2s's isolated sysimage tree. This is the ONLY y2s input with its own
# selector and IconState overlay; the shared ../sysimage tree is never changed,
# so x1slte keeps its small selection.
#
# The default is the debloated selector (~3.1 GB extracted, 2.4 GB system.apfs),
# which fits TWRP's /tmp and the installer's system window. Set Y2S_FULL_ROOT=1
# only for a diagnostic full-root image (all Apple apps, languages, media and the
# other bloat, about 8 GB extracted); that image is not used by the TWRP ZIP.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -d sysimage-y2s ]; then
	python3 tools/release/copy_tree.py sysimage sysimage-y2s
fi
# Force one regeneration when a tree copied from another selection is reused.
rm -f sysimage-y2s/.done-rootfs sysimage-y2s/.done-rootfs-full
export KEEP=${KEEP:-1}
echo "fetch-full-root.sh: refreshing sysimage-y2s ($([ -n "${Y2S_FULL_ROOT:-}" ] && echo 'diagnostic full root' || echo 'debloated default selection'))"
bash sysimage-y2s/fetch.sh
# Apple's root includes mode-000 markers such as /.file. The manifest keeps their
# original modes for mkapfs.py, but the local clone must be able to read them.
find sysimage-y2s/rootfs -type f -exec chmod u+r {} +
echo "fetch-full-root.sh: sysimage-y2s is ready; rebuild with userland/build-gpu-y2s.sh"
