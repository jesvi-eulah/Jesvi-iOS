#!/usr/bin/env python3
"""Derive y2s board constants from *stock* SM-G986B firmware images.

Usage:
  tools/y2s/stock-info.py dtb  <stock boot.img> [output-dtb]
  tools/y2s/stock-info.py dtbo <stock dtbo.img>
  tools/y2s/stock-info.py super <raw super image>   # output of simg2img super.img

Nothing in inputs/ is committed. The ROM dumps under inputs/y2s/probe-* are not
inputs to this tool: on this phone they are a different boot/DT/super layout.
"""
import re
import struct
import sys
from pathlib import Path

DTB_MAGIC = bytes.fromhex('d7b7ab1e')
LP_GEOMETRY_MAGIC = 0x616c4467
LP_HEADER_MAGIC = 0x414C5030


def dt_tables(data, tag):
    out = []
    i = 0
    while True:
        i = data.find(DTB_MAGIC, i)
        if i < 0:
            break
        w = struct.unpack_from('>8I', data, i)
        total, entry_size, count, entries_off = w[1], w[3], w[4], w[5]
        table = data[i:i + total]
        print(f'{tag} table {len(out)} at {i:#x}: {count} entries, {entry_size:#x} B each')
        for n in range(count):
            o = entries_off + n * entry_size
            size, off = struct.unpack_from('>II', table, o)
            ident, rev = struct.unpack_from('>II', table, o + 8)
            name = table[o + 16:o + entry_size].split(b'\0', 1)[0].decode(errors='replace')
            print(f'  {n}: {name!r} size={size:#x} off={off:#x} id={ident:#x} rev={rev:#x}')
            out.append((name, table[off:off + size]))
        i += max(total, 4)
    return out


def cmd_dtb(args):
    if len(args) not in (1, 2):
        raise SystemExit('usage: stock-info.py dtb <boot.img> [output-dtb]')
    path = Path(args[0])
    tables = dt_tables(path.read_bytes(), 'boot DTBH')
    if not tables:
        raise SystemExit('no DTBH table found')
    out = Path(args[1]) if len(args) == 2 else Path('inputs/y2s/stock-boot-dtb.img')
    out.write_bytes(tables[0][1])
    print(f'wrote {out} ({out.stat().st_size} bytes)')


def cmd_dtbo(args):
    if len(args) != 1:
        raise SystemExit('usage: stock-info.py dtbo <dtbo.img>')
    dt_tables(Path(args[0]).read_bytes(), 'DTBO')


def cmd_super(args):
    if len(args) != 1:
        raise SystemExit('usage: stock-info.py super <raw-super.img>')
    path = Path(args[0])
    size = path.stat().st_size
    with path.open('rb') as f:
        f.seek(0x1000)
        geom = struct.unpack('<II32sIII', f.read(52))
        if geom[0] != LP_GEOMETRY_MAGIC:
            raise SystemExit(f'bad LP geometry magic {geom[0]:#x}')
        print(f'geometry: metadata_max={geom[3]} slots={geom[4]} logical_block={geom[5]}')
        f.seek(0x3000)
        header = f.read(128)
        magic, major, minor, hsize = struct.unpack_from('<IHHI', header, 0)
        if magic != LP_HEADER_MAGIC:
            raise SystemExit(f'bad LP header magic {magic:#x}')
        tables_size = struct.unpack_from('<I', header, 44)[0]
        desc = {}
        for label, off in (('partitions', 80), ('extents', 92), ('groups', 104), ('blockdevs', 116)):
            desc[label] = struct.unpack_from('<III', header, off)
        print(f'header: v{major}.{minor} tables_size={tables_size:#x}')

        f.seek(0x3000 + hsize)
        tables = f.read(tables_size)
    t_off, n, es = desc['partitions']
    parts = []
    for i in range(n):
        e = tables[t_off + i * es:t_off + (i + 1) * es]
        name = e[:36].split(b'\0', 1)[0].decode()
        first_extent, num_extents = struct.unpack_from('<II', e, 40)
        parts.append((name, first_extent, num_extents))
    e_off, n, es = desc['extents']
    extents = []
    for i in range(n):
        e = tables[e_off + i * es:e_off + (i + 1) * es]
        sectors, typ, target_data, _ = struct.unpack_from('<QIQI', e, 0)
        extents.append((sectors, typ, target_data))

    end = 0
    for name, fe, ne in parts:
        for i in range(fe, fe + ne):
            sectors, _, target = extents[i]
            start, stop = target * 512, (target + sectors) * 512
            print(f'{name:12s} {start:#11x} .. {stop:#11x} ({stop - start} bytes)')
            end = max(end, stop)
    tail = (end + 0xFFFFF) & ~0xFFFFF
    print(f'super size:        {size:#x} ({size})')
    print(f'last logical end:  {end:#x} ({end})')
    print(f'1MiB-aligned tail: {tail:#x} ({tail})')
    print(f'free tail bytes:   {size - tail}')


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cmd, args = sys.argv[1], sys.argv[2:]
    {'dtb': cmd_dtb, 'dtbo': cmd_dtbo, 'super': cmd_super}[cmd](args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
