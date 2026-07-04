#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REAL_DIR="$ROOT_DIR/orchestration/real"
SCOPE="staged"
RUST_PATH_PATTERN='^orchestration/real/.*\.rs$'

usage() {
  cat <<'EOF'
Usage: ./scripts/quality/format-rust.sh [--scope staged|modified|all]
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
      echo "[format-rust] unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log_step() {
  printf '\n[format-rust] %s\n' "$1"
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
        rg --files orchestration/real -g '*.rs'
      )
      ;;
    *)
      echo "[format-rust] unknown scope: $SCOPE" >&2
      exit 1
      ;;
  esac | grep -E "$RUST_PATH_PATTERN" || true
}

mapfile -t RUST_FILES < <(list_files)

if [ "${#RUST_FILES[@]}" -eq 0 ]; then
  log_step "No Rust files to format"
  exit 0
fi

log_step "Files to format (total: ${#RUST_FILES[@]})"
for file in "${RUST_FILES[@]}"; do
  printf '  - %s\n' "$file"
done

log_step "Formatting Rust crate with cargo fmt"
(
  cd "$REAL_DIR"
  cargo fmt
)

log_step "Rust formatting completed successfully"
