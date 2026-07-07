#!/usr/bin/env bash
# 5a 首跑适配器全量运动日志(采样)+ 关键统计
echo "=== INTENT 前10条 ==="
docker logs s4_adapter 2>&1 | grep "INTENT" | head -10
echo "=== INTENT 每5条采样(中段) ==="
docker logs s4_adapter 2>&1 | grep "INTENT" | awk 'NR%5==1' | head -30
echo "=== dist 最小值(最接近 waypoint 的程度) ==="
docker logs s4_adapter 2>&1 | grep -oE "dist=[0-9.]+" | sort -t= -k2 -n | head -3
echo "=== dyaw 演化(每5条) ==="
docker logs s4_adapter 2>&1 | grep -oE "dyaw=-?[0-9.]+" | awk 'NR%5==1' | head -25
echo "=== TRAJ/GATE/MIXED 全部 ==="
docker logs s4_adapter 2>&1 | grep -E "TRAJ#|GATE|MIXED|KILL|ENABLED" | head -10
