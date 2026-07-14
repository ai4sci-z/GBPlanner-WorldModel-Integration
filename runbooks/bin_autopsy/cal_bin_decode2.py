#!/usr/bin/env python3
# BIN 全程 GUIP 1Hz 采样 + 与 EKF 位置(XKF1)对照:看位置目标是否"跑飞"
import sys

from pymavlink import mavutil

m = mavutil.mavlink_connection(sys.argv[1])
t0 = None
last_g = last_p = -9.0
print("t | GUIP target (pX,pY) | XKF1 pos (PN,PE) | target-pos 距离")
gp = None
xk = None
import math
while True:
    msg = m.recv_match(type=["GUIP", "XKF1"], blocking=False)
    if msg is None:
        break
    t = getattr(msg, "TimeUS", 0) / 1e6
    if t0 is None:
        t0 = t
    tr = t - t0
    k = msg.get_type()
    if k == "GUIP":
        gp = (getattr(msg, "pX", 0.0), getattr(msg, "pY", 0.0))
        if tr - last_g >= 1.0:
            last_g = tr
            d = ""
            if xk:
                d = " gap=%.2f" % math.hypot(gp[0] - xk[0], gp[1] - xk[1])
            print("t=%.1f GUIP=(%.2f,%.2f) XKF1=(%s)%s" % (
                tr, gp[0], gp[1], "%.2f,%.2f" % xk if xk else "-", d))
    else:
        if getattr(msg, "C", 0) == 0:
            xk = (getattr(msg, "PN", 0.0), getattr(msg, "PE", 0.0))
