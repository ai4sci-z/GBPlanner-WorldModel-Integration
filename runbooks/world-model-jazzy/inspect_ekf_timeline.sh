#!/usr/bin/env bash
# 从最新 run 的 SITL tlog 抽 EKF3/AHRS/takeoff 的完整时间线(按序,不去重)。
set -o pipefail
BASE=/home/ai4s/ws/world-model/artifacts/sim/exploration
RUN="${1:-$(ls -t "$BASE" | head -1)}"
D="$BASE/$RUN"
echo "=== run: $RUN ==="
echo "--- sitl 目录 ---"; find "$D/sitl" -type f 2>/dev/null | sed "s#$D/##"
TLOG="$D/sitl/mav.tlog"
echo "--- statustext 时间线(pymavlink 解 tlog) ---"
python3 - "$TLOG" << 'PYEOF'
import sys
try:
    from pymavlink import mavutil
except Exception as e:
    print("no pymavlink:",e); sys.exit()
m=mavutil.mavlink_connection(sys.argv[1])
n=0
while True:
    msg=m.recv_match(type=["STATUSTEXT"], blocking=False)
    if msg is None: break
    t=getattr(msg,"text","")
    if any(k in t for k in ["EKF","AHRS","GUIDED","Takeoff","takeoff","PreArm","arm","Arm","failsafe","variance","GPS"]):
        print(t)
    n+=1
print("--- total statustext:",n)
PYEOF
echo "--- runtime 日志文件名 ---"; ls "$D/runtime/logs" | grep -iE "fcu|controller|external_nav|height"
echo "--- fcu_controller.runtime 尾 ---"
tail -15 "$D/runtime/logs/fcu_controller.runtime.log" 2>/dev/null | cut -c1-180
