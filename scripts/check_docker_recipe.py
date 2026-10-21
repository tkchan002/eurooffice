#!/usr/bin/env python3
"""Fail closed on undefined Docker build stages and missing parser wiring."""
import argparse
import json
from pathlib import Path
import re
import sys

PARSER_COPY = ('COPY --from=html /core/Common/3dParty/html '
               '/core/Common/3dParty/html')
REQUIRED_FB2_LIB = ('COPY --from=fb2file /core/build/lib/linux_64/libFb2File.a '
                    '/core/build/lib/linux_64/')


def segment(text, start, end):
    a = text.find(start)
    b = text.find(end, a + len(start)) if a >= 0 else -1
    return text[a + len(start):b] if a >= 0 and b >= 0 else ''


def inspect(text):
    stages = re.findall(r'(?im)^\s*FROM\s+\S+\s+AS\s+([a-z0-9_.-]+)\s*$', text)
    copies = re.findall(r'(?im)^\s*COPY\s+--from=([a-z0-9_.-]+)\b', text)
    missing = sorted(set(copies) - set(stages))
    html = segment(text, 'FROM base AS html\n', 'FROM base AS heif\n')
    fb2 = segment(text, 'FROM base AS fb2file\n', 'FROM base AS htmlfile2\n')
    build = text.split('FROM base AS build\n', 1)[1] if 'FROM base AS build\n' in text else ''
    log_symbols = segment(text, 'FROM base AS log-symbols\n', 'FROM scratch AS log-symbols-output\n')
    checks = {
        'html_fetches_pinned_parser_sources': 'RUN python fetch.py' in html,
        'fb2_copies_fetched_parser_tree': PARSER_COPY in fb2,
        'final_link_includes_fb2': REQUIRED_FB2_LIB in build,
        'no_unresolved_parser_archives': not any(x in log_symbols for x in
                ('--from=gumbo', '--from=katana')),
        'no_undefined_copy_sources': not missing,
    }
    errors = [k for k, ok in checks.items() if not ok]
    return {
        'defined_stages': sorted(stages),
        'undefined_copy_sources': missing,
        'parser_strategy': 'reuse-html-fetch-and-pri-direct-C-compilation',
        'checks': checks,
        'errors': errors,
        'ok': not errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dockerfile')
    ap.add_argument('--report', required=True)
    a = ap.parse_args()
    result = inspect(Path(a.dockerfile).read_text(encoding='utf-8'))
    dest = Path(a.report)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if result['errors']:
        print('DOCKER PREFLIGHT FAILED: ' + ', '.join(result['errors']), file=sys.stderr)
        print('Undefined COPY sources: ' + ', '.join(result['undefined_copy_sources']), file=sys.stderr)
        return 1
    print('PASS: all COPY --from sources defined; HTML parser source and FB2 library wiring verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
