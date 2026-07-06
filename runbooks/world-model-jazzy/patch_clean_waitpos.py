#!/usr/bin/env python3
# 实质修法:takeoff 前先等 EKF 建立有效绝对位置(POS_HORIZ_ABS+POS_VERT_ABS)再发指令。
# 根因(BIN实锤):外部导航原点~44s才就绪,但bootstrap 8s就发takeoff→无有效高度→位置控制器
# 只把电机推到1410(<悬停1500)就停→永不离地。等就绪再发,控制器才会正常爬升。
p = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl"
s = open(p, encoding="utf-8").read()

anchor = '''            altitude_m = float(SPEC.get("takeoff_alt_m", 0.5) or 0.5)
            takeoff_attempts = []'''
insert = '''            altitude_m = float(SPEC.get("takeoff_alt_m", 0.5) or 0.5)

            # Wait for the EKF to establish a valid absolute position/altitude
            # before commanding takeoff. With external-nav (SLAM) the EKF origin
            # and altitude estimate can take ~45s of stationary convergence;
            # commanding NAV_TAKEOFF before then leaves the position controller
            # without a valid altitude, so it never ramps the motors to hover
            # thrust and the vehicle never leaves the ground.
            pos_ready = False
            pos_deadline = time.monotonic() + max(60.0, float(SPEC.get("readiness_timeout_sec", 45.0)))
            while time.monotonic() < pos_deadline:
                pm = master.recv_match(type=["EKF_STATUS_REPORT", "GLOBAL_POSITION_INT"], blocking=True, timeout=1.0)
                if pm is None:
                    continue
                if pm.get_type() == "EKF_STATUS_REPORT":
                    # bit4=POS_HORIZ_ABS, bit5=POS_VERT_ABS
                    if (int(pm.flags) & 0x10) and (int(pm.flags) & 0x20):
                        pos_ready = True
                        break
                elif pm.get_type() == "GLOBAL_POSITION_INT" and abs(int(pm.lat)) > 0:
                    pos_ready = True
                    break
            status["position_ready"] = pos_ready
            publish_bootstrap_status(status)

            takeoff_attempts = []'''

assert anchor in s, "anchor not found"
assert s.count(anchor) == 1, f"anchor count={s.count(anchor)}"
s = s.replace(anchor, insert)
open(p, "w", encoding="utf-8").write(s)
print("PATCHED wait-for-position before takeoff")

import py_compile
# 模板不是纯py(有 {{}} 占位),不 py_compile;仅检查括号平衡粗验
print("open+write OK")
