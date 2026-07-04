#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTO_DIR="$ROOT_DIR/contracts/proto"
OUT_DIR="$ROOT_DIR/contracts/gen/go"
PROTOC_GEN_GO_VERSION="v1.36.11"

log_step() {
  printf '\n[contracts-go] %s\n' "$1"
}

fail() {
  printf '[contracts-go] %s\n' "$1" >&2
  exit 1
}

command -v protoc >/dev/null 2>&1 || fail "protoc is required"
command -v protoc-gen-go >/dev/null 2>&1 || fail "protoc-gen-go is required"
if [ "$(protoc-gen-go --version)" != "protoc-gen-go $PROTOC_GEN_GO_VERSION" ]; then
  fail "protoc-gen-go $PROTOC_GEN_GO_VERSION is required; found $(protoc-gen-go --version)"
fi

mapfile -t PROTO_FILES < <(find "$PROTO_DIR" -name '*.proto' | sort)
if [ "${#PROTO_FILES[@]}" -eq 0 ]; then
  fail "no proto files found under $PROTO_DIR"
fi

log_step "Generating Go protobuf contracts"
find "$OUT_DIR/navlab" -name '*.pb.go' -delete 2>/dev/null || true
protoc \
  -I "$PROTO_DIR" \
  --go_out="$OUT_DIR" \
  --go_opt=paths=source_relative \
  "${PROTO_FILES[@]}"

log_step "Tidying generated Go module"
(
  cd "$OUT_DIR"
  go mod tidy
)

log_step "Go protobuf contracts generated"
