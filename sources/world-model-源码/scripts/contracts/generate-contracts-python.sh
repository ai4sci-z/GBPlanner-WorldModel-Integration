#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTO_DIR="$ROOT_DIR/contracts/proto"
OUT_DIR="$ROOT_DIR/contracts/gen/python/navlab_contracts"

log_step() {
  printf '\n[contracts-python] %s\n' "$1"
}

fail() {
  printf '[contracts-python] %s\n' "$1" >&2
  exit 1
}

command -v protoc >/dev/null 2>&1 || fail "protoc is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

mapfile -t PROTO_FILES < <(find "$PROTO_DIR" -name '*.proto' | sort)
if [ "${#PROTO_FILES[@]}" -eq 0 ]; then
  fail "no proto files found under $PROTO_DIR"
fi

log_step "Generating Python protobuf contracts"
find "$OUT_DIR/navlab" -name '*_pb2.py' -delete 2>/dev/null || true
protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  "${PROTO_FILES[@]}"

find "$OUT_DIR/navlab" -type d -exec sh -c 'touch "$1/__init__.py"' sh {} \;

python3 - "$OUT_DIR" <<'PY'
from __future__ import annotations

import pathlib
import re
import sys

out_dir = pathlib.Path(sys.argv[1])
pattern = re.compile(r"from navlab((?:\.[A-Za-z0-9_]+)+) import ([A-Za-z0-9_]+_pb2)")

for path in out_dir.rglob("*_pb2.py"):
    text = path.read_text(encoding="utf-8")
    text = pattern.sub(r"from navlab_contracts.navlab\1 import \2", text)
    path.write_text(text, encoding="utf-8")
PY

log_step "Python protobuf contracts generated"
