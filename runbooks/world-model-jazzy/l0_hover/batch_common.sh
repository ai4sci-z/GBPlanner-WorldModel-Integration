#!/usr/bin/env bash
# WP303 批脚本公共契约(单一职责:结构化 run 记录 + 聚合 rc + 主机 SITL 互斥)。
# 被 l15_batch.sh / l2_batch.sh / l2fix_batch.sh source。可用 batch_lifecycle.py 监视,
# 也可独立跑;结构化记录使二者都能判定,不靠 grep 散文日志。
#
# 契约:
#   bc_init <tag>         建 artifact_root(唯一批目录)+runs/,取主机 SITL 互斥锁,写人读日志头。
#   bc_run <i> <cmd...>   跑一个 run,写 runs/run_<i>.json {run_index,start,end,rc},返回该 run rc。
#   bc_finalize           写 batch_final.json {schema_version,final,run_rc_map},聚合 rc
#                         (任一 run rc≠0 → 非零),打印,返回聚合 rc。
# 锁:主机级 SITL 互斥(/tmp/navlab_sitl_host.lock),职责仅互斥(同一时刻本机只跑一个真实 SITL 批),
#     不是生命探针(生命判定归 batch_lifecycle.py 的身份契约)。替代已废弃的共用 /tmp/l1_bisect_batch.lock。
set -uo pipefail

BC_LOCK_PATH="${BC_LOCK_PATH:-/tmp/navlab_sitl_host.lock}"
BC_ARTIFACT_BASE="${BC_ARTIFACT_BASE:-${WM:-/home/ai4s/projects/world-model}/artifacts/sim}"

bc_write_atomic() {
  # 原子写:同目录临时文件 + fsync + rename + fsync 目录;失败不留伪终态
  local dst="$1" content="$2" dir tmp
  dir="$(dirname "$dst")"
  tmp="$(mktemp "$dir/.bc.XXXXXX")" || return 1
  printf '%s' "$content" > "$tmp" || { rm -f "$tmp"; return 1; }
  python3 - "$tmp" "$dst" "$dir" <<'PY'
import os,sys
tmp,dst,d=sys.argv[1],sys.argv[2],sys.argv[3]
fd=os.open(tmp,os.O_RDONLY); os.fsync(fd); os.close(fd)
os.replace(tmp,dst)
dfd=os.open(d,os.O_RDONLY); os.fsync(dfd); os.close(dfd)
PY
}

bc_init() {
  local tag="$1"
  BC_TAG="$tag"
  BC_BATCH_ID="${WP303_BATCH_ID:-${BATCH_ID:-unknown}}"
  BC_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BC_ROOT="${BC_ROOT:-$BC_ARTIFACT_BASE/batch_${tag}_${BC_STAMP}}"
  mkdir -p "$BC_ROOT/runs"
  BC_LOG="$BC_ROOT/batch.log"
  BC_RCS=()
  {
    echo "batch start: $(date -u +%FT%TZ)  tag=$tag  root=$BC_ROOT"
    [ -n "${WM:-}" ] && echo "wm_head: $(git -C "$WM" rev-parse HEAD 2>/dev/null || echo n/a)"
    [ -n "${WM:-}" ] && echo "wm_dirty: $(git -C "$WM" status --porcelain 2>/dev/null | wc -l) files"
  } | tee "$BC_LOG"
  return 0
}

bc_run() {
  local i="$1"; shift
  local start end rc
  start="$(date -u +%FT%TZ)"
  echo "=== $BC_TAG run $i start $start ===" | tee -a "$BC_LOG"
  # E1C-03 run 身份握手(纯观察:目录集合冻结;失败绝不改 run rc,不动 navlab-sim argv)
  # 默认跟随 WP303_TELEMETRY(off=零变化;telemetry on 时必须有 registry 供 sidecar 取 run_id)
  local _rr_on="${WP303_RUN_REGISTRY:-${WP303_TELEMETRY:-off}}"
  local _rrdir="$BC_ROOT/run_registry" _rrwatch="${BC_WATCH_DIR:-$BC_ARTIFACT_BASE/hover}"
  local _rrpy="$(dirname "${BASH_SOURCE[0]}")/open1/run_registry.py"
  local _rrwpid=""
  if [ "$_rr_on" = "on" ] && [ -f "$_rrpy" ]; then
    python3 "$_rrpy" begin --registry-dir "$_rrdir" --batch-id "$BC_BATCH_ID" \
      --run-index "$i" --watch-dir "$_rrwatch" >>"$BC_LOG" 2>&1 || true
    # E1L-02:并发 watcher——producer 运行期间即时 RESOLVE,不等 producer 结束
    python3 "$_rrpy" watch --registry-dir "$_rrdir" --run-index "$i" \
      --timeout-sec "${BC_REGISTRY_WATCH_SEC:-${WP303_IDENTITY_WAIT_SEC:-300}}" --poll-sec 0.05 >>"$BC_LOG" 2>&1 &
    _rrwpid=$!
  fi
  "$@" >>"$BC_LOG" 2>&1
  rc=$?
  if [ "$_rr_on" = "on" ] && [ -f "$_rrpy" ]; then
    # finish 前有界回收 watcher(先给自然完成窗;仍活则 TERM→CANCELLED 终态)
    if [ -n "$_rrwpid" ]; then
      local _w
      for _w in $(seq 1 20); do kill -0 "$_rrwpid" 2>/dev/null || break; sleep 0.05; done
      kill -0 "$_rrwpid" 2>/dev/null && kill -TERM "$_rrwpid" 2>/dev/null
      wait "$_rrwpid" 2>/dev/null || true
    fi
    python3 "$_rrpy" finish --registry-dir "$_rrdir" --run-index "$i" --rc "$rc" >>"$BC_LOG" 2>&1 || true
  fi
  end="$(date -u +%FT%TZ)"
  echo "=== $BC_TAG run $i rc=$rc end $end ===" | tee -a "$BC_LOG"
  bc_write_atomic "$BC_ROOT/runs/run_$i.json" \
    "$(printf '{"schema_version":1,"batch_id":"%s","run_index":%d,"start":"%s","end":"%s","rc":%d}' "$BC_BATCH_ID" "$i" "$start" "$end" "$rc")"
  BC_RCS+=("$rc")
  return "$rc"
}

bc_finalize() {
  local agg=0 map="" first=1 idx=1 rc
  for rc in "${BC_RCS[@]:-}"; do
    [ -z "$rc" ] && continue
    [ "$rc" -ne 0 ] && agg=10
    [ $first -eq 1 ] || map+=","
    map+="\"$idx\":$rc"; first=0; idx=$((idx+1))
  done
  bc_write_atomic "$BC_ROOT/batch_final.json" \
    "$(printf '{"schema_version":1,"batch_id":"%s","final":"done","run_rc_map":{%s}}' "$BC_BATCH_ID" "$map")"
  echo "batch done: $(date -u +%FT%TZ)  agg_rc=$agg  root=$BC_ROOT" | tee -a "$BC_LOG"
  return "$agg"
}
