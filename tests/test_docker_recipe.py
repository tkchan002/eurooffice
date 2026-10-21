"""Pinned CryptPad Docker recipe regression tests (including the observed failure)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location(path.removesuffix('.py'), ROOT / 'scripts' / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tune = load('tune_docker_recipe.py')
audit = load('check_docker_recipe.py')


# A minimal accurate excerpt of pinned CryptPad 95f775f Docker stage layout;
# this is not a full C++ compilation fixture.
RECIPE = '''FROM ubuntu:22.04 AS base
FROM base AS html
COPY core/Common/3dParty/html /core/Common/3dParty/html
WORKDIR /core/Common/3dParty/html
RUN python fetch.py
RUN sed -i 's/tty()/0/' katana-parser/src/katana.lex.c
FROM base AS heif
RUN true
FROM base AS fb2file
COPY core/Common /core/Common
COPY --from=gumbo /gumbo-parser /gumbo-parser
WORKDIR /core
RUN embuild.sh Fb2File
FROM base AS htmlfile2
COPY --from=html /core/Common/3dParty/html /core/Common/3dParty/html
RUN embuild.sh HtmlFile2
FROM base AS log-symbols
RUN mkdir -p /core/build/lib/linux_64/
COPY --from=gumbo /usr/local/lib/libgumbo.a /core/build/lib/linux_64/
COPY --from=katana /usr/local/lib/libkatana.a /core/build/lib/linux_64/
COPY --from=fb2file /core/build/lib/linux_64/libFb2File.a /core/build/lib/linux_64/
FROM scratch AS log-symbols-output
COPY --from=log-symbols /out /
FROM base AS build
COPY --from=htmlfile2 /core/build/lib/linux_64/libHtmlFile2.a /core/build/lib/linux_64/
FROM scratch AS output
COPY --from=build /core/build/bin/linux_64/x2t.wasm x2t.wasm
'''


class RepairTests(unittest.TestCase):
    def test_original_recipe_is_rejected_before_docker(self):
        original = audit.inspect(RECIPE)
        self.assertEqual(['gumbo', 'katana'], original['undefined_copy_sources'])
        self.assertFalse(original['ok'])

    def test_repairs_original_gumbo_and_katana_references(self):
        fixed = tune.modify(RECIPE)
        self.assertNotIn('--from=gumbo', fixed)
        self.assertNotIn('--from=katana', fixed)
        self.assertIn('COPY --from=html /core/Common/3dParty/html /core/Common/3dParty/html', fixed)
        self.assertEqual(1, fixed.split('FROM base AS build\n')[1].count(tune.FB2_LIB))
        self.assertTrue(audit.inspect(fixed)['ok'])
        self.assertEqual([], audit.inspect(fixed)['undefined_copy_sources'])

    def test_repair_is_idempotent(self):
        once = tune.modify(RECIPE)
        self.assertEqual(once, tune.modify(once))

    def test_preserves_main_parser_fetch_stage(self):
        fixed = tune.modify(RECIPE)
        self.assertIn('RUN python fetch.py', fixed)
        self.assertIn('katana-parser/src/katana.lex.c', fixed)
        self.assertNotIn('RUN emcc', fixed)  # no invented build steps

    def test_missing_or_changed_gumbo_copy_stops_early(self):
        changed = RECIPE.replace(tune.OLD_FB2_PARSER, 'COPY --from=unknown /gumbo-parser /gumbo-parser\n')
        with self.assertRaisesRegex(ValueError, 'FB2 Gumbo'):
            tune.modify(changed)

    def test_missing_archive_line_stops_early(self):
        changed = RECIPE.replace(tune.OLD_KATANA_ARCHIVE, '')
        with self.assertRaisesRegex(ValueError, 'archive'):
            tune.modify(changed)

    def test_html_parser_copy_required(self):
        fixed = tune.modify(RECIPE)
        broken = fixed.replace(tune.NEW_FB2_PARSER, '')
        self.assertFalse(audit.inspect(broken)['ok'])
        self.assertIn('fb2_copies_fetched_parser_tree', audit.inspect(broken)['errors'])

    def test_new_undefined_stage_is_fatal(self):
        fixed = tune.modify(RECIPE)
        broken = fixed.replace('RUN embuild.sh Fb2File', 'COPY --from=mistake /x /y\nRUN embuild.sh Fb2File')
        self.assertEqual(['mistake'], audit.inspect(broken)['undefined_copy_sources'])
        self.assertFalse(audit.inspect(broken)['ok'])

    def test_output_includes_fb2(self):
        fixed = tune.modify(RECIPE)
        self.assertIn(tune.FB2_LIB, fixed.split('FROM base AS build\n')[1])

    def test_deletion_of_html_fetch_is_rejected(self):
        recipe = RECIPE.replace('RUN python fetch.py\n', '')
        with self.assertRaisesRegex(ValueError, 'fetch'):
            tune.modify(recipe)

    def test_multiple_html_stages_are_rejected(self):
        recipe = RECIPE.replace('FROM base AS html\n', 'FROM base AS html\nFROM base AS html\n')
        with self.assertRaisesRegex(ValueError, 'html fetch'):
            tune.modify(recipe)

    def test_cli_audit_writes_report_and_exits_nonzero_on_missing_stages(self):
        import subprocess, json
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dockerfile = root / 'Dockerfile'
            report = root / 'report.json'
            dockerfile.write_text(RECIPE)
            command = ['python3', str(ROOT / 'scripts/check_docker_recipe.py'), str(dockerfile), '--report', str(report)]
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(['gumbo', 'katana'], json.loads(report.read_text())['undefined_copy_sources'])
            dockerfile.write_text(tune.modify(RECIPE))
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(json.loads(report.read_text())['ok'])


if __name__ == '__main__':
    unittest.main()
