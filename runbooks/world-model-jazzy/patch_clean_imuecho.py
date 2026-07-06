#!/usr/bin/env python3
# 干净版 IMU 自吞回声修复(B6+B7):净化桥输出话题从 /imu 改 /navlab/slam/imu,
# 避免桥订阅自己的输出→重复/乱序 IMU→cartographer "Non-sorted data" abort。
import py_compile  # noqa (仅示意;go 文件不 py_compile)

# 1) slam.go L89: IMUTopic 默认
p1 = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/slam.go"
s1 = open(p1, encoding="utf-8").read()
old1 = 'IMUTopic:                           "/imu",'
new1 = 'IMUTopic:                           "/navlab/slam/imu",'
assert s1.count(old1) == 1, f"slam.go 匹配数={s1.count(old1)}"
open(p1, "w", encoding="utf-8").write(s1.replace(old1, new1))
print("slam.go PATCHED")

# 2) defaults.go 仅 defaultSlamBackend 那处(按行号 129,1-indexed)
p2 = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/config/defaults.go"
lines = open(p2, encoding="utf-8").read().split("\n")
idx = 129 - 1
assert 'cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")' in lines[idx], f"L129 实际={lines[idx]!r}"
lines[idx] = lines[idx].replace('"/imu"', '"/navlab/slam/imu"')
open(p2, "w", encoding="utf-8").write("\n".join(lines))
print("defaults.go L129 PATCHED:", lines[idx].strip())
