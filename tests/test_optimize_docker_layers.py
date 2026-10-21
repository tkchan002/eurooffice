"""Synthetic pinned-recipe invariants: no network or Docker required."""
import importlib.util
import unittest
from pathlib import Path
import tempfile
import json

SRC = Path(__file__).resolve().parents[1] / 'scripts' / 'optimize_docker_layers.py'
spec = importlib.util.spec_from_file_location('optimize_docker_layers', SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture():
    chunks = ['FROM ubuntu:22.04 AS base\nRUN echo base\n\n',
              'FROM base AS build-tools\nRUN echo tools\n\n']
    for i in range(18):
        # CryptPad's independent stages copy these very frequently.
        chunks.append(f'FROM base AS library{i}\n'
                      'COPY core/Common /core/Common\n'
                      'COPY core/DesktopEditor/ /core/DesktopEditor/\n'
                      'COPY core/OOXML /core/OOXML\n'
                      'COPY core/OdfFile /core/OdfFile\n'
                      'COPY --from=build-tools /build_tools /build_tools\n'
                      'RUN test -e /core/Common\n\n')
    chunks.append('FROM base AS doctrenderer\n'
                  'COPY core/DesktopEditor /core/DesktopEditor\n'
                  'RUN cp /core/DesktopEditor/doctrenderer/doctrenderer_empty.cpp /core/DesktopEditor/doctrenderer/doctrenderer.cpp\n'
                  'COPY core/Common /core/Common\n'
                  'COPY core/OOXML /core/OOXML\n'
                  'COPY core/OdfFile /core/OdfFile\n\n')
    chunks.append('FROM base AS build\nCOPY core /core\n'
                  'COPY --from=library12 /core/build/lib/linux_64/libtest.a /core/build/lib/linux_64/\n'
                  'RUN embuild.sh X2tConverter\n\nFROM scratch AS output\n'
                  'COPY --from=build /core/build/bin/linux_64/x2t.wasm x2t.wasm\n')
    return ''.join(chunks)


class DeduplicateTests(unittest.TestCase):
    def test_removes_copies_but_preserves_compile_steps_and_artifact_copies(self):
        original = fixture()
        rewritten, report = mod.analyze(original)
        self.assertTrue(report['ok'])
        self.assertGreater(report['removed_redundant_source_copy_instructions'], 70)
        self.assertEqual(rewritten.count('COPY core/ /core/'), 1)
        self.assertIn('FROM eurooffice-core AS library10', rewritten)
        self.assertIn('FROM eurooffice-core AS build', rewritten)
        self.assertIn('FROM base AS build-tools', rewritten)
        self.assertIn('RUN embuild.sh X2tConverter', rewritten)
        self.assertIn('RUN cp /core/DesktopEditor/doctrenderer/doctrenderer_empty.cpp', rewritten)
        self.assertIn('COPY --from=library12 /core/build/lib/linux_64/libtest.a', rewritten)
        self.assertIn('FROM scratch AS output', rewritten)

    def test_second_pass_is_identical(self):
        rewritten, _ = mod.analyze(fixture())
        again, report = mod.analyze(rewritten)
        self.assertEqual(rewritten, again)
        self.assertTrue(report['previously_optimized'])
        self.assertEqual(report['removed_redundant_source_copy_instructions'], 0)

    def test_fail_closed_on_changed_parent(self):
        changed = fixture().replace('FROM ubuntu:22.04 AS base', 'FROM ubuntu:24.04 AS base')
        with self.assertRaisesRegex(ValueError, 'pinned Ubuntu'):
            mod.analyze(changed)

    def test_fail_closed_on_inadequate_build_scope(self):
        changed = fixture().replace('FROM base AS library', 'FROM scratch AS library')
        with self.assertRaisesRegex(ValueError, 'few converter library copies'):
            mod.analyze(changed)

    def test_non_identical_context_paths_are_never_removed(self):
        original = fixture().replace('COPY core/OOXML /core/OOXML',
                   'COPY core/OOXML /backup/OOXML', 1)
        rewritten, _ = mod.analyze(original)
        self.assertIn('COPY core/OOXML /backup/OOXML', rewritten)

    def test_writes_diagnostics_and_does_not_modify_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dockerfile=Path(tmp)/'Dockerfile'
            diagnostics=Path(tmp)/'layers.json'
            source=fixture().replace('FROM ubuntu:22.04 AS base', 'FROM ubuntu:24.04 AS base')
            dockerfile.write_text(source)
            self.assertEqual(mod.main([str(dockerfile), '--report', str(diagnostics)]), 1)
            self.assertFalse(json.loads(diagnostics.read_text())['ok'])
            self.assertEqual(dockerfile.read_text(), source)

    def test_roundtrip_cli_produces_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            dockerfile=Path(tmp)/'Dockerfile'
            diagnostics=Path(tmp)/'layers.json'
            dockerfile.write_text(fixture())
            self.assertEqual(mod.main([str(dockerfile), '--report', str(diagnostics)]), 0)
            self.assertTrue(json.loads(diagnostics.read_text())['ok'])

if __name__ == '__main__':
    unittest.main()
