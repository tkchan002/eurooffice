import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def module(script_name):
    p = ROOT / 'scripts' / script_name
    spec = importlib.util.spec_from_file_location(script_name.removesuffix('.py'), p)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prep = module('prepare_eurooffice.py')
audit = module('check_docker_recipe.py')
docker = module('tune_docker_recipe.py')
POLICY = json.loads((ROOT / 'config' / 'port-policy.json').read_text())


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.cp = self.root / 'cryptpad'
        self.eo = self.root / 'eurooffice'
        self.cp.mkdir()
        self.eo.mkdir()
        self.policy = {
            'schemaVersion': 3,
            'importIfMissing': ['DesktopEditor/doctrenderer/doctrenderer_empty.cpp', 'Common/kernel.pro'],
            'replaceExact': [
                {'file': 'X2tConverter/src/main.cpp', 'old': '#include "x.h"', 'new': '#if 0\n#include "x.h"\n#endif', 'reason': 'test'}
            ],
            'preserveEuroOffice': ['PdfFile/lib/xpdf/Decrypt.cc'],
            'assertEuroOfficeContent': [
                {'file': 'PdfFile/lib/xpdf/Decrypt.cc', 'needle': '#include <openssl/sha.h>'}
            ],
        }
        self.write(self.cp, 'DesktopEditor/doctrenderer/doctrenderer_empty.cpp', '// stub\n')
        self.write(self.cp, 'Common/kernel.pro', 'cp project\n')
        self.write(self.eo, 'X2tConverter/src/main.cpp', '#include "x.h"\n// preserve rights notice\n')
        self.write(self.eo, 'PdfFile/lib/xpdf/Decrypt.cc', '#include <openssl/sha.h>\n')

    def write(self, root, rel, content):
        file = root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def test_allowlist_copies_and_preserves_copyright(self):
        self.write(self.cp, 'Common/Network/FileTransporter/src/FileTransporter_curl.cpp', 'SSL_VERIFY_PEER=0')
        self.write(self.eo, 'Common/Network/FileTransporter/src/FileTransporter_curl.cpp', 'SSL_VERIFY_PEER=1')
        result = prep.prepare(self.cp, self.eo, self.policy)
        self.assertEqual([], result['errors'])
        self.assertEqual(2, len(result['copied']))
        self.assertEqual('SSL_VERIFY_PEER=1', (self.eo / 'Common/Network/FileTransporter/src/FileTransporter_curl.cpp').read_text())
        self.assertIn('// preserve rights notice', (self.eo / 'X2tConverter/src/main.cpp').read_text())
        self.assertEqual('#include <openssl/sha.h>\n', (self.eo / 'PdfFile/lib/xpdf/Decrypt.cc').read_text())

    def test_twice_idempotent(self):
        self.assertFalse(prep.prepare(self.cp, self.eo, self.policy)['errors'])
        report = prep.prepare(self.cp, self.eo, self.policy)
        self.assertFalse(report['errors'])
        self.assertEqual(len(self.policy['replaceExact']), len(report['already_patched']))

    def test_missing_source_fails_closed(self):
        (self.cp / 'DesktopEditor/doctrenderer/doctrenderer_empty.cpp').unlink()
        result = prep.prepare(self.cp, self.eo, self.policy)
        self.assertTrue(any('absent' in e['reason'] for e in result['errors']))

    def test_unrecognised_edit_fails(self):
        self.write(self.eo, 'X2tConverter/src/main.cpp', 'unexpected upstream code')
        result = prep.prepare(self.cp, self.eo, self.policy)
        self.assertTrue(any('precondition failed' in e['reason'] for e in result['errors']))

    def test_unsafe_source_path_rejected(self):
        for name in ('../../outside', '/etc/passwd', 'foo\\..\\bar'):
            with self.assertRaises(ValueError):
                prep.safe_path(self.eo, name)

    def test_existing_eurooffice_project_is_not_overwritten(self):
        self.write(self.eo, 'Common/kernel.pro', 'EuroOffice project\n')
        result = prep.prepare(self.cp, self.eo, self.policy)
        self.assertFalse(result['errors'])
        self.assertEqual('EuroOffice project\n', (self.eo / 'Common/kernel.pro').read_text())

    def test_changed_empty_stub_requires_review(self):
        self.write(self.eo, 'DesktopEditor/doctrenderer/doctrenderer_empty.cpp', 'EuroOffice implementation')
        self.assertTrue(prep.prepare(self.cp, self.eo, self.policy)['errors'])

    def test_security_assertion_fails(self):
        self.write(self.eo, 'PdfFile/lib/xpdf/Decrypt.cc', 'unsafe implementation')
        self.assertTrue(prep.prepare(self.cp, self.eo, self.policy)['errors'])

    def test_all_reported_22_conflict_files_have_explicit_decision(self):
        conflict_paths = {
            'Apple/CMakeLists.txt', 'Common/3dParty/html/css/src/CCssCalculator_Private.h',
            'Common/3dParty/html/htmltoxhtml.cpp', 'Common/3dParty/md/md2html.cpp',
            'Common/CMakeLists.txt', 'Common/Network/CMakeLists.txt',
            'Common/Network/FileTransporter/src/FileTransporter_curl.cpp',
            'Common/js/desktop_fetch_new.js', 'DesktopEditor/doctrenderer/CMakeLists.txt',
            'DesktopEditor/fontengine/TextHyphen.cpp',
            'DesktopEditor/graphics/cmake/CMakeLists.txt',
            'DesktopEditor/graphics/pro/js/CMakeLists.txt',
            'DesktopEditor/graphics/pro/js/wasm/patches/fix-wasm-openssl.patch',
            'DesktopEditor/xmlsec/src/CMakeLists.txt',
            'DesktopEditor/xmlsec/src/wasm/3rdParty/patches/fix-wasm-openssl.patch',
            'DjVuFile/CMakeLists.txt', 'HtmlFile2/HTMLReader.cpp',
            'MsBinaryFile/Common/Vml/PPTShape/BinaryReader.cpp',
            'MsBinaryFile/Common/Vml/PPTShape/BinaryReader.h',
            'OdfFile/Reader/Converter/StarMath2OOXML/CMakeLists.txt',
            'OfficeUtils/CMakeLists.txt', 'PdfFile/lib/xpdf/Decrypt.cc',
        }
        resolved = set(POLICY['preserveEuroOffice']) | {x['file'] for x in POLICY['replaceExact']}
        self.assertEqual(conflict_paths, conflict_paths & resolved)

    def test_no_gross_merge_or_stubbed_fb2(self):
        script = (ROOT / 'scripts/prepare_eurooffice.py').read_text()
        self.assertNotIn('git merge-file', script)
        self.assertNotIn('return 0;', script)
        self.assertNotIn('onlyoffice-base', (ROOT / 'scripts/fetch_sources.sh').read_text())
        self.assertNotIn('html.h', [x['file'] for x in POLICY['replaceExact']])


class DockerTests(unittest.TestCase):
    def test_detect_external_sources(self):
        text = 'FROM alpine AS base\nFROM base AS build\nCOPY --from=gumbo /a /b\nCOPY --from=build /x /y\n'
        result = audit.inspect(text)
        self.assertEqual(['gumbo'], result['undefined_copy_sources'])

    def test_add_fb2_library_only_to_final_stage(self):
        marker = 'COPY --from=htmlfile2 /core/build/lib/linux_64/libHtmlFile2.a /core/build/lib/linux_64/\n'
        recipe = 'FROM base AS log-symbols\n' + marker + 'FROM base AS build\n' + marker
        text = docker.modify(recipe)
        self.assertEqual(1, text.count('COPY --from=fb2file /core/build/lib/linux_64/libFb2File.a'))
        self.assertEqual(text, docker.modify(text))

    def test_recipe_without_marker_fails(self):
        with self.assertRaises(ValueError):
            docker.modify('FROM base AS build\n')


if __name__ == '__main__':
    unittest.main()
