import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_config  # noqa: E402
from manage import ROOT, profile  # noqa: E402


class ReleaseConfigTests(unittest.TestCase):
    def conf(self, text, *overrides):
        with tempfile.NamedTemporaryFile('w', suffix='.conf', delete=False) as f:
            f.write(text)
        try:
            return release_config.load(f.name, overrides)
        finally:
            os.unlink(f.name)

    def test_repository_config_plans_s20_and_y2s_and_skips_unmeasured(self):
        c = release_config.load(None, ['TARGETS=x1slte y2s', 'WRITES=true'])
        todo, skipped = release_config.plan(c)
        self.assertEqual([(t, o) for t, o, _ in todo],
                         [('x1slte', 'twrp'), ('x1slte', 'restore'), ('y2s', 'twrp'), ('y2s', 'restore')])
        self.assertEqual(skipped, [])
        n = release_config.names(c, 'x1slte', '20260101')
        self.assertEqual(c['MODE'], 'fresh')
        self.assertEqual(n['twrp'], 'Jesvi-iOS_0.1.1_20260101_fresh_x1slte.zip')
        self.assertEqual(n['restore'], 'Jesvi-iOS-Restore_0.1.1_20260101_x1slte.zip')

    def test_preflight_names_say_so(self):
        c = self.conf('VERSION=1.2\nWRITES=false\n')
        n = release_config.names(c, 'x1slte', '20260101')
        self.assertTrue(n['twrp'].endswith('_preflight.zip'))
        self.assertTrue(n['restore'].endswith('_preflight.zip'))

    def test_missing_mode_defaults_to_fresh_but_writes_stay_explicit(self):
        c = self.conf('')
        self.assertEqual(c['MODE'], 'fresh')
        self.assertFalse(c['WRITES'])

    def test_install_modes_produce_distinct_names_and_reach_packager(self):
        names = set()
        for mode in ('choose', 'fresh', 'update'):
            with self.subTest(mode=mode):
                c = self.conf('', f'MODE={mode}', 'WRITES=true', 'OUTPUTS=twrp preflight restore')
                n = release_config.names(c, 'x1slte', '20260101')
                names.add(n['twrp'])
                if mode != 'choose':
                    self.assertIn(f'_{mode}_x1slte', n['twrp'])
                self.assertNotIn(f'_{mode}_', n['restore'])
                with mock.patch('release_config.bundle_for', return_value=Path('/candidate')), \
                     mock.patch('twrp_package.package') as package, \
                     mock.patch('twrp_package.package_restore'), \
                     mock.patch('builtins.print'):
                    release_config.build(c)
                self.assertEqual([call.args[2:] for call in package.call_args_list],
                                 [(mode, True), (mode, False)])
        self.assertEqual(len(names), 3)

    def test_dry_run_shows_install_policy_without_building(self):
        c = self.conf('MODE=fresh\nWRITES=true\nOUTPUTS=twrp preflight\n')
        with mock.patch('builtins.print') as output, mock.patch('release_config.bundle_for') as bundle:
            release_config.build(c, dry_run=True)
        bundle.assert_not_called()
        messages = [call.args[0] for call in output.call_args_list]
        self.assertIn('  install mode=fresh; writes=True', messages)
        self.assertIn('  install mode=fresh; writes=False', messages)

    def test_bad_settings_fail(self):
        for text in ('BOGUS=1\n', 'OUTPUTS=odin\n', 'MODE=wipe\n', 'WRITES=yes\n',
                     'OUT=/tmp\n', 'OUT=dist/../..\n', 'NAME=a/b\n', 'TARGETS=\n'):
            with self.assertRaises(ValueError, msg=text):
                self.conf(text)
        with self.assertRaises(ValueError):
            self.conf('', 'NOPE=1')
        with self.assertRaises(ValueError):
            release_config.plan(self.conf('TARGETS=../x1slte\n'))

    def test_environment_overrides_file(self):
        os.environ['JESVI_VERSION'] = '9.9'
        try:
            self.assertEqual(self.conf('VERSION=1.0\n')['VERSION'], '9.9')
        finally:
            del os.environ['JESVI_VERSION']

    def test_profile_carries_measured_android_layout_outside_image_binding(self):
        d = profile('x1slte')
        self.assertEqual(d['android_super']['groups'][0]['name'], 'group_basic')
        self.assertGreater(d['layout']['android_stash_offset'], d['layout']['super_log_offset'])
        self.assertNotIn('android', (ROOT / 'devices/exynos990/x1slte/device.json').read_text())


if __name__ == '__main__':
    unittest.main()
