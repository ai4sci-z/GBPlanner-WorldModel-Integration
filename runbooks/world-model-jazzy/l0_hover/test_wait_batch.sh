#!/usr/bin/env bash
# WP303 fixture 硬门:20 例,每例断言三轴状态 + 精确 monitor 退出码 + 有界时间 + PID/PGID 残留。
# 只用 fake producer,绝不跑真实仿真/容器。残留用 fixture 记录的 PID/PGID 判定,不用 pgrep 模糊名。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BL="$HERE/batch_lifecycle.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; jobs -p | xargs -r kill 2>/dev/null' EXIT
export WP303_POLL_SEC=0.05 WP303_TERM_GRACE_SEC=0.3
PASS=0; FAIL=0

ck(){ if [ "$2" = "$3" ]; then echo "PASS: $1 [$2]"; PASS=$((PASS+1)); else echo "FAIL: $1 期望[$2] 实得[$3]"; FAIL=$((FAIL+1)); fi; }
jget(){ python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2" 2>/dev/null; }
# 判 pgid 下有无存活组员(非僵尸),排除测试自身
grp_alive(){ python3 -c '
import os,sys
pg=int(sys.argv[1]); me=os.getpid(); n=0
for d in os.listdir("/proc"):
    if not d.isdigit(): continue
    p=int(d)
    if p==me: continue
    try:
        f=open(f"/proc/{p}/stat").read()
        fields=f[f.rfind(")")+2:].split()
        if int(fields[2])==pg and fields[0]!="Z": n+=1
    except OSError: pass
print(n)' "$1"; }

mkroot(){ local r="$TMP/$1"; mkdir -p "$r/runs"; echo "$r"; }

# 通用 producer 生成器:$1=root $2=n_runs $3=fail_run(0=无) $4=final(1/0) $5=pre_sleep $6=post_sleep
gen_prod(){ local r=$1 n=$2 fr=$3 fin=$4 pre=${5:-0} post=${6:-0}
cat > "$r/prod.sh" <<EOF
#!/usr/bin/env bash
AR="$r"; sleep $pre
for i in \$(seq 1 $n); do
  rc=0; [ "\$i" = "$fr" ] && rc=1
  printf '{"run_index":%d,"rc":%d}\n' "\$i" "\$rc" > "\$AR/runs/run_\$i.json"
  sleep 0.03
done
[ "$fin" = "1" ] && printf '{"schema_version":1,"final":"done"}\n' > "\$AR/batch_final.json"
sleep $post
EOF
chmod +x "$r/prod.sh"; }

launch(){ local r=$1; shift; python3 "$BL" launch --artifact-root "$r" --batch-id "b_$(basename $r)" \
  --startup-budget 1 --duration 0.3 --per-run-teardown 0.1 --inter-run-gap 0.05 --finalization-budget 0.5 "$@" \
  -- bash "$r/prod.sh"; }

echo "=== 1 全部成功 ==="; R=$(mkroot f1); gen_prod "$R" 2 0 1
launch "$R" --expected-runs 2 >/dev/null 2>&1; ck "1 rc" 0 $?
ck "1 outcome" SUCCEEDED "$(jget "$R/monitor_status.json" producer_outcome)"
ck "1 evidence" COMPLETE "$(jget "$R/monitor_status.json" evidence_status)"
ck "1 cleanup" CLEAN "$(jget "$R/monitor_status.json" cleanup_status)"

echo "=== 2 某run失败但producer退0 ==="; R=$(mkroot f2); gen_prod "$R" 2 2 1
launch "$R" --expected-runs 2 >/dev/null 2>&1; ck "2 rc(聚合非producer退码)" 10 $?
ck "2 outcome" FAILED "$(jget "$R/monitor_status.json" producer_outcome)"

echo "=== 3 producer启动延迟 ==="; R=$(mkroot f3); gen_prod "$R" 2 0 1 0.5
launch "$R" --expected-runs 2 >/dev/null 2>&1; ck "3 rc(延迟不误判)" 0 $?
ck "3 outcome" SUCCEEDED "$(jget "$R/monitor_status.json" producer_outcome)"

echo "=== 4 producer崩溃 ==="; R=$(mkroot f4)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"; kill -9 -\$\$
EOF
chmod +x "$R/prod.sh"
launch "$R" --expected-runs 2 >/dev/null 2>&1; ck "4 rc" 20 $?
ck "4 outcome" CRASHED "$(jget "$R/monitor_status.json" producer_outcome)"
ck "4 partial_index 存在" yes "$([ -f "$R/partial_index.json" ] && echo yes || echo no)"

echo "=== 5 存活但超时 ==="; R=$(mkroot f5)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"; sleep 30
EOF
chmod +x "$R/prod.sh"
# deadline 极短:startup0.3 + 2*(0.1+0.05+0.02)+0.2 ≈ 0.84s
python3 "$BL" launch --artifact-root "$R" --batch-id b5 --startup-budget 0.3 --duration 0.1 \
  --per-run-teardown 0.05 --inter-run-gap 0.02 --finalization-budget 0.2 --expected-runs 2 -- bash "$R/prod.sh" >/dev/null 2>&1
ck "5 rc" 30 $?
ck "5 outcome" TIMED_OUT "$(jget "$R/monitor_status.json" producer_outcome)"
PG=$(jget "$R/task_record.json" pgid); sleep 0.4
ck "5 超时后组已清(存活=0)" 0 "$(grp_alive "$PG")"

echo "=== 6 完成但required缺失→evidence INCOMPLETE ==="; R=$(mkroot f6); gen_prod "$R" 1 0 1
launch "$R" --expected-runs 1 --required missing_bin.BIN >/dev/null 2>&1; ck "6 rc" 50 $?
ck "6 outcome" SUCCEEDED "$(jget "$R/monitor_status.json" producer_outcome)"
ck "6 evidence" INCOMPLETE "$(jget "$R/monitor_status.json" evidence_status)"

echo "=== 7 损坏run JSON不崩溃 ==="; R=$(mkroot f7)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"
printf '{bad json' > "$R/runs/run_2.json"
printf '{"schema_version":1,"final":"done"}\n' > "$R/batch_final.json"
EOF
chmod +x "$R/prod.sh"
launch "$R" --expected-runs 2 >/dev/null 2>&1; RC=$?
ck "7 非内部错误(rc≠70)" yes "$([ $RC -ne 70 ] && echo yes || echo no)"
ck "7 rc(run数不足→FAILED)" 10 $RC

echo "=== 8 profile不要求BIN不误判 ==="; R=$(mkroot f8); gen_prod "$R" 1 0 1
launch "$R" --expected-runs 1 >/dev/null 2>&1; ck "8 rc" 0 $?
ck "8 evidence(空required→COMPLETE)" COMPLETE "$(jget "$R/monitor_status.json" evidence_status)"

echo "=== 9 cleanup失败注入 ==="; R=$(mkroot f9); gen_prod "$R" 1 0 1
WP303_FORCE_CLEANUP_FAIL=1 launch "$R" --expected-runs 1 >/dev/null 2>&1; ck "9 rc" 60 $?
ck "9 cleanup" RESIDUAL "$(jget "$R/monitor_status.json" cleanup_status)"

echo "=== 10 陈旧任务幂等复查 ==="; R=$(mkroot f10); gen_prod "$R" 1 0 1
launch "$R" --expected-runs 1 >/dev/null 2>&1
timeout 5 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "10 幂等复查rc" 0 $?
ck "10 复查outcome" SUCCEEDED "$(jget "$R/monitor_status.json" producer_outcome)"

echo "=== 11 身份不符不误杀 ==="; R=$(mkroot f11); mkdir -p "$R/runs"
sleep 30 & SPID=$!; SPG=$(python3 -c "import os;print(os.getpgid($SPID))")
ST=$(python3 -c "f=open('/proc/$SPID/stat').read();print(f[f.rfind(')')+2:].split()[19])")
BID=$(cat /proc/sys/kernel/random/boot_id)
python3 -c "
import json
json.dump({'schema_version':1,'batch_id':'b11','script':'x','pid':$SPID,'pgid':$SPG,'sid':$SPG,
'pid_starttime':str(int('$ST')+999),'boot_id':'$BID','artifact_root':'$R','log':'$R/l',
'expected_runs':1,'deadline_params':{'startup_budget':0.3,'duration':0.1,'per_run_teardown':0.05,
'inter_run_gap':0.02,'finalization_budget':0.2},'required_artifacts':[],'created_at_monotonic':0,'deadline_monotonic':1e18},
open('$R/task_record.json','w'))
import os; os.chmod('$R/task_record.json',0o600)"
timeout 5 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "11 rc(CRASHED+NOT_ATTEMPTED→cleanup优先60)" 60 $?
ck "11 cleanup" NOT_ATTEMPTED "$(jget "$R/monitor_status.json" cleanup_status)"
ck "11 无辜进程存活未被杀" yes "$(kill -0 $SPID 2>/dev/null && echo yes || echo no)"
kill -9 $SPID 2>/dev/null; wait $SPID 2>/dev/null

echo "=== 12 两monitor竞争(第二只读) ==="; R=$(mkroot f12)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"; sleep 5
EOF
chmod +x "$R/prod.sh"
python3 "$BL" launch --artifact-root "$R" --batch-id b12 --startup-budget 1 --duration 5 \
  --per-run-teardown 0.1 --inter-run-gap 0.05 --finalization-budget 0.5 --expected-runs 1 -- bash "$R/prod.sh" >/dev/null 2>&1 &
LPID=$!; sleep 0.6
[ -f "$R/monitor_status.json" ]; BEFORE=$?   # 主monitor尚未写终态(producer在跑)
timeout 3 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "12 第二monitor退出码(专用让位75)" 75 $?
[ -f "$R/monitor_status.json" ]; AFTER=$?
ck "12 第二monitor未写monitor_status" "$BEFORE" "$AFTER"
touch "$R/CANCEL"; wait $LPID 2>/dev/null

echo "=== 13 两批并行互不误杀 ==="; RA=$(mkroot f13a); RB=$(mkroot f13b)
for RR in "$RA" "$RB"; do cat > "$RR/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$RR/runs/run_1.json"; sleep 5
EOF
chmod +x "$RR/prod.sh"; done
python3 "$BL" launch --artifact-root "$RB" --batch-id b13b --startup-budget 1 --duration 5 \
  --per-run-teardown 0.1 --inter-run-gap 0.05 --finalization-budget 0.5 --expected-runs 1 -- bash "$RB/prod.sh" >/dev/null 2>&1 &
LB=$!; sleep 0.5; PGB=$(jget "$RB/task_record.json" pgid)
# A cancel 触发 A 清理;不得影响 B
python3 "$BL" launch --artifact-root "$RA" --batch-id b13a --startup-budget 0.3 --duration 0.1 \
  --per-run-teardown 0.05 --inter-run-gap 0.02 --finalization-budget 0.2 --expected-runs 1 -- bash "$RA/prod.sh" >/dev/null 2>&1 &
LA=$!; sleep 0.5; touch "$RA/CANCEL"; wait $LA 2>/dev/null; sleep 0.3
ck "13 A清理后B仍存活" yes "$([ "$(grp_alive "$PGB")" -ge 1 ] && echo yes || echo no)"
touch "$RB/CANCEL"; wait $LB 2>/dev/null

echo "=== 14 cancel ==="; R=$(mkroot f14)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"; sleep 30
EOF
chmod +x "$R/prod.sh"
( sleep 0.5; touch "$R/CANCEL" ) &
python3 "$BL" launch --artifact-root "$R" --batch-id b14 --startup-budget 5 --duration 30 \
  --per-run-teardown 1 --inter-run-gap 0.05 --finalization-budget 1 --expected-runs 1 -- bash "$R/prod.sh" >/dev/null 2>&1
ck "14 rc" 40 $?
ck "14 outcome" CANCELLED "$(jget "$R/monitor_status.json" producer_outcome)"
PG=$(jget "$R/task_record.json" pgid); sleep 0.4; ck "14 cancel后组已清" 0 "$(grp_alive "$PG")"

echo "=== 15 deadline边界:producer 恰在 deadline 前完成→自然终态胜 ==="; R=$(mkroot f15)
cat > "$R/prod.sh" <<PEOF
#!/usr/bin/env bash
sleep 0.45
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"
printf '{"schema_version":1,"final":"done"}\n' > "$R/batch_final.json"
PEOF
chmod +x "$R/prod.sh"
python3 "$BL" launch --artifact-root "$R" --batch-id b15 --startup-budget 0.3 --duration 0.1 \
  --per-run-teardown 0.05 --inter-run-gap 0.05 --finalization-budget 0.1 --expected-runs 1 -- bash "$R/prod.sh" >/dev/null 2>&1
ck "15 rc(边界内自然完成胜deadline)" 0 $?
ck "15 outcome" SUCCEEDED "$(jget "$R/monitor_status.json" producer_outcome)"

echo "=== 16 record是symlink拒绝 ==="; R=$(mkroot f16); echo VICTIM > "$TMP/victim16"
ln -s "$TMP/victim16" "$R/task_record.json"
timeout 5 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "16 rc" 5 $?
ck "16 victim不变" VICTIM "$(cat "$TMP/victim16")"

echo "=== 17 record权限过宽拒绝 ==="; R=$(mkroot f17)
echo '{"schema_version":1}' > "$R/task_record.json"; chmod 0644 "$R/task_record.json"
timeout 5 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "17 rc(0644拒绝)" 5 $?

echo "=== 18 未知schema拒绝 ==="; R=$(mkroot f18)
printf '{"schema_version":999}\n' > "$R/task_record.json"; chmod 0600 "$R/task_record.json"
timeout 5 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "18 rc" 5 $?

echo "=== 19 monitor中断后重接管(恢复路径) ==="; R=$(mkroot f19)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"; sleep 2
printf '{"run_index":2,"rc":0}\n' > "$R/runs/run_2.json"
printf '{"schema_version":1,"final":"done"}\n' > "$R/batch_final.json"; sleep 0.5
EOF
chmod +x "$R/prod.sh"
python3 "$BL" launch --artifact-root "$R" --batch-id b19 --startup-budget 1 --duration 3 \
  --per-run-teardown 0.2 --inter-run-gap 0.05 --finalization-budget 1 --expected-runs 2 -- bash "$R/prod.sh" >/dev/null 2>&1 &
LPID=$!; sleep 0.6; kill -9 $LPID 2>/dev/null; wait $LPID 2>/dev/null   # monitor 被 KILL,producer 成孤儿
# 重接管:producer 仍在跑,record 在盘,拿得到锁(旧 monitor 已死)
timeout 8 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "19 重接管rc" 0 $?
ck "19 重接管outcome" SUCCEEDED "$(jget "$R/monitor_status.json" producer_outcome)"

echo "=== 20 半写batch_final崩溃边界 ==="; R=$(mkroot f20)
cat > "$R/prod.sh" <<EOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"
printf '{"schema_ver' > "$R/batch_final.json"   # 半写损坏
kill -9 -\$\$
EOF
chmod +x "$R/prod.sh"
launch "$R" --expected-runs 1 >/dev/null 2>&1; RC=$?
ck "20 非内部错误(rc≠70)" yes "$([ $RC -ne 70 ] && echo yes || echo no)"
ck "20 rc(损坏final不算完成+身份死→CRASHED)" 20 $RC

echo "=== 21 deadline 跨 monitor 重启不重置预算 ==="; R=$(mkroot f21)
cat > "$R/prod.sh" <<PEOF
#!/usr/bin/env bash
printf '{"run_index":1,"rc":0}\n' > "$R/runs/run_1.json"; sleep 30
PEOF
chmod +x "$R/prod.sh"
python3 "$BL" launch --artifact-root "$R" --batch-id b21 --startup-budget 0.3 --duration 0.1 \
  --per-run-teardown 0.05 --inter-run-gap 0.05 --finalization-budget 0.15 --expected-runs 1 -- bash "$R/prod.sh" >/dev/null 2>&1 &
LPID=$!; sleep 0.35; kill -9 $LPID 2>/dev/null; wait $LPID 2>/dev/null
PG=$(jget "$R/task_record.json" pgid); sleep 0.5
T0=$(date +%s%N)
timeout 5 python3 "$BL" monitor --artifact-root "$R" >/dev/null 2>&1; ck "21 重接管rc(不重置→TIMED_OUT)" 30 $?
T1=$(date +%s%N); ELAPMS=$(( (T1-T0)/1000000 ))
ck "21 重接管一个poll内判(<400ms)" yes "$([ $ELAPMS -lt 400 ] && echo yes || echo no)"
ck "21 outcome" TIMED_OUT "$(jget "$R/monitor_status.json" producer_outcome)"
kill -- -"$PG" 2>/dev/null; sleep 0.2

echo "=== 22 表驱动退出码(final_rc 优先级) ==="
python3 "$HERE/test_final_rc.py" >/dev/null 2>&1; ck "22 final_rc 表驱动(13组)" 0 $?

echo "=== 23 正式入口 run_batch.sh 端到端 dry-run(桩替代SITL) ==="; R23="$TMP/f23"; mkdir -p "$R23"
BC_ARTIFACT_BASE="$R23" BC_LOCK_PATH="$TMP/host23.lock" WM="" INTER_RUN_SLEEP=0 \
  WP303_DURATION=0.3 WP303_STARTUP=1 WP303_TEARDOWN=0.1 WP303_GAP=0.05 WP303_FINAL=0.5 \
  NAVLAB_SIM_CMD='exit 0' bash "$HERE/run_batch.sh" l15 2 >/dev/null 2>&1
ck "23 正式入口rc(monitor传播)" 0 $?
ROOT23=$(ls -d "$R23"/batch_l15_* 2>/dev/null | head -1)
ck "23 task_record自动生成" yes "$([ -f "$ROOT23/task_record.json" ] && echo yes || echo no)"
ck "23 monitor_status自动生成" yes "$([ -f "$ROOT23/monitor_status.json" ] && echo yes || echo no)"
ck "23 pid=pgid=sid" yes "$(python3 -c "import json;d=json.load(open('$ROOT23/task_record.json'));print('yes' if d['pid']==d['pgid']==d['sid'] else 'no')" 2>/dev/null)"
ck "23 outcome" SUCCEEDED "$(jget "$ROOT23/monitor_status.json" producer_outcome)"
ck "23 run/final自动生成" yes "$([ -f "$ROOT23/runs/run_1.json" ] && [ -f "$ROOT23/batch_final.json" ] && echo yes || echo no)"

echo "================================"
echo "结果: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
