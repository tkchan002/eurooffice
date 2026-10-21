"""Regression test for the observed Boost.Beast/V8 inspector compile failure."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('port_renderer_qmake', ROOT / 'scripts/port_renderer_qmake.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CPP = '''TARGET = doctrenderer
SOURCES += \\
    $$PWD_CUR/doctrenderer.cpp \\
    $$PWD_CUR/docbuilder.cpp \\
    $$PWD_CUR/docbuilder_p.cpp
include($$PWD_CUR/js_internal/js_base.pri)
'''
EURO_DOC = CPP + '''
ADD_FILES_FOR_EMBEDDED_CLASS_HEADER($$PWD_CUR/embed/HashEmbed.h)
CONFIG += drawingfile_support
drawingfile_support {
    SOURCES += $$PWD_CUR/embed/DrawingFileEmbed.cpp
}
'''
CRYPT_DOC = CPP + '''
# ADD_FILES_FOR_EMBEDDED_CLASS_HEADER($$PWD_CUR/embed/HashEmbed.h)
# CONFIG += drawingfile_support
# SOURCES += $$PWD_CUR/embed/NativeControlEmbed.cpp
# SOURCES += $$PWD_CUR/json/json.cpp
'''
EURO_JS = '''include($$PWD/js_base_embed.pri)
SOURCES += $$PWD/js_base.cpp
SOURCES += $$PWD/js_logger.cpp
!use_javascript_core {
    SOURCES += $$PWD/v8/v8_base.cpp
    !disable_v8_use_inspector:CONFIG += v8_use_inspector
    v8_use_inspector {
        DEFINES += V8_INSPECTOR
        SOURCES += $$V8_INSPECTOR_PATH/inspector.cpp
    }
}
'''
CRYPT_JS = '''include($$PWD/js_base_embed.pri)
SOURCES += $$PWD/js_base.cpp
SOURCES += $$PWD/js_logger.cpp
# CryptPad: Do not build any actual JS engine
# !use_javascript_core {
# SOURCES += $$PWD/v8/v8_base.cpp
# !disable_v8_use_inspector:CONFIG += v8_use_inspector
# v8_use_inspector {
# DEFINES += V8_INSPECTOR
# SOURCES += $$V8_INSPECTOR_PATH/inspector.cpp
# }
# }
'''


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cp = self.base / 'cryptpad'
        self.eo = self.base / 'eurooffice'
        for root, files in ((self.cp, {'doctrenderer.pri': CRYPT_DOC, 'js_internal/js_base.pri': CRYPT_JS}),
                            (self.eo, {'doctrenderer.pri': EURO_DOC, 'js_internal/js_base.pri': EURO_JS})):
            for rel, content in files.items():
                path = root / mod.ROOT / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

    def test_removes_compiled_inspector_without_editing_cpp(self):
        result = mod.port(self.cp, self.eo)
        self.assertTrue(result['ok'])
        self.assertEqual(['ported', 'ported'], [x['status'] for x in result['files']])
        copied = (self.eo / mod.ROOT / 'js_internal/js_base.pri').read_text()
        self.assertEqual(CRYPT_JS, copied)
        self.assertNotIn('V8_INSPECTOR', mod.active_lines(copied))
        self.assertNotIn('v8_base.cpp', mod.active_lines(copied))
        self.assertNotIn('inspector.cpp', mod.active_lines(copied))

    def test_idempotent(self):
        mod.port(self.cp, self.eo)
        result = mod.port(self.cp, self.eo)
        self.assertEqual(['already_patched', 'already_patched'], [x['status'] for x in result['files']])

    def test_missing_cryptpad_marker_refuses_both_changes(self):
        target = self.cp / mod.ROOT / 'js_internal/js_base.pri'
        target.write_text(CRYPT_JS.replace('# CryptPad: Do not build any actual JS engine', '# no marker'))
        with self.assertRaisesRegex(ValueError, 'marker'):
            mod.port(self.cp, self.eo)
        self.assertEqual(EURO_DOC, (self.eo / mod.ROOT / 'doctrenderer.pri').read_text())

    def test_native_v8_accidentally_enabled_refused(self):
        target = self.cp / mod.ROOT / 'js_internal/js_base.pri'
        target.write_text(CRYPT_JS + '\nSOURCES += $$PWD/v8/v8_base.cpp\n')
        with self.assertRaisesRegex(ValueError, 'native source unexpectedly active'):
            mod.port(self.cp, self.eo)

    def test_inspector_beast_dependency_refused(self):
        target = self.cp / mod.ROOT / 'doctrenderer.pri'
        target.write_text(CRYPT_DOC + '\nINCLUDEPATH += boost/beast/core.hpp\n')
        with self.assertRaisesRegex(ValueError, 'Beast'):
            mod.port(self.cp, self.eo)

    def test_mismatch_eurooffice_fails_closed(self):
        target = self.eo / mod.ROOT / 'doctrenderer.pri'
        target.write_text('completely different editor configuration')
        with self.assertRaisesRegex(ValueError, 'native configuration'):
            mod.port(self.cp, self.eo)
        self.assertEqual(EURO_JS, (self.eo / mod.ROOT / 'js_internal/js_base.pri').read_text())

    def test_missing_source_fails_closed(self):
        (self.cp / mod.ROOT / 'doctrenderer.pri').unlink()
        with self.assertRaisesRegex(ValueError, 'missing or symlinked'):
            mod.port(self.cp, self.eo)

    def test_missing_project_command_refused(self):
        target = self.cp / mod.ROOT / 'doctrenderer.pri'
        target.write_text(CRYPT_DOC.replace('include($$PWD_CUR/js_internal/js_base.pri)', ''))
        with self.assertRaisesRegex(ValueError, 'required browser-only'):
            mod.port(self.cp, self.eo)

    def test_cli_reports_provenance(self):
        report = self.base / 'report.json'
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/port_renderer_qmake.py'), '--cryptpad', str(self.cp),
                               '--target', str(self.eo), '--report', str(report)], capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stderr)
        data = json.loads(report.read_text())
        self.assertTrue(data['ok'])
        self.assertEqual(2, len(data['files']))
        self.assertTrue(all(len(x['wasm_sha256']) == 64 for x in data['files']))

    def test_cli_failure_has_diagnostic_artifact(self):
        report = self.base / 'report.json'
        (self.cp / mod.ROOT / 'doctrenderer.pri').unlink()
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/port_renderer_qmake.py'), '--cryptpad', str(self.cp),
                               '--target', str(self.eo), '--report', str(report)], capture_output=True, text=True)
        self.assertNotEqual(0, proc.returncode)
        self.assertFalse(json.loads(report.read_text())['ok'])

    def test_action_order_and_port_script_compile(self):
        workflow = (ROOT / '.github/workflows/build-eurooffice-x2t.yml').read_text()
        self.assertLess(workflow.index('Prepare reviewed EuroOffice WASM source'), workflow.index('Port CryptPad browser-only renderer'))
        self.assertLess(workflow.index('Port CryptPad browser-only renderer'), workflow.index('Record exact source modifications'))
        compile((ROOT / 'scripts/port_renderer_qmake.py').read_text(), 'port_renderer_qmake.py', 'exec')


if __name__ == '__main__':
    unittest.main()
