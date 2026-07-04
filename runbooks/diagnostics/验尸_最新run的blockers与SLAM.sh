#!/bin/bash
set -u
D=$(ls -dt /home/ai4s/ws/world-model/artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "run: $D"

echo "== 1. gazebo_sensor 日志(这次必须有!) =="
tail -15 "${D}runtime/logs/gazebo_sensor.runtime.log" 2>/dev/null || echo "(仍无日志)"

echo
echo "== 2. SLAM 质量 + scan 等待情况 =="
python3 - "${D}summary.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
s = d['metrics']['gate']['slam_runtime_log']
print('slam quality:', s.get('quality'), '| error:', s.get('error_count'))
lp = s.get('last_problem_lines') or ['(none)']
print('last_problem:', lp[-1][:140])
bc = d.get('blockerCodes', [])
print()
print('== 3. blockers:', len(bc), '个 ==')
for c in bc:
    print('  ', c[:120])
PYEOF
