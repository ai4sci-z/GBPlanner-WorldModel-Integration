#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
docker run --rm --network none \
  -v "$DIRB":/exp:ro -v "$RUNDIR":/run:ro \
  navlab/official-baseline:jazzy-latest \
  bash -lc "python3 /exp/cal_bin_decode2.py /run/sitl/logs/00000001.BIN 2>/dev/null"
echo "=== setpoint output 计数真值 ==="
python3 - "$RUNDIR/probes/exploration_probe.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
s = json.dumps(d)
import re
for k in ("mavlink_local_position_count", "mavlink_setpoint_count", "mavlink_setpoint_error", "cmd_vel_publish_count", "setpoint_intent_samples"):
    for m in set(re.findall('"%s"\\s*:\\s*("[^"]*"|[0-9.]+|null)' % k, s)):
        print(k, "=", m)
PY
