#!/usr/bin/env bash
# wait_batch.sh 四类 fixture 自动测试(R003 验收门二·G09):
#   成功 / 完成但有失败 run / 生产者崩溃 / 超时 / 已完成陈旧日志(F10 原始 bug 场景)。
# 每例断言退出码,并做监视器前后进程快照证明无孤儿。
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
WB="$HERE/wait_batch.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

check() { # name expected_rc actual_rc
  if [ "$2" -eq "$3" ]; then echo "PASS: $1 (rc=$3)"; PASS=$((PASS+1));
  else echo "FAIL: $1 期望 rc=$2 实得 rc=$3"; FAIL=$((FAIL+1)); fi
}

orphan_check() { # name
  local n
  n=$(pgrep -fc "wait_batch.sh $TMP" || true)
  if [ "${n:-0}" -eq 0 ]; then echo "PASS: $1 无孤儿监视器"; PASS=$((PASS+1));
  else echo "FAIL: $1 残留 $n 个监视器进程"; pgrep -af "wait_batch.sh $TMP"; FAIL=$((FAIL+1)); fi
}

fake_producer() { # log lock body...
  local log=$1 lock=$2; shift 2
  ( exec 9>>"$lock"; flock -n 9 || exit 90; "$@" "$log" ) &
  echo $!
}

echo "=== fixture 1: 成功(全部 rc=0 后 batch done) ==="
L=$TMP/ok.log; K=$TMP/ok.lock
body_ok() { { echo "batch start"; echo "=== run 1 rc=0 end ==="; sleep 1; echo "batch done"; } >>"$1"; }
fake_producer "$L" "$K" body_ok >/dev/null
LOCK=$K POLL=1 "$WB" "$L" 30 >/dev/null 2>&1; check "成功" 0 $?
orphan_check "成功"

echo "=== fixture 2: 完成但含失败 run ==="
L=$TMP/mixed.log; K=$TMP/mixed.lock
body_mixed() { { echo "batch start"; echo "=== run 1 rc=0 end ==="; echo "=== run 2 rc=1 end ==="; sleep 1; echo "batch done"; } >>"$1"; }
fake_producer "$L" "$K" body_mixed >/dev/null
LOCK=$K POLL=1 "$WB" "$L" 30 >/dev/null 2>&1; check "含失败run" 1 $?
orphan_check "含失败run"

echo "=== fixture 3: 生产者崩溃(无 batch done 即死) ==="
L=$TMP/crash.log; K=$TMP/crash.lock
body_crash() { { echo "batch start"; echo "=== run 1/3 start ==="; } >>"$1"; sleep 1; }
fake_producer "$L" "$K" body_crash >/dev/null
LOCK=$K POLL=1 "$WB" "$L" 30 >/dev/null 2>&1; check "生产者崩溃" 2 $?
orphan_check "生产者崩溃"

echo "=== fixture 4: 超时(生产者存活但不完成) ==="
L=$TMP/hang.log; K=$TMP/hang.lock
body_hang() { echo "batch start" >>"$1"; sleep 20; }
PID=$(fake_producer "$L" "$K" body_hang)
LOCK=$K POLL=1 "$WB" "$L" 4 >/dev/null 2>&1; check "超时" 3 $?
kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
orphan_check "超时"

echo "=== fixture 5: 陈旧已完成日志(F10 原始场景:批早已 done,无锁持有者) ==="
L=$TMP/stale.log
{ echo "batch start"; echo "=== run 1 rc=0 end ==="; echo "batch done"; } >"$L"
START=$(date +%s)
LOCK=$TMP/stale.lock POLL=1 "$WB" "$L" 30 >/dev/null 2>&1; RC=$?
ELAPSED=$(( $(date +%s) - START ))
check "陈旧done退出码" 0 $RC
if [ "$ELAPSED" -le 3 ]; then echo "PASS: 陈旧done 即时退出(${ELAPSED}s)"; PASS=$((PASS+1));
else echo "FAIL: 陈旧done 退出耗时 ${ELAPSED}s(>3s)"; FAIL=$((FAIL+1)); fi
orphan_check "陈旧done"

echo "================================"
echo "结果: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
