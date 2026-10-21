#!/usr/bin/env python3
"""Share the pinned EuroOffice source across CryptPad's large library stages.

Original CryptPad stages repeatedly use `FROM base` + `COPY core/<directory>`;
BuildKit retains all these COPY layers. Create one immutable, shared source parent,
then remove only *identical* context COPYs for stages inheriting it. Never
rewrite COPY --from, generated library COPYs, RUN commands, or downloaded deps.

No attempt is made to delete C++ source after compiling: such a deletion in a
later Docker layer does not recover disk from earlier immutable layers.
This patch is restricted to the pinned recipe shape and is designed to fail
closed if its shape changes. Does not perform upstream downloads.
"""
import argparse
import json
from pathlib import Path
import re
import sys

PARENT = 'eurooffice-core'
INSERT_AT = 'FROM base AS build-tools\n'
PARENT_DECL = 'FROM base AS eurooffice-core\nCOPY core/ /core/\n\n'
STAGE_LINE = re.compile(r'^FROM\s+([^\s]+)\s+AS\s+([A-Za-z0-9_.-]+)\s*$', re.I)
PLAIN_COPY = re.compile(r'^COPY\s+(core(?:/[^\s]*)?)\s+(/core(?:/[^\s]*)?)\s*$', re.I)


def same_source_destination(line):
    match = PLAIN_COPY.match(line.strip())
    if not match:
        return False
    src = match.group(1).strip('/').rstrip('/')
    dst = match.group(2).strip('/').rstrip('/')
    return src == dst


def split_stages(text):
    """Preserve every original instruction, including multiline RUN blocks."""
    headers = [m.start() for m in re.finditer(r'(?m)^FROM\s+[^\n]+$', text)]
    if not headers or headers[0] != 0:
        raise ValueError('Dockerfile does not start with FROM; verify pinned recipe')
    return [text[headers[i]:(headers[i+1] if i+1 < len(headers) else len(text))]
            for i in range(len(headers))]


def analyze(text):
    stages = split_stages(text)
    base_names = []
    changed_names = []
    removed = 0
    new_parts = []
    already = PARENT_DECL in text
    if text.count('FROM ubuntu:22.04 AS base\n') != 1:
        raise ValueError('Expected pinned Ubuntu 22.04 base stage')
    if text.count(INSERT_AT) != 1:
        raise ValueError('Pinned build-tools stage not found at expected location')
    if already and text.count(PARENT_DECL) != 1:
        raise ValueError('Multiple or unexpected shared-source stages')
    if not already and 'AS eurooffice-core' in text:
        raise ValueError('Shared source parent exists but its body is unexpected')
    for stage in stages:
        lines = stage.splitlines(keepends=True)
        first = lines[0].rstrip('\n')
        matched = STAGE_LINE.match(first)
        if not matched:
            raise ValueError('Unexpected stage declaration: '+first)
        parent, name = matched.groups()
        if parent.lower() == 'base':
            base_names.append(name)
        # COPY context paths only; all COPY --from instructions stay identical.
        candidates = [i for i, line in enumerate(lines[1:], start=1)
                      if same_source_destination(line)]
        if parent.lower() == 'base' and candidates and name != PARENT:
            lines[0] = f'FROM {PARENT} AS {name}\n'
            # Exact-identity COPYs are redundant once the full source is in parent.
            for i in candidates:
                lines[i] = ''
            changed_names.append(name)
            removed += len(candidates)
        new_parts.append(''.join(lines))
    updated = ''.join(new_parts)
    if not already:
        if len(changed_names) < 12 or removed < 45:
            raise ValueError(f'Unexpectedly few converter library copies: stages={len(changed_names)} copies={removed}; refusing partial optimisation')
        updated = updated.replace(INSERT_AT, PARENT_DECL + INSERT_AT, 1)
    # Strong invariant: no source context COPYs remain under a shared parent,
    # and only one copy of the full tree is used in the new parent.
    if updated.count(PARENT_DECL) != 1:
        raise ValueError('Shared parent count != 1 after transformation')
    for block in split_stages(updated):
        name_m = STAGE_LINE.match(block.splitlines()[0])
        if not name_m:
            raise ValueError('Invalid stage header after transformation')
        if name_m.group(1).lower() == PARENT and name_m.group(2) != PARENT:
            leaking = [line for line in block.splitlines()[1:] if same_source_destination(line)]
            if leaking:
                raise ValueError('Redundant source COPY remains in shared stage: '+name_m.group(2))
    stage_names = [STAGE_LINE.match(s.splitlines()[0]).group(2) for s in split_stages(updated)]
    if len(stage_names) != len(set(stage_names)):
        raise ValueError('Duplicate stage names')
    if 'output' not in stage_names or 'build' not in stage_names:
        raise ValueError('Final converter build/output stage missing')
    return updated, {'ok': True, 'strategy': 'shared-immutable-eurooffice-source-parent',
        'source_parent': PARENT, 'previously_optimized': already,
        'modified_stages': changed_names, 'modified_stage_count': len(changed_names),
        'removed_redundant_source_copy_instructions': removed,
        'total_docker_stages': len(stage_names), 'uses_original_build_target': 'output' in stage_names,
        'notes': ['COPY --from and RUN instructions untouched',
                  'All C++ library compile targets retained',
                  'Disk savings are unmeasured until a real BuildKit run']}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('dockerfile')
    ap.add_argument('--report', required=True)
    args = ap.parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        source = Path(args.dockerfile).read_text(encoding='utf-8')
        output, report = analyze(source)
        Path(args.dockerfile).write_text(output, encoding='utf-8')
    except (ValueError, OSError) as e:
        report_path.write_text(json.dumps({'ok': False, 'error': str(e)}, indent=2)+'\n')
        print('SHARED-LAYER OPTIMIZATION FAILED: '+str(e), file=sys.stderr)
        return 1
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    print('Shared EuroOffice source parent prepared: removed',
          report['removed_redundant_source_copy_instructions'],
          'redundant context COPY instructions from', report['modified_stage_count'], 'stages.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
