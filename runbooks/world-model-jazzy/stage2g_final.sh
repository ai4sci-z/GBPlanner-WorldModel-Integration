#!/usr/bin/env bash
# 阶段2g·薄桥最终验收(修正验收顺序:先订阅后触发;ROS2 端已加异常日志):
#   fresh 仿真 -> 双端桥 -> [长驻订阅容器先就位] -> 起飞+触发 -> 数条 trajectory 落到订阅端。
set -u
DIR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref
BR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2g_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }

{
echo "=== STAGE2G START $(date) ==="
echo "--- 0. fresh 仿真 + 双端桥 ---"
docker rm -f thin_ros2 s2g_sub >/dev/null 2>&1 || true
bash "$DIR/run_light_hostnet.sh"
sleep 45
docker cp "$BR/thinbridge_ros1_side.py" gbplanner_ref:/tmp/thinbridge_ros1_side.py
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 4
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$BR":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"

echo "--- 1. 长驻订阅容器先就位(计数 /gbp/trajectory) ---"
docker run -d --network host --name s2g_sub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic echo /gbp/trajectory --field header.frame_id"
sleep 8

echo "--- 2. 起飞 + 触发探索 ---"
bash "$DIR/takeoff_and_explore.sh" 2>&1 | grep -E "success|z:" | head -6

echo "--- 3. 观察 90s(飞机自主探索,轨迹持续过桥) ---"
sleep 90

echo "--- 4. 验收:订阅端收到几条 trajectory ---"
N=$(docker logs s2g_sub 2>&1 | grep -c "map")
echo "SUB_RECEIVED_COUNT=$N (frame_id=map,证明 frame 映射 world->map 生效)"
docker logs s2g_sub 2>&1 | head -4
echo "[ros1端] "; E "grep -c 'traj -> tcp' /tmp/thinbridge_ros1.log"
E "tail -3 /tmp/thinbridge_ros1.log"
echo "[ros2端] "; docker logs thin_ros2 2>&1 | grep -E "traj ->|error|lost" | tail -6
docker logs thin_ros2 2>&1 | grep -E "stats" | tail -2
if [ "$N" -ge 2 ]; then echo "STAGE2=PASS"; else echo "STAGE2=FAIL"; fi

echo "--- 5. 清理长驻订阅 ---"
docker rm -f s2g_sub >/dev/null 2>&1 || true
echo "=== STAGE2G END $(date) ==="
} 2>&1 | tee "$OUT"
