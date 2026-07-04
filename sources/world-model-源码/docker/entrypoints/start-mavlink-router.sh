#!/usr/bin/env bash
set -euo pipefail

ROUTER_DOWNSTREAM_ENDPOINTS="${ROUTER_DOWNSTREAM_ENDPOINTS:?ROUTER_DOWNSTREAM_ENDPOINTS is required}"

SESSION_ID="${SESSION_ID:-manual}"
ROUTER_LISTEN="${ROUTER_LISTEN:-0.0.0.0:14550}"
ROUTER_TCP_PORT="${ROUTER_TCP_PORT:-0}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts/sessions}"
LOG_FILE="${ARTIFACT_ROOT}/${SESSION_ID}/router.log"

mkdir -p "$(dirname "$LOG_FILE")"

if ! command -v mavlink-routerd >/dev/null 2>&1; then
  echo "mavlink-routerd not found in container" | tee -a "$LOG_FILE" >&2
  exit 2
fi

resolve_endpoint() {
  local endpoint="$1"
  local host="${endpoint%:*}"
  local port="${endpoint##*:}"
  local resolved_host=""

  if [[ -z "$host" || -z "$port" || "$host" == "$port" ]]; then
    echo "Invalid endpoint format: ${endpoint}" | tee -a "$LOG_FILE" >&2
    return 1
  fi

  if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf '%s\n' "${host}:${port}"
    return 0
  fi

  resolved_host="$(getent ahostsv4 "$host" | awk 'NR == 1 { print $1 }')"
  if [[ -z "$resolved_host" ]]; then
    echo "Failed to resolve endpoint host: ${host}" | tee -a "$LOG_FILE" >&2
    return 1
  fi

  printf '%s\n' "${resolved_host}:${port}"
}

cmd=(mavlink-routerd -t "$ROUTER_TCP_PORT")

IFS=',' read -r -a endpoints <<< "$ROUTER_DOWNSTREAM_ENDPOINTS"
endpoint_count=0
for endpoint in "${endpoints[@]}"; do
  endpoint="$(echo "$endpoint" | xargs)"
  if [[ -n "$endpoint" ]]; then
    endpoint="$(resolve_endpoint "$endpoint")"
    cmd+=(-e "$endpoint")
    endpoint_count=$((endpoint_count + 1))
  fi
done

if [[ "$endpoint_count" -eq 0 ]]; then
  echo "ROUTER_DOWNSTREAM_ENDPOINTS is empty; provide at least one HOST:PORT endpoint" | tee -a "$LOG_FILE" >&2
  exit 2
fi

cmd+=("$ROUTER_LISTEN")

echo "Starting mavlink-router session=${SESSION_ID} listen=${ROUTER_LISTEN} tcp_port=${ROUTER_TCP_PORT} downstream_endpoints=${ROUTER_DOWNSTREAM_ENDPOINTS}" | tee -a "$LOG_FILE"
echo "Command: ${cmd[*]}" | tee -a "$LOG_FILE"

"${cmd[@]}" > >(tee -a "$LOG_FILE") 2>&1 &
child=$!

trap 'kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true' TERM INT
wait "$child"
