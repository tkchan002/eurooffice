#!/usr/bin/env python3
"""Create and verify independently owned, pinned x2t source snapshots.

Create: from audited pinned checkouts, emits two tar.gz and a committed lockfile.
Restore: from *local* checksummed archives, no network. Use for offline drill.
Do not confuse source independence with fully hermetic toolchain compilation.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile

PINS = {
    'cryptpad': '95f775fd3c42fae9e9af66ca072d3da3763e6c76',
    'eurooffice': '5a33ce6',  # checked by bootstrap against full git revision
}
ARCHIVES = {'cryptpad': 'cryptpad-source.tar.gz', 'eurooffice': 'eurooffice-source.tar.gz'}

def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def valid_repo(repo: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo))

def make_archive(source: Path, name: str, output: Path) -> None:
    if not (source / 'X2tConverter/src/main.cpp').is_file() and name == 'eurooffice':
        raise ValueError('EuroOffice source missing X2tConverter/src/main.cpp')
    if not (source / 'core/X2tConverter/src/main.cpp').is_file() and name == 'cryptpad':
        raise ValueError('CryptPad source missing core/X2tConverter/src/main.cpp')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tf:
            for item in sorted(source.rglob('*')):
                rel = item.relative_to(source)
                if '.git' in rel.parts or '__pycache__' in rel.parts:
                    continue
                if item.is_symlink():
                    # Preserve relative symlinks only if they resolve within snapshot root.
                    if not (item.parent / os.readlink(item)).resolve().is_relative_to(source.resolve()):
                        raise ValueError(f'Symlink escapes source: {item}')
                info = tf.gettarinfo(str(item), arcname=f'{name}/{rel.as_posix()}')
                info.uid = 0; info.gid = 0; info.uname = ''; info.gname = ''; info.mtime = 0
                if info.isfile():
                    with item.open('rb') as src:
                        tf.addfile(info, src)
                else:
                    tf.addfile(info)

def create(args):
    if not valid_repo(args.repository):
        raise ValueError('repository must be OWNER/REPO')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{4,128}', args.release_tag):
        raise ValueError('Invalid release tag')
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name in ('cryptpad', 'eurooffice'):
        source = Path(getattr(args, name)).resolve()
        revision = Path(getattr(args, name + '_commit')).read_text().strip()
        if not re.fullmatch(r'[0-9a-f]{40}', revision) or not revision.startswith(PINS[name]):
            raise ValueError(f'{name} revision differs from pinned source: {revision!r}')
        file = out / ARCHIVES[name]
        make_archive(source, name, file)
        entries[name] = {'asset': ARCHIVES[name], 'sha256': checksum(file),
                         'size': file.stat().st_size, 'commit': revision}
        print(f'{name}: {file.stat().st_size} bytes, sha256 {entries[name]["sha256"]}', flush=True)
    lock = {'schema': 1, 'archive_kind': 'pinned-source-snapshot',
            'repository': args.repository, 'release_tag': args.release_tag,
            'sources': entries}
    dest = Path(args.lock_output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n', encoding='utf8')
    print(f'Lockfile written: {dest}')

def verify_lock(lock):
    if lock.get('schema') != 1 or not valid_repo(lock.get('repository', '')):
        raise ValueError('Invalid source lockfile metadata')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{4,128}', lock.get('release_tag', '')):
        raise ValueError('Invalid locked release tag')
    if set(lock.get('sources', {})) != set(ARCHIVES):
        raise ValueError('Source lockfile must contain both snapshots')
    for name, filename in ARCHIVES.items():
        item = lock['sources'][name]
        if item.get('asset') != filename or not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', '')):
            raise ValueError(f'Invalid hash or asset for {name}')
        if not isinstance(item.get('size'), int) or item['size'] <= 0:
            raise ValueError(f'Invalid size for {name}')
        if not re.fullmatch(r'[0-9a-f]{40}', item.get('commit', '')) or not item['commit'].startswith(PINS[name]):
            raise ValueError(f'Unexpected revision for {name}')

def verify_assets(lock, directory):
    for name in ARCHIVES:
        info = lock['sources'][name]
        file = directory / info['asset']
        if not file.is_file() or file.stat().st_size != info['size']:
            raise ValueError(f'Missing/incorrect snapshot size: {file}')
        actual = checksum(file)
        if actual != info['sha256']:
            raise ValueError(f'SHA256 mismatch for {file}: {actual}')

def restore(args):
    lock = json.loads(Path(args.lock).read_text(encoding='utf8'))
    verify_lock(lock)
    archives = Path(args.archives_dir).resolve()
    verify_assets(lock, archives)  # verify both archives before writing any output
    target = Path(args.work_root).resolve()
    target.mkdir(parents=True, exist_ok=True)
    for name in ('cryptpad', 'eurooffice'):
        dest = target / name
        if dest.exists():
            raise ValueError(f'Refusing to overwrite existing source: {dest}')
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=target) as stage:
            # The data filter rejects escaping links, traversal and special files.
            with tarfile.open(archives / ARCHIVES[name], 'r:gz') as tar:
                for member in tar.getmembers():
                    parts = Path(member.name).parts
                    if not parts or parts[0] != name or '..' in parts or member.name.startswith('/'):
                        raise ValueError(f'Unexpected archive path: {member.name}')
                    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                        raise ValueError(f'Unsupported source archive entry: {member.name}')
                tar.extractall(stage, filter='data')
            restored = Path(stage) / name
            if not restored.is_dir():
                raise ValueError(f'Missing expected source root for {name}')
            needed = ('core/' if name == 'cryptpad' else '') + 'X2tConverter/src/main.cpp'
            if not (restored / needed).is_file():
                raise ValueError(f'Missing expected converter input: {needed}')
            shutil.move(str(restored), dest)
        (target / (name + '.commit')).write_text(lock['sources'][name]['commit'] + '\n')
    print('PASS: both pinned snapshots restored from local verified archives; zero network calls.')

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='action', required=True)
    create_cmd = sub.add_parser('create')
    for name in ('cryptpad', 'eurooffice'):
        create_cmd.add_argument('--' + name, required=True)
        create_cmd.add_argument('--' + name + '-commit', required=True)
    create_cmd.add_argument('--repository', required=True)
    create_cmd.add_argument('--release-tag', required=True)
    create_cmd.add_argument('--output-dir', required=True)
    create_cmd.add_argument('--lock-output', required=True)
    restore_cmd = sub.add_parser('restore')
    restore_cmd.add_argument('--lock', required=True)
    restore_cmd.add_argument('--archives-dir', required=True)
    restore_cmd.add_argument('--work-root', required=True)
    args = ap.parse_args()
    if args.action == 'create': create(args)
    else: restore(args)

if __name__ == '__main__':
    main()
