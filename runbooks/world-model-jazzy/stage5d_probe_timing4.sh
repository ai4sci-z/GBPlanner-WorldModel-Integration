#!/usr/bin/env bash
CLEAN=/home/ai4s/ws-clean/world-model
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
P=$(find "$RUNDIR" -name "exploration_probe.py" | head -1)
echo "=== 预算常数 ==="
grep -n "STRING_READY_TIMEOUT_SEC\s*=\|TOPIC_SAMPLE_TIMEOUT_SEC\s*=\|PROBE_TIMEOUT_SEC\s*=" "$P"
echo "=== string_holder_ok / string_payload_ok(landing 例外?) ==="
sed -n '/def string_holder_ok/,/^def sample_message/p' "$P" | head -30
echo "=== run 事件时间线(probe.running / service 时刻) ==="
find "$RUNDIR" -name "*.jsonl" -o -name "*event*" | head -5
EV=$(find "$RUNDIR" -name "*.jsonl" | head -1)
[ -n "$EV" ] && grep -oE '"ts[^,]*|"phase":"[^"]*"|"component":"[^"]*"|"name":"[^"]*"' "$EV" | paste - - - - 2>/dev/null | grep -iE "probe|workflow|service" | head -20
echo "=== summary 里 probe 事件时间(若有) ==="
python3 -c "
import json
d=json.load(open('$RUNDIR/summary.json'))
evs=d.get('events') or d.get('runtime_execution',{}).get('events') or []
for e in evs:
    if 'probe' in str(e.get('phase','')) or 'probe' in str(e.get('component','')):
        print(e.get('timestamp',e.get('ts','?')), e.get('phase'), e.get('component'), e.get('message',''))
" 2>/dev/null | head -15
