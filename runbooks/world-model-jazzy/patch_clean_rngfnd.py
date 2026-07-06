#!/usr/bin/env python3
# 干净版测距仪修复(B14):RNGFND1_MIN_CM/MAX_CM/GNDCLEAR(4.5前旧名,固件忽略)→ MIN/MAX/GNDCLR(新名,单位m)。
# 根因实锤:旧名被忽略→RNGFND1_MIN 落默认0.20m,而测距仪读0.095m<0.20→判无效"No Data"→高度源(POSZ=2)死→takeoff拒。
# MIN 用 0.05(<0.095)。
CLEAN = "/home/ai4s/ws-clean/world-model"

# 1) Go 生成器 navlab_models.go
g = f"{CLEAN}/orchestration/sim/internal/tasks/helpers/navlab_models.go"
s = open(g, encoding="utf-8").read()
s = s.replace(
    '''	minCM := int(spec.RangefinderMinDistanceM*100 + 0.5)
	maxCM := int(spec.RangefinderMaxDistanceM*100 + 0.5)
''', '')
s = s.replace(
    '''		"RNGFND1_MIN_CM":   fmt.Sprintf("%d", minCM),
		"RNGFND1_MAX_CM":   fmt.Sprintf("%d", maxCM),
		"RNGFND1_GNDCLEAR": "15",''',
    '''		// ArduPilot 4.5 renamed RNGFND1_MIN_CM/MAX_CM/GNDCLEAR to MIN/MAX/GNDCLR
		// (cm->m); the old names are silently ignored by current firmware, so MIN
		// fell to its 0.20 m default and the 0.095 m sim reading was rejected.
		"RNGFND1_MIN":    fmt.Sprintf("%.2f", spec.RangefinderMinDistanceM),
		"RNGFND1_MAX":    fmt.Sprintf("%.2f", spec.RangefinderMaxDistanceM),
		"RNGFND1_GNDCLR": "0.15",''')
s = s.replace(
    '"RNGFND1_TYPE", "RNGFND1_ORIENT", "RNGFND1_MIN_CM", "RNGFND1_MAX_CM", "RNGFND1_GNDCLEAR"',
    '"RNGFND1_TYPE", "RNGFND1_ORIENT", "RNGFND1_MIN", "RNGFND1_MAX", "RNGFND1_GNDCLR"')
open(g, "w", encoding="utf-8").write(s)
print("navlab_models.go PATCHED")

# 2) 两个 parm 文件
for f in [f"{CLEAN}/docker/profiles/navlab-sitl-external-nav.parm",
          f"{CLEAN}/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl"]:
    t = open(f, encoding="utf-8").read()
    t = t.replace("RNGFND1_MIN_CM 10", "RNGFND1_MIN 0.05")
    t = t.replace("RNGFND1_MAX_CM 1200", "RNGFND1_MAX 12")
    t = t.replace("RNGFND1_GNDCLEAR 15", "RNGFND1_GNDCLR 0.15")
    open(f, "w", encoding="utf-8").write(t)
    print("PATCHED", f.split("/")[-1])
