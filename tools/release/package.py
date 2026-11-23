#!/usr/bin/env python3
"""Assemble a PRIVATE development candidate. Never a flashable release ZIP.

No arbitrary globs: exactly the three images plus provenance/checksums. The boot
head is derived from recovery's validated header, never from the raw UEFI embed.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from cache import digest
from images import android_head, apfs, recovery, hfs_kit
from manage import ROOT, profile


def package(device, dest):
    d = profile(device)
    if device not in ('x1slte', 'y2s'):
        raise ValueError('no packaging adapter for this unqualified board')
    dest = dest.absolute()
    if dest.exists():
        raise ValueError('destination already exists; use a new candidate directory')
    # x1slte keeps its long-standing paths. y2s has its own stock-geometry
    # recovery image and a debloated sysimage tree; never share the x1slte input.
    rec = ROOT / ('out/y2s/y2s-recovery.img' if device == 'y2s' else 'out/x1slte-recovery.img')
    system = ROOT / 'userland/system.apfs'
    recovery(rec, d)
    apfs(system, d['layout']['system_max_bytes'])
    if system.stat().st_size > d['layout']['system_max_bytes']:
        raise ValueError('system image exceeds its slot')
    import targets
    _data = targets.data_bytes(d['partitions']['userdata'])
    hfs_kit(targets.kit_path(ROOT, _data, d['partitions']['userdata']), _data)
    # An external tool/input ledger is mandatory even for private candidates.
    ledger = ROOT / 'inputs/private-inputs.lock.json'
    if not ledger.is_file():
        raise ValueError('missing inputs/private-inputs.lock.json (build.sh lock-inputs)')
    from private_inputs import verify
    verify()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.candidate-', dir=dest.parent))
    try:
        shutil.copyfile(rec, tmp / 'recovery.img')
        shutil.copyfile(system, tmp / 'system.apfs')
        with rec.open('rb') as f:
            (tmp / 'boot.img').write_bytes(f.read(android_head(rec)))
        files = {}
        for name, part in [('boot.img', 'boot'), ('recovery.img', 'recovery'), ('system.apfs', 'super')]:
            p = tmp / name
            files[name] = {'partition': part, 'offset': 0, 'bytes': p.stat().st_size, 'sha256': digest(p)}
        manifest = {'schema': 1, 'kind': 'private-development-candidate', 'device': device,
                    'installer_validated': False, 'layout': 'ios-only-v1', 'files': files,
                    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)),
                    'device_profile_sha256': digest(ROOT / f'devices/exynos990/{device}/device.json'),
                    'private_inputs_sha256': digest(ledger),
                    'notice': 'Contains locally supplied proprietary inputs. Do not publish. Structural checks are not hardware qualification.'}
        (tmp / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        names = sorted(files) + ['manifest.json']
        (tmp / 'SHA256SUMS').write_text(''.join(f'{digest(tmp / n)}  {n}\n' for n in names))
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    print(f'Private candidate: {dest}; installer is NOT qualified')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', default='x1slte')
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        package(a.device, a.output)
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f'package: {e}')
