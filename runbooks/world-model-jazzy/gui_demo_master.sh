#!/usr/bin/env bash
# 组会三 GUI 演示总控(阶段性可视化演示,live 失败不算演示失败——fallback 见手册)
# 流程:①拉起桥接栈(external)②起 world-model live run ③开 Gazebo GUI ④开 RViz
# ⑤enable+触发规划,让 RViz 里出现 3D 点云/voxblox/轨迹 ⑥run 自然结束后 yaml 自动还原
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
DIRB=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/ros1_bridge
HERE=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy
YAML=$CLEAN/orchestration/sim/configs/tasks/exploration.yaml
JAZZY_IMG=navlab/official-baseline:jazzy-latest
URI='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
E() { docker exec gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; $1"; }
restore_yaml() { sed -i 's/strategy: external/strategy: frontier_lite/' "$YAML"; }
trap restore_yaml EXIT

echo "=== [1/6] 桥接栈复位 ==="
docker rm -f thin_ros2 s4_adapter s5c_probe gbp_rviz wm_gzgui >/dev/null 2>&1 || true
docker restart gbplanner_ref >/dev/null
sleep 25
docker exec -d gbplanner_ref bash -c "source /opt/ros/noetic/setup.bash; source /root/gbp_ws/devel/setup.bash; export ROS_MASTER_URI=http://localhost:11311 ROS_HOSTNAME=localhost; python3 /tmp/thinbridge_ros1_side.py > /tmp/thinbridge_ros1.log 2>&1"
sleep 3
docker run -d --network host --name thin_ros2 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/thinbridge_ros2_side.py"
docker run -d --network host --name s4_adapter \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" \
  -v "$DIRB":/exp:ro "$JAZZY_IMG" bash -lc "python3 /exp/trajectory_to_intent_stage4.py"

echo "=== [2/6] RViz(GUI2)先起——栈就绪即可看到订阅对象 ==="
bash "$HERE/gui2_rviz.sh" || echo "RViz 启动失败,fallback=结果面板"

echo "=== [3/6] world-model live run(external)==="
sed -i 's/strategy: frontier_lite/strategy: external/' "$YAML"
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/gui_demo_run.log 2>&1 &
RUN_PID=$!
sleep 12

echo "=== [4/6] Gazebo GUI(GUI1)附着 ==="
bash "$HERE/gui1_gazebo.sh" || echo "Gazebo GUI 启动失败,fallback=RViz+结果面板"

echo "=== [5/6] ENABLE + 触发规划(RViz 里将出现点云/体素/轨迹)==="
sleep 15
docker run --rm --network host -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 -e CYCLONEDDS_URI="$URI" "$JAZZY_IMG" \
  bash -lc "timeout 5 ros2 topic pub /gbp/enable std_msgs/msg/Bool '{data: true}' -r 2 >/dev/null 2>&1; echo enabled"
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"
sleep 15
E "timeout 10 rosservice call /planner_control_interface/std_srvs/automatic_planning '{}' 2>&1 | head -2"

echo "=== [6/6] 等 run 结束(期间讲解;结果面板= gui/results_panel.html)==="
wait $RUN_PID
tail -2 /home/ai4s/gui_demo_run.log
restore_yaml
echo "=== DEMO RUN 结束;GUI 窗口保留;再来一遍直接重跑本脚本 ==="
