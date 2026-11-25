import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import targets  # noqa: E402
from manage import ROOT, profile  # noqa: E402


class TargetTests(unittest.TestCase):
    def test_every_target_loads_and_matches_its_install_profile(self):
        self.assertEqual(targets.names(), ['c1s', 'c2s', 'r8s', 'x1s', 'x1slte', 'y2s', 'y2slte', 'z3s'])
        for name in targets.names():
            d = profile(name)  # raises on target.conf/device.json disagreement
            self.assertEqual(d['target']['TARGET_CODENAME'], name)
            targets.bootline(d['target'])

    def test_s20_boot_line_is_the_measured_one(self):
        line = targets.bootline(targets.load('x1slte'))
        self.assertEqual(sorted(line.split()), sorted((ROOT / 'devices/exynos990/x1slte/x1slte.cmdline').read_text().split()))
        self.assertLessEqual(len(line), targets.BOOTLINE_MAX)

    def test_y2s_boot_line_matches_its_target(self):
        line = targets.bootline(targets.load('y2s'))
        self.assertEqual(sorted(line.split()),
                         sorted((ROOT / 'devices/exynos990/y2s/y2s.cmdline').read_text().split()))
        words = line.split()
        self.assertIn('cam_s20_y2s=1', words)
        self.assertIn('island=1', words)
        for word in ('touch_ts=1', 'haptic=5', 'shub=6', 'torch=3', 'wifi_pcie=4',
                     'wifi_nvram=1', 'wifi_pcie_wait=3'):
            self.assertIn(word, words)
        self.assertNotIn('softpasscode=1', words)
        self.assertLessEqual(len(line), targets.BOOTLINE_MAX)

    def test_z3s_first_boot_line(self):
        # The S20 Ultra boots the y2s image path with only the drivers known to match.
        line = targets.bootline(targets.load('z3s'))
        self.assertEqual(sorted(line.split()),
                         sorted((ROOT / 'devices/exynos990/z3s/z3s.cmdline').read_text().split()))
        words = line.split()
        for word in ('touch_ts=1', 'wifi_pcie=4', 'mali=1', 'metal=1', 'ufs_userdata_all=1', 'bms=1'):
            self.assertIn(word, words)
        for prefix in ('cam=', 'cam_s20', 'haptic=', 'shub=', 'torch=', 'softpasscode='):
            self.assertFalse([w for w in words if w.startswith(prefix)], prefix)
        self.assertLessEqual(len(line), targets.BOOTLINE_MAX)

    def test_touchid_off_without_ported_libbkdm1(self):
        import tempfile
        line = targets.bootline(targets.load('x1slte'))
        with tempfile.TemporaryDirectory() as d:
            words = targets.without_unbuilt_touchid(line, Path(d)).split()
            self.assertIn('touchid=0', words)
            self.assertNotIn('touchid=1', words)
            (Path(d) / 'sysimage/iphone8').mkdir(parents=True)
            (Path(d) / 'sysimage/iphone8/libBKDM1.dylib').write_bytes(b'')
            self.assertEqual(targets.without_unbuilt_touchid(line, Path(d)), line)

    def test_ios_data_size_window(self):
        import os
        u = 116253523968
        os.environ['JESVI_IOS_DATA_GB'] = '64'
        try:
            d = targets.data_bytes(u)
            words = targets.bootline(targets.load('x1slte'), (), d, u).split()
            self.assertEqual(d, 64000000000)
            self.assertIn('ufs_win=0:15625000', words)
            self.assertNotIn('ufs_userdata_all=1', words)
            os.environ['JESVI_IOS_DATA_GB'] = 'all'
            self.assertEqual(targets.data_bytes(u), u)
            os.environ['JESVI_IOS_DATA_GB'] = '200'
            self.assertRaises(ValueError, targets.data_bytes, u)
        finally:
            os.environ.pop('JESVI_IOS_DATA_GB', None)

    def test_optional_mods_can_be_left_out(self):
        conf = targets.load('x1slte')
        words = targets.bootline(conf, ['island']).split()
        self.assertNotIn('island=1', words)
        self.assertIn('softpasscode=1', words)

    def test_inherited_target_overrides_parent(self):
        s20_5g, s20 = targets.load('x1s'), targets.load('x1slte')
        self.assertEqual(s20_5g['TARGET_MODEM'], '5g')
        self.assertEqual(s20_5g['TARGET_DISPLAY_RESOLUTION'], s20['TARGET_DISPLAY_RESOLUTION'])
        self.assertEqual(s20_5g['TARGET_STATUS'], 'unmaintained')
        self.assertIn('x1slte', s20_5g['TARGET_PARENT_DIRS'].split())

    def test_note_targets_have_spen_and_others_do_not(self):
        for name in targets.names():
            self.assertEqual(targets.load(name)['TARGET_HAS_SPEN'] == 'true', name in ('c1s', 'c2s'))

    def test_unsafe_or_unknown_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            for text in ('TARGET_NAME="$(reboot)"\n', 'TARGET_BOGUS="1"\n', 'PLATFORM_SOC="x"\n',
                         'TARGET_NAME=a b\n', 'TARGET_NAME="`id`"\n'):
                p = Path(t) / 'target.conf'
                p.write_text(text)
                with self.assertRaises(ValueError, msg=text):
                    conf = targets.read_conf(p, ('TARGET_',))
                    if set(conf) - set(targets.DEFAULTS) - set(targets.REQUIRED):
                        raise ValueError('unknown')
        with self.assertRaises(ValueError):
            targets.load('../x1slte')

    def test_mod_overlays_filters_and_customize(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t) / 'exynos990'
            (base / 'x1slte').mkdir(parents=True)
            for f in ('platform.conf',):
                (base / f).write_text((targets.PLATFORM / f).read_text())
            (base / 'x1slte/target.conf').write_text((targets.PLATFORM / 'x1slte/target.conf').read_text())
            def mod(where, name, prop='', files=()):
                m = base / where / name
                m.mkdir(parents=True)
                (m / 'module.prop').write_text(f'id={name}\nname={name}\n{prop}')
                for rel, data in files:
                    (m / rel).parent.mkdir(parents=True, exist_ok=True)
                    (m / rel).write_text(data)
                return m
            mod('patches', 'a_common', files=[('root/etc/common.txt', 'p'), ('system/etc/sys.txt', 's')])
            mod('x1slte/patches', 'b_device', files=[('root/etc/common.txt', 'device wins'),
                                                       ('customize.sh', 'echo "$TARGET_PANEL:$STAGE" > from-script\n')])
            mod('patches', 'c_spen_only', 'requires=TARGET_HAS_SPEN\n', [('root/spen', 'x')])
            mod('patches', 'd_other_phone', 'targets=c2s\n', [('root/other', 'x')])
            mod('mods', 'e_optional', files=[('root/optional', 'x')])
            off = mod('mods', 'f_off', files=[('root/off', 'x')])
            (off / 'disable').write_text('')
            with mock.patch.object(targets, 'PLATFORM', base):
                conf = targets.load('x1slte')
                dest = Path(t) / 'root'
                dest.mkdir()
                done = targets.apply(conf, 'root', dest, ['e_optional'])
                self.assertEqual(done, ['a_common', 'b_device'])
                self.assertEqual((dest / 'etc/common.txt').read_text(), 'device wins')
                self.assertEqual((dest / 'from-script').read_text().strip(), 's6e3hab:root')
                for absent in ('spen', 'other', 'optional', 'off', 'etc/sys.txt'):
                    self.assertFalse((dest / absent).exists(), absent)
                bad = mod('patches', 'g_link')
                (bad / 'root').mkdir()
                os.symlink('/etc/passwd', bad / 'root/link')
                with self.assertRaises(ValueError):
                    targets.apply(conf, 'root', dest)


if __name__ == '__main__':
    unittest.main()
