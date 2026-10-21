#!/usr/bin/env python3
"""Surface non-hermetic build downloads; reporting only, never claims offline C++ builds."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlparse

URL = re.compile(r'https?://[^\s"\x27<>\\)]+')
OPERATIONS = re.compile(r'\b(?:git\s+clone|wget|curl|apt(?:-get)?|pip(?:3)?\s+install|npm\s+install)\b', re.I)

def audit(recipe: str):
    lines = []
    all_hosts = set()
    for index, line in enumerate(recipe.splitlines(), 1):
        if not (OPERATIONS.search(line) or URL.search(line)):
            continue
        hosts = sorted({urlparse(u.rstrip(';,:')).hostname for u in URL.findall(line)} - {None})
        all_hosts.update(hosts)
        lines.append({'line': index, 'excerpt': line[:280], 'hosts': hosts})
    return {'schema': 1, 'status': 'NOT_HERMETIC',
            'summary': 'Other build stages may fetch remote dependencies even when sources are mirrored.',
            'hosts': sorted(all_hosts), 'network_reference_lines': lines}

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('dockerfile')
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    report = audit(Path(args.dockerfile).read_text())
    path = Path(args.report); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print('External dependency audit:', len(report['network_reference_lines']), 'lines; hosts:', ', '.join(report['hosts']))
    print('WARNING: source mirroring does not archive Emscripten, apt, git dependencies or compiler images.')
