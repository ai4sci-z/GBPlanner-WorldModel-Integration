#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REAL_DIR="$ROOT_DIR/orchestration/real"
PROFILE="${RUST_CHECK_PROFILE:-full}"

RUN_FORMAT=1
RUN_TESTS=1
RUN_BUILD=1
RUN_CLIPPY=1
RUN_INTEGRATION=0
RUN_BENCHES=1

log_step() {
  printf '\n[rust] %s\n' "$1"
}

fail() {
  printf '[rust] %s\n' "$1" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./scripts/quality/check-rust.sh [--skip-format] [--skip-tests] [--skip-build] [--skip-clippy] [--skip-benches] [--integration]

Profiles:
  RUST_CHECK_PROFILE=pre-commit  run format check and tests
  RUST_CHECK_PROFILE=ci          run format check, clippy, and tests
  RUST_CHECK_PROFILE=full        run format check, clippy, tests, build, and compile benchmarks
EOF
}

case "$PROFILE" in
  pre-commit)
    RUN_BUILD=0
    RUN_CLIPPY=0
    RUN_BENCHES=0
    ;;
  ci)
    RUN_BUILD=0
    RUN_BENCHES=0
    ;;
  full)
    ;;
  *)
    fail "unknown RUST_CHECK_PROFILE: $PROFILE"
    ;;
esac

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-format)
      RUN_FORMAT=0
      ;;
    --skip-tests)
      RUN_TESTS=0
      ;;
    --skip-build)
      RUN_BUILD=0
      ;;
    --skip-clippy)
      RUN_CLIPPY=0
      ;;
    --skip-benches)
      RUN_BENCHES=0
      ;;
    --integration)
      RUN_INTEGRATION=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

cd "$REAL_DIR"

if [ "$RUN_FORMAT" -eq 1 ]; then
  log_step "Checking Rust formatting"
  cargo fmt -- --check
fi

if [ "$RUN_CLIPPY" -eq 1 ]; then
  log_step "Running Rust clippy"
  cargo clippy --all-targets -- -D warnings
fi

if [ "$RUN_TESTS" -eq 1 ]; then
  log_step "Running Rust tests"
  cargo test
fi

if [ "$RUN_INTEGRATION" -eq 1 ]; then
  log_step "Running Rust integration tests"
  cargo test --features integration
fi

if [ "$RUN_BENCHES" -eq 1 ]; then
  log_step "Verifying Rust benchmarks compile"
  cargo bench --no-run
fi

if [ "$RUN_BUILD" -eq 1 ]; then
  log_step "Building Rust packages"
  cargo build
fi

log_step "Rust checks passed"
