#!/usr/bin/env python3
# B14 遗留(clean 分支):79643b9 把 RNGFND1_MIN_CM/MAX_CM/GNDCLEAR 改为 4.5 新名
# MIN/MAX/GNDCLR,但 TestGenerateRuntimeArtifactsFromConfiguredTasks 仍断言旧名。
# 更新 want 为新名;stale 收紧为裸旧参数名(旧名被固件静默无视,出现即 bug)。幂等。
import io

f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/runtime_artifacts_test.go"
src = io.open(f, "r", encoding="utf-8").read()

OLD_WANT = "\t\t\"RNGFND1_MIN_CM 10\",\n\t\t\"RNGFND1_MAX_CM 1200\",\n\t\t\"RNGFND1_GNDCLEAR 15\","
NEW_WANT = ("\t\t// ArduPilot 4.5 renamed RNGFND1_MIN_CM/MAX_CM/GNDCLEAR to MIN/MAX/GNDCLR\n"
            "\t\t// (cm->m); the old names are silently ignored by current firmware.\n"
            "\t\t\"RNGFND1_MIN 0.05\",\n\t\t\"RNGFND1_MAX 12\",\n\t\t\"RNGFND1_GNDCLR 0.15\",")

OLD_STALE = "\t\t\"RNGFND1_MIN_CM 5\",\n\t\t\"RNGFND1_MAX_CM 600\",\n\t\t\"RNGFND1_GNDCLEAR 10\","
NEW_STALE = ("\t\t// pre-4.5 param names must never appear: current firmware ignores them\n"
             "\t\t// silently, so MIN would fall back to 0.20m and reject the sim reading.\n"
             "\t\t\"RNGFND1_MIN_CM\",\n\t\t\"RNGFND1_MAX_CM\",\n\t\t\"RNGFND1_GNDCLEAR\",")

changed = False
if NEW_WANT in src:
    print("ALREADY: want")
elif OLD_WANT in src:
    src = src.replace(OLD_WANT, NEW_WANT, 1)
    changed = True
    print("PATCHED: want -> new param names")
else:
    print("PATTERN_NOT_FOUND: want")
    raise SystemExit(2)

if NEW_STALE in src:
    print("ALREADY: stale")
elif OLD_STALE in src:
    src = src.replace(OLD_STALE, NEW_STALE, 1)
    changed = True
    print("PATCHED: stale -> bare legacy names guard")
else:
    print("PATTERN_NOT_FOUND: stale")
    raise SystemExit(2)

if changed:
    io.open(f, "w", encoding="utf-8", newline="\n").write(src)
