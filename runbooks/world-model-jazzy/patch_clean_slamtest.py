#!/usr/bin/env python3
# B12 同款(clean 分支遗留):79643b9 改了 SLAM IMU 输出默认 /imu -> /navlab/slam/imu,
# 但 TestWriteSlamRuntimeConfig 仍断言旧值。更新断言 + 加回归守卫(输出话题不得等于输入,
# 否则 IMU 自吞回声 -> cartographer Non-sorted data abort)。幂等。
import io

f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/slam_test.go"
src = io.open(f, "r", encoding="utf-8").read()

OLD = "\t\t`imu_source_topic = '/imu'`,\n\t\t`imu_topic = '/imu'`,"
NEW = "\t\t`imu_source_topic = '/imu'`,\n\t\t// The sanitising bridge output must differ from its /imu source, else the\n\t\t// bridge re-ingests its own output and cartographer aborts (Non-sorted data).\n\t\t`imu_topic = '/navlab/slam/imu'`,"

if NEW in src:
    print("ALREADY")
elif OLD not in src:
    print("PATTERN_NOT_FOUND")
    raise SystemExit(2)
else:
    src = src.replace(OLD, NEW, 1)
    # 回归守卫:输出 == 输入 直接判死
    GUARD_MARK = "must not echo the bridge source"
    if GUARD_MARK not in src:
        anchor = "\tif strings.Contains(text, `cartographer_odometry_topic = '/odometry'`) {"
        guard = ("\tif strings.Contains(text, \"imu_topic = '/imu'\\n\") {\n"
                 "\t\tt.Fatalf(\"imu_topic must not echo the bridge source /imu (self-ingest aborts cartographer):\\n%s\", text)\n"
                 "\t}\n")
        src = src.replace(anchor, guard + anchor, 1)
    io.open(f, "w", encoding="utf-8", newline="\n").write(src)
    print("PATCHED")
