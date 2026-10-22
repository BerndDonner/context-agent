#!/usr/bin/env bash
# Reproducible local LMTX compile, no global TeX installation needed.
# Usage: scripts/local-lmtx.sh /path/context-lmtx-ready.tar.xz /path/job/result/main.tex
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo 'usage: local-lmtx.sh ARCHIVE SOURCE.tex' >&2
  exit 2
fi
archive="$(realpath "$1")"
source_file="$(realpath "$2")"
[[ -f "$archive" && -f "$source_file" ]] || { echo 'archive or source missing' >&2; exit 2; }
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/install" "$work/cache"
tar -xJf "$archive" -C "$work/install" --strip-components=1
(
  cd "$(dirname "$source_file")"
  TEXMFCACHE="$work/cache" bash "$work/install/context-local.sh" "$(basename "$source_file")"
)
