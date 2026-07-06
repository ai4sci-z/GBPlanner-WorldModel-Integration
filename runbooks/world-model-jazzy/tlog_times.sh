#!/usr/bin/env bash
# 用 official-baseline 容器里的 pymavlink 解 tlog,打印 EKF/AHRS/takeoff 相关 STATUSTEXT 的时间戳(相对首条)。
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
TLOG="$BASE/$RUN/sitl/mav.tlog"
echo "=== run: $RUN tlog: $TLOG ==="
docker run --rm -v "$BASE/$RUN/sitl:/d:ro" --entrypoint python3 navlab/official-baseline:jazzy-latest - << 'PYEOF'
from pymavlink import mavutil
m=mavutil.mavlink_connection("/d/mav.tlog")
t0=None
rows=[]
while True:
    msg=m.recv_match(type=["STATUSTEXT","LOCAL_POSITION_NED"], blocking=False)
    if msg is None: break
    ts=getattr(msg,"_timestamp",None)
    if t0 is None and ts: t0=ts
    rel=(ts-t0) if (ts and t0) else 0.0
    if msg.get_type()=="STATUSTEXT":
        t=msg.text
        if any(k in t for k in ["EKF","AHRS","GUIDED","Takeoff","VisOdom","arm","Arm"]):
            rows.append((rel,"TXT",t))
    else:  # LOCAL_POSITION_NED
        rows.append((rel,"POS","z=%.3f" % msg.z))
# 只打印 STATUSTEXT 全部 + 每 ~2s 一个 POS 采样
last_pos=-99
for rel,k,v in rows:
    if k=="TXT": print("%6.1fs  %s" % (rel,v))
    elif rel-last_pos>=2.0:
        print("%6.1fs  [z] %s" % (rel,v)); last_pos=rel
PYEOF
