#!/usr/bin/env bash
# Stage5b·单变体联跑(用法: stage5b_variant.sh A_FOV30|B_FOV5)
# 对照量全部 topic/数值:输入点云 z、voxblox TSDF z、trajectory z、gate 指标。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
VARIANT=${1:?usage: stage5b_variant.sh A_FOV30|B_FOV5}
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
OUT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/stage5b_${VARIANT}_evidence.txt
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
TMPL=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/sdf/rangefinder_down_overlay.sdf.tmpl
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
JRUN() { docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" bash -lc "$1"; }
restore_all() {
  sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"
  sed -i 's/<min_angle>-0.0873<\/min_angle>/<min_angle>-0.523599<\/min_angle>/' "$TMPL"
  sed -i 's/<max_angle>0.0873<\/max_angle>/<max_angle>0.523599<\/max_angle>/' "$TMPL"
}
trap restore_all EXIT

{
echo "=== STAGE5B VARIANT $VARIANT START $(date) ==="
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
if [ "$VARIANT" = "B_FOV5" ]; then
  sed -i 's/<min_angle>-0.523599<\/min_angle>/<min_angle>-0.0873<\/min_angle>/' "$TMPL"
  sed -i 's/<max_angle>0.523599<\/max_angle>/<max_angle>0.0873<\/max_angle>/' "$TMPL"
fi
echo "--- 变量确认(vertical FOV / strategy) ---"
grep -n "min_angle>-0.0873\|min_angle>-0.523599" "$TMPL"
grep -n 'strategy:' "$YAML"

echo "--- 栈复位 ---"
docker rm -f thin_ros2 s4_adapter s5b_trajz >/dev/null 2>&1 || true
docker restart gbplanner_ref >/dev/null
sleep 25
docker cp "$DIRB/ros1_cloud_z.py" gbplanner_ref:/tmp/ros1_cloud_z.py >/dev/null
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s4_adapter \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"
docker run -d --network host --name s5b_trajz \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/sub_traj_z.py; sleep 200"
sleep 5

echo "--- world-model 真栈起(external) ---"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/s5b_run.log 2>&1 &
RUN_PID=$!
sleep 30
JRUN "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 45

echo "--- [核心] 输入点云 z 分布(/wm/points) ---"
E "timeout 40 python3 /tmp/ros1_cloud_z.py /wm/points 35"
echo "--- [核心] voxblox TSDF z 分布 ---"
E "timeout 40 python3 /tmp/ros1_cloud_z.py /gbplanner_node/tsdf_pointcloud 35"

echo "--- 等 run 结束 ---"
wait $RUN_PID
tail -2 /home/ai4s/s5b_run.log

echo "--- trajectory z 分布(全程) ---"
docker logs s5b_trajz 2>&1 | grep -E "TRAJ#|RESULT" | head -15
echo "--- gate.exploration 指标 ---"
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
echo "RUNDIR=$RUNDIR"
python3 -c "
import json
d=json.load(open('$RUNDIR/summary.json'))
print('task_status =', d.get('status'))
print('gate.exploration =', json.dumps((d.get('metrics') or {}).get('gate',{}).get('exploration',{}), ensure_ascii=False))
"
echo "--- 适配器 GATE/TRAJ 摘要 ---"
docker logs s4_adapter 2>&1 | grep -E "GATE OK|TRAJ#|WP REACHED" | head -8
docker rm -f s5b_trajz >/dev/null 2>&1 || true
restore_all
echo "--- 已还原 ---"
grep -n "min_angle>-0.523599" "$TMPL" | head -1
grep -n 'strategy:' "$YAML"
echo "=== STAGE5B VARIANT $VARIANT END $(date) ==="
} 2>&1 | tee "$OUT"
