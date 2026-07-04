#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="${PYTHON_CHECK_PROFILE:-${PYTHON_SERVICE_CHECK_PROFILE:-local}}"
CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.cache/uv}"
RUN_SYNC=0
CHECK_TARGETS=("navlab" "scripts")
TEST_PROJECTS=("navlab" "command")

log_step() {
  printf '\n[python] %s\n' "$1"
}

fail() {
  printf '[python] %s\n' "$1" >&2
  exit 1
}

run_uv() {
  local project_dir="$1"
  shift

  (
    cd "$ROOT_DIR"
    uv run --project "$project_dir" --no-sync "$@"
  )
}

run_navlab_uv() {
  (
    cd "$ROOT_DIR"
    uv run --project "$ROOT_DIR/navlab" --no-sync --all-groups "$@"
  )
}

sync_project() {
  local project_dir="$1"
  shift

  uv sync --project "$project_dir" "$@"
}

has_target_prefix() {
  local prefix="$1"
  local target

  for target in "${CHECK_TARGETS[@]}"; do
    if [[ "$target" == "$prefix"* ]]; then
      return 0
    fi
  done

  return 1
}

add_test_project() {
  local project="$1"
  local existing

  for existing in "${TEST_PROJECTS[@]}"; do
    if [ "$existing" = "$project" ]; then
      return
    fi
  done

  TEST_PROJECTS+=("$project")
}

load_staged_targets() {
  mapfile -t CHECK_TARGETS < <(
    git -C "$ROOT_DIR" diff --cached --name-only --diff-filter=ACMR -- '*.py'
  )

  TEST_PROJECTS=()

  if has_target_prefix "navlab/"; then
    add_test_project "navlab"
  fi
  if has_target_prefix "scripts/command/"; then
    add_test_project "command"
  fi
}

case "$PROFILE" in
  pre-commit|local)
    if [ "$PROFILE" = "pre-commit" ]; then
      load_staged_targets
    fi
    ;;
  ci|full)
    RUN_SYNC=1
    ;;
  *)
    fail "unknown PYTHON_CHECK_PROFILE: $PROFILE"
    ;;
esac

mkdir -p "$CACHE_DIR"
export UV_CACHE_DIR="$CACHE_DIR"

if [ "$RUN_SYNC" -eq 1 ]; then
  log_step "Syncing navlab dependencies with uv"
  sync_project "$ROOT_DIR/navlab" --locked --all-groups

  log_step "Syncing command dependencies with uv"
  sync_project "$ROOT_DIR/scripts/command" --locked --group dev
fi

if [ "${#CHECK_TARGETS[@]}" -gt 0 ]; then
  log_step "Running Ruff check"
  run_navlab_uv ruff check --config "$ROOT_DIR/pyproject.toml" --force-exclude "${CHECK_TARGETS[@]}"

  log_step "Running Ruff format check"
  run_navlab_uv ruff format --check --config "$ROOT_DIR/pyproject.toml" --force-exclude "${CHECK_TARGETS[@]}"
else
  log_step "No Python targets to lint"
fi

for project in "${TEST_PROJECTS[@]}"; do
  case "$project" in
    navlab)
      log_step "Running navlab pytest"
      run_navlab_uv pytest navlab/tests -q
      ;;
    command)
      if find "$ROOT_DIR/scripts/command/tests" -name 'test_*.py' -print -quit 2>/dev/null | grep -q .; then
        log_step "Running command pytest"
        run_uv "$ROOT_DIR/scripts/command" pytest scripts/command/tests -q
      else
        log_step "No command pytest files found"
      fi
      ;;
    *)
      fail "unknown test project: $project"
      ;;
  esac
done

log_step "Python checks passed"
