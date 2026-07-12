#!/usr/bin/env bash
# GATE-4: world-model exploration live run(原生 Linux 版,HANDOVER_LINUX.md §4 GATE-4)
#
#   sg docker -c 'bash runbooks/world-model-jazzy/gate4_live_native.sh'
#
# 移植自 stage6_live2.sh(WSL 版),只做路径参数化;跑法/口径逐字保持一致。
# 验收: summary.json → task_status=TASK_STATUS_OK 且 blockers=[]
# 对照证据: runbooks/world-model-jazzy/stage6_live_evidence.txt(WSL 侧 20260708T101402 全绿)
#
# 🔴 铁律(勿改): 不传 --artifact-root,用默认值(workspace 内)。
#    历史根因: --artifact-root 指到 workspace 外(如 /tmp),docker 探针容器按 workspace
#    前缀映射路径 → 探针输出落到容器里不存在的 /workspace/tmp/... → 四探针全 rc=1
#    output_missing → runner 在 +6s 拆栈,伪装成"冷启动环境失败"。
export PATH=/usr/local/go/bin:/usr/bin:/bin
export NAVLAB_SIM_DISTRO=jazzy
export GOFLAGS=-mod=mod

WM="${WM:-/home/ai4s/projects/world-model}"
cd "${WM}/orchestration/sim" || { echo "CD_FAIL: ${WM}/orchestration/sim"; exit 99; }

LOG="${LOG:-${HOME}/build-logs-jazzy/gate4_live.log}"
mkdir -p "$(dirname "$LOG")"

echo "=== LIVE RUN START $(date) HEAD=$(git -C "$WM" rev-parse --short HEAD) ==="
timeout 480 go run ./cmd/navlab-sim run exploration --live-preflight > "$LOG" 2>&1
RC=$?
echo "RUN_RC=$RC"
echo "--- tail 12 of run log ---"
tail -12 "$LOG"

RUNDIR=$(ls -dt artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "=== RUNDIR=$RUNDIR ==="

echo "=== frame_contract_probe.py sampled TOPICS (expect local_position_pose) ==="
grep -h '^TOPICS' "$RUNDIR"/probes/frame_contract_probe.py 2>/dev/null | head -1

echo "=== probe result jsons ==="
for p in frame_contract imu rangefinder exploration; do
  F=$(find "$RUNDIR" -name "${p}_probe.json" -o -name "${p}.json" 2>/dev/null | head -1)
  [ -z "$F" ] && { echo "$p: NO_RESULT_FILE"; continue; }
  python3 -c "import json;d=json.load(open('$F'));print('$p: ok=',d.get('ok'),' rc=',d.get('return_code'),' missing=',d.get('missing_topics'))" 2>/dev/null || echo "$p: unparsable $F"
done

echo "=== summary.json task_status / blockers ==="
SUM="$RUNDIR/summary.json"
python3 -c "import json;d=json.load(open('$SUM'));print(' task_status=',d.get('task_status') or d.get('status'));print(' blockers=',[b.get('code') for b in (d.get('blockers') or [])])" 2>/dev/null | head -5
echo "=== DONE ==="
