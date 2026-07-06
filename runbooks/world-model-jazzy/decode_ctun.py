#!/usr/bin/env python3
# 读 ArduPilot CTUN 高度控制回路:DAlt期望高/Alt当前高/DCRt期望爬升率/CRt实际爬升率/ThO油门out
# 直击核心:控制器有没有设爬升目标?看到的高度是什么?为什么收油?
import sys
from pymavlink import mavutil
m = mavutil.mavlink_connection(sys.argv[1])
rows = []
fields = None
while True:
    msg = m.recv_match(type=["CTUN"], blocking=False)
    if msg is None:
        break
    d = msg.to_dict()
    if fields is None:
        fields = [k for k in d if k != "mavpackettype"]
    rows.append(d)
print("CTUN 字段:", fields)
print("总记录:", len(rows))
if not rows:
    sys.exit()

def gv(r, k):
    v = r.get(k)
    return round(v, 3) if isinstance(v, (int, float)) else v

print("t(s) | DAlt期望高 | Alt当前高 | DCRt期望爬升 | CRt实际爬升 | ThO油门out | ThH悬停油门")
step = max(1, len(rows) // 30)
for r in rows[::step]:
    t = r.get("TimeUS", 0)
    t = round(t / 1e6, 1) if isinstance(t, (int, float)) else t
    line = "  {}s  DAlt={}  Alt={}  DCRt={}  CRt={}  ThO={}  ThH={}".format(
        t, gv(r, "DAlt"), gv(r, "Alt"), gv(r, "DCRt"), gv(r, "CRt"), gv(r, "ThO"), gv(r, "ThH"))
    print(line)
# 最大 ThO
tho = [r.get("ThO", 0) for r in rows if isinstance(r.get("ThO"), (int, float))]
print(">>> ThO 油门输出范围:", round(min(tho), 3), "~", round(max(tho), 3), "(0~1, 悬停约0.5)")
dalt = [r.get("DAlt", 0) for r in rows if isinstance(r.get("DAlt"), (int, float))]
print(">>> DAlt 期望高度范围:", round(min(dalt), 3), "~", round(max(dalt), 3), "m")
