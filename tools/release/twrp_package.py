#!/usr/bin/env python3
"""Build native arm64 TWRP ZIPs: the Jesvi iOS installer and Jesvi-iOS-Restore.

Experimental writes require an explicit opt-in. Both ZIPs share one recovery
executable; the bound installer.json (hashed into the binary) selects the action.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
from cache import digest, fingerprint
from go_toolchain import ensure, environment
from manage import ROOT, profile, Y2S_FAMILY

META = {'installer.json', 'README.txt',
        'META-INF/com/google/android/update-binary', 'META-INF/com/google/android/updater-script'}
ENTRIES = META | {'hfs-kit.bin', 'candidate.json', 'boot.img', 'recovery.img', 'system.apfs'}


def _sources():
    sources = {str(p.relative_to(ROOT)): p for p in (ROOT / 'tools/recovery').iterdir()
               if (p.suffix == '.go' and not p.name.endswith('_test.go')) or p.name == 'go.mod'}
    sources['builder'] = Path(__file__)
    sources['toolchain'] = Path(__file__).with_name('go_toolchain.py')
    sources['filesystem-checks'] = Path(__file__).with_name('filesystem_checks.py')
    return sources


def _partitions(device):
    """The four iOS destinations, plus up_param (Samsung's power-on pictures) when the profile measured it: the
    install puts iOS's boot logo there, Jesvi-iOS-Restore puts the phone's own logo back (tools/recovery/splash.go).
    Other partitions recorded as stock evidence (dtbo, vbmeta, metadata on y2s) are not installer destinations."""
    parts = {name: device['partitions'][name] for name in ('boot', 'recovery', 'super', 'userdata')}
    if device.get('splash_partition_bytes'):
        parts['up_param'] = device['splash_partition_bytes']
    return parts


def device_config(device, action, mode, experimental):
    """Installer config from the measured device profile (bound into the binary)."""
    l = device['layout']
    return {'schema': 2, 'action': action, 'device': device['id'], 'mode': mode,
            'allow_writes': experimental, 'installer_validated': False,
            'models': device['models'], 'bootloaders': device['bootloaders'],
            'products': device['recovery_products'], 'partitions': _partitions(device),
            'system_max_bytes': l['system_max_bytes'], 'stash_offset': l['android_stash_offset'],
            'android_super': device['android_super'], 'files': {}, 'kit_sha256': '', 'kit_bytes': 0}


def _check_output(output):
    output = output.absolute()
    if (ROOT / 'dist').resolve() not in output.resolve().parents or output.suffix != '.zip':
        raise ValueError('TWRP output must be a new .zip under this checkout’s dist/')
    if any(p.exists() or p.is_symlink() for p in (output, Path(str(output) + '.sha256'), Path(str(output) + '.build.json'))):
        raise ValueError(f'output already exists: {output.name}')
    return output


def _build(output, config, files, readme, inventory, extra_build=None):
    """Cross-compile, assemble a stored ZIP, verify it with the same parser, publish."""
    sources = _sources()
    source_key = fingerprint(sources, {})
    raw = (json.dumps(config, indent=2, sort_keys=True) + '\n').encode()
    sha = hashlib.sha256(raw).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    go = ensure()
    with tempfile.TemporaryDirectory(prefix='build-', dir=output.parent) as work:
        work = Path(work)
        binary = work / 'update-binary'
        base = environment()
        parts = Path(output).name.removesuffix('.zip').split('_')  # NAME_VERSION_DATE_[MODE_]target[_preflight]
        shown = f'v{parts[1]} ({parts[2][:4]}-{parts[2][4:6]}-{parts[2][6:]})' if len(parts) >= 4 and parts[2].isdigit() else 'build ' + Path(output).stem
        shown = ''.join(c for c in shown if c.isalnum() or c in '.-() ')
        flags = ['-p', '4', '-trimpath', '-buildvcs=false', '-ldflags', f'-s -w -buildid= -X main.configSHA={sha} -X "main.releaseName={shown}"']
        subprocess.run([str(go), 'build', *flags, '-o', str(binary), '.'],
                       cwd=ROOT / 'tools/recovery', env=dict(base, GOOS='linux', GOARCH='arm64', GOARM64='v8.0'), check=True)
        if binary.read_bytes()[:4] != b'\x7fELF':
            raise ValueError('recovery executable is not ELF')
        pending = work / 'candidate.zip'
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            def small(name, data, executable=False):
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o100755 if executable else 0o100644) << 16
                z.writestr(info, data)
            small('installer.json', raw)
            small('META-INF/com/google/android/update-binary', binary.read_bytes(), True)
            small('META-INF/com/google/android/updater-script', b'# Native Jesvi iOS recovery program\n')
            small('README.txt', readme.encode())
            for name, src in files.items():
                if isinstance(src, bytes):
                    small(name, src)
                else:
                    z.write(src, name)
        with zipfile.ZipFile(pending) as z:
            if set(z.namelist()) != inventory or len(z.namelist()) != len(inventory):
                raise ValueError('unexpected ZIP inventory')
            if z.testzip() is not None:
                raise ValueError('ZIP CRC validation failed')
        # Run exactly the recovery parser/validators on host before publishing ZIP.
        inspector = work / 'inspect'
        subprocess.run([str(go), 'build', *flags, '-o', str(inspector), '.'],
                       cwd=ROOT / 'tools/recovery', env=base, check=True)
        subprocess.run([str(inspector), '--inspect', str(pending)], check=True)
        if fingerprint(sources, {}) != source_key:
            raise ValueError('installer sources changed during packaging; rerun from stable sources')
        os.link(pending, output)  # atomic no-clobber publication
        pending.unlink()
    Path(str(output) + '.sha256').write_text(f'{digest(output)}  {output.name}\n')
    info = {'action': config['action'], 'device': config['device'], 'mode': config['mode'], 'installer_source_key': source_key,
            'zip_sha256': digest(output),
            'go_version': subprocess.check_output([str(go), 'version'], text=True).strip(),
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)),
            'hardware_qualified': False, 'writes_enabled': config['allow_writes']}
    info.update(extra_build or {})
    Path(str(output) + '.build.json').write_text(json.dumps(info, indent=2) + '\n')


def package(bundle, output, mode='fresh', experimental=False):
    """Jesvi iOS installer ZIP from a verified candidate bundle."""
    from flash_plan import verify
    from images import hfs_kit
    bundle = bundle.resolve()
    output = _check_output(output)
    if mode not in ('choose', 'update', 'fresh'):
        raise ValueError('unsupported installer mode')
    manifest, device = verify(bundle)
    # y2s is a first-install target only: this ZIP always erases and initializes
    # userdata. Once iOS is running, updates come from the loader's Log access
    # menu (./y2s.sh rflash / tflash), never from a second TWRP flash.
    if device['id'] in Y2S_FAMILY and mode != 'fresh':
        raise ValueError(f"{device['id']} TWRP ZIP is first-install only; pass --mode fresh; use the loader for updates")
    avb, avb_key = ROOT / 'inputs/tools/avbtool.py', ROOT / 'inputs/tools/testkey_rsa4096.pem'
    for tool in (avb, avb_key):
        if tool.is_symlink() or not tool.is_file():
            raise ValueError('reviewed AOSP AVB tool/public test key inputs required')
    ledger = json.loads((ROOT / 'inputs/private-inputs.lock.json').read_text())
    if fingerprint({'inputs/tools': ROOT / 'inputs/tools'}, {}) != ledger['inputs']['inputs/tools']:
        raise ValueError('AVB tool inputs differ from reviewed input lock')
    subprocess.run(['python3', '-I', str(avb), 'verify_image', '--image', str(bundle / 'recovery.img'),
                    '--key', str(avb_key)], cwd=ROOT, check=True)
    import targets
    kit = targets.kit_path(ROOT, targets.data_bytes(device['partitions']['userdata']), device['partitions']['userdata'])
    hfs_kit(kit, __import__('targets').data_bytes(device['partitions']['userdata']))
    from filesystem_checks import verify as verify_filesystems
    verify_filesystems(bundle / 'recovery.img', bundle / 'system.apfs', kit, device)
    config = device_config(device, 'install', mode, experimental)
    config.update(files=manifest['files'], kit_sha256=digest(kit), kit_bytes=kit.stat().st_size,
                  data_bytes=__import__('targets').data_bytes(device['partitions']['userdata']))
    if device['id'] in Y2S_FAMILY:
        readme = (f'Jesvi iOS for {device["name"]} ({device["id"]}). Mode: fresh. Writes enabled: {experimental}.\n'
                  'HARDWARE QUALIFICATION PENDING. No partition-table changes, no automatic reboot.\n'
                  'FIRST INSTALL ONLY, from TWRP: works from Android or over an old Jesvi iOS install,\n'
                  'but always erases Android/iOS data and initializes a clean HFSX userdata volume.\n'
                  'Back up anything you want to keep before flashing; this is not an update.\n'
                  'Keep this ZIP on microSD or in TWRP /tmp; internal storage is replaced.\n'
                  'Android: the installer unmounts /data and super mappings itself after you confirm;\n'
                  'if a mount is busy, choose Mount > Disable MTP in TWRP and flash again.\n'
                  'Android\'s partition map is saved in super\'s free tail for Jesvi-iOS-Restore.\n'
                  'Installation proceeds after 10 seconds unless cancelled. Volume Up starts now, Volume Down/Power cancels.\n'
                  'TWRP is replaced by the iOS runtime. Updates are NEVER flashed with Odin or TWRP:\n'
                  'boot the loader, choose Log access (USB) and run ./y2s.sh rflash or ./y2s.sh tflash.\n'
                  'Do not flash this ZIP again over an existing Jesvi iOS installation.\n'
                  'Back to Android: use the loader\'s restore path or an Android ROM restore ZIP,\n'
                  'then Format Data and flash any Android ROM.\n'
                  'This is not an authenticated public release. See tools/y2s/README.md.\n')
    else:
        readme = (f'Jesvi iOS for {device["name"]} ({device["id"]}). Mode: {mode}. Writes enabled: {experimental}.\n'
                  'HARDWARE QUALIFICATION PENDING. No partition-table changes, no automatic reboot.\n'
                  'Works from TWRP whether the phone runs Jesvi iOS or an Android ROM (ExtremeROM, UN1CA, ...).\n'
                  'Keep this ZIP on microSD/USB-OTG or use adb sideload: internal storage is replaced.\n'
                  'Android: the installer unmounts /data and super mappings itself after you confirm;\n'
                  'if a mount is busy, choose Mount > Disable MTP in TWRP and flash again.\n'
                  'Android\'s partition map is saved in super\'s free tail for Jesvi-iOS-Restore.\n'
                  'Existing iOS data is preserved in update/choose mode. Fresh install destroys userdata.\n'
                  'Installation proceeds after 10 seconds unless cancelled. Volume Up starts now, Volume Down/Power cancels.\n'
                  'TWRP is replaced by the iOS runtime. To update later, flash TWRP with Odin first.\n'
                  'Back to Android: flash Jesvi-iOS-Restore, Format Data, then any Android ROM ZIP.\n'
                  'This is not an authenticated public release. See docs/release/twrp.md and rollback.md.\n')
    files = {'candidate.json': bundle / 'manifest.json', 'hfs-kit.bin': kit,
             'boot.img': bundle / 'boot.img', 'recovery.img': bundle / 'recovery.img', 'system.apfs': bundle / 'system.apfs'}
    inventory = ENTRIES
    if 'up_param' in config['partitions']:
        # the power-on splash: iOS's boot logo, made by tools/bootlogo/mkbootlogo.py in the payload step
        logo = ROOT / 'out/bootlogo/logo.jpg'
        data = logo.read_bytes() if logo.is_file() else b''
        if not data.startswith(b'\xff\xd8') or len(data) > 1 << 20:
            raise ValueError('out/bootlogo/logo.jpg missing or not a JPEG of at most 1 MiB (tools/bootlogo/mkbootlogo.py)')
        config['splash'] = {'bytes': len(data), 'sha256': digest(logo)}
        files['splash.jpg'] = data
        inventory = ENTRIES | {'splash.jpg'}
        # iPhone's charging pictures for the phone-off screens (tools/bootlogo/mkcharging.py), when they were made
        pics = {}
        for name in ('lpm.jpg', 'low_battery_alert.jpg'):
            pic = ROOT / 'out/bootlogo' / name
            if pic.is_file():
                d = pic.read_bytes()
                if not d.startswith(b'\xff\xd8') or len(d) > 1 << 20:
                    raise ValueError(f'out/bootlogo/{name} is not a JPEG of at most 1 MiB')
                pics[name] = {'bytes': len(d), 'sha256': digest(pic)}
                files[name] = d
        if pics:
            config['pictures'] = pics
            inventory = inventory | set(pics)
    _build(output, config, files, readme, inventory, {
        'candidate_manifest_sha256': digest(bundle / 'manifest.json'),
        'avb_test_key_verification': True, 'native_apfs_checks': True, 'hfs_seed_fsck_check': True})
    print(f'TWRP ZIP: {output}; writes={experimental}; hardware qualification pending')


def package_restore(device_id, output, experimental=False):
    """Jesvi-iOS-Restore: needs only the device profile (no Apple inputs)."""
    device = profile(device_id)
    if device['status'] == 'unmaintained':
        raise ValueError(f'{device_id}: no measured device profile yet (see docs/release/porting.md)')
    output = _check_output(output)
    config = device_config(device, 'restore', 'restore', experimental)
    readme = (f'Jesvi-iOS-Restore for {device["name"]} ({device["id"]}). Writes enabled: {experimental}.\n'
              'HARDWARE QUALIFICATION PENDING. Flash in TWRP (install TWRP with Odin first: iOS replaces it).\n'
              'Puts back Android\'s partition map in super (the copy saved at install time, otherwise the\n'
              'measured stock layout) and clears the iOS data headers on userdata. ALL iOS DATA IS LOST.\n'
              'Restore requires a Volume Up hold; its 45-second timeout cancels.\n'
              'Refuses to touch a super that already holds Android partitions. BOOT/TWRP/EFS untouched.\n'
              'Then, without rebooting: Wipe > Format Data (type yes), and flash any Android ROM ZIP\n'
              '(ExtremeROM, UN1CA, LineageOS ...). For stock: Odin BL+AP+CP+CSC (not HOME_CSC).\n')
    _build(output, config, {}, readme, META)
    print(f'Restore ZIP: {output}; writes={experimental}; hardware qualification pending')
