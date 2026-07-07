#!/usr/bin/env bash
# Stage5a 修复 v2:改真源头 docker/profiles/navlab-sitl-external-nav.parm
#  EK3_SRC1_YAW 6(yaw 与位置同源=外部导航)+ COMPASS_USE 全关(消除罗盘世界系与
#  SLAM map 系的 δ 打架;室内外部导航标准配置)。fixture 模板同步(测试奇偶校验)。
set -e
CLEAN=/home/ai4s/ws-clean/world-model
REAL=$CLEAN/docker/profiles/navlab-sitl-external-nav.parm
TMPL=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl

echo "=== 真源头修改前 ==="
grep -nE "EK3_SRC1_YAW|COMPASS_USE" "$REAL" || echo "(无 COMPASS 行)"

sed -i 's/^EK3_SRC1_YAW[[:space:]].*/EK3_SRC1_YAW 6/' "$REAL"
grep -q "^COMPASS_USE " "$REAL" && sed -i 's/^COMPASS_USE[[:space:]].*/COMPASS_USE 0/' "$REAL" || printf 'COMPASS_USE 0\n' >> "$REAL"
grep -q "^COMPASS_USE2" "$REAL" && sed -i 's/^COMPASS_USE2[[:space:]].*/COMPASS_USE2 0/' "$REAL" || printf 'COMPASS_USE2 0\n' >> "$REAL"
grep -q "^COMPASS_USE3" "$REAL" && sed -i 's/^COMPASS_USE3[[:space:]].*/COMPASS_USE3 0/' "$REAL" || printf 'COMPASS_USE3 0\n' >> "$REAL"

# fixture 模板同步(EK3_SRC1_YAW 已是 6;补 COMPASS 行保持奇偶)
grep -q "^COMPASS_USE " "$TMPL" || printf 'COMPASS_USE 0\nCOMPASS_USE2 0\nCOMPASS_USE3 0\n' >> "$TMPL"

echo "=== 真源头修改后 ==="
grep -nE "EK3_SRC1_YAW|COMPASS_USE" "$REAL"
echo "=== fixture 同步后 ==="
grep -nE "EK3_SRC1_YAW|COMPASS_USE" "$TMPL"
echo "=== go test(tasks 包) ==="
export PATH=/usr/local/go/bin:$PATH
cd "$CLEAN/orchestration/sim"
go test ./internal/tasks/... 2>&1 | tail -3
git -C "$CLEAN" status --short | head
