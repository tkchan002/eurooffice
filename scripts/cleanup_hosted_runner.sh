#!/usr/bin/env bash
# Limited cleanup, strictly for ephemeral standard GitHub-hosted Ubuntu runners.
# Never run on self-hosted or unknown machines: this removes preinstalled SDKs.
set -euo pipefail

if [[ "${RUNNER_ENVIRONMENT:-}" != "github-hosted" || "${RUNNER_OS:-}" != "Linux" ]]; then
  echo "INFO: Not a recognized ephemeral GitHub-hosted Linux runner; no host cleanup."
  exit 0
fi

# Never assume a custom/self-hosted runner is disposable even when Linux.
if [[ "${BUILD_RUNNER_LABEL:-}" != "ubuntu-24.04" ]]; then
  echo "INFO: Not targeting a standard ubuntu-24.04 runner; no host cleanup."
  exit 0
fi

if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true 2>/dev/null; then
  echo "INFO: Passwordless sudo unavailable; no host cleanup."
  exit 0
fi

printf 'Disk before cleanup:\n'
df -h / || true
for p in /usr/local/lib/android /usr/share/dotnet /opt/ghc /usr/local/.ghcup /usr/local/share/powershell /opt/hostedtoolcache/CodeQL; do
  if [[ -e "$p" ]]; then
    printf 'Removing unused preinstalled SDK %s (size: ' "$p"
    sudo du -sh "$p" 2>/dev/null | awk '{print $1}' || true
    sudo rm -rf -- "$p"
  fi
done
printf 'Disk after cleanup:\n'
df -h / || true
