import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_snapshot as snap
import audit_external_inputs as audit

class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cp = self.root/'cryptpad'; self.eo = self.root/'eurooffice'
        for base, rel in ((self.cp, 'core/X2tConverter/src/main.cpp'), (self.eo, 'X2tConverter/src/main.cpp')):
            p = base/rel; p.parent.mkdir(parents=True); p.write_text('int main() { return 0; }\n')
        (self.cp/'Dockerfile').write_text('FROM ubuntu:22.04\n')
        self.cpcommit = self.root/'cryptpad.commit'; self.cpcommit.write_text(snap.PINS['cryptpad']+'\n')
        self.eocommit = self.root/'eurooffice.commit'; self.eocommit.write_text('5a33ce6123456789012345678901234567890123\n')
        self.lock = self.root/'lock.json'; self.output = self.root/'archives'

    def make(self):
        return snap.create(type('Args', (), dict(cryptpad=str(self.cp), eurooffice=str(self.eo),
          cryptpad_commit=str(self.cpcommit), eurooffice_commit=str(self.eocommit),
          repository='test-org/test-repo', release_tag='source-v9-test',
          output_dir=str(self.output), lock_output=str(self.lock)))())

    def do_restore(self):
        return snap.restore(type('Args', (), dict(lock=str(self.lock), archives_dir=str(self.output),
             work_root=str(self.root/'restored')))())

    def test_round_trip_without_network(self):
        self.make(); self.do_restore()
        self.assertEqual((self.root/'restored/cryptpad/core/X2tConverter/src/main.cpp').read_text(),
                         (self.cp/'core/X2tConverter/src/main.cpp').read_text())
        self.assertEqual((self.root/'restored/eurooffice.commit').read_text().strip(), self.eocommit.read_text().strip())

    def test_hash_verification_rejects_tamper(self):
        self.make()
        with (self.output/'cryptpad-source.tar.gz').open('ab') as f: f.write(b'junk')
        with self.assertRaises(ValueError): self.do_restore()
        self.assertFalse((self.root/'restored/cryptpad').exists())

    def test_commit_pin_enforced(self):
        self.cpcommit.write_text('a'*40)
        with self.assertRaisesRegex(ValueError,'differs'): self.make()

    def test_repository_metadata_rejected(self):
        self.make()
        lock=json.loads(self.lock.read_text());lock['repository']='https://evil.test/evil'
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError,'Invalid source lockfile'):self.do_restore()

    def test_traversal_rejected_after_matching_hash(self):
        self.make()
        p=self.output/'cryptpad-source.tar.gz'
        with tarfile.open(p,'w:gz') as archive:
            data=b'bad'; member=tarfile.TarInfo('cryptpad/../../escape.txt');member.size=len(data)
            archive.addfile(member, io.BytesIO(data))
        lock=json.loads(self.lock.read_text());lock['sources']['cryptpad']['sha256']=snap.checksum(p)
        lock['sources']['cryptpad']['size']=p.stat().st_size;self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError,'Unexpected archive path'):self.do_restore()
        self.assertFalse((self.root/'escape.txt').exists())

    def test_symlink_outside_source_refused(self):
        (self.cp/'bad').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'Symlink escapes'):self.make()

    def test_no_git_metadata_in_snapshot(self):
        (self.cp/'.git').mkdir(); (self.cp/'.git/config').write_text('secret')
        self.make()
        with tarfile.open(self.output/'cryptpad-source.tar.gz','r:gz') as f:
            self.assertFalse(any('.git/' in n for n in f.getnames()))

    def test_offline_shell_end_to_end_without_gh_or_network(self):
        self.make()
        project=self.root/'offline-project'
        (project/'scripts').mkdir(parents=True)
        (project/'config').mkdir()
        (project/'.work/source-archives').mkdir(parents=True)
        shutil.copy2(ROOT/'scripts/fetch_archived_sources.sh', project/'scripts/fetch_archived_sources.sh')
        shutil.copy2(ROOT/'scripts/source_snapshot.py', project/'scripts/source_snapshot.py')
        shutil.copy2(self.lock, project/'config/sources.lock.json')
        for asset in snap.ARCHIVES.values():
            shutil.copy2(self.output/asset, project/'.work/source-archives'/asset)
        env=dict(__import__('os').environ, SOURCE_OFFLINE='true')
        run=subprocess.run(['bash','scripts/fetch_archived_sources.sh'],cwd=project,env=env,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertTrue((project/'.work/cryptpad/core/X2tConverter/src/main.cpp').exists())

    def test_snapshot_bytes_are_stable(self):
        self.make()
        first = {n: snap.checksum(self.output/asset) for n,asset in snap.ARCHIVES.items()}
        self.make()
        second = {n: snap.checksum(self.output/asset) for n,asset in snap.ARCHIVES.items()}
        self.assertEqual(first,second)

    def test_unmirrored_external_deps_reported(self):
        report = audit.audit('RUN git clone https://github.com/boostorg/boost\nRUN apt-get update')
        self.assertEqual(report['status'],'NOT_HERMETIC')
        self.assertIn('github.com',report['hosts'])
        self.assertEqual(len(report['network_reference_lines']),2)

    def test_no_live_cryptpad_fetch_in_build_script(self):
        script=(ROOT/'scripts/fetch_archived_sources.sh').read_text()
        self.assertNotIn('github.com/cryptpad',script)
        workflow=(ROOT/'.github/workflows/build-eurooffice-x2t.yml').read_text()
        self.assertIn('scripts/fetch_archived_sources.sh',workflow)
        self.assertNotIn('run: bash scripts/fetch_sources.sh',workflow)

if __name__ == '__main__': unittest.main()
