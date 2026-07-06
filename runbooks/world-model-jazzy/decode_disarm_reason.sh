#!/usr/bin/env bash
# 解 tlog:按时间顺序打印 arm/disarm 事件 + 每个事件前后的 STATUSTEXT,锁定 disarm 触发原因。
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
TLOG="$BASE/$RUN/sitl/mav.tlog"
echo "=== run: $RUN ==="
python3 - "$TLOG" << 'PYEOF'
import sys
from pymavlink import mavutil
m=mavutil.mavlink_connection(sys.argv[1])
t0=None; armed=None
events=[]
while True:
    msg=m.recv_match(type=["HEARTBEAT","STATUSTEXT"], blocking=False)
    if msg is None: break
    ts=getattr(msg,"_timestamp",None)
    if t0 is None and ts: t0=ts
    rel=(ts-t0) if (ts and t0) else 0.0
    tp=msg.get_type()
    if tp=="HEARTBEAT" and msg.type==2:  # quad only
        a=bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        if a!=armed:
            events.append((rel,"ARM" if a else "DISARM", "armed=%s"%a)); armed=a
    elif tp=="STATUSTEXT":
        events.append((rel,"TXT", msg.text))
# 打印全时间线(合并),重点看 DISARM 前后
for rel,k,v in events:
    mark = ">>>" if k in ("ARM","DISARM") else "   "
    print("%s %6.2fs %-7s %s" % (mark,rel,k,v))
PYEOF