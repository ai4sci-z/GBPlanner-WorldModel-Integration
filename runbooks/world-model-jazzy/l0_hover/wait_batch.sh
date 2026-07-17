#!/usr/bin/env bash
# WP303 monitor 薄封装:历史入口名保留,实体在 batch_lifecycle.py(Python,身份/JSON/原子写更稳)。
# 用法: wait_batch.sh monitor --artifact-root <DIR>
#       wait_batch.sh launch  --artifact-root <DIR> --batch-id <ID> --expected-runs N ... -- <producer...>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/batch_lifecycle.py" "$@"
