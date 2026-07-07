#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
P=$(find "$RUNDIR" -name "exploration_probe.py" | head -1)
echo "=== sample_string_topics 全文 ==="
sed -n '/def sample_string_topics/,/^def [a-z_]*(/p' "$P" | head -70
echo "=== 探针实际日志时间戳(v2run7 run,对照 latch) ==="
J=$(find "$RUNDIR/probes" -name "exploration_probe.json" | head -1)
python3 -c "
import json
d=json.load(open('$J'))
for t,s in (d.get('samples') or {}).items():
    print(t, 'ok=', s.get('ok'), 'rc=', s.get('return_code'), 'latency=', s.get('latency_sec'))
"
