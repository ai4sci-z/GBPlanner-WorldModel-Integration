#!/usr/bin/env bash
# 追参数链:渲染 parm 产物 vs BIN 实际值;运行时 PARAM_SET 嫌疑
CLEAN=/home/ai4s/ws-clean/world-model
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
echo "=== run 产物中的 parm 文件 ==="
find "$RUNDIR" -name "*.parm" | head -5
for f in $(find "$RUNDIR" -name "*.parm" | head -3); do
  echo "-- $f --"
  grep -E "EK3_SRC1_YAW|COMPASS_USE" "$f" || echo "(无)"
done
echo "=== 模板当前值(clean 分支) ==="
grep -E "EK3_SRC1_YAW|COMPASS_USE" "$CLEAN/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl" || echo "(无)"
echo "=== 运行时 PARAM_SET 嫌疑(模板/代码里谁设 EK3/COMPASS) ==="
grep -rn "EK3_SRC1_YAW\|COMPASS_USE" "$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python/" | head -10
grep -rn "param_set\|PARAM_SET\|set_parameters" "$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl" | head -10
echo "=== SITL 启动命令里的 defaults ==="
grep -rn "defaults\|\.parm" "$RUNDIR/runtime" 2>/dev/null | grep -v Binary | head -8
