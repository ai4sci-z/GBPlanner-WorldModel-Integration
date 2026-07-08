#!/usr/bin/env bash
# stage6 fix6 live validation, take 2.
# Root cause of prior "cold-start" failures: --artifact-root /tmp/stage6_live is OUTSIDE
# the workspace root; docker runtime maps artifact paths by workspace-prefix replacement
# (mount ws->/workspace), so probes redirect to /workspace/tmp/... which doesn't exist
# in-container -> all probes rc=1 output_missing -> runner tears stack down at +6s.
# Fix: use the DEFAULT artifact root (inside workspace), like all previously green runs.
export PATH=/usr/local/go/bin:/usr/bin:/bin
export NAVLAB_SIM_DISTRO=jazzy
export GOFLAGS=-mod=mod
cd /home/ai4s/ws-clean/world-model/orchestration/sim || exit 99

LOG=/tmp/stage6_live2.log
echo "=== LIVE RUN START $(date) HEAD=$(git -C /home/ai4s/ws-clean/world-model rev-parse --short HEAD) ==="
timeout 480 go run ./cmd/navlab-sim run exploration --live-preflight > "$LOG" 2>&1
RC=$?
echo "RUN_RC=$RC"
echo "--- tail 12 of run log ---"
tail -12 "$LOG"

RUNDIR=$(ls -dt artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "=== RUNDIR=$RUNDIR ==="

echo "=== frame_contract_probe.py sampled TOPICS (expect local_position_pose) ==="
grep -h '^TOPICS' "$RUNDIR"/probes/frame_contract_probe.py 2>/dev/null | head -1

echo "=== probe result jsons ==="
for p in frame_contract imu rangefinder exploration; do
  F=$(find "$RUNDIR" -name "${p}_probe.json" -o -name "${p}.json" 2>/dev/null | head -1)
  [ -z "$F" ] && { echo "$p: NO_RESULT_FILE"; continue; }
  python3 -c "import json;d=json.load(open('$F'));print('$p: ok=',d.get('ok'),' rc=',d.get('return_code'),' missing=',d.get('missing_topics'))" 2>/dev/null || echo "$p: unparsable $F"
done

echo "=== summary.json task_status / blockers ==="
SUM="$RUNDIR/summary.json"
python3 -c "import json;d=json.load(open('$SUM'));print(' task_status=',d.get('task_status') or d.get('status'));print(' blockers=',[b.get('code') for b in (d.get('blockers') or [])])" 2>/dev/null | head -5
echo "=== DONE ==="
