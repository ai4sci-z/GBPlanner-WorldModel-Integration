#!/usr/bin/env bash
# C类查证①:渲染出的 exploration_probe.py 的采样逻辑(等待谁/等多久/何时开始)
CLEAN=/home/ai4s/ws-clean/world-model
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
P=$(find "$RUNDIR" -name "exploration_probe.py" | head -1)
echo "PROBE_SCRIPT=$P  ($(wc -l < "$P") lines)"
echo "=== 采样/超时/等待逻辑关键行 ==="
grep -n -E "timeout|Timeout|wait|sleep|ok|deadline|sample|spin" "$P" | head -40
