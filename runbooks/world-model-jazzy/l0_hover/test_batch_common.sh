#!/usr/bin/env bash
# WP303 批脚本结构测试(干跑,NAVLAB_SIM_CMD 桩替代真实 SITL;绝不启动 go run/Gazebo/ArduPilot)。
# 验证:批脚本(producer-only)结构化 run 记录/聚合 rc/日志可读/无残留;正式入口 run_batch 主机锁互斥。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; jobs -p | xargs -r kill 2>/dev/null' EXIT
PASS=0; FAIL=0
ck(){ if [ "$2" = "$3" ]; then echo "PASS: $1 [$2]"; PASS=$((PASS+1)); else echo "FAIL: $1 期望[$2] 实得[$3]"; FAIL=$((FAIL+1)); fi; }
jget(){ python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2" 2>/dev/null; }

export WM=""  # 干跑不碰真实 wm(git 头行会写 n/a)
export BC_LOCK_PATH="$TMP/host.lock"
export INTER_RUN_SLEEP=0

echo "=== 1 全成功:3 run rc=0 → 批 rc=0,batch_final 完整 ==="
R1="$TMP/r1"
BC_ROOT="$R1" RUNS=3 NAVLAB_SIM_CMD='exit 0' bash "$HERE/l15_batch.sh" >/dev/null 2>&1
ck "1 批聚合rc" 0 $?
ck "1 run_1 存在" 0 "$([ -f "$R1/runs/run_1.json" ] && echo 0 || echo 1)"
ck "1 run_1 rc字段" 0 "$(jget "$R1/runs/run_1.json" rc)"
ck "1 batch_final final" done "$(jget "$R1/batch_final.json" final)"
ck "1 batch_final schema" 1 "$(jget "$R1/batch_final.json" schema_version)"

echo "=== 2 含失败 run:第2 run rc=1 → 批非零(聚合) ==="
R2="$TMP/r2"
# 桩:按 run 递增计数,第2次返回1
cat > "$TMP/stub2.sh" <<'EOF'
c="$TMP/cnt2"; n=$(( $(cat "$c" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$c"
[ "$n" = "2" ] && exit 1 || exit 0
EOF
BC_ROOT="$R2" RUNS=3 TMP="$TMP" NAVLAB_SIM_CMD="bash $TMP/stub2.sh" bash "$HERE/l15_batch.sh" >/dev/null 2>&1
ck "2 批聚合rc(有失败→10)" 10 $?
ck "2 run_2 rc=1" 1 "$(jget "$R2/runs/run_2.json" rc)"

echo "=== 3 正式入口 run_batch 主机锁互斥:持锁时被拒(rc=90) ==="
R3="$TMP/r3"; mkdir -p "$R3"
( exec 9>"$BC_LOCK_PATH"; flock -n 9; sleep 3 ) &
HOLDER=$!; sleep 0.3
BC_ARTIFACT_BASE="$R3" BC_LOCK_PATH="$BC_LOCK_PATH" WM="" INTER_RUN_SLEEP=0 \
  WP303_DURATION=0.3 WP303_STARTUP=1 WP303_TEARDOWN=0.1 WP303_GAP=0.05 WP303_FINAL=0.5 \
  NAVLAB_SIM_CMD='exit 0' bash "$HERE/run_batch.sh" l2 1 >/dev/null 2>&1
ck "3 run_batch 持锁时rc(主机互斥)" 90 $?
kill "$HOLDER" 2>/dev/null; wait "$HOLDER" 2>/dev/null

echo "=== 4 l2fix 同契约:干跑成功 + batch_lifecycle 可判定 ==="
R4="$TMP/r4"
BC_ROOT="$R4" RUNS=2 NAVLAB_SIM_CMD='exit 0' bash "$HERE/l2fix_batch.sh" >/dev/null 2>&1
ck "4 l2fix 批rc" 0 $?
# batch_lifecycle monitor 能读这批的结构化记录(用 monitor-only 幂等复查;需 task_record→此处直接验 final)
ck "4 run_rc_map 非空" 0 "$(python3 -c 'import json;d=json.load(open("'"$R4"'/batch_final.json"));print(0 if d["run_rc_map"] else 1)' 2>/dev/null)"

echo "=== 5 日志可读保留 ==="
ck "5 batch.log 存在且含 run 行" 0 "$(grep -q 'run 1 start' "$R1/batch.log" && echo 0 || echo 1)"

echo "=== 6 无残留(桩即时退出,无长进程) ==="
ck "6 无 l15/l2 批残留" 0 "$(ps -eo args | grep -E '/l15_batch|/l2_batch|/l2fix_batch' | grep -v grep | wc -l | tr -d ' ')"

echo "================================"
echo "结果: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
