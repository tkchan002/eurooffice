#!/usr/bin/env bash
# Strictly from owner-controlled GitHub Release or pre-cached local files.
# Never contacts cryptpad/onlyoffice-x2t-wasm, Euro-Office/core, or any source repo.
set -euo pipefail
cd "$(dirname "$0")/.."
lock="${SOURCE_LOCK:-config/sources.lock.json}"
cache="${SOURCE_ARCHIVE_CACHE:-.work/source-archives}"
mkdir -p "$cache" .work
if [[ ! -s "$lock" ]]; then
  echo "No pinned source lockfile. Run 'Archive Pinned Source Inputs' first." >&2
  exit 2
fi
# Validate lock *before* running any external command.
python3 - "$lock" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from source_snapshot import verify_lock
verify_lock(json.loads(Path(sys.argv[1]).read_text()))
PY
readarray -t release < <(python3 - "$lock" <<'PY'
import json,sys
j=json.load(open(sys.argv[1]));print(j['repository']);print(j['release_tag'])
PY
)
if [[ ! -s "$cache/cryptpad-source.tar.gz" || ! -s "$cache/eurooffice-source.tar.gz" ]]; then
  if [[ "${SOURCE_OFFLINE:-false}" == true ]]; then
    echo "SOURCE_OFFLINE=true: required cached snapshot archives are missing" >&2
    exit 3
  fi
  command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required for snapshot download' >&2; exit 3; }
  # A public Release controlled by the user, rather than the original upstreams.
  gh release download "${release[1]}" \
    --repo "${release[0]}" \
    --pattern 'cryptpad-source.tar.gz' --pattern 'eurooffice-source.tar.gz' \
    --dir "$cache" --clobber
fi
python3 scripts/source_snapshot.py restore --lock "$lock" --archives-dir "$cache" --work-root .work
