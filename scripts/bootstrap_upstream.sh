#!/usr/bin/env bash
# Run only once to establish an independent baseline from documented upstream commits.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -e .work/cryptpad || -e .work/eurooffice ]]; then
  echo 'Refusing to overwrite existing .work source directories' >&2
  exit 2
fi
bash scripts/fetch_sources.sh
# Ensure a complete checkout, not a sparse or empty submodule placeholder.
for root in .work/cryptpad .work/eurooffice; do
  [[ -f "$root/X2tConverter/src/main.cpp" || -f "$root/core/X2tConverter/src/main.cpp" ]] || exit 3
  if [[ -f "$root/.gitmodules" ]]; then
    git -C "$root" submodule status --recursive | tee ".work/$(basename "$root").submodules"
    if grep -Eq '^[+-]' ".work/$(basename "$root").submodules"; then
      echo "Uninitialized or mismatched submodule in $root; stop for a reviewed source snapshot" >&2
      exit 4
    fi
  fi
done
