#!/usr/bin/env bash
# 从 GitHub 全新克隆的作者源码跑 exploration(干净复现)。用已建的 jazzy 镜像。
# 只报实测:跑到哪、卡什么。不预判、不打补丁(补丁只在撞到真 blocker 时逐个加并记录)。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
cd "$CLEAN/orchestration/sim" || { echo "CD_FAIL"; exit 9; }
LOG=/home/ai4s/clean_repro.log
echo "=== CLEAN REPRO START $(date) HEAD=$(git -C "$CLEAN" rev-parse --short HEAD) 源=作者原版 ===" | tee "$LOG"
go run ./cmd/navlab-sim run exploration --live-preflight 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
echo "=== CLEAN REPRO END rc=${RC} $(date) ===" | tee -a "$LOG"
exit "$RC"
