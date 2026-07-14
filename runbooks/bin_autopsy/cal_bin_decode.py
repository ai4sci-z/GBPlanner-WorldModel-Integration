#!/usr/bin/env python3
# 校准 run BIN 验尸:GUIDED 目标(GUIP/GUID)与 EKF 位置(POS/XKF1)时间线
# 用法: python3 cal_bin_decode.py <BIN路径>
import sys

from pymavlink import mavutil

m = mavutil.mavlink_connection(sys.argv[1])
t0 = None
last = {}
n = {"GUIP": 0, "POS": 0}
print("== GUIP(guided position target)/GUID 序列(变化采样)+ POS 每2s ==")
while True:
    msg = m.recv_match(type=["GUIP", "GUID", "POS", "CMD"], blocking=False)
    if msg is None:
        break
    t = getattr(msg, "TimeUS", 0) / 1e6
    if t0 is None:
        t0 = t
    tr = t - t0
    k = msg.get_type()
    if k in ("GUIP", "GUID"):
        n["GUIP"] += 1
        cur = (getattr(msg, "Type", -1), round(getattr(msg, "pX", getattr(msg, "PX", 0.0)), 2),
               round(getattr(msg, "pY", getattr(msg, "PY", 0.0)), 2),
               round(getattr(msg, "vX", getattr(msg, "VX", 0.0)), 3),
               round(getattr(msg, "vY", getattr(msg, "VY", 0.0)), 3))
        if last.get(k) != cur:
            last[k] = cur
            print("t=%.1f %s type=%s pX=%.2f pY=%.2f vX=%.3f vY=%.3f" % (
                tr, k, cur[0], cur[1], cur[2], cur[3], cur[4]))
    elif k == "POS":
        n["POS"] += 1
        if tr - last.get("pos_t", -9) >= 2.0:
            last["pos_t"] = tr
            print("t=%.1f POS lat/lng rel: RelHomeAlt=%.2f" % (tr, getattr(msg, "RelHomeAlt", 0.0)))
print("counts:", n)
