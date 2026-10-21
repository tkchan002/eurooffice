"""Source-level invariant checks for the storage-aware GitHub workflow."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StorageWorkflowTests(unittest.TestCase):
    def test_buildkit_concurrency_bounded(self):
        toml = (ROOT / 'config/buildkitd.toml').read_text()
        self.assertIn('[worker.oci]', toml)
        self.assertIn('max-parallelism = 1', toml)

    def test_workflow_uses_real_configured_builder(self):
        shell = (ROOT / 'scripts/build_with_telemetry.sh').read_text()
        self.assertIn('--driver docker-container', shell)
        self.assertIn('--buildkitd-config', shell)
        self.assertIn('--builder "$builder"', shell)
        self.assertIn('disk-samples.log', shell)
        self.assertIn('docker-build.log', shell)

    def test_preflight_before_heavy_compile(self):
        workflow = (ROOT / '.github/workflows/build-eurooffice-x2t.yml').read_text()
        self.assertLess(workflow.index('name: Check Docker filesystem capacity'),
                        workflow.index('name: Compile with storage telemetry'))
        self.assertIn('runs-on: ${{ inputs.runner_label }}', workflow)
        self.assertIn('minimum_free_gib:', workflow)
        self.assertIn("default: '8'", workflow)

    def test_source_move_replaces_duplicate_rsync(self):
        workflow = (ROOT / '.github/workflows/build-eurooffice-x2t.yml').read_text()
        self.assertIn('mv .work/eurooffice .work/cryptpad/core', workflow)
        self.assertNotIn('rsync -a', workflow)
        self.assertIn('rm -rf .work/cryptpad/core/.git .work/cryptpad/.git', workflow)
        self.assertIn('optimize_docker_layers.py', workflow)

    def test_cleanup_fails_closed_on_non_github_host(self):
        script = ROOT / 'scripts/cleanup_hosted_runner.sh'
        result = subprocess.run(['bash', str(script)], capture_output=True,
                                text=True, env={'PATH':'/usr/bin:/bin'})
        self.assertEqual(result.returncode, 0)
        self.assertIn('no host cleanup', result.stdout)

    def test_shell_syntax(self):
        for p in ('scripts/fetch_sources.sh', 'scripts/cleanup_hosted_runner.sh',
                  'scripts/build_with_telemetry.sh'):
            result = subprocess.run(['bash', '-n', str(ROOT / p)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, (p, result.stderr))


if __name__ == '__main__':
    unittest.main()
