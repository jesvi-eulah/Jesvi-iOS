import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cache import Cache, fingerprint
from images import android_head, apfs, hfs_kit
from flash_plan import match_report, verify
from manage import profile


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        (self.inputs / 'nested').mkdir()
        self.file = self.inputs / 'nested/a'
        self.file.write_bytes(b'old')
        self.cache = Cache(self.root / 'cache')

    def key(self, **options):
        return fingerprint({'input': self.inputs}, options)

    def test_nested_edit_with_same_mtime_invalidates(self):
        before = self.key()
        t = self.file.stat().st_mtime_ns
        self.file.write_bytes(b'new')
        os.utime(self.file, ns=(t, t))
        self.assertNotEqual(before, self.key())

    def test_mtime_only_and_checkout_location_do_not_invalidate(self):
        before = self.key()
        os.utime(self.file, ns=(1, 1))
        self.assertEqual(before, self.key())
        import shutil
        copy = self.root / 'other-checkout'
        shutil.copytree(self.inputs, copy)
        self.assertEqual(before, fingerprint({'input': copy}, {}))

    def test_added_removed_modes_and_options_invalidate(self):
        before = self.key()
        self.assertNotEqual(before, self.key(device='other'))
        self.file.chmod(0o700)
        self.assertNotEqual(before, self.key())
        after = self.key()
        (self.inputs / 'extra').write_text('x')
        self.assertNotEqual(after, self.key())
        (self.inputs / 'extra').unlink()
        self.assertEqual(after, self.key())

    def test_symlink_target_changes_invalidate_without_following(self):
        link = self.inputs / 'link'
        link.symlink_to('/not/a/real/file')
        before = self.key()
        link.unlink()
        link.symlink_to('/another/file')
        self.assertNotEqual(before, self.key())

    def test_restore_miss_hit_and_corruption(self):
        key = self.key()
        target = self.root / 'image.apfs'
        self.assertFalse(self.cache.restore(key, target))
        self.cache.store(key, self.file)
        self.assertTrue(self.cache.restore(key, target))
        self.assertEqual(target.read_bytes(), b'old')
        (self.cache.root / key / 'payload').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'corrupt'):
            self.cache.restore(key, target)
        self.assertEqual(target.read_bytes(), b'old')

    def test_output_symlink_and_empty_input_refused(self):
        target = self.root / 'image.apfs'
        target.symlink_to(self.file)
        with self.assertRaises(ValueError):
            self.cache.restore(self.key(), target)
        self.file.write_bytes(b'')
        with self.assertRaises(ValueError):
            self.cache.store(self.key(), self.file)

    def test_bad_key_and_missing_input_refused(self):
        with self.assertRaises(ValueError):
            self.cache.restore('../escape', self.root / 'out')
        with self.assertRaises(ValueError):
            fingerprint({'missing': self.root / 'none'}, {})

    def test_failed_publish_does_not_leave_visible_entry(self):
        from unittest.mock import patch
        key = self.key()
        with patch('cache.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.cache.store(key, self.file)
        self.assertFalse((self.cache.root / key).exists())
        self.assertEqual(list(self.cache.root.glob('.pending-*')), [])

    def test_concurrent_publish_and_restore(self):
        from concurrent.futures import ThreadPoolExecutor
        key = self.key()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.cache.store(key, self.file), range(8)))
        target = self.root / 'result'
        self.assertTrue(self.cache.restore(key, target))
        self.assertEqual(target.read_bytes(), b'old')
        self.assertEqual(list(self.cache.root.glob('.pending-*')), [])


class SystemCacheTests(unittest.TestCase):
    def setUp(self):
        import subprocess
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in ('userland/build.sh', 'tools/apfs/mkapfs.py',
                     'tools/storage/stage-provider.py', 'userland/obj/stage0',
                     'userland/obj/LocalFilesHost', 'sysimage/system.manifest',
                     'sysimage/rootfs/usr/lib/test', 'sysimage/cryptex/test',
                     'sysimage/cryptex-app/test', 'sysimage/20F66__iPhone10,3_6/cache',
                     'fw-sound/calliope.bin'):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'original')
        subprocess.run(['git', '-C', str(self.root), 'add', 'tools/apfs'], check=True)

    def key(self):
        from system_cache import key
        return key(self.root, self.root / 'sysimage')

    def test_kernel_and_docs_do_not_invalidate_system(self):
        key = self.key()
        (self.root / 'kernel').write_bytes(b'new kernel')
        (self.root / 'README.md').write_text('new docs')
        self.assertEqual(key, self.key())

    def test_firmware_and_actual_binary_changes_invalidate_system(self):
        key = self.key()
        (self.root / 'fw-sound/calliope.bin').write_bytes(b'changed firmware')
        self.assertNotEqual(key, self.key())
        key = self.key()
        (self.root / 'userland/obj/LocalFilesHost').write_bytes(b'changed provider')
        self.assertNotEqual(key, self.key())

    def test_firmware_symlink_is_not_a_hidden_cache_dependency(self):
        target = self.root / 'fw-sound/calliope.bin'
        target.unlink()
        target.symlink_to('/private/other-agent/firmware')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.key()

    def test_generated_apfs_tools_do_not_invalidate(self):
        key = self.key()
        (self.root / 'tools/apfs/generated-tool').write_bytes(b'tool build output')
        self.assertEqual(key, self.key())


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'image'

    def boot(self):
        b = bytearray(6144)
        b[:8] = b'ANDROID!'
        struct.pack_into('<I', b, 8, 2048)
        struct.pack_into('<I', b, 36, 2048)
        struct.pack_into('<I', b, 40, 2)
        struct.pack_into('<I', b, 1648, 4)
        b[4096:4100] = bytes.fromhex('d7b7ab1e')
        return b

    def test_samsung_table_required(self):
        b = self.boot()
        self.path.write_bytes(b)
        self.assertEqual(android_head(self.path), 6144)
        b[4096:4100] = bytes.fromhex('d00dfeed')
        self.path.write_bytes(b)
        with self.assertRaisesRegex(ValueError, 'raw FDT'):
            android_head(self.path)

    def test_truncated_or_wrong_version_boot_refused(self):
        b = self.boot()
        self.path.write_bytes(b[:4096])
        with self.assertRaises(ValueError):
            android_head(self.path)
        struct.pack_into('<I', b, 40, 3)
        self.path.write_bytes(b)
        with self.assertRaises(ValueError):
            android_head(self.path)

    def test_apfs_geometry(self):
        b = bytearray(4096)
        b[32:36] = b'NXSB'
        struct.pack_into('<IQ', b, 36, 4096, 1)
        self.path.write_bytes(b)
        self.assertEqual(apfs(self.path, 4096), 4096)
        with self.assertRaises(ValueError):
            apfs(self.path, 2048)
        struct.pack_into('<Q', b, 40, 2)
        self.path.write_bytes(b)
        with self.assertRaisesRegex(ValueError, 'truncated'):
            apfs(self.path, 8192)

    def test_hfs_kit_wrong_capacity_or_crc_refused(self):
        body = struct.pack('<QII', 0, 1, 0)
        b = b'HFSKIT01' + struct.pack('<IIQII', 4096, 1, 8192, zlib.crc32(body), 0) + body
        self.path.write_bytes(b)
        hfs_kit(self.path, 8192)
        with self.assertRaises(ValueError):
            hfs_kit(self.path, 16384)
        self.path.write_bytes(b[:-1] + b'1')
        with self.assertRaises(ValueError):
            hfs_kit(self.path, 8192)


class SafetyTests(unittest.TestCase):
    def report(self):
        d = profile('x1slte')
        return dict(model='SM-G980F', product='x1s', bootloader=d['bootloaders'][0],
                    partitions=d['partitions'].copy(), environment='twrp', root=True, mounted_targets=[])

    def test_exact_board_report(self):
        match_report(profile('x1slte'), self.report())

    def test_other_models_capacities_bootloaders_and_mounts_fail(self):
        for patch in ({'model': 'SM-G981B'}, {'product': 'y2s'}, {'bootloader': 'newer'},
                      {'partitions': {}}, {'mounted_targets': ['/data']}, {'root': False},
                      {'environment': 'android'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                match_report(profile('x1slte'), dict(self.report(), **patch))

    def test_missing_mount_evidence_fails(self):
        r = self.report()
        del r['mounted_targets']
        with self.assertRaises(ValueError):
            match_report(profile('x1slte'), r)

    def test_path_traversal_profile_fails(self):
        with self.assertRaises(ValueError):
            profile('../x1slte')

    def test_roadmap_targets_are_not_marked_supported(self):
        for name in ('z3s', 'c1s', 'c2s', 'r8s'):
            d = profile(name)
            self.assertEqual(d['status'], 'unmaintained')
            self.assertFalse(d['installer_validated'])
            self.assertEqual(d['models'], [])

    def test_y2s_has_measured_first_install_profile(self):
        d = profile('y2s')
        self.assertEqual(d['status'], 'development')
        self.assertEqual(d['models'], ['SM-G986B'])
        self.assertEqual(d['bootloaders'], ['G986BXXSNHYB1'])
        self.assertEqual(d['layout']['system_max_bytes'], 0x174200000)
        self.assertEqual(d['layout']['android_stash_offset'], d['partitions']['super'] - (2 << 20))
        self.assertEqual(d['android_super']['alignment'], 1048576)
        self.assertFalse(d['installer_validated'])

    def test_manifest_with_protected_target_rejected(self):
        from cache import digest
        from manage import ROOT
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            m = {'schema': 1, 'kind': 'private-development-candidate', 'installer_validated': False,
                 'layout': 'ios-only-v1', 'device': 'x1slte',
                 'device_profile_sha256': digest(ROOT / 'devices/exynos990/x1slte/device.json'),
                 'files': {'efs.img': {}}}
            (p / 'manifest.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, 'unexpected/missing'):
                verify(p)


class CandidateTests(unittest.TestCase):
    """Synthetic board-sized images exercise the full verifier without hardware."""
    def setUp(self):
        from cache import digest
        from manage import ROOT
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Path(self.tmp.name)
        self.d = profile('x1slte')
        head = bytearray(6144)
        head[:8] = b'ANDROID!'
        for off, value in [(8, 2048), (36, 2048), (40, 2), (1648, 4)]:
            struct.pack_into('<I', head, off, value)
        head[4096:4100] = bytes.fromhex('d7b7ab1e')
        (self.bundle / 'boot.img').write_bytes(head)
        apfs_image = bytearray(4096)
        apfs_image[32:36] = b'NXSB'
        struct.pack_into('<IQ', apfs_image, 36, 4096, 1)
        (self.bundle / 'system.apfs').write_bytes(apfs_image)
        with (self.bundle / 'recovery.img').open('wb') as f:
            f.truncate(self.d['partitions']['recovery'])
            f.write(head)
            f.seek(self.d['layout']['kernel_offset'])
            f.write(bytes.fromhex('cffaedfe'))
            f.seek(self.d['layout']['root_offset'])
            f.write(apfs_image)
            f.seek(self.d['partitions']['recovery'] - 64)
            footer = bytearray(64)
            footer[:4] = b'AVBf'
            struct.pack_into('>QQQ', footer, 12, 6144, 8192, 4096)
            f.write(footer)
        self.manifest = {'schema': 1, 'kind': 'private-development-candidate',
                         'device': 'x1slte', 'installer_validated': False, 'layout': 'ios-only-v1',
                         'device_profile_sha256': digest(ROOT / 'devices/exynos990/x1slte/device.json'),
                         'files': {}}
        for name, part in [('boot.img', 'boot'), ('recovery.img', 'recovery'), ('system.apfs', 'super')]:
            p = self.bundle / name
            self.manifest['files'][name] = dict(partition=part, offset=0, bytes=p.stat().st_size, sha256=digest(p))
        self.save()

    def save(self):
        from cache import digest
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.bundle / 'SHA256SUMS').write_text(''.join(
            f'{digest(self.bundle / name)}  {name}\n'
            for name in sorted(self.manifest['files']) + ['manifest.json']))

    def test_full_candidate_verifies_and_tamper_fails(self):
        verify(self.bundle)
        with (self.bundle / 'system.apfs').open('r+b') as f:
            f.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            verify(self.bundle)

    def test_boot_head_mismatch_even_with_updated_checksum_fails(self):
        from cache import digest
        with (self.bundle / 'boot.img').open('r+b') as f:
            f.seek(100)
            f.write(b'bad')
        self.manifest['files']['boot.img']['sha256'] = digest(self.bundle / 'boot.img')
        self.save()
        with self.assertRaisesRegex(ValueError, 'does not match recovery'):
            verify(self.bundle)

    def test_footer_overlapping_kernel_fails_even_with_updated_checksum(self):
        from cache import digest
        with (self.bundle / 'recovery.img').open('r+b') as f:
            f.seek(self.d['partitions']['recovery'] - 64 + 20)
            f.write(struct.pack('>Q', self.d['layout']['kernel_offset']))
        self.manifest['files']['recovery.img']['sha256'] = digest(self.bundle / 'recovery.img')
        self.save()
        with self.assertRaisesRegex(ValueError, 'AVB metadata overlaps'):
            verify(self.bundle)

    def test_retained_candidates_deduplicate_images(self):
        from private_store import retain
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp)
            retain(self.bundle, store)
            # Metadata changes without changing any image, as on a repeated pull.
            self.manifest['source_commit'] = 'another-source-commit'
            self.save()
            retain(self.bundle, store)
            blobs = [p for p in (store / 'blobs').iterdir() if p.is_dir()]
            candidates = [p for p in (store / 'candidates').iterdir() if p.is_dir()]
            self.assertEqual(len(blobs), 3)
            self.assertEqual(len(candidates), 2)


if __name__ == '__main__':
    unittest.main()
