#!/usr/bin/env bash
set -euo pipefail

SESSION_ID="${SESSION_ID:-manual}"
SITL_UPSTREAM_ENDPOINT="${SITL_UPSTREAM_ENDPOINT:-mavlink-router:14550}"
SITL_ROUTER_ONLY="${SITL_ROUTER_ONLY:-false}"
SITL_MODEL="${SITL_MODEL:-JSON}"
SITL_SPEEDUP="${SITL_SPEEDUP:-1}"
SITL_INSTANCE="${SITL_INSTANCE:-0}"
SITL_HOME="${SITL_HOME:-}"
SITL_EXTRA_ARGS="${SITL_EXTRA_ARGS:-}"
ARDUPILOT_BIN="${ARDUPILOT_BIN:-/usr/local/bin/arducopter}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts/sessions}"
LOG_FILE="${ARTIFACT_ROOT}/${SESSION_ID}/sitl.log"
RUN_DIR="${ARTIFACT_ROOT}/${SESSION_ID}/sitl_work"

SITL_UPSTREAM_HOST="${SITL_UPSTREAM_ENDPOINT%:*}"
SITL_UPSTREAM_PORT="${SITL_UPSTREAM_ENDPOINT##*:}"

if [[ -z "$SITL_UPSTREAM_HOST" || -z "$SITL_UPSTREAM_PORT" || "$SITL_UPSTREAM_HOST" == "$SITL_UPSTREAM_PORT" ]]; then
  echo "Invalid SITL_UPSTREAM_ENDPOINT: ${SITL_UPSTREAM_ENDPOINT}" | tee -a "$LOG_FILE" >&2
  exit 2
fi

mkdir -p "$(dirname "$LOG_FILE")" "$RUN_DIR"

if [[ ! -x "$ARDUPILOT_BIN" ]]; then
  echo "arducopter SITL binary missing or not executable: ${ARDUPILOT_BIN}" | tee -a "$LOG_FILE" >&2
  exit 2
fi

unset TMUX STY ZELLIJ DISPLAY

cmd=(
  "$ARDUPILOT_BIN"
  "--model"
  "$SITL_MODEL"
  "--speedup"
  "$SITL_SPEEDUP"
  "--instance"
  "$SITL_INSTANCE"
)

if [[ -n "$SITL_HOME" ]]; then
  cmd+=("--home" "$SITL_HOME")
fi

case "${SITL_ROUTER_ONLY,,}" in
  1|true|yes|y)
    ;;
  *)
    cmd+=("--serial0" "udpclient:${SITL_UPSTREAM_HOST}:${SITL_UPSTREAM_PORT}")
    ;;
esac

if [[ -n "$SITL_EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  extra_args=($SITL_EXTRA_ARGS)
  cmd+=("${extra_args[@]}")
fi

echo "Starting ArduPilot SITL session=${SESSION_ID} model=${SITL_MODEL} upstream=${SITL_UPSTREAM_HOST}:${SITL_UPSTREAM_PORT} router_only=${SITL_ROUTER_ONLY}" | tee -a "$LOG_FILE"
echo "Command: ${cmd[*]}" | tee -a "$LOG_FILE"

cd "$RUN_DIR"
"${cmd[@]}" > >(tee -a "$LOG_FILE") 2>&1 &
child=$!

trap 'kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true' TERM INT
wait "$child"
