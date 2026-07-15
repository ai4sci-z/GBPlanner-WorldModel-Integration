#!/usr/bin/env bash
# 有界批监视器(R003 动作三 / 发现四 / 验收门二·G09)。
# 取代裸 `tail -f`:跟踪批处理的真实活性(批脚本全程持有的 flock),
# 识别完成标记/生产者崩溃/超时后在有界时间内退出,并传播真实结果。
#
# 用法: wait_batch.sh <batch_log> [timeout_sec]
#   env: LOCK=/tmp/l1_bisect_batch.lock(须与批脚本一致) POLL=5
#
# 退出码契约:
#   0 = 观察到 "batch done" 且全部 run rc=0
#   1 = 观察到 "batch done" 但存在 rc!=0 的 run(逐条打印)
#   2 = 生产者已死(锁可获取)且无 "batch done" —— 批中途崩溃
#   3 = 超时(生产者仍活但未在期限内完成)
#   64 = 参数错误
# 等待期间把日志新增行透传到 stdout(负责人可见进度,不静默)。
set -u
LOG=${1:?用法: wait_batch.sh <batch_log> [timeout_sec]}
TIMEOUT_SEC=${2:-7200}
LOCK=${LOCK:-/tmp/l1_bisect_batch.lock}
POLL=${POLL:-5}

deadline=$(( $(date +%s) + TIMEOUT_SEC ))
offset=0

emit_new_lines() {
  [ -f "$LOG" ] || return 0
  local size
  size=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
  if [ "$size" -gt "$offset" ]; then
    tail -c +$((offset + 1)) "$LOG"
    offset=$size
  fi
}

finish_done() {
  emit_new_lines
  local bad
  bad=$(grep -Eo 'rc=[0-9]+' "$LOG" | grep -cv 'rc=0' || true)
  if [ "${bad:-0}" -gt 0 ]; then
    echo "wait_batch: batch done,但 $bad 个 run rc!=0:" >&2
    grep -E 'rc=[1-9]' "$LOG" >&2 || true
    exit 1
  fi
  echo "wait_batch: batch done,全部 run rc=0" >&2
  exit 0
}

producer_alive() {
  # 批脚本(l15_batch.sh/l2_batch.sh 等)全程以 fd 9 持有 $LOCK 的排他锁。
  # 锁可获取 = 无批进程存活。flock 在子 shell 中探测后立即释放。
  if ( exec 9>>"$LOCK"; flock -n 9 ) 2>/dev/null; then
    return 1  # 锁空闲 → 生产者不在
  fi
  return 0
}

while :; do
  emit_new_lines
  if [ -f "$LOG" ] && grep -q '^batch done' "$LOG"; then
    finish_done
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "wait_batch: 超时(${TIMEOUT_SEC}s),生产者状态未决" >&2
    exit 3
  fi
  if [ -f "$LOG" ] && ! producer_alive; then
    # 竞态防护:生产者可能刚写完 done 就退出——释放锁后再核对一次标记
    if grep -q '^batch done' "$LOG"; then
      finish_done
    fi
    echo "wait_batch: 生产者已死且无 batch done —— 批中途崩溃" >&2
    exit 2
  fi
  sleep "$POLL"
done
