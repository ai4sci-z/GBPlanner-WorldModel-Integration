#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIM_DIR="$ROOT_DIR/orchestration/sim"
SCOPE="staged"
GO_PATH_PATTERN='^orchestration/sim/.*\.go$'

usage() {
  cat <<'EOF'
Usage: ./scripts/quality/format-go.sh [--scope staged|modified|all]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --scope)
      [ "$#" -ge 2 ] || {
        usage >&2
        exit 1
      }
      SCOPE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[format-go] unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log_step() {
  printf '\n[format-go] %s\n' "$1"
}

fail() {
  printf '[format-go] %s\n' "$1" >&2
  exit 1
}

devbox_has_golangci_lint() {
  command -v devbox >/dev/null 2>&1 &&
    devbox run -- bash -lc "command -v golangci-lint >/dev/null 2>&1" >/dev/null 2>&1
}

list_files() {
  case "$SCOPE" in
    staged)
      git -C "$ROOT_DIR" diff --cached --name-only --diff-filter=ACMR
      ;;
    modified)
      {
        git -C "$ROOT_DIR" diff --cached --name-only --diff-filter=ACMR
        git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMR
        git -C "$ROOT_DIR" ls-files --others --exclude-standard
      } | awk '!seen[$0]++'
      ;;
    all)
      (
        cd "$ROOT_DIR"
        rg --files orchestration/sim -g '*.go'
      )
      ;;
    *)
      fail "unknown scope: $SCOPE"
      ;;
  esac | grep -E "$GO_PATH_PATTERN" || true
}

run_lint_packages() {
  if devbox_has_golangci_lint; then
    log_step "Linting affected Go packages via devbox"
    devbox run -- bash -lc "cd '$SIM_DIR' && GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/golangci-lint-cache golangci-lint run --config='$ROOT_DIR/.golangci.yml' $*"
    return
  fi

  if command -v golangci-lint >/dev/null 2>&1; then
    log_step "Linting affected Go packages with golangci-lint"
    (
      cd "$SIM_DIR"
      GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/golangci-lint-cache \
        golangci-lint run --config="$ROOT_DIR/.golangci.yml" "$@"
    )
    return
  fi

  if [ "${GO_ALLOW_BOOTSTRAP:-0}" = "1" ]; then
    log_step "Linting affected Go packages via go run bootstrap"
    (
      cd "$SIM_DIR"
      GOCACHE=/tmp/gocache GOLANGCI_LINT_CACHE=/tmp/golangci-lint-cache \
        go run github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.11.0 \
        run --config="$ROOT_DIR/.golangci.yml" "$@"
    )
    return
  fi

  fail "golangci-lint is required; install it locally or set GO_ALLOW_BOOTSTRAP=1"
}

is_lintable_package() {
  local pkg="$1"
  local stderr

  if (
    cd "$SIM_DIR"
    GOCACHE=/tmp/gocache go list "$pkg" >/dev/null 2>&1
  ); then
    return 0
  fi

  stderr="$(
    cd "$SIM_DIR" &&
      GOCACHE=/tmp/gocache go list "$pkg" 2>&1 >/dev/null
  )"

  if grep -q "build constraints exclude all Go files" <<<"$stderr"; then
    printf '[format-go] Skipping %s: no default-tag Go files to lint.\n' "$pkg"
    return 1
  fi

  printf '%s\n' "$stderr" >&2
  return 2
}

mapfile -t GO_FILES < <(list_files)

if [ "${#GO_FILES[@]}" -eq 0 ]; then
  log_step "No Go files to format"
  exit 0
fi

log_step "Files to format (total: ${#GO_FILES[@]})"
for file in "${GO_FILES[@]}"; do
  printf '  - %s\n' "$file"
done

log_step "Formatting Go files with gofmt"
gofmt -w "${GO_FILES[@]}"

declare -A SEEN_DIRS=()
declare -A SEEN_PACKAGES=()
PACKAGES=()

for file in "${GO_FILES[@]}"; do
  rel_path="${file#orchestration/sim/}"
  pkg_dir="$(dirname "$rel_path")"
  if [ -n "${SEEN_DIRS[$pkg_dir]:-}" ]; then
    continue
  fi
  SEEN_DIRS["$pkg_dir"]=1

  pkg="."
  if [ "$pkg_dir" != "." ]; then
    pkg="./$pkg_dir"
  fi

  if is_lintable_package "$pkg"; then
    if [ -z "${SEEN_PACKAGES[$pkg]:-}" ]; then
      SEEN_PACKAGES["$pkg"]=1
      PACKAGES+=("$pkg")
    fi
  else
    status=$?
    if [ "$status" -ne 1 ]; then
      exit "$status"
    fi
  fi
done

if [ "${#PACKAGES[@]}" -eq 0 ]; then
  log_step "No Go packages matched the selected files"
  exit 0
fi

run_lint_packages "${PACKAGES[@]}"

log_step "Go formatting completed successfully"
