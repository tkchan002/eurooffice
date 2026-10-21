#!/usr/bin/env python3
"""Fail early when the Docker filesystem lacks reasonable build headroom.

This is a *floor*, not a prediction of actual EuroOffice/BuildKit consumption.
On normal local Docker installations data-root is /var/lib/docker, but
respect `docker info` so self-hosted runners can dedicate larger disks.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

GIB = 1024 ** 3


def docker_data_root():
    proc = subprocess.run(
        ["docker", "info", "--format", "{{.DockerRootDir}}"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode:
        raise RuntimeError("Cannot connect to Docker daemon: " + proc.stderr.strip())
    p = proc.stdout.strip()
    if not p or not p.startswith("/"):
        raise RuntimeError("Unexpected Docker data-root path: " + repr(p))
    return Path(p)


def writable_mount(path):
    """Get volume usage at path, or an accessible ancestor on same mount.

    `df -P` can inspect directory metadata on a non-readable path; if even
    that fails, stop rather than incorrectly using the runner's root mount.
    """
    proc = subprocess.run(["df", "-PB1", str(path)], capture_output=True,
                          text=True, check=False)
    if proc.returncode:
        raise RuntimeError("Cannot inspect Docker data-root filesystem: " +
                           (proc.stderr.strip() or str(path)))
    lines = proc.stdout.splitlines()
    if len(lines) < 2:
        raise RuntimeError("Invalid `df` output for " + str(path))
    cols = lines[-1].split()
    if len(cols) < 6:
        raise RuntimeError("Invalid filesystem fields for " + str(path))
    return {
        "device": cols[0],
        "total_bytes": int(cols[1]),
        "used_bytes": int(cols[2]),
        "available_bytes": int(cols[3]),
        "mountpoint": cols[5],
    }


def inspect(available_bytes, required_gib):
    if required_gib < 1:
        raise ValueError("minimum free space must be positive")
    return {
        "minimum_free_gib": required_gib,
        "available_gib": round(available_bytes / GIB, 2),
        "ok": available_bytes >= required_gib * GIB,
        "warning": "Minimum threshold is a preflight floor, not a peak-disk estimate",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-gib", type=int, required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "minimum_free_gib": args.minimum_gib}
    try:
        root = docker_data_root()
        mount = writable_mount(root)
        report = {"docker_data_root": str(root), **mount,
                  **inspect(mount["available_bytes"], args.minimum_gib)}
    except (RuntimeError, OSError, ValueError) as e:
        report["error"] = str(e)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Docker storage: {report.get('available_gib', '?')} GiB free; "
          f"minimum {args.minimum_gib} GiB")
    if not report["ok"]:
        print("Insufficient disk headroom, or unable to confirm it. "
              "Consider a runner with more free SSD (custom runner_label), "
              "or explicitly lower the floor for an experimental attempt. "
              "See artifacts/provenance/storage-preflight.json.", file=sys.stderr)
        if report.get("error"):
            print("Reason: " + report["error"], file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
