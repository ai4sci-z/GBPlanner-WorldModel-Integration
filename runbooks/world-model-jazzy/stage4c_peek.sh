#!/usr/bin/env bash
# 联跑期间偷看:探针与适配器容器日志(只读)
echo "== s4c_probe =="
docker logs s4c_probe 2>&1 | tail -15
echo "== s4_adapter (INTENT/TRAJ 尾5) =="
docker logs s4_adapter 2>&1 | grep -E "INTENT|TRAJ#|MOTION" | tail -5
echo "== 薄桥 ROS1 侧尾3 =="
docker exec gbplanner_ref bash -c "tail -3 /tmp/thinbridge_ros1.log" 2>/dev/null
