#!/usr/bin/env python3
# 实质修法:让飞机撑到 EKF 外部导航收敛(原点/高度就绪,~44s)再起飞。
# 根因(BIN实锤):takeoff 11s触发但高度估计43.7s才有;DISARM_DELAY=10 让飞机41.2s(原点前)被上锁。
# ①DISARM_DELAY 0(别提前上锁) ②readiness_timeout 45->90(takeoff循环撑过44s)
CLEAN = "/home/ai4s/ws-clean/world-model"

# ① 两个 parm 文件加 DISARM_DELAY 0(EK3_SRC1_YAW 行后插,若已有则改)
for f in [f"{CLEAN}/docker/profiles/navlab-sitl-external-nav.parm",
          f"{CLEAN}/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl"]:
    t = open(f, encoding="utf-8").read()
    if "DISARM_DELAY" in t:
        import re
        t = re.sub(r"DISARM_DELAY\s+\d+", "DISARM_DELAY 0", t)
    else:
        # 插在 EK3_SRC1_POSXY 行前
        t = t.replace("EK3_SRC1_POSXY 6", "DISARM_DELAY 0\nEK3_SRC1_POSXY 6", 1)
    open(f, "w", encoding="utf-8").write(t)
    print("DISARM_DELAY patched:", f.split("/")[-1])

# ② readiness_timeout 默认 45 -> 90(defaults.go)
d = f"{CLEAN}/orchestration/sim/internal/config/defaults.go"
s = open(d, encoding="utf-8").read()
old = "cfg.ReadinessTimeoutSec = defaultFloat(cfg.ReadinessTimeoutSec, 45)"
assert old in s, "readiness default 45 not found"
s = s.replace(old, "cfg.ReadinessTimeoutSec = defaultFloat(cfg.ReadinessTimeoutSec, 90)")
open(d, "w", encoding="utf-8").write(s)
print("readiness_timeout 45->90 patched")
