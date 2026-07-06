#!/usr/bin/env python3
# 读 BIN: SIM.Alt(仿真地面真值高度)、RCOU C1-4(电机PWM)、CTUN DAlt/Alt/ThO。
# 判物理是否真离地(唯一起飞指标=SIM物理高度真涨 + 电机PWM>1500)。用法: decode_takeoff_bin.py <BIN>
import sys
from pymavlink import mavutil

m = mavutil.mavlink_connection(sys.argv[1])
sim_alt = []
rcou = []
ctun = []
while True:
    msg = m.recv_match(type=["SIM", "RCOU", "CTUN"], blocking=False)
    if msg is None:
        break
    d = msg.to_dict()
    t = d.get("TimeUS", 0)
    ts = t / 1e6 if isinstance(t, (int, float)) else t
    typ = d.get("mavpackettype")
    if typ == "SIM":
        a = d.get("Alt")
        if isinstance(a, (int, float)):
            sim_alt.append((ts, a))
    elif typ == "RCOU":
        rcou.append((ts, [d.get("C%d" % i) for i in range(1, 5)]))
    elif typ == "CTUN":
        ctun.append((ts, d.get("DAlt"), d.get("Alt"), d.get("ThO")))


def rng(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return (round(min(vals), 3), round(max(vals), 3)) if vals else (None, None)


print("=== SIM (仿真地面真值) records:", len(sim_alt))
if sim_alt:
    a0 = sim_alt[0][1]
    amax = max(a for _, a in sim_alt)
    amin = min(a for _, a in sim_alt)
    print("  SIM.Alt first=%.3f min=%.3f max=%.3f  上升(max-first)=%.3f m" % (a0, amin, amax, amax - a0))

print("=== RCOU (电机PWM) records:", len(rcou))
if rcou:
    allc = [c for _, chans in rcou for c in chans if isinstance(c, (int, float))]
    print("  四电机 PWM 全体范围:", rng(allc))
    peak = max((max((c for c in chans if isinstance(c, (int, float))), default=0)) for _, chans in rcou)
    print("  峰值单通道 PWM:", round(peak, 1))

print("=== CTUN (高度控制回路) records:", len(ctun))
if ctun:
    print("  DAlt(期望高) 范围:", rng([d for _, d, _, _ in ctun]))
    print("  Alt(当前高)  范围:", rng([a for _, _, a, _ in ctun]))
    print("  ThO(油门out) 范围:", rng([t for _, _, _, t in ctun]))
