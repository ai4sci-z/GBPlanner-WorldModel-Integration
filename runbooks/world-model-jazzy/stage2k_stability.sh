#!/usr/bin/env bash
# 阶段2.5+2.6·稳定性复跑(带心跳/全日志)+ GBPlanner 订阅关系查证(Review_008 §3.1/§3.3):
#   ①TCP 断连根因(两端日志+ping)②rostopic info 实证 GBPlanner/voxblox 订谁
#   ③粉线=command/trajectory 的发布者确认(PCI,非 /vis/*)
set -u
DIR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2k_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2K START $(date) ==="
echo "--- 0. fresh 仿真 + 双端桥(带心跳/日志版)+ rclpy 订阅就位 ---"
docker rm -f thin_ros2 s2k_sub >/dev/null 2>&1 || true
bash "$DIR/run_light_hostnet.sh"
sleep 45
docker cp "$BR/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 4
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s2k_sub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "timeout 200 python3 /exp/sub_test_traj.py; sleep 600"
sleep 10

echo "--- 1. [2.6] rostopic info:GBPlanner/voxblox/PCI 实际订阅谁(实证,Review_008) ---"
for T in /wm/odom /wm/points /rmf_obelix/ground_truth/odometry_throttled /rmf_obelix/velodyne_points /rmf_obelix/command/trajectory; do
  echo "==== $T"
  E "timeout 8 rostopic info $T 2>&1 | grep -vE '^\s*$' | head -12"
done

echo "--- 2. 起飞 + 触发探索 ---"
bash "$DIR/takeoff_and_explore.sh" 2>&1 | grep -E "success|z:" | head -6

echo "--- 3. 观察 120s(心跳每 3s,若断连日志会锁方向) ---"
sleep 120

echo "--- 4. 验收与断连诊断 ---"
docker logs s2k_sub 2>&1 | tail -3
echo "[ros1端全部异常/连接日志] "
E "grep -E 'ERROR|WARN|connected|FIN|failed' /tmp/thinbridge_ros1.log | tail -10"
E "tail -3 /tmp/thinbridge_ros1.log"
echo "[ros2端全部异常/连接日志] "
docker logs thin_ros2 2>&1 | grep -E "error|warn|lost|failed|connected" -i | tail -10
docker logs thin_ros2 2>&1 | grep stats | tail -2
N=$(docker logs s2k_sub 2>&1 | grep -oE "RESULT count=[0-9]+" | grep -oE "[0-9]+" | tail -1)
echo "SUB_RECEIVED=$N"

docker rm -f s2k_sub >/dev/null 2>&1 || true
echo "=== STAGE2K END $(date) ==="
} 2>&1 | tee "$OUT"
