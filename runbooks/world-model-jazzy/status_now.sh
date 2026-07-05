#!/usr/bin/env bash
# 老实汇报:最新 run 的真实 status + blockers 全量 + takeoff/height 真值。不粉饰。
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
D="$BASE/$RUN"
python3 - "$D/summary.json" << 'PYEOF'
import json,sys
s=json.load(open(sys.argv[1]))
print("run status =", s.get("status"))
bl=s.get("blockers") or []
print("blockers 总数 =", len(bl))
for b in bl:
    print("  -", b.get("code"), "|", b.get("source"))
def dig(o,path):
    for k in path.split("/"):
        if not k: continue
        o=o.get(k) if isinstance(o,dict) else None
        if o is None: return None
    return o
t=dig(s,"metrics/gate/controller/bootstrap/takeoff")
if t:
    print("takeoff.ok =", t.get("ok"))
    for i,a in enumerate(t.get("attempts") or []):
        ack=a.get("ack") or {} if isinstance(a,dict) else {}
        h=a.get("height") or {} if isinstance(a,dict) else {}
        lat=h.get("latest") or {}
        z=lat.get("z") or lat.get("relative_alt") or lat.get("alt")
        print(f"  takeoff[{i}] ack.result={ack.get('result')} accepted={ack.get('accepted')} height.ok={h.get('ok')} z/alt={z}")
PYEOF
