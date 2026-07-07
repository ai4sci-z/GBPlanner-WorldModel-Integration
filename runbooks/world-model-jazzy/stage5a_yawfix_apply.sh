#!/usr/bin/env bash
# Stage5a 上游修复:EKF yaw/位置参考系对齐(clean 分支,PR 素材)
#  ①EK3_SRC1_YAW 1(罗盘)→6(外部导航):yaw 与位置同源,消除 map↔NED 固定偏角 δ
#  ②sim spec 去掉 --align-yaw-to-fcu:sender 发真 SLAM yaw(原来把 FCU yaw 喂回自己=循环)
# 证据链:stage5a 三跑 + BIN(t=47.2 stopped aiding→t=48.1 position lost,XKF1 跑飞34m)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
PARM=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl
SPEC=$CLEAN/orchestration/sim/internal/tasks/runtime_specs.go
PARMTEST=$CLEAN/orchestration/sim/internal/tasks/runtime_artifacts_test.go
SPECTEST=$CLEAN/orchestration/sim/internal/tasks/runtime_specs_test.go

cd "$CLEAN"
echo "=== 修改前 ==="
grep -n "EK3_SRC1_YAW" "$PARM"
grep -n "align-yaw-to-fcu" "$SPEC" || true

sed -i 's/^EK3_SRC1_YAW 1$/EK3_SRC1_YAW 6/' "$PARM"
# 删除 spec 里的 flag 行(保留 real 路侧不动:只动 sim runtime_specs.go)
sed -i '/"--align-yaw-to-fcu",/d' "$SPEC"
# 同步测试断言
sed -i 's/"EK3_SRC1_YAW 1"/"EK3_SRC1_YAW 6"/' "$PARMTEST"
sed -i '/"--align-yaw-to-fcu",/d' "$SPECTEST"

echo "=== 修改后 ==="
grep -n "EK3_SRC1_YAW" "$PARM"
grep -n "align-yaw-to-fcu" "$SPEC" "$SPECTEST" || echo "flag 已移除"
echo "=== go build/test ==="
export PATH=/usr/local/go/bin:$PATH
cd "$CLEAN/orchestration/sim"
go build ./... && go vet ./internal/tasks/... && go test ./internal/tasks/... 2>&1 | tail -5
git -C "$CLEAN" status --short | head
