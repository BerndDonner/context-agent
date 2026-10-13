#!/usr/bin/env bash
set -euo pipefail
job_dir="${1:-/mnt/data/work/job}"
[[ -d "$job_dir/include" && -d "$job_dir/result" ]] || {
  echo 'Missing job/include or job/result' >&2; exit 2;
}
# The include tree is captured after compiling so main.tex and the corresponding
# module versions can be downloaded and validated together.
tar -czf "$job_dir/result/include-snapshot.tar.gz" -C "$job_dir" include
