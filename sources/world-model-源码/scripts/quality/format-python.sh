#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.cache/uv}"
SCOPE="staged"
PYTHON_PATH_PATTERN='^(navlab|scripts/command|scripts/ops)(/.*)?\.py$'

usage() {
  cat <<'EOF'
Usage: ./scripts/quality/format-python.sh [--scope staged|modified|all]
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
      echo "[format-python] unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log_step() {
  printf '\n[format-python] %s\n' "$1"
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
        rg --files navlab scripts -g '*.py'
      )
      ;;
    *)
      echo "[format-python] unknown scope: $SCOPE" >&2
      exit 1
      ;;
  esac | grep -E "$PYTHON_PATH_PATTERN" || true
}

run_ruff() {
  (
    cd "$ROOT_DIR"
    mkdir -p "$CACHE_DIR"
    export UV_CACHE_DIR="$CACHE_DIR"
    uv run --project "$ROOT_DIR/navlab" --no-sync --all-groups ruff "$@"
  )
}

mapfile -t PYTHON_FILES < <(list_files)

if [ "${#PYTHON_FILES[@]}" -eq 0 ]; then
  log_step "No Python files to format"
  exit 0
fi

log_step "Files to format (total: ${#PYTHON_FILES[@]})"
for file in "${PYTHON_FILES[@]}"; do
  printf '  - %s\n' "$file"
done

log_step "Fixing Python files with Ruff"
run_ruff check --fix --unsafe-fixes --config "$ROOT_DIR/pyproject.toml" --force-exclude "${PYTHON_FILES[@]}"

log_step "Formatting Python files with Ruff"
run_ruff format --config "$ROOT_DIR/pyproject.toml" --force-exclude "${PYTHON_FILES[@]}"

log_step "Python formatting completed successfully"
