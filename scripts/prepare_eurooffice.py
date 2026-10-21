#!/usr/bin/env python3
"""Prepare EuroOffice 9.3.5 for the CryptPad qmake/Emscripten recipe.

The previous broad three-way merge was an incorrect model: CryptPad's tree
contains historical ONLYOFFICE changes, not only WASM fixes. This adapter is
allowlisted, preserves all unreviewed EuroOffice source, and fails closed.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import sys


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, rel):
    pure = pathlib.PurePosixPath(rel)
    if pure.is_absolute() or '..' in pure.parts or '\\' in rel or not rel.strip():
        raise ValueError('Unsafe relative source path: ' + repr(rel))
    p = root.joinpath(*pure.parts)
    if p.is_symlink():
        raise ValueError('Symlink not allowed in source preparation: ' + str(p))
    return p


def prepare(cryptpad, target, policy):
    if policy['schemaVersion'] != 3:
        raise ValueError('Unsupported policy version')
    report = {'version': 3, 'strategy': 'allowlisted-eurooffice-first',
              'copied': [], 'already_present': [], 'patched': [],
              'already_patched': [], 'preserved': [], 'assertions': [],
              'errors': [], 'source': str(cryptpad), 'target': str(target)}

    for rel in policy['importIfMissing']:
        src = safe_path(cryptpad, rel)
        dst = safe_path(target, rel)
        if not src.is_file():
            report['errors'].append({'file': rel, 'reason': 'Required CryptPad build-support file absent'})
            continue
        if dst.is_file():
            if sha256(src) == sha256(dst):
                report['already_present'].append({'file': rel, 'sha256': sha256(dst)})
            elif rel.endswith('_empty.cpp'):
                report['errors'].append({'file': rel, 'reason': 'Renderer stub differs; requires reviewed adaptation'})
            else:
                report['preserved'].append({'file': rel, 'reason': 'EuroOffice already provides build-support file'})
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        report['copied'].append({'file': rel, 'sha256': sha256(dst)})

    for item in policy['replaceExact']:
        rel, old, new = item['file'], item['old'], item['new']
        dst = safe_path(target, rel)
        if not dst.is_file():
            report['errors'].append({'file': rel, 'reason': 'EuroOffice source missing for targeted edit'})
            continue
        source = dst.read_text(encoding='utf-8')
        if source.count(new) == 1:
            # For wrapper edits the original string is contained inside the new
            # text. Test the completed state first or a second run corrupts it.
            report['already_patched'].append({'file': rel, 'reason': item['reason']})
        elif source.count(old) == 1:
            revised = source.replace(old, new, 1)
            dst.write_text(revised, encoding='utf-8')
            report['patched'].append({'file': rel, 'reason': item['reason'], 'sha256': sha256(dst)})
        else:
            report['errors'].append({'file': rel, 'reason': 'Exact edit precondition failed; do not guess',
                                     'found_old': source.count(old), 'found_new': source.count(new)})

    for rel in policy['preserveEuroOffice']:
        dst = safe_path(target, rel)
        if not dst.is_file():
            report['errors'].append({'file': rel, 'reason': 'Expected EuroOffice file missing'})
        else:
            report['preserved'].append({'file': rel, 'reason': 'Reviewed conflict: keep EuroOffice',
                                        'sha256': sha256(dst)})

    for item in policy['assertEuroOfficeContent']:
        dst = safe_path(target, item['file'])
        ok = dst.is_file() and item['needle'] in dst.read_text(encoding='utf-8')
        report['assertions'].append({'file': item['file'], 'needle': item['needle'], 'pass': ok})
        if not ok:
            report['errors'].append({'file': item['file'], 'reason': 'Safety/correctness assertion failed',
                                     'needle': item['needle']})
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cryptpad', required=True)
    ap.add_argument('--target', required=True)
    ap.add_argument('--policy', default='config/port-policy.json')
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    policy = json.loads(pathlib.Path(args.policy).read_text(encoding='utf-8'))
    target = pathlib.Path(args.target).resolve()
    cryptpad = pathlib.Path(args.cryptpad).resolve()
    if not target.is_dir() or not cryptpad.is_dir():
        ap.error('Missing source directory')
    try:
        report = prepare(cryptpad, target, policy)
    except Exception as exc:
        report = {'version': 3, 'errors': [{'reason': type(exc).__name__ + ': ' + str(exc)}]}
    report_file = pathlib.Path(args.report)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for name in ('copied', 'patched', 'already_patched', 'preserved', 'errors'):
        print(name + ':', len(report.get(name, [])))
    for problem in report.get('errors', []):
        print('SOURCE PREPARATION ERROR: ' + str(problem), file=sys.stderr)
    if report.get('errors'):
        return 1
    if not (report['copied'] or report['patched'] or report['already_patched']):
        print('No build changes applied; inspect source pins', file=sys.stderr)
        return 1
    print('PASS: EuroOffice source prepared with reviewed edits only; no whole-tree merge.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
