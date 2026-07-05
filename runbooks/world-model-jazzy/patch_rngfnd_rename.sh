#!/usr/bin/env bash
# 坑#16 修复:ArduPilot 4.5 改名 RNGFND1_MIN_CM/MAX_CM/GNDCLEAR → MIN/MAX/GNDCLR(单位 cm→m)。
# 作者 profile/模板/Go 生成器全用旧名 → pinned master 静默无视 → MIN 落默认 0.2m
# → TFmini 地面读数 0.095m 无效 → EK3_SRC1_POSZ=2 高度源死 → EKF3 not started → takeoff 拒。
# MIN 统一 0.05(作者 Go 默认 defaults.go:110 本就是 0.05;模板 10cm 边界卡死 9.5cm 地面读数)。
set -euo pipefail
R=/home/ai4s/ws/world-model
T=$R/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl
P=$R/docker/profiles/navlab-sitl-external-nav.parm
G=$R/orchestration/sim/internal/tasks/helpers/navlab_models.go
Y=$R/navlab/tests/slam/test_sitl_external_nav_params.py

for f in "$T" "$P"; do
  sed -i \
    -e 's/^RNGFND1_MIN_CM 10$/RNGFND1_MIN 0.05/' \
    -e 's/^RNGFND1_MAX_CM 1200$/RNGFND1_MAX 12/' \
    -e 's/^RNGFND1_GNDCLEAR 15$/RNGFND1_GNDCLR 0.15/' "$f"
done

python3 - "$G" << 'PYEOF'
import sys,re
p=sys.argv[1]; s=open(p).read()
s=s.replace('''	minCM := int(spec.RangefinderMinDistanceM*100 + 0.5)
	maxCM := int(spec.RangefinderMaxDistanceM*100 + 0.5)
''','''''')
s=s.replace('''		"RNGFND1_MIN_CM":   fmt.Sprintf("%d", minCM),
		"RNGFND1_MAX_CM":   fmt.Sprintf("%d", maxCM),
		"RNGFND1_GNDCLEAR": "15",''','''		// ArduPilot 4.5 renamed RNGFND1_MIN_CM/MAX_CM/GNDCLEAR to
		// RNGFND1_MIN/MAX/GNDCLR (centimetres -> metres); the old names are
		// silently ignored by current firmware.
		"RNGFND1_MIN":    fmt.Sprintf("%.2f", spec.RangefinderMinDistanceM),
		"RNGFND1_MAX":    fmt.Sprintf("%.2f", spec.RangefinderMaxDistanceM),
		"RNGFND1_GNDCLR": "0.15",''')
s=s.replace('"RNGFND1_TYPE", "RNGFND1_ORIENT", "RNGFND1_MIN_CM", "RNGFND1_MAX_CM", "RNGFND1_GNDCLEAR"','"RNGFND1_TYPE", "RNGFND1_ORIENT", "RNGFND1_MIN", "RNGFND1_MAX", "RNGFND1_GNDCLR"')
open(p,"w").write(s)
print("go patched")
PYEOF

python3 - "$Y" << 'PYEOF'
import sys
p=sys.argv[1]; s=open(p).read()
s=s.replace('assert params["RNGFND1_MIN_CM"] == "10"','assert params["RNGFND1_MIN"] == "0.05"')
s=s.replace('assert params["RNGFND1_MAX_CM"] == "1200"','assert params["RNGFND1_MAX"] == "12"')
s=s.replace('assert params["RNGFND1_GNDCLEAR"] == "15"','assert params["RNGFND1_GNDCLR"] == "0.15"')
open(p,"w").write(s)
print("test patched")
PYEOF

echo "=== 验证 ==="
grep -n "RNGFND1_MIN\|RNGFND1_MAX\|RNGFND1_GNDCL" "$T" "$P" | head
grep -n "RNGFND1_MIN\|RNGFND1_GNDCLR" "$G" | head -6
grep -n "RNGFND1_MIN\|RNGFND1_MAX\|RNGFND1_GNDCL" "$Y"
echo "=== go build/vet/test ==="
cd $R/orchestration/sim
export PATH=/usr/local/go/bin:$PATH
go build ./... && go vet ./internal/tasks/helpers/ && go test ./internal/tasks/helpers/ 2>&1 | tail -3
