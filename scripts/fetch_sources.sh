#!/usr/bin/env bash
set -euo pipefail
mkdir -p .work
cd .work

fetch_pinned() {
  local name="$1" url="$2" ref="$3" expected_prefix="$4"
  if [ -d "$name/.git" ]; then
    echo "Existing checkout: $name"
  else
    mkdir "$name"
    git -C "$name" init -q
    git -C "$name" remote add origin "$url"
  fi
  git -C "$name" fetch --quiet --depth 1 origin "$ref"
  git -C "$name" checkout -q --detach FETCH_HEAD
  local got
  got="$(git -C "$name" rev-parse HEAD)"
  case "$got" in
    "$expected_prefix"*) echo "$name: $got" ;;
    *) echo "PIN MISMATCH for $name: expected $expected_prefix, got $got" >&2; exit 1 ;;
  esac
  printf '%s\n' "$got" > "$name.commit"
}

fetch_pinned cryptpad https://github.com/cryptpad/onlyoffice-x2t-wasm.git 95f775fd3c42fae9e9af66ca072d3da3763e6c76 95f775fd3c42fae9e9af66ca072d3da3763e6c76
fetch_pinned onlyoffice-base https://github.com/ONLYOFFICE/core.git refs/tags/v9.3.0.140 269dd9b
fetch_pinned eurooffice https://github.com/Euro-Office/core.git refs/tags/v9.3.5 5a33ce6

for dir in cryptpad/core onlyoffice-base eurooffice; do
  test -f "$dir/X2tConverter/src/main.cpp" || { echo "Missing x2t source: $dir" >&2; exit 1; }
done
