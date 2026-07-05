#!/usr/bin/env bash
# 提取最新 run 的 FCU bootstrap 全貌(mode/arm/takeoff 各步结果)+ controller 日志尾部。
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
D="$BASE/$RUN"
echo "=== run: $RUN ==="
python3 - "$D/summary.json" << 'PYEOF'
import json,sys
s=json.load(open(sys.argv[1]))
def dig(o,path):
    for k in path.split("/"):
        if not k: continue
        o=o.get(k) if isinstance(o,dict) else None
        if o is None: return None
    return o
b=dig(s,"metrics/gate/controller/bootstrap")
if b is None:
    print("no bootstrap metrics"); sys.exit()
def brief(o,depth=0,key=""):
    pad="  "*depth
    if isinstance(o,dict):
        print(f"{pad}{key}:")
        for k,v in o.items():
            if k=="statustext": print(f"{pad}  statustext: [{len(v)} msgs]"); continue
            brief(v,depth+1,k)
    elif isinstance(o,list):
        print(f"{pad}{key}: [{len(o)} items]")
        for i,v in enumerate(o[:4]): brief(v,depth+1,f"{key}[{i}]")
    else:
        print(f"{pad}{key} = {str(o)[:120]}")
brief(b,0,"bootstrap")
PYEOF
echo "=== fcu/controller 相关日志尾 ==="
for f in "$D"/runtime/logs/*controller*.log "$D"/runtime/logs/*fcu*.log "$D"/runtime/logs/*companion*.log; do
  [ -f "$f" ] || continue
  echo "───── $(basename "$f")"
  tail -12 "$f" | cut -c1-170
done
