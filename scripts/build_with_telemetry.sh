#!/usr/bin/env bash
# One auditable BuildKit invocation with constrained parallelism and disk telemetry.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p artifacts/provenance artifacts/converter
builder="eurooffice-x2t-${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}"
probe_file="artifacts/provenance/disk-samples.log"
status_file="artifacts/provenance/docker-build-status.txt"
: > "$probe_file"
echo "Starting docker build with builder: $builder" | tee "$status_file"

# Snapshot resources every 60 seconds. Stop it even when Docker fails.
probe_pid=''
cleanup() {
  status=$?
  trap - EXIT INT TERM
  if [[ -n "$probe_pid" ]]; then
    kill "$probe_pid" 2>/dev/null || true
    wait "$probe_pid" 2>/dev/null || true
  fi
  {
    echo "Exit code: $status"
    echo "Final disk state:"
    df -h / "${GITHUB_WORKSPACE:-.}" 2>/dev/null || true
    docker system df 2>/dev/null || true
  } >> "$status_file"
  # A failed build might fill the disk; releasing its dedicated BuildKit
  # container and volume may allow diagnostics to upload.
  docker buildx rm --force "$builder" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

(
  while :; do
    printf '\n[%s]\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    df -h / "${GITHUB_WORKSPACE:-.}" 2>&1 || true
    docker system df 2>&1 || true
    sleep 60
  done
) >> "$probe_file" 2>&1 &
probe_pid=$!

# Use a dedicated docker-container driver to load buildkitd.toml. The previous
# implicit Docker driver ignored BuildKit's max-parallelism setting.
docker buildx create \
  --name "$builder" --driver docker-container \
  --buildkitd-config "$ROOT/config/buildkitd.toml" --use
docker buildx inspect "$builder" --bootstrap
python3 scripts/check_build_resources.py \
  --minimum-gib "${MINIMUM_FREE_GIB:-8}" \
  --report artifacts/provenance/storage-after-buildkit.json

set +e
(
  cd .work/cryptpad
  docker buildx build --builder "$builder" \
    --file Dockerfile --target output \
    --output "type=local,dest=$ROOT/artifacts/converter" \
    --progress=plain .
) 2>&1 | tee artifacts/provenance/docker-build.log
result=${PIPESTATUS[0]}
set -e
printf '\nDocker result: %s\n' "$result" >> "$status_file"
exit "$result"
