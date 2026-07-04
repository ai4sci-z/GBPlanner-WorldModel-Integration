#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTO_DIR="$ROOT_DIR/contracts/proto"
EXAMPLES_DIR="$ROOT_DIR/contracts/examples"
GEN_GO_DIR="$ROOT_DIR/contracts/gen/go"
GEN_RUST_DIR="$ROOT_DIR/contracts/gen/rust"
GEN_PYTHON_DIR="$ROOT_DIR/contracts/gen/python"
PROTOC_GEN_GO_VERSION="v1.36.11"

log_step() {
  printf '\n[contracts] %s\n' "$1"
}

fail() {
  printf '[contracts] %s\n' "$1" >&2
  exit 1
}

command -v jq >/dev/null 2>&1 || fail "jq is required"
command -v protoc >/dev/null 2>&1 || fail "protoc is required"
command -v go >/dev/null 2>&1 || fail "go is required"
export PATH="$(go env GOPATH)/bin:$PATH"
if ! command -v protoc-gen-go >/dev/null 2>&1; then
  if [ "${CONTRACTS_ALLOW_BOOTSTRAP:-0}" = "1" ]; then
    log_step "Installing protoc-gen-go"
    go install "google.golang.org/protobuf/cmd/protoc-gen-go@$PROTOC_GEN_GO_VERSION"
  else
    fail "protoc-gen-go is required; install it or set CONTRACTS_ALLOW_BOOTSTRAP=1"
  fi
fi
if [ "$(protoc-gen-go --version)" != "protoc-gen-go $PROTOC_GEN_GO_VERSION" ]; then
  if [ "${CONTRACTS_ALLOW_BOOTSTRAP:-0}" = "1" ]; then
    log_step "Installing protoc-gen-go $PROTOC_GEN_GO_VERSION"
    go install "google.golang.org/protobuf/cmd/protoc-gen-go@$PROTOC_GEN_GO_VERSION"
  else
    fail "protoc-gen-go $PROTOC_GEN_GO_VERSION is required; found $(protoc-gen-go --version)"
  fi
fi
command -v cargo >/dev/null 2>&1 || fail "cargo is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

log_step "Validating golden JSON examples"
find "$EXAMPLES_DIR" -name '*.json' -print0 | sort -z | xargs -0 -n1 jq empty

require_field() {
  local file="$1"
  local field="$2"

  jq -e --arg field "$field" 'has($field)' "$file" >/dev/null ||
    fail "$file is missing required field $field"
}

log_step "Validating required schemaVersion fields"
require_field "$EXAMPLES_DIR/orchestration/sim_task_request.json" "schemaVersion"
require_field "$EXAMPLES_DIR/orchestration/sim_navigation_summary.json" "schemaVersion"
require_field "$EXAMPLES_DIR/orchestration/real_task_result.json" "schemaVersion"
require_field "$EXAMPLES_DIR/orchestration/doctor_result_blocked.json" "schemaVersion"
require_field "$EXAMPLES_DIR/runtime/sim_runtime_plan.json" "schemaVersion"
require_field "$EXAMPLES_DIR/runtime/real_process_event.json" "schemaVersion"

log_step "Validating proto syntax"
mapfile -t PROTO_FILES < <(find "$PROTO_DIR" -name '*.proto' | sort)
if [ "${#PROTO_FILES[@]}" -eq 0 ]; then
  fail "no proto files found under $PROTO_DIR"
fi
protoc -I "$PROTO_DIR" --include_imports --descriptor_set_out=/tmp/navlab_contracts.pb "${PROTO_FILES[@]}"

log_step "Validating generated Go protobuf contracts"
BEFORE_STATUS="$(mktemp)"
AFTER_STATUS="$(mktemp)"
BEFORE_DIFF="$(mktemp)"
AFTER_DIFF="$(mktemp)"
git status --short -- contracts/gen/go >"$BEFORE_STATUS"
git diff -- contracts/gen/go >"$BEFORE_DIFF"
"$ROOT_DIR/scripts/contracts/generate-contracts-go.sh"
(
  cd "$GEN_GO_DIR"
  go test ./...
)
git status --short -- contracts/gen/go >"$AFTER_STATUS"
git diff -- contracts/gen/go >"$AFTER_DIFF"
cmp -s "$BEFORE_STATUS" "$AFTER_STATUS" ||
  fail "generated Go contract file status changed; run scripts/contracts/generate-contracts-go.sh"
cmp -s "$BEFORE_DIFF" "$AFTER_DIFF" ||
  fail "generated Go contract contents changed; run scripts/contracts/generate-contracts-go.sh"

log_step "Validating generated Rust protobuf contracts"
(
  cd "$GEN_RUST_DIR"
  cargo test
)

log_step "Validating generated Python protobuf contracts"
BEFORE_PY_STATUS="$(mktemp)"
AFTER_PY_STATUS="$(mktemp)"
BEFORE_PY_DIFF="$(mktemp)"
AFTER_PY_DIFF="$(mktemp)"
git status --short -- contracts/gen/python >"$BEFORE_PY_STATUS"
git diff -- contracts/gen/python >"$BEFORE_PY_DIFF"
"$ROOT_DIR/scripts/contracts/generate-contracts-python.sh"
PYTHONWARNINGS="ignore::UserWarning" \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$GEN_PYTHON_DIR" \
  python3 -m unittest discover -s "$GEN_PYTHON_DIR/tests" -v
git status --short -- contracts/gen/python >"$AFTER_PY_STATUS"
git diff -- contracts/gen/python >"$AFTER_PY_DIFF"
cmp -s "$BEFORE_PY_STATUS" "$AFTER_PY_STATUS" ||
  fail "generated Python contract file status changed; run scripts/contracts/generate-contracts-python.sh"
cmp -s "$BEFORE_PY_DIFF" "$AFTER_PY_DIFF" ||
  fail "generated Python contract contents changed; run scripts/contracts/generate-contracts-python.sh"

log_step "Contracts checks passed"
