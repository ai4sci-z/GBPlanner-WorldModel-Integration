#!/usr/bin/env bash
# 活体探测:等 slam-backend 容器起来,在【它内部】实测关键话题频率,定位 external_nav_bridge 卡点。
set -o pipefail
echo "等待 slam-backend 容器..."
for i in $(seq 1 40); do
  C=$(docker ps --format '{{.Names}}' | grep -iE 'slam' | head -1)
  [ -n "$C" ] && break
  sleep 2
done
C=$(docker ps --format '{{.Names}}' | grep -iE 'slam' | head -1)
if [ -z "$C" ]; then echo "没等到 slam 容器"; docker ps --format '{{.Names}}'; exit 1; fi
echo "slam 容器 = $C ; 再等 25s 让数据流稳定"
sleep 25
echo "===== 在 $C 内部看得见的话题 ====="
docker exec "$C" bash -c "source /opt/ros/jazzy/setup.bash; ros2 topic list 2>/dev/null | grep -iE 'slam|odom|height|scan|imu|map|ap/v1' | head -30"
echo "===== 关键话题真实频率(各测 4s) ====="
for t in /slam/odom /height/estimate /scan /imu; do
  echo "--- $t"
  timeout 5 docker exec "$C" bash -c "source /opt/ros/jazzy/setup.bash; ros2 topic hz $t 2>/dev/null" | head -2
done
