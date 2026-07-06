#!/usr/bin/env bash
# 阶段2a·Foxy(ros1-bridge 镜像的 ROS2 侧) <-> jazzy DDS 互通冒烟 + 关键消息定义对比。
# 只用两个临时容器,不碰 gbplanner/world-model。验收=双向 String 收到 + 三消息定义一致。
set -u
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2a_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
FOXY_IMG=ros:foxy-ros1-bridge
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

{
echo "=== STAGE2A START $(date) ==="

echo "--- 0. 清场 ---"
docker rm -f s2a_foxy_pub s2a_jazzy_pub >/dev/null 2>&1 || true

echo "--- 1. foxy 发布(fastrtps 默认) -> jazzy 订阅(cyclonedds),等最长 45s ---"
docker run -d --rm --network host --name s2a_foxy_pub "$FOXY_IMG" \
  bash -c "source /opt/ros/foxy/setup.bash && ros2 topic pub /bridge_smoke std_msgs/msg/String 'data: from_foxy' -r 2"
docker run --rm --network host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "timeout 45 ros2 topic echo /bridge_smoke --once 2>&1 | tail -3"
RC1=$?
echo "F2J_RC=$RC1 (0=收到)"
docker rm -f s2a_foxy_pub >/dev/null 2>&1 || true

echo "--- 2. jazzy 发布 -> foxy 订阅,等最长 45s ---"
docker run -d --rm --network host --name s2a_jazzy_pub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic pub /bridge_smoke2 std_msgs/msg/String 'data: from_jazzy' -r 2"
docker run --rm --network host "$FOXY_IMG" \
  bash -c "source /opt/ros/foxy/setup.bash && timeout 45 ros2 topic echo /bridge_smoke2 2>&1 | head -3"
RC2=$?
echo "J2F_RC(head截断非0正常,看有无 data 行)=$RC2"
docker rm -f s2a_jazzy_pub >/dev/null 2>&1 || true

echo "--- 3. 三个桥接核心消息定义对比(foxy vs jazzy) ---"
for M in nav_msgs/msg/Odometry sensor_msgs/msg/PointCloud2 trajectory_msgs/msg/MultiDOFJointTrajectory; do
  N=$(echo "$M" | tr '/' '_')
  docker run --rm "$FOXY_IMG" bash -c "source /opt/ros/foxy/setup.bash && ros2 interface show $M" > /tmp/foxy_$N.txt 2>/dev/null
  docker run --rm "$JAZZY_IMG" bash -lc "ros2 interface show $M" > /tmp/jazzy_$N.txt 2>/dev/null
  # 去注释/空行后比对
  A=$(grep -vE "^\s*#|^\s*$" /tmp/foxy_$N.txt | tr -d " \t")
  B=$(grep -vE "^\s*#|^\s*$" /tmp/jazzy_$N.txt | tr -d " \t")
  if [ "$A" = "$B" ]; then echo "  $M : IDENTICAL"; else
    echo "  $M : DIFF!"; diff <(echo "$A") <(echo "$B") | head -10
  fi
done

echo "=== STAGE2A END $(date) ==="
} 2>&1 | tee "$OUT"
