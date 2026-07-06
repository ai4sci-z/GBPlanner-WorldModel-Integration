#!/usr/bin/env bash
# 阶段2a-2:①消息定义对比修正(只比顶层字段,排除 jazzy 递归展开的假阳性)
#          ②J2F 方向分辨:foxy 换 cyclonedds / 用 rclpy 订阅,判定 bad_alloc 是 CLI 还是 RMW 层
set -u
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage2a2_evidence.txt
JAZZY_IMG=navlab/official-baseline:jazzy-latest
FOXY_IMG=ros:foxy-ros1-bridge
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'

{
echo "=== STAGE2A2 START $(date) ==="

echo "--- 1. 消息定义对比修正(只比顶层字段,即非缩进行) ---"
for M in nav_msgs/msg/Odometry sensor_msgs/msg/PointCloud2 trajectory_msgs/msg/MultiDOFJointTrajectory geometry_msgs/msg/PoseStamped; do
  N=$(echo "$M" | tr '/' '_')
  docker run --rm "$FOXY_IMG" bash -c "source /opt/ros/foxy/setup.bash && ros2 interface show $M" > /tmp/f_$N.txt 2>/dev/null
  docker run --rm "$JAZZY_IMG" bash -lc "ros2 interface show $M" > /tmp/j_$N.txt 2>/dev/null
  A=$(grep -E "^[a-zA-Z]" /tmp/f_$N.txt | grep -vE "^\s*#" | sed "s/#.*//" | tr -d " \t")
  B=$(grep -E "^[a-zA-Z]" /tmp/j_$N.txt | grep -vE "^\s*#" | sed "s/#.*//" | tr -d " \t")
  if [ "$A" = "$B" ]; then echo "  $M : TOP-LEVEL IDENTICAL"; else
    echo "  $M : TOP-LEVEL DIFF!"; diff <(echo "$A") <(echo "$B") | head -8
  fi
done

echo "--- 2. foxy 镜像里有无 rmw_cyclonedds ---"
docker run --rm "$FOXY_IMG" bash -c "ls /opt/ros/foxy/lib/librmw_cyclonedds_cpp.so 2>/dev/null && echo HAVE_CYCLONE || echo NO_CYCLONE"

echo "--- 3. J2F 重试 A:foxy 订阅换 cyclonedds(若有) ---"
docker rm -f s2a2_jpub >/dev/null 2>&1 || true
docker run -d --rm --network host --name s2a2_jpub \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  "$JAZZY_IMG" bash -lc "ros2 topic pub /bridge_smoke3 std_msgs/msg/String 'data: from_jazzy' -r 2"
docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp "$FOXY_IMG" \
  bash -c "source /opt/ros/foxy/setup.bash && timeout 30 ros2 topic echo /bridge_smoke3 2>&1 | head -4"
echo "  (上面有 data: from_jazzy = cyclone 路通)"

echo "--- 4. J2F 重试 B:foxy 用 rclpy(fastrtps 默认)订阅,判定 bad_alloc 层级 ---"
cat > /tmp/foxy_sub.py <<'PYEOF'
import rclpy, time
from std_msgs.msg import String
rclpy.init()
node = rclpy.create_node("s2a2_foxy_sub")
got = {"n": 0}
def cb(m):
    got["n"] += 1
    if got["n"] == 1:
        print("GOT:", m.data, flush=True)
sub = node.create_subscription(String, "/bridge_smoke3", cb, 10)
t0 = time.monotonic()
while time.monotonic() - t0 < 30 and got["n"] == 0:
    rclpy.spin_once(node, timeout_sec=0.2)
print("RESULT=", "OK" if got["n"] else "NO_MSG", flush=True)
PYEOF
docker run --rm --network host -v /tmp/foxy_sub.py:/tmp/foxy_sub.py:ro "$FOXY_IMG" \
  bash -c "source /opt/ros/foxy/setup.bash && timeout 40 python3 /tmp/foxy_sub.py 2>&1 | tail -3"
docker rm -f s2a2_jpub >/dev/null 2>&1 || true

echo "=== STAGE2A2 END $(date) ==="
} 2>&1 | tee "$OUT"
