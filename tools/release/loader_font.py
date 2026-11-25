#!/usr/bin/env python3
"""Generate the boot menu font from the pinned XNU source used by this build."""
import json
import os
from pathlib import Path
import re
from manage import ROOT


def kernel_metadata(root, device=None):
    """build.json of the kernel ci/build-kernel.sh made for this target (x1slte: out/kernel, others: out/experimental/<id>)."""
    device = device or os.environ.get('JESVI_TARGET', 'x1slte')
    device = 'y2s' if device == 'z3s' else device  # z3s boots the shared y2s kernel
    path = root / ('out/kernel' if device == 'x1slte' else f'out/experimental/{device}') / 'build.json'
    return json.loads(path.read_text())


def generate(root, device=None):
    metadata = kernel_metadata(root, device)
    key = metadata['kernel_source_key']
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise ValueError('invalid kernel source key')
    source = root / '.cache/release-kernel' / key / 'osfmk/console/iso_font.c'
    text = source.read_text()
    declaration = 'unsigned char iso_font[256 * 16] = {'
    notices, body = text.split(declaration, 1)
    body = body.split('};', 1)[0]
    data = re.findall(r'0x([0-9a-fA-F]{2})', body)
    if len(data) != 4096:
        raise ValueError('pinned XNU console font has unexpected geometry')
    result = notices + '/* Generated from pinned XNU for the loader; retain source notices above. */\n'
    result += 'static const unsigned char menu_font[256 * 16] = {\n'
    for at in range(0, len(data), 16):
        result += '    ' + ', '.join('0x' + x for x in data[at:at+16]) + ',\n'
    result += '};\n'
    destination = root / 'xnuloader/menu_font.h'
    pending = destination.with_suffix('.h.new')
    pending.write_text(result)
    pending.replace(destination)
    print('Loader menu font generated from pinned XNU console font')

if __name__ == '__main__':
    generate(ROOT)
