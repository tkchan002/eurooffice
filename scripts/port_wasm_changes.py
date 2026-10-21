#!/usr/bin/env python3
"""Conservative, build-scoped CryptPad adaptation for EuroOffice/core v9.3.5.

Select only source subtrees used by CryptPad's x2t Docker build. Changes in
unrelated vendored tools (especially V8/socketio and nc-build scripts) are
logged as excluded; they are never merged and cannot conflict. A remaining
conflict in build-scoped material is fatal and needs an explicit source fix.
No auto-ours/auto-theirs resolution is permitted for build-scoped changes.
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

SKIP_DIRS = {'.git', '.svn', '__pycache__'}


def inventory(root):
    found = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and
                         not pathlib.Path(current, d).is_symlink())
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
    for p in paths:
        if p.stat().st_size > 25 * 1024 * 1024:
            return False
        with open(p, 'rb') as stream:
            if b'\0' in stream.read(1024 * 1024):
                return False
    return True


def load_policy(path):
    data = json.loads(pathlib.Path(path).read_text('utf-8'))
    if data['schemaVersion'] != 1:
        raise ValueError('Unsupported scope schemaVersion')
    required = ('compiledSourceRoots', 'compiledThirdPartyRoots',
                'excludedPrefixes', 'excludedBasenames', 'mandatorySourceFiles')
    for field in required:
        if not isinstance(data.get(field), list) or not data[field]:
            raise ValueError('Missing or empty scope field: ' + field)
    if len(data['mandatorySourceFiles']) != 3:
        raise ValueError('Expected all three CryptPad renderer stubs')
    return data


def inclusion_reason(relative_path, policy):
    """Return (included, reason) -- exclusions are explicit and auditable."""
    if relative_path.startswith(tuple(policy['excludedPrefixes'])):
        return False, 'excluded unrelated third-party subtree'
    if pathlib.PurePosixPath(relative_path).name in policy['excludedBasenames']:
        return False, 'excluded non-Docker nc-build / vendored tooling'
    components = relative_path.split('/')
    if components[0] not in policy['compiledSourceRoots']:
        return False, 'outside x2t compiler source roots'
    if relative_path.startswith('Common/3dParty/'):
        if len(components) < 4 or components[2] not in policy['compiledThirdPartyRoots']:
            return False, 'third-party component not built by x2t Docker recipe'
    return True, 'source in x2t compilation scope'


def port(base, patched, target, policy):
    originals = inventory(base)
    adaptations = inventory(patched)
    existing = inventory(target)
    report = {
        'source_base': str(base), 'cryptpad_tree': str(patched),
        'target_eurooffice': str(target), 'policyVersion': policy['schemaVersion'],
        'modified': [], 'added': [], 'already_present': [], 'merged': [],
        'copied': [], 'excluded': [], 'removed_in_cryptpad_ignored': [],
        'conflicts': [], 'mandatory': [], 'version': 2
    }
    for rel, patch_file in sorted(adaptations.items()):
        ancestor = originals.get(rel)
        if ancestor is not None and fingerprint(ancestor) == fingerprint(patch_file):
            continue
        included, reason = inclusion_reason(rel, policy)
        if not included:
            report['excluded'].append({'file': rel, 'reason': reason})
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
            report['conflicts'].append({'file': rel, 'reason': 'Both forks independently added a build-scoped file with different contents'})
            continue
        if fingerprint(out) == fingerprint(ancestor):
            shutil.copy2(patch_file, out)
            report['copied'].append(rel)
            continue
        if not text_only(ancestor, patch_file, out):
            report['conflicts'].append({'file': rel, 'reason': 'Non-identical binary or oversized build-scoped source'})
            continue
        proc = subprocess.run(['git', 'merge-file', '-p', '-L', 'EuroOffice 9.3.5',
                               '-L', 'ONLYOFFICE 9.3.0 baseline', '-L', 'CryptPad WASM',
                               str(out), str(ancestor), str(patch_file)], capture_output=True)
        if proc.returncode != 0:
            report['conflicts'].append({'file': rel, 'reason': 'Three-way merge conflict',
                                        'stderr': proc.stderr.decode('utf-8', errors='replace')[:1500]})
            conflict_path = target.parent / 'merge-conflicts' / rel
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            conflict_path.write_bytes(proc.stdout)
            continue
        out.write_bytes(proc.stdout)
        report['merged'].append(rel)
    report['removed_in_cryptpad_ignored'] = sorted(set(originals) - set(adaptations))
    required = policy['mandatorySourceFiles']
    for rel in required:
        file = target / rel
        status = 'present' if file.is_file() and file.stat().st_size else 'missing'
        report['mandatory'].append({'file': rel, 'status': status})
        if status != 'present':
            report['conflicts'].append({'file': rel, 'reason': 'Mandatory CryptPad renderer stub missing after scoped port'})
    return report


def emit_review_patch(base, patched, report, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', encoding='utf-8') as out:
        out.write('# Selected CryptPad changes (review only; not an applicable patch)\n')
        out.write('# Ignored upstream differences are listed in source-merge.json\n\n')
        for rel in sorted(report['modified'] + report['added']):
            old, new = base / rel, patched / rel
            if not text_only(*[p for p in (old, new) if p.is_file()]):
                out.write('# BINARY OR OVERSIZED: ' + rel + '\n')
                continue
            before = old.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True) if old.is_file() else []
            after = new.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
            out.writelines(difflib.unified_diff(before, after, fromfile='ONLYOFFICE/' + rel,
                                               tofile='CryptPad/' + rel, n=3))
            out.write('\n')


def main():
    ap = argparse.ArgumentParser()
    for arg in ('base', 'patched', 'target', 'report'):
        ap.add_argument('--' + arg, required=True)
    ap.add_argument('--scope', default='config/port-scope.json')
    ap.add_argument('--patch', help='Optional selected-source review diff')
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
        policy = load_policy(a.scope)
        report = port(*dirs, policy)
    except Exception as error:
        report = {'fatal': type(error).__name__ + ': ' + str(error)}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if a.patch and not report.get('fatal'):
        emit_review_patch(dirs[0], dirs[1], report, pathlib.Path(a.patch).resolve())
    for key in ('modified', 'added', 'excluded', 'already_present', 'merged', 'copied', 'mandatory', 'conflicts'):
        print(key + ':', len(report.get(key, [])))
    if report.get('fatal'):
        print(report['fatal'], file=sys.stderr)
        return 2
    for c in report['conflicts'][:25]:
        print('CONFLICT', c['file'], c['reason'], file=sys.stderr)
    if report['conflicts']:
        print('ERROR: unresolved conflicts remain INSIDE compilation scope; see source-merge.json', file=sys.stderr)
        return 1
    if not report['modified'] and not report['added']:
        print('ERROR: No build-scoped adaptations identified; verify source pins/scope.', file=sys.stderr)
        return 1
    print('PASS: prepared scoped EuroOffice source. Excluded changes have NOT been merged.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
