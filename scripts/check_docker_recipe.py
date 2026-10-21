#!/usr/bin/env python3
"""Audit pins and absent named build stages in the CryptPad Docker recipe."""
import argparse
import json
import pathlib
import re
import sys


def inspect(text):
    stages = []
    for match in re.finditer(r'(?im)^\s*FROM\s+\S+\s+AS\s+([a-z0-9_.-]+)\s*$', text):
        stages.append(match.group(1))
    copies = re.findall(r'(?im)^\s*COPY\s+--from=([a-z0-9_.-]+)\b', text)
    # External references are not assumed valid! An undefined stage probably
    # causes Docker to pull an unrelated public image; document this risk.
    missing = sorted(set(copies) - set(stages))
    return {'defined_stages': sorted(stages), 'undefined_copy_sources': missing,
            'risk': 'Undefined COPY --from names may resolve to external images, not build stages'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('dockerfile')
    p.add_argument('--report', required=True)
    a = p.parse_args()
    report = inspect(pathlib.Path(a.dockerfile).read_text())
    dst = pathlib.Path(a.report)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(report, indent=2) + '\n')
    if report['undefined_copy_sources']:
        print('RECIPE WARNING: undefined COPY --from build stages: ' + ', '.join(report['undefined_copy_sources']), file=sys.stderr)
        print('These stages must be resolved before expecting a successful converter compile.', file=sys.stderr)
    else:
        print('PASS: no undefined COPY --from stage names')


if __name__ == '__main__':
    main()
