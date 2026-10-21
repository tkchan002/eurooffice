"""Disk policy regression checks; no Docker daemon or network required."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_build_resources.py"
spec = importlib.util.spec_from_file_location("check_build_resources", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DiskPolicyTests(unittest.TestCase):
    def test_meets_floor(self):
        self.assertTrue(module.inspect(61 * module.GIB, 60)["ok"])

    def test_below_floor(self):
        self.assertFalse(module.inspect(59 * module.GIB, 60)["ok"])

    def test_exact_floor_passes(self):
        self.assertTrue(module.inspect(60 * module.GIB, 60)["ok"])

    def test_invalid_floor_fails(self):
        with self.assertRaises(ValueError):
            module.inspect(100 * module.GIB, 0)

    def test_mount_parser(self):
        from subprocess import CompletedProcess
        fake = CompletedProcess(args=[], returncode=0,
            stdout="Filesystem 1B-blocks Used Available Use% Mounted on\n"
                   "/dev/sdb1 100000 40000 60000 40% /mnt/data\n")
        with patch.object(module.subprocess, "run", return_value=fake):
            got = module.writable_mount(Path("/mnt/data/docker"))
        self.assertEqual(got["available_bytes"], 60000)
        self.assertEqual(got["mountpoint"], "/mnt/data")

    def test_main_reports_low_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            sample = dict(device="/dev/sda", total_bytes=70 * module.GIB,
                          used_bytes=55 * module.GIB,
                          available_bytes=15 * module.GIB, mountpoint="/")
            with patch.object(module, "docker_data_root", return_value=Path("/var/lib/docker")), \
                 patch.object(module, "writable_mount", return_value=sample):
                status = module.main(["--minimum-gib", "60", "--report", str(report)])
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(report.read_text())["ok"])

    def test_main_reports_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            sample = dict(device="/dev/sda", total_bytes=100 * module.GIB,
                          used_bytes=30 * module.GIB,
                          available_bytes=70 * module.GIB, mountpoint="/")
            with patch.object(module, "docker_data_root", return_value=Path("/var/lib/docker")), \
                 patch.object(module, "writable_mount", return_value=sample):
                status = module.main(["--minimum-gib", "60", "--report", str(report)])
            self.assertEqual(status, 0)
            self.assertTrue(json.loads(report.read_text())["ok"])

    def test_unavailable_docker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            with patch.object(module, "docker_data_root", side_effect=RuntimeError("No daemon")):
                status = module.main(["--minimum-gib", "60", "--report", str(report)])
            self.assertEqual(status, 1)
            self.assertIn("No daemon", json.loads(report.read_text())["error"])


if __name__ == "__main__":
    unittest.main()
