#!/usr/bin/env bash
export PATH=/usr/local/go/bin:/usr/bin:/bin
RUNDIR=/home/ai4s/ws-clean/world-model/artifacts/sim/exploration/20260708T101402.733430807Z
echo "=== TOPICS in frame_contract_probe.py ==="
grep -h '^TOPICS' "$RUNDIR/probes/frame_contract_probe.py" | head -1
echo "=== probe results ==="
for p in frame_contract imu rangefinder exploration; do
  F=$(find "$RUNDIR" -name "${p}_probe.json" | head -1)
  [ -z "$F" ] && { echo "$p: NO_RESULT_FILE"; continue; }
  python3 -c "import json;d=json.load(open('$F'));print('$p: ok=',d.get('ok'),' blockers=',d.get('blockers'))"
done
echo "=== summary ==="
python3 -c "
import json
d=json.load(open('$RUNDIR/summary.json'))
print('task_status=', d.get('task_status') or d.get('status'))
print('blockers=', [b.get('code') for b in (d.get('blockers') or [])])
"
echo "=== rosbag recorder final state ==="
python3 -c "import json;d=json.load(open('$RUNDIR/runtime/rosbag_exploration_rosbag_fsm.json'));print(' state=',d.get('state'),' ok=',d.get('ok'),' blocked=',d.get('blocked'))"
echo "=== exploration accepted goals (from exploration probe) ==="
python3 -c "
import json
d=json.load(open('$RUNDIR/probes/exploration_probe.json'))
for k in ('accepted_goals','accepted','goals_accepted','path_length'):
    if k in d: print(' ',k,'=',d[k])
" 2>/dev/null
echo "=== DONE ==="
