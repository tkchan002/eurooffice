import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'port_wasm_changes.py'
spec = importlib.util.spec_from_file_location('port_wasm_changes', SCRIPT)
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)

class PortTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.d.name)
        self.base, self.patched, self.target = [root / name for name in ('base','patched','target')]
        for d in (self.base,self.patched,self.target): d.mkdir()

    def tearDown(self): self.d.cleanup()

    def file(self,folder,name,data):
        p=folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def test_added_cryptpad_stubs_are_preserved(self):
        self.file(self.patched,'DesktopEditor/doctrenderer/doctrenderer_empty.cpp',b'// necessary wasm stub\n')
        result=port.port(self.base,self.patched,self.target)
        self.assertEqual(result['conflicts'], [])
        self.assertEqual((self.target/'DesktopEditor/doctrenderer/doctrenderer_empty.cpp').read_bytes(),b'// necessary wasm stub\n')

    def test_new_eurooffice_lines_survive_three_way_merge(self):
        self.file(self.base,'x.cpp',b'line 1\nline 2\nline 3\nline 4\nline 5\n')
        self.file(self.patched,'x.cpp',b'line 1 cryptpad\nline 2\nline 3\nline 4\nline 5\n')
        self.file(self.target,'x.cpp',b'line 1\nline 2\nline 3\nline 4\nline 5 eurooffice\n')
        result=port.port(self.base,self.patched,self.target)
        self.assertEqual(result['conflicts'], [])
        self.assertIn('x.cpp', result['merged'])
        self.assertIn(b'cryptpad', (self.target/'x.cpp').read_bytes())
        self.assertIn(b'eurooffice', (self.target/'x.cpp').read_bytes())

    def test_conflict_does_not_overwrite_eurooffice(self):
        self.file(self.base,'x.cpp',b'original\n')
        self.file(self.patched,'x.cpp',b'from cryptpad\n')
        self.file(self.target,'x.cpp',b'from eurooffice\n')
        result=port.port(self.base,self.patched,self.target)
        self.assertEqual(len(result['conflicts']),1)
        self.assertEqual((self.target/'x.cpp').read_bytes(),b'from eurooffice\n')
        self.assertTrue((self.target.parent/'merge-conflicts/x.cpp').exists())

    def test_binary_conflict_fails_closed(self):
        self.file(self.base,'x.bin',b'base\0')
        self.file(self.patched,'x.bin',b'patched\0')
        self.file(self.target,'x.bin',b'euro\0')
        report=port.port(self.base,self.patched,self.target)
        self.assertEqual(len(report['conflicts']),1)
        self.assertEqual((self.target/'x.bin').read_bytes(), b'euro\0')

    def test_missing_cryptpad_file_does_not_delete_eurooffice(self):
        self.file(self.base,'legacy.cpp',b'legacy\n')
        self.file(self.target,'legacy.cpp',b'eurooffice version\n')
        report=port.port(self.base,self.patched,self.target)
        self.assertIn('legacy.cpp',report['removed_in_cryptpad_ignored'])
        self.assertTrue((self.target/'legacy.cpp').exists())

if __name__ == '__main__': unittest.main()
