#!/usr/bin/env bash
# 检查最新 exploration run 的 summary blockers + 服务健康。用法: inspect_run.sh [run_id]
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
D="$BASE/$RUN"
echo "=== run dir: $D ==="
ls "$D" | head -30
echo "=== summary 状态/blockers ==="
python3 - "$D/summary.json" << 'PYEOF'
import json,sys
s=json.load(open(sys.argv[1]))
def walk(o,p=""):
    if isinstance(o,dict):
        for k,v in o.items(): walk(v,p+"/"+k)
    elif isinstance(o,list):
        for i,v in enumerate(o): walk(v,p+"[%d]"%i)
    else:
        low=p.lower()
        if any(w in low for w in ["blocker","status","error","health"]) and o not in (None,"","ok","passed",True,0): print(p,"=",str(o)[:200])
walk(s)
PYEOF
echo "=== 服务日志(每个尾 4 行) ==="
LOGDIR=""
for c in "$D/runtime/logs" "$D/logs"; do [ -d "$c" ] && LOGDIR="$c" && break; done
if [ -z "$LOGDIR" ]; then LOGDIR=$(dirname "$(find "$D" -name '*.log' | head -1)"); fi
echo "logdir=$LOGDIR"
for f in "$LOGDIR"/*.log; do
  [ -f "$f" ] || continue
  echo "───── $(basename "$f") ($(wc -l < "$f") 行)"
  tail -4 "$f" | cut -c1-160
done
echo "=== 探针输出 ==="
for f in "$D"/probes/*; do
  [ -f "$f" ] || continue
  echo "───── $(basename "$f")"
  tail -6 "$f" | cut -c1-160
done
