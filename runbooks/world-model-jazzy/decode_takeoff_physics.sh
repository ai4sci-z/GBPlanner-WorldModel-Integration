#!/usr/bin/env bash
# 解 tlog:takeoff 期间 mode/armed/throttle/alt/climb 时间线,判定是"油门没给"还是"给了推不起来"。
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
TLOG="$BASE/$RUN/sitl/mav.tlog"
echo "=== run: $RUN ==="
python3 - "$TLOG" << 'PYEOF'
import sys
from pymavlink import mavutil
m=mavutil.mavlink_connection(sys.argv[1])
t0=None; mode=None; armed=None
rows=[]
while True:
    msg=m.recv_match(type=["HEARTBEAT","VFR_HUD","LOCAL_POSITION_NED","EKF_STATUS_REPORT"], blocking=False)
    if msg is None: break
    ts=getattr(msg,"_timestamp",None)
    if t0 is None and ts: t0=ts
    rel=(ts-t0) if (ts and t0) else 0.0
    tp=msg.get_type()
    if tp=="HEARTBEAT" and msg.type!=6:  # skip GCS heartbeat (type6)
        a=bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        cm=msg.custom_mode
        if (a,cm)!=(armed,mode):
            rows.append((rel,"MODE","armed=%s custom_mode=%d"%(a,cm))); armed,mode=a,cm
    elif tp=="VFR_HUD":
        rows.append((rel,"HUD","thr=%3d%% alt=%.2f climb=%.2f"%(msg.throttle,msg.alt,msg.climb)))
    elif tp=="EKF_STATUS_REPORT":
        rows.append((rel,"EKF","flags=0x%x velvar=%.2f posvar=%.2f hgtvar=%.2f"%(msg.flags,msg.velocity_variance,msg.pos_horiz_variance,msg.pos_vert_variance)))
# 打印:MODE/EKF 全部 + HUD 每 ~2s 采样
lasthud=-9
for rel,k,v in rows:
    if k in ("MODE","EKF"): print("%6.1fs %s %s"%(rel,k,v))
    elif rel-lasthud>=2.0: print("%6.1fs HUD %s"%(rel,v)); lasthud=rel
PYEOF
