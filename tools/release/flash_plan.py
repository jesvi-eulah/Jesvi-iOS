#!/usr/bin/env python3
"""Verify a local candidate and produce a read-only installation plan.

Deliberately contains no adb, fastboot, Odin, Heimdall, dd or block-write call.
The board's first-install and recovery procedure still needs hardware qualification.
"""
import argparse
import json
from pathlib import Path
import sys
from cache import digest
from images import android_head, apfs, recovery, regular
from manage import ROOT, profile


def verify(bundle):
    regular(bundle / 'manifest.json')
    m = json.loads((bundle / 'manifest.json').read_text())
    if m.get('schema') != 1 or m.get('kind') != 'private-development-candidate' or m.get('installer_validated') is not False:
        raise ValueError('unknown or unqualified manifest format')
    if m.get('layout') != 'ios-only-v1':
        raise ValueError('unknown storage layout')
    d = profile(m['device'])
    # Only boards with a measured layout and a complete image validator may be
    # packaged. y2s's validator uses the same checks against stock geometry.
    if d['id'] not in ('x1slte', 'y2s'):
        raise ValueError('no image validator for this board')
    if digest(ROOT / f'devices/exynos990/{d["id"]}/device.json') != m['device_profile_sha256']:
        raise ValueError('device profile does not match this candidate')
    expected = {'boot.img': 'boot', 'recovery.img': 'recovery', 'system.apfs': 'super'}
    if set(m['files']) != set(expected):
        raise ValueError('unexpected/missing image; only boot, recovery and system are allowed')
    for name, part in expected.items():
        f = m['files'][name]
        p = regular(bundle / name)
        limit = d['layout']['system_max_bytes'] if part == 'super' else d['partitions'][part]
        if f.get('partition') != part or f.get('offset') != 0:
            raise ValueError(f'invalid write destination for {name}')
        if not 0 < f['bytes'] <= limit or p.stat().st_size != f['bytes'] or digest(p) != f['sha256']:
            raise ValueError(f'size/checksum mismatch: {name}')
    recovery(bundle / 'recovery.img', d)
    end = android_head(bundle / 'boot.img')
    if (bundle / 'boot.img').stat().st_size != end:
        raise ValueError('boot image has unexpected trailing data')
    with (bundle / 'recovery.img').open('rb') as f:
        if f.read(end) != (bundle / 'boot.img').read_bytes():
            raise ValueError('boot head does not match recovery')
    apfs(bundle / 'system.apfs', d['layout']['system_max_bytes'])
    sums = regular(bundle / 'SHA256SUMS').read_text().splitlines()
    expected_sums = [f'{digest(bundle / name)}  {name}'
                     for name in sorted(expected) + ['manifest.json']]
    if sums != expected_sums:
        raise ValueError('SHA256SUMS does not match the complete candidate')
    return m, d


def match_report(d, report):
    # A report is evidence supplied by a tester, not an authenticated device probe.
    if report.get('model') not in d['models'] or report.get('product') not in d['recovery_products']:
        raise ValueError('model/product mismatch; same SoC is insufficient')
    if report.get('bootloader') not in d['bootloaders']:
        raise ValueError('unqualified bootloader')
    if report.get('partitions') != d['partitions']:
        raise ValueError('partition geometry mismatch (including userdata capacity)')
    if report.get('environment') != 'twrp' or report.get('root') is not True:
        raise ValueError('first-install plan requires a root TWRP environment')
    if report.get('mounted_targets') != []:
        raise ValueError('target partitions must be unmounted; missing mount evidence is a failure')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['verify', 'plan'])
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--device-report', type=Path)
    a = p.parse_args()
    m, d = verify(a.bundle)
    print('Checksums and image structure verified. This does not prove bootability or authenticity.')
    if a.command == 'plan':
        if a.device_report is None:
            raise ValueError('plan needs --device-report; see docs/release/flashing.md')
        match_report(d, json.loads(a.device_report.read_text()))
        print(json.dumps({'device': d['id'], 'executable': False,
                          'intended_order': ['super (system)', 'recovery (runtime replaces TWRP)', 'boot (last)'],
                          'first_boot': 'requires previously initialized HFSX; boot halts on missing or damaged data',
                          'protected': json.loads((ROOT / 'devices/exynos990/platform.json').read_text())['protected_partitions'],
                          'blocked_by': ['first install / rollback / power-loss tests',
                                         'boot head AVB behavior qualification',
                                         'authenticated device and backup verification']}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f'run: {exc}')
