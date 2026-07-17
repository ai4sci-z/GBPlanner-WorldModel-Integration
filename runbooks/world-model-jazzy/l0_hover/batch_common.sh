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

bc_init() {
  local tag="$1"
  BC_TAG="$tag"
  BC_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BC_ROOT="${BC_ROOT:-$BC_ARTIFACT_BASE/batch_${tag}_${BC_STAMP}}"
  mkdir -p "$BC_ROOT/runs"
  BC_LOG="$BC_ROOT/batch.log"
  BC_RCS=()
  # 主机 SITL 互斥锁(纯互斥;fd 9)
  exec 9>"$BC_LOCK_PATH"
  if ! flock -n 9; then
    echo "batch_common: another real SITL batch holds the host lock ($BC_LOCK_PATH)" >&2
    return 90
  fi
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
  "$@" >>"$BC_LOG" 2>&1
  rc=$?
  end="$(date -u +%FT%TZ)"
  echo "=== $BC_TAG run $i rc=$rc end $end ===" | tee -a "$BC_LOG"
  printf '{"run_index":%d,"start":"%s","end":"%s","rc":%d}\n' "$i" "$start" "$end" "$rc" \
    > "$BC_ROOT/runs/run_$i.json"
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
  printf '{"schema_version":1,"final":"done","run_rc_map":{%s}}\n' "$map" \
    > "$BC_ROOT/batch_final.json"
  echo "batch done: $(date -u +%FT%TZ)  agg_rc=$agg  root=$BC_ROOT" | tee -a "$BC_LOG"
  return "$agg"
}
