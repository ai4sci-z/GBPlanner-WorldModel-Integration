#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIM_DIR="$ROOT_DIR/orchestration/sim"
PROFILE="${GO_CHECK_PROFILE:-full}"

RUN_LINT=1
RUN_TESTS=1
RUN_BUILD=1
RUN_MOD_TIDY=1
RUN_INTEGRATION=0

log_step() {
  printf '\n[go] %s\n' "$1"
}

fail() {
  printf '[go] %s\n' "$1" >&2
  exit 1
}

devbox_has_golangci_lint() {
  command -v devbox >/dev/null 2>&1 &&
    devbox run -- bash -lc "command -v golangci-lint >/dev/null 2>&1" >/dev/null 2>&1
}

run_lint() {
  if devbox_has_golangci_lint; then
    log_step "Running golangci-lint via devbox"
    devbox run -- bash -lc "cd '$SIM_DIR' && GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/golangci-lint-cache golangci-lint run --config='$ROOT_DIR/.golangci.yml' ./..."
    return
  fi

  if command -v golangci-lint >/dev/null 2>&1; then
    log_step "Running golangci-lint via local toolchain"
    (
      cd "$SIM_DIR"
      GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/golangci-lint-cache \
        golangci-lint run --config="$ROOT_DIR/.golangci.yml" ./...
    )
    return
  fi

  if [ "${GO_ALLOW_BOOTSTRAP:-0}" = "1" ]; then
    log_step "Running golangci-lint via go run bootstrap"
    (
      cd "$SIM_DIR"
      GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/golangci-lint-cache \
        go run github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.11.0 \
        run --config="$ROOT_DIR/.golangci.yml" ./...
    )
    return
  fi

  fail "golangci-lint is required; install it locally or set GO_ALLOW_BOOTSTRAP=1"
}

usage() {
  cat <<'EOF'
Usage: ./scripts/quality/check-go.sh [--skip-lint] [--skip-tests] [--skip-build] [--skip-mod-tidy] [--integration]

Profiles:
  GO_CHECK_PROFILE=pre-commit  run tests only
  GO_CHECK_PROFILE=ci          run lint and tests
  GO_CHECK_PROFILE=full        run lint, tests, build, and go mod tidy verification
EOF
}

case "$PROFILE" in
  pre-commit)
    RUN_LINT=0
    RUN_BUILD=0
    RUN_MOD_TIDY=0
    ;;
  ci)
    RUN_BUILD=0
    RUN_MOD_TIDY=0
    ;;
  full)
    ;;
  *)
    fail "unknown GO_CHECK_PROFILE: $PROFILE"
    ;;
esac

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-lint)
      RUN_LINT=0
      ;;
    --skip-tests)
      RUN_TESTS=0
      ;;
    --skip-build)
      RUN_BUILD=0
      ;;
    --skip-mod-tidy)
      RUN_MOD_TIDY=0
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

cd "$SIM_DIR"

if [ "$RUN_LINT" -eq 1 ]; then
  run_lint
fi

if [ "$RUN_TESTS" -eq 1 ]; then
  log_step "Running Go unit tests"
  go test ./...
fi

if [ "$RUN_INTEGRATION" -eq 1 ]; then
  log_step "Running Go integration tests"
  go test -tags integration ./...
fi

if [ "$RUN_BUILD" -eq 1 ]; then
  log_step "Building Go packages"
  go build ./...
fi

if [ "$RUN_MOD_TIDY" -eq 1 ]; then
  log_step "Verifying go.mod and go.sum are tidy"
  go mod tidy
  git -C "$ROOT_DIR" diff --exit-code -- orchestration/sim/go.mod orchestration/sim/go.sum
fi

log_step "Go checks passed"
