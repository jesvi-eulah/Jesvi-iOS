#!/usr/bin/env python3
"""Print the physical partition map from a Samsung PIT (y2s bring-up helper).

Usage: tools/y2s/pit.py path/to/foo.pit [NAME ...]

The PIT is stock-firmware evidence only. The running custom ROM on the y2s
phone has a different by-name map, so never use live /dev/block/by-name offsets
for the port.
"""
import struct
import sys
from pathlib import Path

MAGIC = 0x12349876
HEADER = 0x40
ENTRY = 0x84


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    data = Path(sys.argv[1]).read_bytes()
    magic, count = struct.unpack_from('<II', data, 0)
    if magic != MAGIC:
        raise SystemExit(f'not a Samsung PIT: magic {magic:#x}')
    model = data[8:40].split(b'\0', 1)[0].decode(errors='replace')
    print(f'PIT model={model} entries={count}')
    wanted = [x.upper() for x in sys.argv[2:]]
    for n in range(count):
        off = HEADER + n * ENTRY
        if off + ENTRY > len(data):
            break
        name = data[off:off + 32].split(b'\0', 1)[0].decode(errors='replace')
        filename = data[off + 32:off + 64].split(b'\0', 1)[0].decode(errors='replace')
        block_sectors, ident, ptype, flags = struct.unpack_from('<IIII', data, off + 0x64)
        start, blocks = struct.unpack_from('<II', data, off + 0x74)
        if not block_sectors or not name:
            continue  # trailing signer/metadata pseudo-entry
        sector = 512
        block = block_sectors * sector
        if wanted and name.upper() not in wanted:
            continue
        print(f'{name:20s} file={filename:22s} id={ident:#04x} type={ptype:#04x} flags={flags:#04x} '
              f'start={start * block:#x} size={blocks * block:#x} '
              f'({blocks * block} bytes, {start} start-blocks, {blocks} size-blocks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
