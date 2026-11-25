#!/usr/bin/env python3
"""One entry point for source checks, kernel builds and private image assembly."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTAL_KERNEL_TARGETS = ('y2s', 'z3s')
# Boards built on the S20+ (y2s) image path: the y2s kernel, Mu-y2s UEFI and stock DTBH,
# with their own board config, boot line and TWRP ZIP. First-install ZIPs only.
Y2S_FAMILY = ('y2s', 'z3s')
IMAGE_TARGETS = ('x1slte',) + Y2S_FAMILY


def profile(name):
    if not re.fullmatch('[a-z0-9]+', name):
        raise ValueError('invalid device id')
    p = ROOT / 'devices/exynos990' / name / 'device.json'
    if not p.is_file():
        raise ValueError(f'unknown device: {name}')
    d = json.loads(p.read_text())
    if d['id'] != name or d['platform'] != 'exynos990' or d['schema'] != 1:
        raise ValueError(f'invalid profile: {name}')
    if d['status'] not in ('development', 'unmaintained', 'validated'):
        raise ValueError(f'invalid status: {name}')
    if d['installer_validated']:
        # A qualification is a record of a real install on the phone, not a flipped boolean.
        q = d.get('qualification', '')
        if not q or not (ROOT / q).is_file() or 'EXIT=0' not in (ROOT / q).read_text():
            raise ValueError('installer hardware qualification is not recorded; see docs/release/twrp.md')
    import targets
    t = targets.load(name)
    if t['TARGET_STATUS'] != d['status']:
        raise ValueError(f'{name}: target.conf status {t["TARGET_STATUS"]} differs from device.json {d["status"]}')
    d['target'] = t
    if d['status'] != 'unmaintained':
        if d['models'] != t['TARGET_ASSERT_MODEL'].split() or d['bootloaders'] != t['TARGET_ASSERT_BOOTLOADER'].split() \
                or d['recovery_products'] != t['TARGET_RECOVERY_PRODUCTS'].split():
            raise ValueError(f'{name}: models/bootloaders/products differ between target.conf and device.json')
        if t['TARGET_SUPER_PARTITION_SIZE'] and int(t['TARGET_SUPER_PARTITION_SIZE']) != d['partitions'].get('super'):
            raise ValueError(f'{name}: super size differs between target.conf and device.json')
        if not d['models'] or not d['bootloaders'] or not d['evidence']:
            raise ValueError(f'missing identity/evidence: {name}')
        for part in ('boot', 'recovery', 'super', 'userdata'):
            if not isinstance(d['partitions'].get(part), int) or d['partitions'][part] <= 0:
                raise ValueError(f'missing partition size: {name}/{part}')
        l = d['layout']
        if not (l['system_offset'] + l['system_max_bytes'] <= l['super_log_offset'] <
                d['partitions']['super']):
            raise ValueError('system/log overlap')
        # Android-side facts live beside the profile, outside the image-bound device.json.
        ap = p.with_name('android.json')
        android = json.loads(ap.read_text()) if ap.is_file() else {}
        if android and android.get('schema') != 1:
            raise ValueError(f'invalid android.json: {name}')
        d['android_super'] = a = android.get('android_super') or {}
        stash = android.get('android_stash_offset', 0)
        l['android_stash_offset'] = stash
        if not a.get('groups') or not all(isinstance(a.get(k), int) and a[k] > 0 for k in (
                'metadata_max_size', 'metadata_slots', 'logical_block_size', 'alignment', 'first_logical_sector')):
            raise ValueError(f'missing measured Android super layout: {name}')
        if not (l['super_log_offset'] + (8 << 20) <= stash and stash + 4096 + (1 << 20) <= d['partitions']['super']):
            raise ValueError('Android map stash must sit in super\'s free tail after the log')
        if not (l['log_offset'] + l['log_bytes'] <= l['kernel_offset'] and
                l['kernel_offset'] + l['kernel_max_bytes'] <= l['root_offset'] <
                d['partitions']['recovery']):
            raise ValueError('recovery slots overlap')
    return d


def run(*args, env=None):
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def touchid_inputs():
    """Touch ID in a clean build: the ported libBKDM1 (made from Apple's iPhone 8 firmware by tools/touchid/fetch-bkdm1.sh,
    once) and Samsung's fingerprint TA set (fw-fingerprint, the phone's vendor/tee). touchid=1 without libBKDM1 leaves
    SpringBoard waiting on the Apple logo, so a missing piece stops the build; JESVI_TOUCHID=0 builds without Touch ID."""
    if os.environ.get('JESVI_TOUCHID', '1') == '0':
        return
    if not (ROOT / 'sysimage/iphone8/libBKDM1.dylib').is_file():
        tools = ROOT.parents[1] / 'tools/bin'   # ipsw, ldid of the research tree, when the checkout is inside it
        env = dict(os.environ, PATH=f'{tools}:{os.environ.get("PATH", "")}') if tools.is_dir() else None
        run('bash', 'tools/touchid/fetch-bkdm1.sh', env=env)
    if not (ROOT / 'sysimage/iphone8/libBKDM1.dylib').is_file():
        raise ValueError('Touch ID: no sysimage/iphone8/libBKDM1.dylib after tools/touchid/fetch-bkdm1.sh')
    if not (ROOT / 'fw-fingerprint').is_dir():
        raise ValueError('Touch ID: no fw-fingerprint/ (the phone\'s /vendor/tee: FINGE TA + driver TAs); '
                         'copy it in and regenerate the private-inputs lock, or JESVI_TOUCHID=0')


def doctor(device, images=False, experimental_kernel=False):
    d = profile(device)
    problems = []
    if d['status'] == 'unmaintained' and not experimental_kernel:
        problems.append('target has no qualified board profile or build adapter')
    if platform.system() != 'Darwin':
        problems.append('the release build adapter currently requires macOS')
    for tool in ('git', 'python3', 'clang', 'make'):
        if shutil.which(tool) is None:
            problems.append(f'missing host tool: {tool}')
    if ' ' in str(ROOT):
        problems.append('XNU makefiles require a checkout path without spaces')
    if images:
        for p in ('sysimage/rootfs', 'sysimage/cryptex', 'sysimage/cryptex-app',
                  'sysimage/system.manifest', 'sysimage/20F66__iPhone10,3_6/dyld_shared_cache_arm64',
                  'inputs/x1slte/Mu-x1slte.img', 'inputs/x1slte/boot-dtb.img',
                  'inputs/tools/avbtool.py', 'inputs/tools/testkey_rsa4096.pem',
                  'inputs/toolchain.json', 'inputs/private-inputs.lock.json'):
            if not (ROOT / p).exists():
                problems.append(f'missing private/local input: {p}')
        for p in ('ssh', 'apps', 'common/devices/x1slte.local.conf', 'fw-wifi/network'):
            if (ROOT / p).exists():
                problems.append(f'personal input present; use a dedicated sanitized checkout: {p}')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('devices')
    sub.add_parser('validate')
    sub.add_parser('lock-inputs')
    sub.add_parser('identity')
    p = sub.add_parser('local')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--check-only', action='store_true')
    p.add_argument('--twrp', action=argparse.BooleanOptionalAction, default=True, help='build TWRP ZIP by default; --no-twrp requests a transport tar')
    p.add_argument('--experimental', action='store_true', help='with --twrp, enable unqualified writes after physical confirmation')
    p = sub.add_parser('twrp')
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=['choose', 'update', 'fresh'], default='fresh')
    p.add_argument('--experimental', action='store_true', help='enable unqualified device writes after physical confirmation')
    p = sub.add_parser('release', help='build everything release.conf asks for')
    p.add_argument('--config', type=Path)
    p.add_argument('--set', action='append', default=[], metavar='KEY=value')
    p.add_argument('--dry-run', action='store_true', help='print the plan only')
    p = sub.add_parser('restore', help='Jesvi-iOS-Restore ZIP for one device')
    p.add_argument('--device', default='x1slte')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--experimental', action='store_true', help='enable writes after physical confirmation')
    p = sub.add_parser('target', help='list targets, or show one target\'s merged config/boot line/mods')
    p.add_argument('rest', nargs=argparse.REMAINDER)
    p = sub.add_parser('package')
    p.add_argument('--device', default='x1slte')
    p.add_argument('--output', required=True, type=Path)
    for cmd in ('doctor', 'kernel', 'images'):
        p = sub.add_parser(cmd)
        p.add_argument('--device', default='x1slte')
        if cmd == 'doctor':
            p.add_argument('--images', action='store_true')
        elif cmd == 'kernel':
            p.add_argument('--experimental', action='store_true',
                           help='build a shared Exynos 990 kernel artifact for y2s or z3s bring-up')
            p.add_argument('--jobs', type=int, default=4)
        elif cmd == 'images':
            p.add_argument('--development', action='store_true',
                           help='acknowledge unqualified private development candidate')
    a = parser.parse_args()
    if a.command == 'target':
        import targets
        return targets.main(a.rest)
    if a.command == 'release':
        import release_config
        return release_config.build(release_config.load(a.config, a.set), a.dry_run)
    if a.command == 'restore':
        from twrp_package import package_restore
        package_restore(a.device, a.output, a.experimental)
        return 0
    if a.command == 'twrp':
        from twrp_package import package
        package(a.bundle, a.output, a.mode, a.experimental)
        return 0
    if a.command == 'identity':
        tree = ROOT / 'sysimage/DeviceTree.d22ap.im4p'
        if not tree.is_file():
            run('python3', 'sysimage/fetch-from-ipsw.py', 'Firmware/all_flash/DeviceTree.d22ap.im4p', str(tree) + '.part')
            Path(str(tree) + '.part').replace(tree)
        run('bash', 'xnuloader/mkidentity.sh', str(tree))
        return 0
    if a.command == 'local':
        from local_build import build
        if a.experimental and not a.twrp:
            raise ValueError('--experimental requires --twrp')
        build(a.output, a.check_only, a.twrp, a.experimental)
        return 0
    if a.command == 'lock-inputs':
        from private_inputs import write
        write()
        return 0
    if a.command == 'package':
        from package import package
        package(a.device, a.output)
        return 0
    if a.command in ('devices', 'validate'):
        for p in sorted((ROOT / 'devices/exynos990').glob('*/device.json')):
            d = profile(p.parent.name)
            print(f'{d["id"]:8} {d["status"]:13} {d["name"]}; installer: unqualified')
        return 0
    experimental_kernel = a.command == 'kernel' and a.experimental
    if a.command == 'kernel':
        if not 1 <= a.jobs <= 64:
            raise ValueError('jobs must be 1..64')
        if experimental_kernel and a.device not in EXPERIMENTAL_KERNEL_TARGETS:
            raise ValueError('--experimental requires --device y2s or z3s')
        if not experimental_kernel and a.device != 'x1slte':
            raise ValueError('use --experimental for y2s or z3s kernel bring-up')
    problems = doctor(a.device, images=a.command == 'images' or getattr(a, 'images', False),
                      experimental_kernel=experimental_kernel)
    if problems:
        for problem in problems:
            print('BLOCKED: ' + problem, file=sys.stderr)
        return 1
    if a.command == 'doctor':
        print('Host prerequisites found. Run kernel to verify the actual compiler/toolchain.')
        return 0
    if a.command == 'kernel':
        if a.experimental:
            print(f'{a.device}: building a shared kernel for experimental bring-up', flush=True)
        run('bash', 'ci/build-kernel.sh', str(a.jobs), a.device)
    elif a.command == 'images':
        if a.device not in IMAGE_TARGETS or not a.development:
            raise ValueError('full images are private development candidates only; pass --development')
        from private_inputs import verify, Y2S_BOARD_INPUTS
        from images import hfs_kit
        from extraction import verify as verify_extraction
        verify_extraction(ROOT)
        verify()
        import targets
        userdata = profile(a.device)['partitions']['userdata']
        data = targets.data_bytes(userdata)
        hfs_kit(targets.kit_path(ROOT, data, userdata), data)
        if a.device in Y2S_FAMILY:
            if data != userdata:
                raise ValueError(f'{a.device} requires IOS_DATA_GB=all for the current loader')
            if any(not (ROOT / path).is_file() for path in Y2S_BOARD_INPUTS):
                raise ValueError('missing y2s Mu image or stock DTBH')
        else:
            touchid_inputs()
        env = dict(os.environ, SHARE='1', REST='1', IOS_INPUT_DIR='../sysimage', REQUIRE_SOURCE='1', JESVI_TARGET=a.device)
        env['HACKIOS_IMAGE_CACHE'] = str(Path(env.get('HACKIOS_IMAGE_CACHE', ROOT / '.cache/private-images')).resolve())
        # Build locally, never export xnu-src over the source under review.
        run('bash', 'ci/build-kernel.sh', '4', 'y2s' if a.device in Y2S_FAMILY else a.device)
        if a.device == 'x1slte':
            shutil.copyfile(ROOT / 'out/kernel/mach.x1slte', ROOT / 'out/mach.x1slte')
        run('bash', 'ci/build-openh264.sh', env=env)
        env['OPENH264'] = str(ROOT / '.cache/release-deps/openh264-source')
        run('bash', 'userland/build-gpu-y2s.sh', env=env)
        for name in ('root.apfs', 'system.apfs'):
            if not (ROOT / 'userland' / name).is_file():
                raise ValueError(f'image builder produced no {name}')
        run('./build.sh', 'identity', env=env)
        run('python3', 'tools/release/loader_font.py', env=env)
        if a.device in Y2S_FAMILY:
            run('python3', '-I', 'tools/bootlogo/mkbootlogo.py', env=env)
            run('bash', 'tools/y2s/build-image.sh', env=dict(env, UEFI=Y2S_BOARD_INPUTS[0], BOARD=a.device))
            verify()
            return 0
        run('bash', 'x1slte.sh', 'embed', env=env)
        # Boot line from the target config: platform + hardware + target + mods.
        # data_bytes and hfs_kit checked the explicitly configured data window.
        payload_env = dict(env, WIN_OK='1' if data < userdata else '0')
        line = targets.bootline(targets.load(a.device), env.get('JESVI_MODS_DISABLE', '').split(), data, userdata)
        run('bash', 'x1slte.sh', 'payload', targets.without_unbuilt_touchid(line), env=payload_env)
        run('bash', 'x1slte.sh', 'pack', env=env)
        verify()
        print('Private development images built. Next: build.sh package --output dist/CANDIDATE')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(f'build: {exc}')
