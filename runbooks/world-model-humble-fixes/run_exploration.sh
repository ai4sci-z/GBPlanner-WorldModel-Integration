#!/usr/bin/env bash
# 9/9 镜像就绪后:预检 + 真跑 exploration + 找 summary
cd /home/ai4s/ws/world-model/orchestration/sim || exit 1
export PATH=/usr/local/go/bin:$PATH
LOG=/home/ai4s/run_exploration.log
echo "=== live-preflight $(date) ===" | tee "$LOG"
go run ./cmd/navlab-sim run exploration --live-preflight 2>&1 | tail -15 | tee -a "$LOG"
echo "=== run exploration(真跑,约150s+起停) ===" | tee -a "$LOG"
go run ./cmd/navlab-sim run exploration 2>&1 | tail -50 | tee -a "$LOG"
echo "RUN_EXIT=${PIPESTATUS[0]} $(date)" | tee -a "$LOG"
echo "=== 最新 summary.json(含 coverage/path/goals 指标) ===" | tee -a "$LOG"
find /home/ai4s/ws/world-model/artifacts -name 'summary.json' -newermt '-20 min' 2>/dev/null | tee -a "$LOG"
