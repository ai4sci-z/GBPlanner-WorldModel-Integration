#!/usr/bin/env bash
# 阶段3·dry-run 验收:复用 2.6 存活栈(纯 planner+薄桥),手工 odom/scan,
# dry-run 节点只打印跟踪量,不发 intent。验收=数值合理(dist/yaw_err/限幅速度)。
set -u
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage3_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN_D() { docker run -d --rm --network host --name "$1" -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$2"; }

{
echo "=== STAGE3 DRYRUN START $(date) ==="
echo "--- 0. fresh planner 栈(PCI 状态机需干净;静止 odom 下旧轨迹永不完成会挂起规划循环) ---"
docker rm -f s3_opub s3_spub s3_dry thin_ros2 >/dev/null 2>&1 || true
docker restart gbplanner_ref >/dev/null
sleep 25
E "rosnode list | head -5"
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
sleep 4

echo "--- 1. 手工输入 + dry-run 节点就位 ---"
JRUN_D s3_opub "ros2 topic pub /slam/odom nav_msgs/msg/Odometry '{header: {frame_id: map}, child_frame_id: base_link, pose: {pose: {position: {x: 0.0, y: 0.0, z: 1.0}, orientation: {w: 1.0}}}}' -r 10"
JRUN_D s3_spub "ros2 topic pub /scan sensor_msgs/msg/LaserScan '{header: {frame_id: base_scan}, angle_min: -3.14, angle_max: 3.14, angle_increment: 0.393, range_min: 0.1, range_max: 12.0, ranges: [6,6,6,.inf,.inf,6,6,6,6,.inf,.inf,6,6,6,6,6,6]}' -r 5"
docker run -d --network host --name s3_dry \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/traj_dryrun.py"
sleep 10

echo "--- 2. 等地图积累 15s 后触发规划 ---"
sleep 15
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 35

echo "--- 3. 验收:dry-run 输出(应见 TRAJ 行 + DRY 行,数值合理,零发布) ---"
echo "[s3_dry 全日志尾部 20 行]"
docker logs s3_dry 2>&1 | tail -20
echo "[TRAJ 行]"; docker logs s3_dry 2>&1 | grep -E "TRAJ" | tail -4
echo "[DRY 行]"; docker logs s3_dry 2>&1 | grep -E "DRY " | tail -6
echo "[薄桥 ros2 端近况]"; docker logs thin_ros2 2>&1 | tail -4

N=$(docker logs s3_dry 2>&1 | grep -c "DRY ")
docker rm -f s3_opub s3_spub >/dev/null 2>&1 || true
if [ "$N" -ge 1 ]; then docker rm -f s3_dry >/dev/null 2>&1; echo "STAGE3=PASS (DRY lines=$N)"; else echo "STAGE3=FAIL(s3_dry 容器保留待尸检)"; fi
echo "=== STAGE3 DRYRUN END $(date) ==="
} 2>&1 | tee "$OUT"
