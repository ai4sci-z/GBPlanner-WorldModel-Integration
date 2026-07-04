#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/ops/kill-serial-holders.sh [--dry-run] [--no-kill] [--force] [--timeout SEC] [DEVICE]

Kill processes that currently hold a serial device.

Arguments:
  DEVICE          Serial device to release. Default: /dev/ttyUSB1

Options:
  --dry-run       Print holders but do not send signals.
  --no-kill       Same as --dry-run.
  --force         Send SIGKILL immediately instead of SIGTERM first.
  --timeout SEC   Seconds to wait after SIGTERM before SIGKILL. Default: 1
  -h, --help      Show this help.

Examples:
  scripts/ops/kill-serial-holders.sh
  scripts/ops/kill-serial-holders.sh /dev/ttyUSB0
  scripts/ops/kill-serial-holders.sh --dry-run /dev/ttyACM0
EOF
}

device="/dev/ttyUSB1"
dry_run=0
force=0
timeout_sec=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--no-kill)
      dry_run=1
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    --timeout)
      if [[ $# -lt 2 ]]; then
        echo "error: --timeout requires a value" >&2
        exit 2
      fi
      timeout_sec="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      device="$1"
      shift
      if [[ $# -gt 0 ]]; then
        echo "error: only one DEVICE argument is supported" >&2
        exit 2
      fi
      ;;
  esac
done

if [[ ! "$timeout_sec" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "error: --timeout must be a non-negative number" >&2
  exit 2
fi

if [[ ! -e "$device" ]]; then
  echo "$device not found" >&2
  exit 2
fi

if ! command -v fuser >/dev/null 2>&1; then
  echo "error: fuser is required but was not found" >&2
  exit 2
fi

echo "Serial device: $device"

if command -v lsof >/dev/null 2>&1; then
  echo
  echo "Open handles before:"
  lsof "$device" 2>/dev/null || true
fi

mapfile -t pids < <(fuser "$device" 2>/dev/null | tr ' ' '\n' | awk 'NF' | sort -u)

if [[ ${#pids[@]} -eq 0 ]]; then
  echo "No process is using $device"
  exit 0
fi

echo
echo "Processes using $device:"
for pid in "${pids[@]}"; do
  ps -p "$pid" -o pid,ppid,user,comm,args --no-headers || true
done

if [[ "$dry_run" -eq 1 ]]; then
  echo
  echo "Dry run: no signals sent."
  exit 0
fi

if [[ "$force" -eq 1 ]]; then
  echo
  echo "Sending SIGKILL to: ${pids[*]}"
  kill -KILL "${pids[@]}" 2>/dev/null || true
else
  echo
  echo "Sending SIGTERM to: ${pids[*]}"
  kill -TERM "${pids[@]}" 2>/dev/null || true
  sleep "$timeout_sec"

  mapfile -t remaining < <(fuser "$device" 2>/dev/null | tr ' ' '\n' | awk 'NF' | sort -u)
  if [[ ${#remaining[@]} -gt 0 ]]; then
    echo
    echo "Still holding $device; sending SIGKILL to: ${remaining[*]}"
    kill -KILL "${remaining[@]}" 2>/dev/null || true
  fi
fi

sleep 0.2

echo
echo "Open handles after:"
if command -v lsof >/dev/null 2>&1; then
  lsof "$device" 2>/dev/null || true
fi
if fuser "$device" >/tmp/navlab_serial_holders_after.$$ 2>/dev/null; then
  cat /tmp/navlab_serial_holders_after.$$
  rm -f /tmp/navlab_serial_holders_after.$$
  echo "warning: $device is still in use" >&2
  exit 1
fi
rm -f /tmp/navlab_serial_holders_after.$$
echo "$device released"
