#!/bin/bash
# Build a development-only y2s (SM-G986B) XNUP payload and recovery image.
#
# This is NOT a flashable or qualified release: it uses the stock G986B DTBH and
# super/PIT geometry. Board evidence is recorded in docs/release/device-evidence-y2s.md,
# but there is no authenticated device report or installer EXIT=0 qualification.
# It exists so the full build chain can be reproduced and reviewed.
#
# Inputs expected in the checkout:
#   out/y2s/Mu-y2s.img          built by Mu-Silicium (see tools/y2s/README.md)
#   out/experimental/y2s/mach.y2s
#   userland/root.apfs
#   xnuloader/identity.h, xnuloader/menu_font.h
#
# Outputs:
#   out/y2s/y2s-embed.img       UEFI Android boot image with the XNUP payload spliced in
#   out/y2s/y2s-payload.bin     XNUP payload
#   out/y2s/y2s-boot.img        Android boot head for the flash plan (not qualified)
#   out/y2s/y2s-recovery.img    recovery-sized image with kernel/root and AVB footer
set -euo pipefail
cd "$(dirname "$0")/../.."

die() { echo "build-image.sh: $*" >&2; exit 1; }
# shellcheck disable=SC1091
. common/devices/y2s.conf

EMBED=out/y2s/y2s-embed.img
PAYLOAD=out/y2s/y2s-payload.bin
BOOT=out/y2s/y2s-boot.img
RECOVERY=out/y2s/y2s-recovery.img
UEFI=${UEFI:-out/y2s/Mu-y2s.img}
KERNEL=${KERNEL:-out/experimental/y2s/mach.y2s}
ROOT=${ROOT:-userland/root.apfs}
PAYLOAD_AT=$((0x100870))
PAYLOAD_MAX=$((0x80000))
BOOTLINE_FILE=${BOOTLINE_FILE:-devices/exynos990/y2s/y2s.cmdline}
AVB=${AVBTOOL:-inputs/tools/avbtool.py}
KEY=${AVB_TEST_KEY:-inputs/tools/testkey_rsa4096.pem}

for f in "$UEFI" "$KERNEL" "$ROOT" "$BOOTLINE_FILE" "$DTBH_FILE" "$AVB" "$KEY"; do
	[ -f "$f" ] || die "missing $f"
done
# x1slte learned this the hard way: a root from plain build.sh boots but gives
# black wallpaper, stutter and broken apps because the GL/Mesa layer is absent.
# Refuse to package that root unless explicitly overridden for a test image.
if [ "${ROOT_OK:-0}" != 1 ] && ! { LC_ALL=C grep -q -a 'libOSMesa' "$ROOT" &&
	LC_ALL=C grep -q -a 'libredwood-gl.dylib' "$ROOT"; }; then
	die "$ROOT has no GPU layer (libOSMesa / libredwood-gl.dylib); rebuild it with userland/build-gpu-y2s.sh (ROOT_OK=1 to override)"
fi
mkdir -p out/y2s
cp "$UEFI" "$EMBED"

printf -v ROOT_OFF_HEX '0x%x' "$((ROOT_SUPER_OFF))"
printf -v ROOT_LEN_HEX '0x%x' "$((ROOT_SUPER_LEN))"
printf -v TAIL_HEX '0x%x' "$((SUPER_TAIL_START))"
printf -v SUPER_ROOT_HEX '0x%x' "$((ROOT_SUPER_LEN))"
printf -v UD_LEN_HEX '0x%x' "$((USERDATA_PARTITION_SIZE))"

cmdline=$(<"$BOOTLINE_FILE")
cmdline=${cmdline//@ROOT_PART@/$ROOT_PART}
cmdline=${cmdline//@ROOT_OFF@/$ROOT_OFF_HEX}
cmdline=${cmdline//@ROOT_LEN@/$ROOT_LEN_HEX}
case " $cmdline " in
	*" cpus="*" cpumask="* | *" cpumask="*" cpus="*) die "cpus= and cpumask= together make XNU panic" ;;
	*" ufs_win="*) die "y2s uses ufs_userdata_all=1; ufs_win= needs an explicit window decision" ;;
esac
[ ${#cmdline} -le 550 ] || die "boot line is ${#cmdline} characters (max 550)"

# The loader must be compiled for this board: GICv2, the stock super tail and the
# stock system/userdata write windows. Prebuilt/loader.efi is not y2s-qualified.
env GIC_V2=1 CELLULAR_RESERVE_CP="${CELLULAR_RESERVE_CP-1}" \
	SUPER_TAIL_START="$TAIL_HEX" SUPER_ROOT_LEN="$SUPER_ROOT_HEX" \
	USERDATA_WIN_OFF=0x0 USERDATA_WIN_LEN="$UD_LEN_HEX" \
	Y2S_LOG_FLASH=1 \
	xnuloader/build.sh >/dev/null
cp xnuloader/loader.efi out/y2s/loader-y2s.efi

rsize=$(printf '%x' "$(wc -c < "$ROOT")")
python3 xnuloader/mkpayload.py -o "$PAYLOAD" loader.efi=xnuloader/loader.efi \
	--kpart recovery --koff 2000000 --rpart recovery --roff 3400000 --rsize "$rsize" \
	--cmdline "$cmdline"

python3 - "$EMBED" "$PAYLOAD" "$PAYLOAD_AT" "$PAYLOAD_MAX" <<'PY'
import sys
embed, payload, at, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
img = bytearray(open(embed, 'rb').read())
p = open(payload, 'rb').read()
assert img[at:at + 4] == b'XNUP' or img[at:at + limit] == b'\xff' * limit, 'no XNUP slot in %s' % embed
assert len(p) <= limit, 'payload too large'
img[at:at + limit] = b'\xff' * limit
img[at:at + len(p)] = p
open(embed, 'wb').write(img)
PY

python3 - "$EMBED" "$KERNEL" "$ROOT" "$RECOVERY" "$RECOVERY_PARTITION_SIZE" <<'PY'
import sys
embed, kernel, root, out, part_size = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
e = open(embed, 'rb').read()
k = open(kernel, 'rb').read()
r = open(root, 'rb').read()
assert len(e) <= 0x1000000 and len(k) <= 0x1400000
assert 0x3400000 + len(r) <= part_size
assert k[:4] == bytes.fromhex('cffaedfe'), 'kernel is not an ARM64 Mach-O'
img = bytearray(part_size)
img[:len(e)] = e
img[0x2000000:0x2000000 + len(k)] = k
img[0x3400000:0x3400000 + len(r)] = r
open(out, 'wb').write(img)
PY

# sboot expects a Samsung DT table (d7b7ab1e), not a bare FDT. Use the stock
# G986B table and recompute the Android header id over the replaced section.
python3 - "$RECOVERY" "$DTBH_FILE" "$BOOT" <<'PY'
import hashlib, struct, sys
p, dtbh_path, boot_path = sys.argv[1], sys.argv[2], sys.argv[3]
dtbh = open(dtbh_path, 'rb').read()
d = bytearray(open(p, 'rb').read())
assert d[:8] == b'ANDROID!' and struct.unpack_from('<I', d, 40)[0] == 2
assert dtbh[:4] == bytes.fromhex('d7b7ab1e')
page = struct.unpack_from('<I', d, 36)[0]
align = lambda n: (n + page - 1) // page * page
ks, rs, ss = (struct.unpack_from('<I', d, o)[0] for o in (8, 16, 24))
rec = struct.unpack_from('<I', d, 1632)[0]
dsz = struct.unpack_from('<I', d, 1648)[0]
koff = page
roff = koff + align(ks)
soff = roff + align(rs)
recoff = soff + align(ss)
doff = recoff + align(rec)
end = doff + align(dsz)
assert end <= 0x2000000, 'boot image overlaps the kernel slot'
d[doff:end] = bytes(end - doff)
d[doff:doff + len(dtbh)] = dtbh
struct.pack_into('<I', d, 1648, len(dtbh))
struct.pack_into('<Q', d, 1652, 0x10000000)
assert doff + align(len(dtbh)) <= 0x1000000
h = hashlib.sha1()
for off, n in ((koff, ks), (roff, rs), (soff, ss), (recoff, rec), (doff, len(dtbh))):
    h.update(bytes(d[off:off + n]))
    h.update(struct.pack('<I', n))
d[576:576 + 32] = h.digest().ljust(32, b'\0')
open(p, 'wb').write(d)
n = (doff + align(len(dtbh)) + 4095) // 4096 * 4096
assert n < 0x1000000
open(boot_path, 'wb').write(d[:n])
PY

# sboot needs an AVB hash footer even with verification disabled. The hash covers
# only the boot head; the kernel, root.apfs and log are outside the first 16 MiB.
python3 - "$RECOVERY" out/y2s/.avb-head.img <<'PY'
import struct, sys
d = open(sys.argv[1], 'rb').read()
page = struct.unpack_from('<I', d, 36)[0]
align = lambda n: (n + page - 1) // page * page
ks, rs, ss = (struct.unpack_from('<I', d, o)[0] for o in (8, 16, 24))
rec, dsz = struct.unpack_from('<I', d, 1632)[0], struct.unpack_from('<I', d, 1648)[0]
n = page + align(ks) + align(rs) + align(ss) + align(rec) + align(dsz)
n = (n + 4095) // 4096 * 4096
assert n < 0x1000000
open(sys.argv[2], 'wb').write(d[:n])
PY
python3 -I "$AVB" add_hash_footer --image out/y2s/.avb-head.img \
	--partition_size "$RECOVERY_PARTITION_SIZE" --partition_name recovery \
	--algorithm SHA256_RSA4096 --key "$KEY" --rollback_index 1
# Put the kernel and root.apfs back, but leave the AVB footer at the partition
# end alone: copying from 0x2000000 to EOF would overwrite the footer.
python3 - out/y2s/.avb-head.img "$RECOVERY" "$KERNEL" "$ROOT" <<'PY'
import sys
out_path, full_path, kernel_path, root_path = sys.argv[1:5]
h = bytearray(open(out_path, 'rb').read())
full = open(full_path, 'rb').read()
kernel = open(kernel_path, 'rb').read()
root = open(root_path, 'rb').read()
assert len(h) == len(full)
h[0x2000000:0x2000000 + len(kernel)] = kernel
h[0x3400000:0x3400000 + len(root)] = root
assert h[-64:-60] == b'AVBf', 'AVB footer was overwritten'
open(full_path, 'wb').write(h)
PY
rm -f out/y2s/.avb-head.img

echo "build-image: $PAYLOAD"
echo "build-image: $EMBED"
echo "build-image: $BOOT"
echo "build-image: $RECOVERY ($RECOVERY_PARTITION_SIZE bytes)"
