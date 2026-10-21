import importlib.util
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'port_wasm_changes.py'
POLICY = SCRIPT.parents[1] / 'config/port-scope.json'
spec = importlib.util.spec_from_file_location('port_wasm_changes', SCRIPT)
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)


class PortTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.d.name)
        self.base, self.patched, self.target = [root / n for n in ('base', 'patched', 'target')]
        for folder in (self.base, self.patched, self.target):
            folder.mkdir()
        self.policy = port.load_policy(POLICY)
        for stub in self.policy['mandatorySourceFiles']:
            self.file(self.patched, stub, b'// stub\n')

    def tearDown(self):
        self.d.cleanup()

    @staticmethod
    def file(folder, name, data):
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def test_mandatory_renderer_stubs_ported(self):
        result = port.port(self.base, self.patched, self.target, self.policy)
        self.assertEqual(result['conflicts'], [])
        self.assertTrue(all(s['status'] == 'present' for s in result['mandatory']))
        self.assertEqual(len(result['copied']), 3)

    def test_excludes_all_reported_unrelated_conflicts(self):
        names = [
            'Common/3dParty/socketio/nc-build.py',
            'Common/3dParty/v8/nc-build.py',
            'Common/3dParty/v8/tools/8.9/arm64-linux-dynamic/gclient_paths.patch',
            'Common/3dParty/v8/tools/8.9/arm64-linux-dynamic/nc-build.sh',
        ]
        for name in names:
            self.file(self.patched, name, b'cryptpad new')
            self.file(self.target, name, b'eurooffice new')
        result = port.port(self.base, self.patched, self.target, self.policy)
        self.assertFalse(result['conflicts'])
        for name in names:
            self.assertIn(name, [e['file'] for e in result['excluded']])
            self.assertEqual((self.target / name).read_bytes(), b'eurooffice new')

    def test_noncompiled_packages_and_project_dirs_are_excluded(self):
        for rel in ('Common/3dParty/fakeengine/build.py', 'Data/build.sh', 'Common/3dParty/v8/app.cpp'):
            self.file(self.patched, rel, b'cryptpad')
            self.file(self.target, rel, b'eurooffice')
        result = port.port(self.base, self.patched, self.target, self.policy)
        self.assertEqual(len(result['excluded']), 3)
        self.assertEqual(result['conflicts'], [])

    def test_compiled_thirdparty_dependencies_remain_in_scope(self):
        self.file(self.base, 'Common/3dParty/html/calc.cpp', b'original\n')
        self.file(self.patched, 'Common/3dParty/html/calc.cpp', b'cryptpad\n')
        self.file(self.target, 'Common/3dParty/html/calc.cpp', b'original\n')
        result = port.port(self.base, self.patched, self.target, self.policy)
        self.assertIn('Common/3dParty/html/calc.cpp', result['copied'])
        self.assertEqual(result['conflicts'], [])

    def test_scoped_three_way_merge_preserves_eurooffice(self):
        rel = 'OOXML/converter.cpp'
        self.file(self.base, rel, b'line 1\nline 2\nline 3\nline 4\nline 5\n')
        self.file(self.patched, rel, b'line 1 wasm\nline 2\nline 3\nline 4\nline 5\n')
        self.file(self.target, rel, b'line 1\nline 2\nline 3\nline 4\nline 5 euro\n')
        result = port.port(self.base, self.patched, self.target, self.policy)
        self.assertEqual(result['conflicts'], [])
        self.assertIn(rel, result['merged'])
        self.assertIn(b'wasm', (self.target/rel).read_bytes())
        self.assertIn(b'euro', (self.target/rel).read_bytes())

    def test_compiled_conflict_fails_closed(self):
        rel = 'OOXML/converter.cpp'
        self.file(self.base, rel, b'orig\n')
        self.file(self.patched, rel, b'cryptpad\n')
        self.file(self.target, rel, b'eurooffice\n')
        result = port.port(self.base, self.patched, self.target, self.policy)
        self.assertEqual(len(result['conflicts']), 1)
        self.assertEqual((self.target/rel).read_bytes(), b'eurooffice\n')
        self.assertTrue((self.target.parent/'merge-conflicts'/rel).exists())

    def test_binary_conflict_fails_closed(self):
        rel='X2tConverter/blob.bin'
        self.file(self.base,rel,b'orig\0')
        self.file(self.patched,rel,b'patched\0')
        self.file(self.target,rel,b'euro\0')
        result=port.port(self.base,self.patched,self.target,self.policy)
        self.assertEqual(len(result['conflicts']),1)

    def test_compiled_dual_add_conflict_fails_closed(self):
        rel = 'X2tConverter/added.cpp'
        self.file(self.patched, rel, b'cryptpad\n')
        self.file(self.target, rel, b'eurooffice\n')
        result=port.port(self.base,self.patched,self.target,self.policy)
        self.assertEqual(len(result['conflicts']),1)

    def test_remove_in_cryptpad_never_deletes_eurooffice(self):
        rel='X2tConverter/legacy.cpp'
        self.file(self.base,rel,b'baseline\n')
        self.file(self.target,rel,b'euro\n')
        result=port.port(self.base,self.patched,self.target,self.policy)
        self.assertIn(rel,result['removed_in_cryptpad_ignored'])
        self.assertTrue((self.target/rel).exists())

    def test_incomplete_mandatory_sources_are_fatal(self):
        self.policy['mandatorySourceFiles'].append('DesktopEditor/doctrenderer/missing.cpp')
        result=port.port(self.base,self.patched,self.target,self.policy)
        self.assertEqual(len(result['conflicts']),1)

    def test_scope_requires_versioned_valid_lists(self):
        self.assertEqual(self.policy['schemaVersion'],1)
        self.assertFalse(port.inclusion_reason('Common/3dParty/v8/foo.cpp',self.policy)[0])
        self.assertTrue(port.inclusion_reason('X2tConverter/src/main.cpp',self.policy)[0])


if __name__ == '__main__':
    unittest.main()
