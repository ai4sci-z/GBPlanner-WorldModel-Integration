#!/usr/bin/env python3
# 撤掉 3 个不符合物理实际的参数 hack,只留真 bug 修复+死锁逻辑修复。
# 撤: ①EK3_SRC1_POSZ 1->2(还原测距仪高度源,室内正解) ②删 DISARM_DELAY 0(还原安全保护)
#     ③readiness_timeout 90->45(还原作者默认)
# 留: %%/空launch参数/IMU回声/测距仪参数名(真bug) + fcu 死锁逻辑修复(相序正解)
CLEAN = "/home/ai4s/ws-clean/world-model"
parms = [
    f"{CLEAN}/docker/profiles/navlab-sitl-external-nav.parm",
    f"{CLEAN}/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl",
]
for f in parms:
    t = open(f, encoding="utf-8").read()
    # ①还原高度源为测距仪(2)
    t = t.replace("EK3_SRC1_POSZ 1", "EK3_SRC1_POSZ 2")
    # ②删掉我插入的 DISARM_DELAY 0 行(它在 EK3_SRC1_POSXY 前)
    t = t.replace("DISARM_DELAY 0\nEK3_SRC1_POSXY 6", "EK3_SRC1_POSXY 6")
    open(f, "w", encoding="utf-8").write(t)
    print("reverted parm hacks:", f.split("/")[-1])

# ③readiness_timeout 90->45
d = f"{CLEAN}/orchestration/sim/internal/config/defaults.go"
s = open(d, encoding="utf-8").read()
s = s.replace('cfg.ReadinessTimeoutSec = defaultFloat(cfg.ReadinessTimeoutSec, 90)',
              'cfg.ReadinessTimeoutSec = defaultFloat(cfg.ReadinessTimeoutSec, 45)')
open(d, "w", encoding="utf-8").write(s)
print("reverted readiness_timeout 90->45")

print("=== 验证:剩余的应只有真fix ===")
