#!/usr/bin/env python3
"""Package locally built y2s images as a PRIVATE read-only manifest.

This is a legacy diagnostic helper, not the flashable installer path: that is
`./build.sh twrp --bundle ... --mode fresh`. It does not touch the x1slte
release gates. y2s's device profile is `development` with measured geometry,
but the output manifest is not flashable, is not an installer profile and makes
no qualification claim. It keeps generated artifacts with their hashes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/release'))
from images import android_head, apfs, regular  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    p = regular(path)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def conf_value(name):
    text = (ROOT / 'common/devices/y2s.conf').read_text()
    m = re.search(rf'^{name}=([^\n#]+)', text, re.M)
    if not m:
        raise ValueError(f'{name} missing from y2s.conf')
    return int(m.group(1).strip(), 0)


def validate(bundle, system_max):
    boot = bundle / 'boot.img'
    rec = bundle / 'recovery.img'
    sysimg = bundle / 'system.apfs'
    end = android_head(boot)
    if boot.stat().st_size != end:
        raise ValueError('boot.img has trailing data')
    with rec.open('rb') as f:
        if f.read(end) != boot.read_bytes():
            raise ValueError('boot head does not match recovery')
    data = rec.read_bytes()
    if len(data) != conf_value('RECOVERY_PARTITION_SIZE'):
        raise ValueError('recovery size does not match stock PIT')
    if data[-64:-60] != b'AVBf':
        raise ValueError('AVB footer missing')
    if data[0x2000000:0x2000004] != bytes.fromhex('cffaedfe'):
        raise ValueError('kernel missing from recovery')
    apfs(sysimg, system_max)
    return {'boot': digest(boot), 'recovery': digest(rec), 'system': digest(sysimg)}


def package(dest, system_max):
    dest = dest.absolute()
    if dest.exists():
        raise ValueError('destination already exists; use a new candidate directory')
    source = {
        'boot.img': ROOT / 'out/y2s/y2s-boot.img',
        'recovery.img': ROOT / 'out/y2s/y2s-recovery.img',
        'system.apfs': ROOT / 'userland/system.apfs',
    }
    for p in source.values():
        regular(p)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.y2s-candidate-', dir=dest.parent))
    try:
        for name, p in source.items():
            shutil.copyfile(p, tmp / name)
        hashes = validate(tmp, system_max)
        manifest = {
            'schema': 1,
            'kind': 'private-y2s-development-candidate',
            'device': 'y2s',
            'status': 'development',
            'installer_validated': False,
            'executable': False,
            'created_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)),
            'root_source': 'sysimage-y2s (default debloated selector; Y2S_FULL_ROOT=1 only for diagnostics)',
            'stock_geometry': {
                'super_tail_start': hex(conf_value('SUPER_TAIL_START')),
                'system_window': [hex(conf_value('ROOT_SUPER_OFF')), hex(conf_value('ROOT_SUPER_LEN'))],
                'userdata_window': [0, hex(conf_value('USERDATA_PARTITION_SIZE'))],
                'recovery_partition_size': conf_value('RECOVERY_PARTITION_SIZE'),
            },
            'files': {
                'boot.img': {'partition': 'boot', 'offset': 0,
                             'bytes': (tmp / 'boot.img').stat().st_size, 'sha256': hashes['boot']},
                'recovery.img': {'partition': 'recovery', 'offset': 0,
                                 'bytes': (tmp / 'recovery.img').stat().st_size, 'sha256': hashes['recovery']},
                'system.apfs': {'partition': 'super', 'offset': 0,
                                'bytes': (tmp / 'system.apfs').stat().st_size, 'sha256': hashes['system']},
            },
            'plan': {
                'executable': False,
                'update_path': 'Log access (USB): ./y2s.sh rflash or ./y2s.sh tflash',
                'intended_order': ['super (system)', 'recovery', 'boot (last)'],
                'blocked_by': [
                    'board evidence is recorded but no authenticated device report exists',
                    'no recorded installer qualification for y2s (one EXIT=0 is not qualification)',
                    'stock PIT geometry is build evidence, not flash authorization',
                ],
            },
            'notice': 'Private development candidate. Structural checks only; no flashing or boot claim.',
        }
        (tmp / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        names = sorted(manifest['files']) + ['manifest.json']
        (tmp / 'SHA256SUMS').write_text(''.join(f'{digest(tmp / n)}  {n}\n' for n in names))
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    print(f'Private y2s candidate: {dest}; development, read-only, not flashable')


def show_plan(bundle):
    m = json.loads(regular(bundle / 'manifest.json').read_text())
    if m.get('kind') != 'private-y2s-development-candidate' or m.get('executable') is not False:
        raise ValueError('not a read-only y2s development candidate')
    print(json.dumps(m['plan'], indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    pk = sub.add_parser('package')
    pk.add_argument('--output', required=True, type=Path)
    pk.add_argument('--system-max', type=lambda x: int(x, 0), default=None)
    pl = sub.add_parser('plan')
    pl.add_argument('--bundle', required=True, type=Path)
    a = p.parse_args()
    try:
        if a.command == 'package':
            package(a.output, a.system_max or conf_value('ROOT_SUPER_LEN'))
        else:
            show_plan(a.bundle)
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f'y2s candidate: {e}')
