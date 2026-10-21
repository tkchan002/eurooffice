#!/usr/bin/env python3
"""Conservatively port CryptPad's x2t-WASM changes onto EuroOffice.

Three-way merge per modified text file:
  common ancestor: upstream ONLYOFFICE/core v9.3.0.140
  incoming: CryptPad onlyoffice-x2t-wasm/core at pinned commit
  current: Euro-Office/core v9.3.5

This is intentionally fail-closed: it NEVER chooses one side silently on a
conflict, never auto-applies binary differences, and never deletes EuroOffice
source simply because a file is absent from CryptPad's old source tree.
"""
import argparse
import difflib
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SKIP_DIRS = {'.git', '.svn', '__pycache__'}


def inventory(root):
    found = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not pathlib.Path(current, d).is_symlink())
        for f in files:
            p = pathlib.Path(current, f)
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                raise RuntimeError('Refusing source symlink: ' + str(p))
            if p.is_file():
                found[rel] = p
    return found


def fingerprint(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.digest()


def text_only(*paths):
    # git merge-file requires line-oriented text. Avoid destructive attempts
    # on binary files and files of excessive size.
    for p in paths:
        if p.stat().st_size > 25 * 1024 * 1024:
            return False
        with open(p, 'rb') as stream:
            if b'\0' in stream.read(1024 * 1024):
                return False
    return True


def port(base, patched, target):
    originals = inventory(base)
    adaptations = inventory(patched)
    existing = inventory(target)
    report = {'source_base': str(base), 'cryptpad_tree': str(patched),
              'target_eurooffice': str(target), 'modified': [], 'added': [],
              'already_present': [], 'merged': [], 'copied': [], 'removed_in_cryptpad_ignored': [],
              'conflicts': [], 'version': 1}

    for rel, patch_file in sorted(adaptations.items()):
        ancestor = originals.get(rel)
        if ancestor is not None and fingerprint(ancestor) == fingerprint(patch_file):
            continue
        if ancestor is None:
            report['added'].append(rel)
        else:
            report['modified'].append(rel)
        out = target / rel
        if rel not in existing:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(patch_file, out)
            report['copied'].append(rel)
            continue
        if fingerprint(out) == fingerprint(patch_file):
            report['already_present'].append(rel)
            continue
        if ancestor is None:
            report['conflicts'].append({'file': rel, 'reason': 'Both EuroOffice and CryptPad independently added this file with different contents'})
            continue
        if fingerprint(out) == fingerprint(ancestor):
            shutil.copy2(patch_file, out)
            report['copied'].append(rel)
            continue
        if not text_only(ancestor, patch_file, out):
            report['conflicts'].append({'file': rel, 'reason': 'Non-identical binary/oversized source cannot be auto-merged'})
            continue
        # Do not edit EuroOffice source until merge result has been verified.
        proc = subprocess.run(['git', 'merge-file', '-p', '-L', 'EuroOffice 9.3.5',
                               '-L', 'ONLYOFFICE 9.3.0 baseline', '-L', 'CryptPad WASM',
                               str(out), str(ancestor), str(patch_file)],
                              capture_output=True)
        if proc.returncode != 0:
            report['conflicts'].append({'file': rel, 'reason': 'Three-way merge conflict',
                                        'stderr': proc.stderr.decode('utf-8', errors='replace')[:1500]})
            # Store conflicted results separately, for engineering review.
            conflict_path = target.parent / 'merge-conflicts' / rel
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            conflict_path.write_bytes(proc.stdout)
            continue
        out.write_bytes(proc.stdout)
        report['merged'].append(rel)

    # Some CryptPad-adapted source removes files. Do NOT remove EuroOffice code
    # automatically; record and review explicitly.
    report['removed_in_cryptpad_ignored'] = sorted(set(originals) - set(adaptations))
    return report


def emit_review_patch(base, patched, report, destination):
    """Produce a textual, file-specific change report; no auto-generated code is executed."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', encoding='utf-8') as out:
        out.write('# CryptPad modifications compared to ONLYOFFICE v9.3.0.140\n')
        out.write('# This is for review, not an automatically applicable git patch.\n\n')
        for rel in sorted(report['modified'] + report['added']):
            old, new = base / rel, patched / rel
            if not text_only(*[p for p in (old, new) if p.is_file()]):
                out.write('# BINARY/OVERSIZED MODIFICATION: ' + rel + '\n')
                continue
            before = old.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True) if old.is_file() else []
            after = new.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
            diff = difflib.unified_diff(before, after, fromfile='ONLYOFFICE/' + rel,
                                        tofile='CryptPad/' + rel, n=3)
            out.writelines(diff)
            out.write('\n')


def main():
    ap = argparse.ArgumentParser()
    for arg in ('base', 'patched', 'target', 'report'):
        ap.add_argument('--' + arg, required=True)
    ap.add_argument('--patch', help='Optional reviewable unified diff of CryptPad adaptations')
    a = ap.parse_args()
    dirs = [pathlib.Path(getattr(a, k)).resolve() for k in ('base', 'patched', 'target')]
    for d in dirs:
        if not d.is_dir():
            ap.error('Not a directory: ' + str(d))
    if len(set(dirs)) != 3:
        ap.error('Inputs must be three different directories')
    report_path = pathlib.Path(a.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = port(*dirs)
    except Exception as error:
        report = {'fatal': type(error).__name__ + ': ' + str(error)}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if a.patch and not report.get('fatal'):
        emit_review_patch(dirs[0], dirs[1], report, pathlib.Path(a.patch).resolve())
    for k in ('modified', 'added', 'already_present', 'merged', 'copied', 'removed_in_cryptpad_ignored', 'conflicts'):
        print(k + ':', len(report.get(k, [])))
    if report.get('fatal'):
        print(report['fatal'], file=sys.stderr)
        return 2
    for c in report['conflicts'][:25]:
        print('CONFLICT', c['file'], c['reason'], file=sys.stderr)
    if report['conflicts']:
        print('ERROR: do not build until all conflicts are explicitly resolved.', file=sys.stderr)
        return 1
    if not report['modified'] and not report['added']:
        print('ERROR: No WASM source adaptations identified; verify CryptPad pin.', file=sys.stderr)
        return 1
    print('PASS: prepared EuroOffice source with ported CryptPad adaptations.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
