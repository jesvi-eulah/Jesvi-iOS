#!/bin/bash
# The GPU pieces of the small image for the Galaxy S20+ (y2s, Mali-G77), built on macOS, where
# build.sh does not compile (it wants the Linux toolchain's ld64 and falls back to prebuilt/userland):
#
#   obj/libOSMesa.8.dylib      Mesa with panfrost (tools/mk-mesa.sh, DRIVERS=softpipe,panfrost)
#   obj/libredwood-gl.dylib    CoreAnimation's OpenGL ES (src/eagl.c, src/gl_osmesa.c)
#   obj/gl_test, obj/mali_test the tests (src/gl_test.c, src/mali_test.c)
#   obj/libredwoodair.dylib    Metal's shader compiler on panfrost (AIR=1 tools/mk-mesa.sh), and the
#   obj/RedwoodMetal, obj/libredwoodmetal.dylib, obj/metal_drv_test, obj/metal_props   Metal driver
#   prebuilt/userland/libredwood.dylib   src/inject.c, which loads libredwood-gl.dylib into backboardd
#                              when the kernel has a GPU service (RedwoodMali: boot-arg mali=1), and
#                              libredwood-sb.dylib (src/inject_sb.c, SpringBoard's, which asks the same);
#                              the ones that were there are kept as *.orig
#
# then build.sh with GL=1 and whatever else is given in the environment (REST=1, RC_JOBS=...).
#   userland/build-gpu-y2s.sh                  REST=1 GL=1
#   RC_JOBS=rc.jobs.mali userland/build-gpu-y2s.sh
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)
# y2s has its own extracted sysimage tree so its selector and IconState overlay
# cannot change x1slte or the release pipeline. It uses the default debloated
# selector; set Y2S_FULL_ROOT=1 in sysimage-y2s/fetch.sh only for diagnostics.
export IOS_INPUT_DIR=${IOS_INPUT_DIR:-../sysimage-y2s}
[ -d "$IOS_INPUT_DIR/cryptex" ] || {
	echo "build-gpu-y2s.sh: $IOS_INPUT_DIR is missing; run tools/y2s/fetch-full-root.sh" >&2
	exit 1
}
# Only y2s gets the full IconState. The shared userland/var tree stays the one
# x1slte has always used; this overlay is applied by build.sh when assembling root.
export VAR_OVERLAY=var-y2s
# y2s has no rootless /var/jb prefix: the inherited x1slte account-store job
# would fail at /var/jb/bin/sh on every boot. Opt out unless explicitly enabled.
export ACCOUNT_RELAY=${ACCOUNT_RELAY:-0}
# The shared softpasscode mod belongs to x1slte's bootline and software bag; y2s
# boots without it. The target carries the same opt-out for generated bootlines.
export JESVI_MODS_DISABLE=${JESVI_MODS_DISABLE:-softpasscode}
set +u # Legacy environment setup reads optional unset variables.
source ../xnu/xnu-env.sh
set -u
SDK=$THEOS/sdks/iPhoneOS16.5.sdk
mkdir -p obj ../prebuilt/userland
DYN="xnu-clang -arch arm64 -isysroot $SDK -O1"
M=$ROOT/xnu-deps/build/mesa/out

# Release builds compile the complete userland recipe. The older macOS shortcut
# below is retained for developer checkouts, but must not overwrite tracked prebuilts.
if [ "${REQUIRE_SOURCE:-0}" = 1 ]; then
	AIR=1 DRIVERS=softpipe,panfrost ../tools/mk-mesa.sh
	export REST=${REST:-1} GL=1
	exec ./build.sh
fi

if [ "$(cat $M/built-from 2>/dev/null)" != "$(cat ../tools/mesa/*.patch ../tools/mesa/redwood-drm/* | sha256sum)" ] ||
    ! grep -q panfrost $M/drivers 2>/dev/null; then
	DRIVERS=softpipe,panfrost ../tools/mk-mesa.sh
fi
# ... and the compiler library whenever anything it is built from changed (tools/mk-mesa.sh writes the same
# hash): its sources, the libdrm stand-in compiled into it, the patches. A driver built against a newer rwa_*
# contract than the library beside it reads one field as another, and a stale shim measures nothing
if [ "$(cat $M/built-from-air 2>/dev/null)" != "$(cat ../tools/mesa/air/* ../tools/mesa/redwood-drm/* ../tools/mesa/*.patch | sha256sum)" ]; then
	echo "build-gpu-y2s.sh: libredwoodair.dylib is older than what it is built from"
	AIR=1 DRIVERS=softpipe,panfrost ../tools/mk-mesa.sh
fi
cp $M/libOSMesa.8.dylib obj/
./mkeagl.py src/eagl_slots.txt $M/gl.xml $M/exported-gl.txt src/eagl.c > obj/eagl_gen.h
$DYN -dynamiclib -install_name /redwood/lib/libredwood-gl.dylib -Iobj -framework CoreFoundation -framework IOKit \
	-framework IOSurface -lobjc $M/libOSMesa.8.dylib -o obj/libredwood-gl.dylib src/eagl.c src/gl_osmesa.c
$DYN -framework CoreFoundation -framework IOKit $M/libOSMesa.8.dylib -o obj/gl_test src/gl_test.c
$DYN -framework IOKit -o obj/mali_test src/mali_test.c
# Metal (PLANS/05-metal.md): the compiler library, the driver as a library and as the bundle Metal's
# discovery loads, and the programs that drive it
[ -f $M/libredwoodair.dylib ] && cp $M/libredwoodair.dylib obj/
$DYN -dynamiclib -install_name /redwood/lib/libredwoodmetal.dylib -framework Foundation -framework IOKit \
	-framework Metal -lobjc -o obj/libredwoodmetal.dylib src/redwoodmetal.m src/redwooddrawable.m
$DYN -bundle -framework Foundation -framework IOKit -framework Metal -lobjc \
	-o obj/RedwoodMetal src/redwoodmetal.m src/redwooddrawable.m
$DYN -framework Foundation -framework IOKit -framework Metal -lobjc -o obj/metal_drv_test src/metal_drv_test.m
$DYN -framework CoreFoundation -framework IOKit -o obj/metal_props src/metal_props.c
# the log daemon: build.sh's own compile line is skipped on macOS (no ld64), so it is built here
# whenever it changes -- /menu (hand back to the loader) lives in it
$DYN -o obj/rwlogd src/rwlogd.c
cp obj/rwlogd ../prebuilt/userland/rwlogd   # the macOS path copies prebuilt/* into obj/, so that is where it must land
$DYN -o obj/clockd src/clockd.c
cp obj/clockd ../prebuilt/userland/clockd
# The macOS image path uses PREBUILT=1 below: refresh AOD's own tracked inputs
# too, so a fresh root never depends on an older data-volume tweak.
bash ../tools/aod/build.sh
cp ../out/aod/libredwood-alwayson.dylib ../prebuilt/userland/libredwood-alwayson.dylib
cp ../out/aod/aod-preview ../prebuilt/userland/aod-preview
# mali2metal's marker for scripts (src/m2m_mark.c; the tour, m2m.tour, uses it)
$DYN -o obj/m2m_mark src/m2m_mark.c
# preferences without Settings' UI (x1slte: WebKit's VP9/VP8 software decoders; src/prefset.c)
$DYN -framework CoreFoundation -o obj/prefset src/prefset.c
${LDID:-ldid} -Cadhoc -S obj/prefset 2>/dev/null || codesign -s - -f obj/prefset
cp obj/prefset ../prebuilt/userland/prefset
$DYN -framework Foundation -framework CoreMotion -o obj/redwood-motiond src/motion_wake.m
${LDID:-ldid} -Cadhoc -S obj/redwood-motiond 2>/dev/null || codesign -s - -f obj/redwood-motiond
cp obj/redwood-motiond ../prebuilt/userland/redwood-motiond
cp obj/m2m_mark ../prebuilt/userland/m2m_mark
$DYN -dynamiclib -install_name /redwood/lib/libredwood.dylib -framework CoreFoundation -framework IOKit -lobjc \
	-o obj/libredwood.dylib.new src/inject.c src/inject_sensors.c src/inject_location.c   # (sensors; locationd/CoreMotion compass)
$DYN -dynamiclib -install_name /redwood/lib/libredwood-sb.dylib -framework CoreFoundation -framework IOKit -lobjc \
	-o obj/libredwood-sb.dylib.new src/inject_sb.c src/inject_location.c
for lib in libredwood libredwood-sb; do
	[ -f ../prebuilt/userland/$lib.dylib.orig ] || [ ! -f ../prebuilt/userland/$lib.dylib ] || cp ../prebuilt/userland/$lib.dylib ../prebuilt/userland/$lib.dylib.orig
	mv obj/$lib.dylib.new ../prebuilt/userland/$lib.dylib
done
# process 1 (src/init.c), static against libmini as build.sh would with ld64; Apple's ld makes the same layout
STATIC="xnu-clang -arch arm64 -Os -static -nostdlib -ffreestanding -fno-stack-protector -fno-builtin"
$STATIC -Ilibmini -c libmini/mini.c -o obj/mini.o
$STATIC -c libmini/start.S -o obj/start.o
$STATIC -Ilibmini -Wl,-e,_start -Wl,-pagezero_size,0x100000000 -o obj/init.new src/init.c obj/mini.o obj/start.o
[ -f ../prebuilt/userland/init.orig ] || [ ! -f ../prebuilt/userland/init ] || cp ../prebuilt/userland/init ../prebuilt/userland/init.orig
cmp -s obj/init.new ../prebuilt/userland/init && rm obj/init.new || mv obj/init.new ../prebuilt/userland/init

REST=${REST:-1} GL=1 EXTRA="${EXTRA:-} obj/mali_test" ./build.sh
