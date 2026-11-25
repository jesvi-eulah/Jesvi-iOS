#!/usr/bin/env python3
"""Per-device targets, modelled on UN1CA/ExtremeROM.

    devices/exynos990/platform.conf        shared Exynos 990 settings (PLATFORM_*)
    devices/exynos990/patches/<mod>/       mods every 990 target gets
    devices/exynos990/mods/<mod>/          optional features (release.conf MODS_DISABLE)
    devices/exynos990/<id>/target.conf     one phone: identity, display, camera, modem, chips (TARGET_*)
    devices/exynos990/<id>/patches/<mod>/  mods only this phone gets

Config files are plain `KEY="value"` lines, so bash can source them too.
Order: platform.conf, then the inherited target (TARGET_INHERIT), then the
target; later values win. A mod folder holds module.prop and any of: bootargs
(extra boot-line words), root/ and system/ (files copied into the two iOS
images), customize.sh (run with the merged config), disable (skip it).
Mods apply platform patches -> target patches -> mods, each sorted by name.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / 'devices/exynos990'
BOOTLINE_MAX = 550  # the loader adds ~52 characters; XNU keeps 607

REQUIRED = ('TARGET_NAME', 'TARGET_CODENAME', 'TARGET_ASSERT_MODEL', 'TARGET_RECOVERY_PRODUCTS')
DEFAULTS = {
    'TARGET_STATUS': 'unmaintained',   # unmaintained | development | validated
    'TARGET_INHERIT': '',
    'TARGET_ASSERT_BOOTLOADER': '',
    # hardware (documentation for users, and inputs to boot-args/mods)
    'TARGET_RAM_GB': '', 'TARGET_STORAGE_GB': '',
    'TARGET_DISPLAY_RESOLUTION': '', 'TARGET_DISPLAY_REFRESH_RATES': '60', 'TARGET_DISPLAY_CUTOUT': 'center',
    'TARGET_PANEL': '', 'TARGET_TOUCH': '',
    'TARGET_MODEM': 'lte',             # lte | 5g | auto (LTE and 5G models share the target) | none
    'TARGET_WIFI_CHIP': '', 'TARGET_NFC_CHIP': '', 'TARGET_FINGERPRINT': '',
    'TARGET_HAS_SPEN': 'false', 'TARGET_HAS_ESIM': 'false',
    'TARGET_CAMERA': '',               # camera driver profile: s20 -> cam_s20=1
    'TARGET_HAPTIC_CHIP': '', 'TARGET_TORCH_CHIP': '', 'TARGET_SENSORHUB': '',
    # build
    'TARGET_BOARD_CONF': '',           # loader memory map, common/devices/<board>.conf
    'TARGET_UEFI': '', 'TARGET_BOOTARGS': '', 'TARGET_FIRMWARE': '',
    'TARGET_DISABLE_MODS': '',        # board-specific opt-out (y2s: softpasscode)
    'TARGET_PACKAGE_NAME': '',         # ZIP name for the board (x1slte -> x1s: one ZIP for G980F + G981B); default codename
    # Android side (ExtremeROM values), used by Jesvi-iOS-Restore and checks
    'TARGET_SUPER_GROUP_NAME': 'group_basic', 'TARGET_SUPER_PARTITION_SIZE': '', 'TARGET_SUPER_GROUP_SIZE': '',
}
PLATFORM_KEYS = ('PLATFORM_SOC', 'PLATFORM_XNU_TAG', 'PLATFORM_IOS_BUILD', 'PLATFORM_GIC', 'PLATFORM_BOOTARGS',
                 'PLATFORM_PROTECTED_PARTITIONS')
SAFE_VALUE = re.compile(r'[^`$\\\n]*')
NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,31}')


def read_conf(path, allowed_prefixes):
    out = {}
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        key, sep, raw = s.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not key.startswith(allowed_prefixes):
            raise ValueError(f'{path}:{n}: expected {"/".join(allowed_prefixes)}NAME="value"')
        words = shlex.split(raw, comments=True)
        if len(words) > 1:
            raise ValueError(f'{path}:{n}: quote values that contain spaces')
        value = words[0] if words else ''
        if not SAFE_VALUE.fullmatch(value):
            raise ValueError(f'{path}:{n}: no $, backticks or backslashes in values')
        out[key] = value
    return out


def target_dir(name):
    if not NAME.fullmatch(name):
        raise ValueError(f'invalid target name: {name!r}')
    return PLATFORM / name


def names():
    return sorted(p.parent.name for p in PLATFORM.glob('*/target.conf'))


def load(name, _seen=()):
    """Merged config: PLATFORM_* + TARGET_* with defaults; raises on missing/unknown keys."""
    if name in _seen:
        raise ValueError(f'TARGET_INHERIT loop: {" -> ".join(_seen + (name,))}')
    conf = dict(DEFAULTS)
    conf.update(read_conf(PLATFORM / 'platform.conf', ('PLATFORM_',)))
    own = read_conf(target_dir(name) / 'target.conf', ('TARGET_',))
    if own.get('TARGET_INHERIT'):
        parent = load(own['TARGET_INHERIT'], _seen + (name,))
        conf.update({k: v for k, v in parent.items() if k not in ('TARGET_STATUS',)})
        conf['TARGET_PARENT_DIRS'] = parent['TARGET_PARENT_DIRS'] + ' ' + own['TARGET_INHERIT']
    else:
        conf['TARGET_PARENT_DIRS'] = ''
    conf['TARGET_STATUS'] = 'unmaintained'
    conf.update(own)
    unknown = set(own) - set(DEFAULTS) - set(REQUIRED)
    if unknown:
        raise ValueError(f'{name}: unknown settings {sorted(unknown)}')
    for k in REQUIRED + PLATFORM_KEYS:
        if not conf.get(k):
            raise ValueError(f'{name}: {k} is required')
    if conf['TARGET_CODENAME'] != name:
        raise ValueError(f'{name}: TARGET_CODENAME must be {name}')
    if conf['TARGET_STATUS'] not in ('unmaintained', 'development', 'validated'):
        raise ValueError(f'{name}: bad TARGET_STATUS')
    if conf['TARGET_MODEM'] not in ('lte', '5g', 'auto', 'none'):
        raise ValueError(f'{name}: TARGET_MODEM is lte, 5g, auto or none')
    for k in ('TARGET_HAS_SPEN', 'TARGET_HAS_ESIM'):
        if conf[k] not in ('true', 'false'):
            raise ValueError(f'{name}: {k} is true or false')
    if conf['TARGET_STATUS'] != 'unmaintained':
        for k in ('TARGET_BOARD_CONF', 'TARGET_ASSERT_BOOTLOADER'):
            if not conf[k]:
                raise ValueError(f'{name}: {k} is required for a buildable target')
        if not (ROOT / conf['TARGET_BOARD_CONF']).is_file():
            raise ValueError(f'{name}: board config missing: {conf["TARGET_BOARD_CONF"]}')
    return conf


def module_dirs(conf):
    """Mod folders in application order (platform patches, target chain patches, mods)."""
    out = []
    def add(base):
        if base.is_dir():
            out.extend(sorted(p for p in base.iterdir() if p.is_dir()))
    add(PLATFORM / 'patches')
    for t in conf['TARGET_PARENT_DIRS'].split() + [conf['TARGET_CODENAME']]:
        add(target_dir(t) / 'patches')
    add(PLATFORM / 'mods')
    return out


def module_info(path):
    prop = {}
    f = path / 'module.prop'
    if not f.is_file():
        raise ValueError(f'{path.relative_to(ROOT)}: module.prop missing')
    for line in f.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            prop[k.strip()] = v.strip()
    if prop.get('id') != path.name:
        raise ValueError(f'{path.relative_to(ROOT)}: module.prop id must be {path.name}')
    return prop


def active_modules(conf, disabled=()):
    """[(path, prop)] that apply to this target: not disabled, targets= matches, requires= true."""
    out = []
    for p in module_dirs(conf):
        prop = module_info(p)
        if (p / 'disable').exists() or (p.parent.name == 'mods' and p.name in disabled):
            continue
        only = prop.get('targets', '').split()
        if only and conf['TARGET_CODENAME'] not in only:
            continue
        need = prop.get('requires', '').split()
        if any(conf.get(k) in ('', 'false', 'none') for k in need):
            continue
        out.append((p, prop))
    return out


def data_bytes(device_userdata):
    """iOS's data volume size in bytes: JESVI_IOS_DATA_GB (release.conf IOS_DATA_GB) GB, 4096-aligned; or all of userdata."""
    import os
    g = os.environ.get('JESVI_IOS_DATA_GB', 'all').strip().lower()
    if g in ('', 'all'):
        return device_userdata
    n = int(g) * 10**9 // 4096 * 4096
    if not 16 * 10**9 <= n <= device_userdata:
        raise ValueError(f'IOS_DATA_GB={g} does not fit userdata ({device_userdata // 10**9} GB)')
    return n


def kit_path(root, data, userdata):
    """The HFSX format kit for this data size: userland/hfs-kit.bin (all of userdata) or userland/hfs-kit-<bytes>.bin
    (SIZE=<bytes> tools/mk-userdata-hfs.sh, then tools/hfs-kit.py /tmp/hfsfmt userland/hfs-kit-<bytes>.bin)."""
    return root / 'userland' / ('hfs-kit.bin' if data == userdata else f'hfs-kit-{data}.bin')


def bootline(conf, disabled=(), data=None, userdata=None):
    """Boot line: platform args, hardware-derived args, target args, then mod args (last word wins)."""
    words = conf['PLATFORM_BOOTARGS'].split()
    if conf['TARGET_HAPTIC_CHIP']:
        words.append('haptic_chip=' + conf['TARGET_HAPTIC_CHIP'])
    if conf['TARGET_TORCH_CHIP']:
        words.append('torch_chip=' + conf['TARGET_TORCH_CHIP'])
    if conf['TARGET_CAMERA']:
        words.append(f'cam_{conf["TARGET_CAMERA"]}=1')
    words += conf['TARGET_BOOTARGS'].split()
    disabled = set(disabled) | set(conf.get('TARGET_DISABLE_MODS', '').split())
    for p, _ in active_modules(conf, disabled):
        if (p / 'bootargs').is_file():
            words += (p / 'bootargs').read_text().split()
    merged = {}
    for w in words:
        merged[w.split('=', 1)[0]] = w   # a later word overrides an earlier key
    if data is not None and userdata is not None and data < userdata:
        # only a window of userdata is iOS's (bsd/dev/redwood_ufs.c ufs_win=FIRST:BLOCKS, /dev/ufs_var)
        merged.pop('ufs_userdata_all', None)
        merged['ufs_win'] = f'ufs_win=0:{data // 4096}'
    line = ' '.join(merged.values())
    if len(line) > BOOTLINE_MAX:
        raise ValueError(f'{conf["TARGET_CODENAME"]}: boot line is {len(line)} characters (max {BOOTLINE_MAX})')
    return line


def without_unbuilt_touchid(line, root=ROOT):
    """touchid=1 only when the image carries the ported libBKDM1 (userland/build.sh copies sysimage/iphone8/libBKDM1.dylib,
    a local file: Apple's code). Without it the loader's /arm-io/mesa node still makes MobileGestalt answer "Touch ID",
    SpringBoard asks biometrickitd at start-up, biometrickitd never answers: Apple logo for ever on a fresh install
    (0.1.2 from a clean checkout, 2026-11-21; touchid=0 booted it). manage.touchid_inputs() makes libBKDM1 first, so
    this only acts for JESVI_TOUCHID=0: a safety net, never a silent loss of Touch ID."""
    words = line.split()
    if 'touchid=1' in words and not (root / 'sysimage/iphone8/libBKDM1.dylib').is_file():
        print('  Touch ID: no sysimage/iphone8/libBKDM1.dylib (tools/touchid/fetch-bkdm1.sh): touchid=0 in the boot line')
        words = ['touchid=0' if w == 'touchid=1' else w for w in words]
    return ' '.join(words)


def apply(conf, stage, dest, disabled=()):
    """Copy each active mod's <stage>/ overlay into dest and run its customize.sh."""
    if stage not in ('root', 'system'):
        raise ValueError('stage is root or system')
    dest = Path(dest).resolve()
    applied = []
    disabled = set(disabled) | set(conf.get('TARGET_DISABLE_MODS', '').split())
    for p, prop in active_modules(conf, disabled):
        overlay = p / stage
        if overlay.is_dir():
            for src in sorted(overlay.rglob('*')):
                rel = src.relative_to(overlay)
                if src.is_symlink() or '..' in rel.parts:
                    raise ValueError(f'{src}: symlinks/parent paths are not allowed in overlays')
                out = dest / rel
                if src.is_dir():
                    out.mkdir(parents=True, exist_ok=True)
                else:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, out)
        script = p / 'customize.sh'
        if script.is_file():
            env = dict(os.environ, **{k: v for k, v in conf.items()}, STAGE=stage, DEST=str(dest),
                       MODPATH=str(p), MODID=prop['id'])
            subprocess.run(['bash', '-euo', 'pipefail', str(script)], env=env, cwd=dest, check=True)
        if overlay.is_dir() or script.is_file():
            applied.append(prop['id'])
    return applied


def shell(conf):
    return ''.join(f'{k}={shlex.quote(v)}\n' for k, v in sorted(conf.items()))


def table():
    cols = ('TARGET_CODENAME', 'TARGET_STATUS', 'TARGET_ASSERT_MODEL', 'TARGET_MODEM', 'TARGET_DISPLAY_RESOLUTION',
            'TARGET_DISPLAY_REFRESH_RATES', 'TARGET_HAS_SPEN', 'TARGET_NAME')
    rows = [[load(n)[c] for c in cols] for n in names()]
    head = ['target', 'status', 'models', 'modem', 'display', 'Hz', 'S Pen', 'name']
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    return '\n'.join('  '.join(str(x).ljust(w) for x, w in zip(r, widths)).rstrip() for r in [head] + rows)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='build.sh target', description='inspect per-device targets')
    ap.add_argument('name', nargs='?')
    ap.add_argument('--format', choices=['sh', 'json', 'bootline', 'mods'], default='sh')
    ap.add_argument('--disable', default='', help='mods to leave out (space separated)')
    a = ap.parse_args(argv)
    if not a.name:
        print(table())
        return 0
    conf = load(a.name)
    off = a.disable.split()
    if a.format == 'json':
        print(json.dumps(conf, indent=2, sort_keys=True))
    elif a.format == 'bootline':
        print(bootline(conf, off))
    elif a.format == 'mods':
        for p, prop in active_modules(conf, off):
            print(f'{p.relative_to(PLATFORM)}: {prop.get("name", prop["id"])}')
    else:
        print(shell(conf), end='')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        sys.exit(f'target: {e}')
