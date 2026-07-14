#!/usr/bin/env python3
# BIN 参数取证:EK3 源/罗盘/VISO 配置 + EKF 状态健康消息
import sys

from pymavlink import mavutil

m = mavutil.mavlink_connection(sys.argv[1])
want = ("EK3_SRC", "COMPASS_USE", "COMPASS_ENABLE", "VISO_", "EK3_GSF", "AHRS_EKF", "ARMING_CHECK")
seen = {}
errs = []
while True:
    msg = m.recv_match(type=["PARM", "MSG", "ERR", "XKF4", "XKV1"], blocking=False)
    if msg is None:
        break
    k = msg.get_type()
    if k == "PARM":
        name = msg.Name
        if any(name.startswith(w) or w in name for w in want):
            seen[name] = msg.Value
    elif k in ("MSG",):
        t = getattr(msg, "Message", "")
        if any(x in t for x in ("EKF", "yaw", "Yaw", "GSF", "vision", "Vision", "ExternalNav")):
            errs.append("MSG t=%.1f %s" % (getattr(msg, "TimeUS", 0) / 1e6, t))
for k in sorted(seen):
    print("%s = %s" % (k, seen[k]))
print("--- EKF/yaw 相关 MSG ---")
for e in errs[:25]:
    print(e)
