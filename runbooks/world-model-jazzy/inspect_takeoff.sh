#!/usr/bin/env bash
# takeoff attempts 明细 + statustext 里 EKF/PreArm 线索 + bootstrap 时间线。
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
t=dig(s,"metrics/gate/controller/bootstrap/takeoff")
print("takeoff.ok =",t.get("ok"))
atts=t.get("attempts") or []
print("attempts 数 =",len(atts))
def g(x,k,d=None):
    return x.get(k,d) if isinstance(x,dict) else x
for i,a in enumerate(atts):
    ack=g(a,"ack") or {}
    h=g(a,"height") or {}
    gd=g(a,"guided")
    print(f"  [{i}] ack.result={g(ack,'result')} accepted={g(ack,'accepted')} height.ok={g(h,'ok')} latest={str(g(h,'latest'))[:90]} guided={gd if not isinstance(gd,dict) else gd.get('ok')}")
# 全 summary 里搜 EKF / PreArm / VisOdom / origin 文本
raw=json.dumps(s)
import re
for pat in ["PreArm[^\"]*","EKF[^\"]*","VisOdom[^\"]*","origin[^\"]{0,60}"]:
    hits=sorted(set(re.findall(pat,raw)))[:8]
    if hits: print(pat.split('[')[0],"::",hits)
PYEOF
echo "=== SITL/EKF 线索 ==="
ls "$D/sitl" 2>/dev/null | head -8
grep -rhoE "EKF3[^\"]{0,80}|external nav[^\"]{0,50}|PreArm[^\"]{0,60}|AHRS[^\"]{0,40}|set_origin[^\"]{0,40}|SIM_|fence" "$D/sitl" "$D/runtime/logs" 2>/dev/null | sort | uniq -c | sort -rn | head -22
echo "=== fcu 日志 bootstrap 事件时间线 ==="
for f in "$D"/runtime/logs/*.log; do
  bn=$(basename "$f")
  case "$bn" in *fcu*|*controller*|*companion*)
    grep -oE '"event": "[^"]*"|fcu_bootstrap[^,}]*|takeoff[^,}]{0,60}' "$f" 2>/dev/null | sort | uniq -c | sort -rn | head -12
  ;; esac
done
