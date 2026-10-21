#!/usr/bin/env python3
"""Port CryptPad's browser-only doctrenderer qmake project descriptions.

Do not port native V8, V8 Inspector, or native JS embedding sources into the
browser-only x2t converter. Only two .pri *build descriptions* are replaced.
The whole source tree remains EuroOffice 9.3.5, including native source, legal
notices and its security fixes. Both inputs come from pinned upstream checkouts.

This is a source adaptation, not a successful WASM compilation claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('DesktopEditor/doctrenderer')
FILES = ('doctrenderer.pri', 'js_internal/js_base.pri')


def active_lines(content):
    """qmake project instructions without comment-only/blank lines."""
    return '\n'.join(line.split('#', 1)[0].strip() for line in content.splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))


def sha(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def validate_cryptpad(rel, content):
    active = active_lines(content)
    if rel == 'doctrenderer.pri':
        required = ('TARGET = doctrenderer', 'SOURCES +=',
                    '$$PWD_CUR/doctrenderer.cpp', '$$PWD_CUR/docbuilder.cpp',
                    '$$PWD_CUR/docbuilder_p.cpp',
                    'include($$PWD_CUR/js_internal/js_base.pri)')
        excluded = ('ADD_FILES_FOR_EMBEDDED_CLASS_HEADER(',
                    'CONFIG += drawingfile_support',
                    '$$PWD_CUR/embed/NativeControlEmbed.cpp',
                    '$$PWD_CUR/json/json.cpp')
    else:
        required = ('include($$PWD/js_base_embed.pri)',
                    '$$PWD/js_base.cpp', '$$PWD/js_logger.cpp')
        excluded = ('$$PWD/v8/v8_base.cpp', 'V8_INSPECTOR',
                    'CONFIG += v8_use_inspector',
                    'include($$PWD/../../../Common/3dParty/v8/v8.pri)',
                    '$$V8_INSPECTOR_PATH/inspector.cpp')
        if '# CryptPad: Do not build any actual JS engine' not in content:
            raise ValueError('CryptPad JS-engine disable marker missing')
    for line in required:
        if line not in active:
            raise ValueError(f'{rel}: required browser-only build instruction missing: {line}')
    for line in excluded:
        if line in active:
            raise ValueError(f'{rel}: native source unexpectedly active: {line}')
    # Broad regression guard: adding a V8 inspector or the V8 SDK is not a fix.
    if 'v8/inspector' in active or 'boost/beast' in active:
        raise ValueError(f'{rel}: native inspector or Beast dependency is active')


def validate_eurooffice(rel, content):
    active = active_lines(content)
    if rel == 'doctrenderer.pri':
        required = ('TARGET = doctrenderer', 'CONFIG += drawingfile_support',
                    'ADD_FILES_FOR_EMBEDDED_CLASS_HEADER(',
                    'include($$PWD_CUR/js_internal/js_base.pri)')
    else:
        required = ('!use_javascript_core {', '$$PWD/v8/v8_base.cpp',
                    'CONFIG += v8_use_inspector', 'DEFINES += V8_INSPECTOR')
    for line in required:
        if line not in active:
            raise ValueError(f'{rel}: EuroOffice source differs from known native configuration: {line}')


def port(cryptpad, eurooffice):
    changes = []
    # Verify both complete inputs before writing either file (no half patch).
    for rel in FILES:
        source = cryptpad / ROOT / rel
        dest = eurooffice / ROOT / rel
        if not source.is_file() or not dest.is_file() or source.is_symlink() or dest.is_symlink():
            raise ValueError(f'Expected regular qmake files missing or symlinked: {rel}')
        original = dest.read_text(encoding='utf-8-sig')
        wasm = source.read_text(encoding='utf-8-sig')
        validate_cryptpad(rel, wasm)
        if original == wasm:
            state = 'already_patched'
        else:
            validate_eurooffice(rel, original)
            state = 'ported'
        changes.append({'file': (ROOT / rel).as_posix(), 'status': state,
                        'previous_sha256': sha(original), 'wasm_sha256': sha(wasm),
                        '_text': wasm, '_path': dest})
    for change in changes:
        if change['status'] == 'ported':
            change['_path'].write_text(change['_text'], encoding='utf-8')
    return {'ok': True, 'strategy': 'two-pinned-CryptPad-browser-only-qmake-projects',
            'reason': 'Exclude native V8/Inspector and optional renderer embedding from x2t WASM',
            'files': [{k: v for k, v in change.items() if not k.startswith('_')}
                      for change in changes]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cryptpad', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = port(args.cryptpad, args.target)
    except (ValueError, OSError, UnicodeError) as exc:
        result = {'ok': False, 'error': str(exc)}
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if not result['ok']:
        print('WASM RENDERER PORT FAILED: '+result['error'], file=sys.stderr)
        return 1
    print('PASS: native renderer V8/Inspector excluded in both pinned qmake project files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
