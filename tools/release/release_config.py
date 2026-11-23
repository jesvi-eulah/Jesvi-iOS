#!/usr/bin/env python3
"""release.conf: one preference file for local and CI release builds."""
import datetime
import os
from pathlib import Path
import re
import shutil
import tarfile
from manage import ROOT, profile

KEYS = {'NAME': 'Jesvi-iOS', 'VERSION': '0.0.0', 'TARGETS': 'x1slte', 'OUTPUTS': 'twrp restore',
        'MODE': 'fresh', 'IOS_DATA_GB': 'all', 'WRITES': 'false', 'BUNDLE': '', 'OUT': 'dist/release', 'MODS_DISABLE': ''}
OUTPUTS = ('twrp', 'preflight', 'restore', 'tar')


def load(path=None, overrides=()):
    path = Path(path or ROOT / 'release.conf')
    conf = dict(KEYS)
    for n, line in enumerate(path.read_text().splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        key, sep, value = line.partition('=')
        key = key.strip()
        if not sep or key not in KEYS:
            raise ValueError(f'{path.name}:{n}: unknown setting {key!r}')
        conf[key] = value.strip()
    for key in KEYS:
        if os.environ.get('JESVI_' + key):
            conf[key] = os.environ['JESVI_' + key]
    for item in overrides:
        key, sep, value = item.partition('=')
        if not sep or key not in KEYS:
            raise ValueError(f'--set expects KEY=value with KEY one of {", ".join(KEYS)}')
        conf[key] = value
    return check(conf)


def check(conf):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}', conf['NAME']):
        raise ValueError('NAME: letters, digits, . _ - only')
    if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+-]{0,31}', conf['VERSION']):
        raise ValueError('VERSION: letters, digits, . + - only')
    conf['TARGETS'] = conf['TARGETS'].replace(',', ' ').split()
    conf['OUTPUTS'] = conf['OUTPUTS'].replace(',', ' ').split()
    if not conf['TARGETS'] or not conf['OUTPUTS']:
        raise ValueError('TARGETS and OUTPUTS must not be empty')
    bad = [o for o in conf['OUTPUTS'] if o not in OUTPUTS]
    if bad:
        raise ValueError(f'unknown OUTPUTS {bad}; use {", ".join(OUTPUTS)}')
    if conf['MODE'] not in ('choose', 'update', 'fresh'):
        raise ValueError('MODE: choose, update or fresh')
    g = conf['IOS_DATA_GB'].strip().lower()
    if g != 'all' and not (g.isdigit() and 16 <= int(g) <= 112):
        raise ValueError('IOS_DATA_GB: all, or 16..112')
    conf['IOS_DATA_GB'] = g
    os.environ['JESVI_IOS_DATA_GB'] = g  # read by targets.data_bytes() in the image build and packaging
    if conf['WRITES'].lower() not in ('true', 'false'):
        raise ValueError('WRITES: true or false')
    conf['WRITES'] = conf['WRITES'].lower() == 'true'
    from targets import PLATFORM
    for m in conf['MODS_DISABLE'].split():
        if not (PLATFORM / 'mods' / m / 'module.prop').is_file():
            raise ValueError(f'MODS_DISABLE: no optional mod {m!r} in devices/exynos990/mods')
    out = (ROOT / conf['OUT']).resolve()
    if (ROOT / 'dist').resolve() not in (out, *out.parents):
        raise ValueError('OUT must be inside dist/')
    conf['OUT'] = out
    return conf


def names(conf, target, date=None):
    stamp = date or datetime.date.today().strftime('%Y%m%d')
    base = f'{conf["NAME"]}_{conf["VERSION"]}_{stamp}_{target}'
    install = base if conf['MODE'] == 'choose' else f'{conf["NAME"]}_{conf["VERSION"]}_{stamp}_{conf["MODE"]}_{target}'
    return {'twrp': install + ('' if conf['WRITES'] else '_preflight') + '.zip',
            'preflight': install + '_preflight.zip',
            'restore': f'{conf["NAME"]}-Restore_{conf["VERSION"]}_{stamp}_{target}'
                       + ('' if conf['WRITES'] else '_preflight') + '.zip',
            'tar': base + '_images.tar'}


def plan(conf):
    """[(target, output, path)] to build, plus [(target, reason)] skipped."""
    todo, skipped = [], []
    for target in conf['TARGETS']:
        d = profile(target)
        if d['status'] == 'unmaintained':
            skipped.append((target, 'no measured device profile yet (docs/release/porting.md)'))
            continue
        if target == 'y2s' and conf['MODE'] != 'fresh' and set(conf['OUTPUTS']) & {'twrp', 'preflight'}:
            raise ValueError('y2s TWRP requires MODE=fresh; use the loader for updates')
        n = names(conf, target)
        for out in dict.fromkeys(conf['OUTPUTS']):
            todo.append((target, out, conf['OUT'] / n[out]))
    return todo, skipped


def build(conf, dry_run=False):
    todo, skipped = plan(conf)
    for target, reason in skipped:
        print(f'SKIP {target}: {reason}')
    for target, out, path in todo:
        print(f'{"PLAN" if dry_run else "BUILD"} {target} {out:9} -> {path.relative_to(ROOT)}')
        if out in ('twrp', 'preflight'):
            print(f'  install mode={conf["MODE"]}; writes={conf["WRITES"] and out == "twrp"}')
    if dry_run:
        return 0 if todo else 1
    if not todo:
        raise ValueError('nothing to build for these TARGETS')
    from twrp_package import package, package_restore
    bundles = {}
    for target, out, path in todo:
        if out == 'restore':
            package_restore(target, path, conf['WRITES'])
            continue
        if target not in bundles:
            bundles[target] = bundle_for(conf, target)
        b = bundles[target]
        if out == 'tar':
            write_tar(b, path)
        else:
            # y2s's TWRP ZIP is first-install only; loader flashes carry updates.
            mode = 'fresh' if target == 'y2s' else conf['MODE']
            package(b, path, mode, conf['WRITES'] and out == 'twrp')
    print(f'Release files in {conf["OUT"].relative_to(ROOT)}; hardware qualification pending')
    return 0


def bundle_for(conf, target):
    if conf['BUNDLE']:
        b = Path(conf['BUNDLE'])
        b = b if b.is_absolute() else ROOT / b
        if not (b / 'manifest.json').is_file():
            raise ValueError(f'BUNDLE has no manifest.json: {b}')
        import json
        if json.loads((b / 'manifest.json').read_text()).get('device') != target:
            raise ValueError(f'BUNDLE was not built for {target}')
        return b
    if target != 'x1slte':
        raise ValueError(f'{target}: no image build adapter yet; set BUNDLE to a verified candidate')
    from local_build import build as local
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    out = ROOT / 'dist' / f'candidate-{target}-{stamp}'
    os.environ['JESVI_MODS_DISABLE'] = ' '.join(conf['MODS_DISABLE'].split())
    local(out, twrp=False, bundle_only=True)
    return out


def write_tar(bundle, path):
    from cache import digest
    if path.exists():
        raise ValueError(f'output already exists: {path.name}')
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = Path(str(path) + '.part')
    try:
        with tarfile.open(pending, 'w') as tar:
            for name in ('boot.img', 'recovery.img', 'system.apfs', 'manifest.json', 'SHA256SUMS'):
                tar.add(bundle / name, arcname=name, recursive=False)
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    Path(str(path) + '.sha256').write_text(f'{digest(path)}  {path.name}\n')
