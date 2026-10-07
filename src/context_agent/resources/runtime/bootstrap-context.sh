#!/usr/bin/env bash
set -euo pipefail

HEADER='CONTEXT_AGENT_ARCHIVE_V1'

find_bundle() {
  find /mnt/data -type f -name '*.ctxbundle' -print -quit
}

run_context() (
  source_file="$1"
  log_file="$2"

  bundle="${CONTEXT_AGENT_CONTEXT_BUNDLE:-$(find_bundle)}"
  if [[ -z "$bundle" || ! -f "$bundle" ]]; then
    echo "Opaque ConTeXt bundle (*.ctxbundle) not found under /mnt/data" >&2
    return 2
  fi
  if [[ ! -f "$source_file" ]]; then
    echo "ConTeXt source not found: $source_file" >&2
    return 2
  fi

  source_file="$(realpath "$source_file")"
  log_file="$(realpath -m "$log_file")"
  mkdir -p "$(dirname "$log_file")"

  temporary="$(mktemp -d /mnt/data/context-agent-lmtx.XXXXXX)"
  trap 'rm -rf "$temporary"' EXIT
  archive="$temporary/context-lmtx-ready.tar.xz"
  context_root="$temporary/context-lmtx"
  mkdir -p "$context_root"

  python - "$bundle" "$archive" "$HEADER" <<'PYCODE'
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
header = (sys.argv[3] + "\n").encode("ascii")
with source.open("rb") as input_stream:
    actual = input_stream.read(len(header))
    if actual != header:
        raise SystemExit("invalid context-agent ConTeXt bundle header")
    with destination.open("wb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
PYCODE

  tar -xJf "$archive" -C "$context_root" --strip-components=1

  (
    cd "$(dirname "$source_file")"
    "$context_root/context-local.sh" "$(basename "$source_file")" >"$log_file" 2>&1
  )
)

case "${1:-}" in
  --smoke)
    smoke_dir="$(mktemp -d /mnt/data/context-agent-smoke.XXXXXX)"
    trap 'rm -rf "$smoke_dir"' EXIT
    cat > "$smoke_dir/smoke.tex" <<'EOF'
\starttext
ConTeXt funktioniert.
\stoptext
EOF
    run_context "$smoke_dir/smoke.tex" "$smoke_dir/context.log"
    if [[ ! -s "$smoke_dir/smoke.pdf" ]]; then
      echo "ConTeXt smoke test failed" >&2
      tail -n 100 "$smoke_dir/context.log" >&2 || true
      exit 3
    fi
    echo "ConTeXt smoke test passed"
    ;;
  --compile)
    if [[ $# -ne 3 ]]; then
      echo "usage: $0 --compile SOURCE.tex LOGFILE" >&2
      exit 2
    fi
    run_context "$2" "$3"
    ;;
  *)
    echo "usage: $0 --smoke | --compile SOURCE.tex LOGFILE" >&2
    exit 2
    ;;
esac
