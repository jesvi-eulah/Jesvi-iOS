#!/usr/bin/env python3
"""One local preparation/build/package command. Never accesses a phone."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from cache import digest
from manage import ROOT, doctor
from extraction import verify as verify_extraction

BOARD_INPUTS = ('inputs/x1slte/Mu-x1slte.img', 'inputs/x1slte/boot-dtb.img',
                'inputs/tools/avbtool.py', 'inputs/tools/testkey_rsa4096.pem',
                'inputs/toolchain.json', 'userland/hfs-kit.bin')

def preflight(output, device='x1slte'):
    from private_inputs import Y2S_BOARD_INPUTS
    errors = doctor(device)
    if (ROOT / 'dist').resolve() not in output.resolve().parents:
        errors.append('local candidate output must be under this checkout’s dist/ directory')
    for tool in ('7z', 'cc', 'curl', 'tar', 'ldid', 'llvm-ar', 'llvm-ranlib', 'llvm-strip', 'lld-link'):
        if shutil.which(tool) is None:
            errors.append('missing tool: ' + tool)
    from manage import Y2S_FAMILY
    for name in BOARD_INPUTS + (Y2S_BOARD_INPUTS if device in Y2S_FAMILY else ()):
        p = ROOT / name
        if p.is_symlink() or not p.is_file():
            errors.append('provision reviewed board/tool input: ' + name)
    for name in ('ssh', 'apps', 'fw-wifi/network', 'common/devices/x1slte.local.conf'):
        if (ROOT / name).exists():
            errors.append('personal input present; use an isolated sanitized checkout: ' + name)
    for name in ('rootfs', 'cryptex', 'cryptex-app'):
        if (ROOT / 'sysimage' / name).is_symlink():
            errors.append('shared extraction directory symlink: ' + name)
    if output.exists() or output.is_symlink() or Path(str(output) + '.tar').exists() or Path(str(output) + '.zip').exists():
        errors.append('output already exists; choose a new candidate path')
    if errors:
        raise ValueError('\n'.join(errors))

def build(output, check_only=False, twrp=True, experimental=False, bundle_only=False, device='x1slte'):
    output = output.absolute()
    preflight(output, device)
    if check_only:
        print('Local prerequisites found; extraction/build will be validated during the run.')
        return
    work = ROOT / 'out/local-build'
    work.mkdir(parents=True, exist_ok=True)
    with (work / 'build.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another local build is running in this checkout')
        def run(label, args, env=None):
            print(label, flush=True)
            log = work / (label.split(':')[0] + '.log')
            with log.open('wb') as stream:
                result = subprocess.run(args, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            if result.returncode:
                raise ValueError(f'{label} failed (exit {result.returncode}); see {log}')
        try:
            verify_extraction(ROOT)
            print('Apple extraction: verified content/recipe cache hit', flush=True)
        except (ValueError, OSError):
            if shutil.disk_usage(ROOT).free < 25 * 1024**3:
                raise ValueError('preparing Apple inputs requires at least 25 GiB free; no files deleted')
            # Old timestamp-only extractions cannot be certified retroactively.
            for name in ('.done-rootfs', '.done-cryptex', '.done-cryptex-app'):
                (ROOT / 'sysimage' / name).unlink(missing_ok=True)
            run('01-apple: fetch and extract pinned Apple inputs', ['bash', 'sysimage/fetch.sh'], dict(os.environ, KEEP='1'))
            verify_extraction(ROOT)
        run('01b-identity: prepare Apple device-tree identity', ['./build.sh', 'identity'])
        # Existing board inputs are never silently blessed after changes.
        ledger = ROOT / 'inputs/private-inputs.lock.json'
        if ledger.exists():
            from private_inputs import inventory
            previous = json.loads(ledger.read_text())['inputs']
            current = inventory()
            private = lambda d: {k: v for k, v in d.items() if not k.startswith('sysimage/')}
            if private(previous) != private(current):
                raise ValueError('board/firmware inputs changed; review and run build.sh lock-inputs explicitly')
        run('02-inputs: lock prepared inputs', ['./build.sh', 'lock-inputs'])
        run('03-build: compile and assemble images', ['./build.sh', 'images', '--development', '--device', device])
        run('04-package: assemble candidate', ['./build.sh', 'package', '--output', str(output), '--device', device])
        run('05-verify: verify candidate', ['./build.sh', 'verify', '--bundle', str(output)])
        if bundle_only:
            print(f'Verified candidate: {output}', flush=True)
            return
        if twrp:
            args = ['./build.sh', 'twrp', '--bundle', str(output), '--output', str(output) + '.zip']
            if experimental:
                args.append('--experimental')
            run('06-twrp: build native recovery ZIP', args)
            print(f'Private TWRP package: {output}.zip; hardware qualification pending', flush=True)
            return
        archive = Path(str(output) + '.tar')
        pending = Path(str(archive) + '.part')
        try:
            with tarfile.open(pending, 'w') as tar:
                for name in ('boot.img', 'recovery.img', 'system.apfs', 'manifest.json', 'SHA256SUMS'):
                    tar.add(output / name, arcname=output.name + '/' + name, recursive=False)
            pending.replace(archive)
        finally:
            pending.unlink(missing_ok=True)
        Path(str(archive) + '.sha256').write_text(f'{digest(archive)}  {archive.name}\n')
        print(f'Private development package: {archive}\nInstaller qualification: pending', flush=True)
