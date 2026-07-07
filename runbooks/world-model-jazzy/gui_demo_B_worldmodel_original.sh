#!/usr/bin/env bash
# GUI-B·原版 world-model(frontier_lite,无桥无适配器)——Gazebo 主仿真窗口 + 一次 live run
# 展示点:飞机真实起飞(SITL 物理)、迷宫世界、2D SLAM 平台本体;run 约 5~6 分钟。
set -o pipefail
export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
CLEAN=/home/ai4s/ws-clean/world-model
HERE=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy

echo "=== [1/3] 清掉融合栈(保证'原版'纯净:无桥/无适配器混入) ==="
docker rm -f thin_ros2 s4_adapter s5c_probe gbp_rviz >/dev/null 2>&1 || true
grep -n 'strategy:' "$CLEAN/orchestration/sim/configs/tasks/exploration.yaml" | head -1   # 应为 frontier_lite

echo "=== [2/3] 起原版 live run(frontier_lite)==="
cd "$CLEAN/orchestration/sim" || exit 9
go run ./cmd/navlab-sim run exploration --live-preflight > /home/ai4s/gui_b_run.log 2>&1 &
RUN_PID=$!
sleep 14

echo "=== [3/3] 附着 Gazebo 主仿真窗口 ==="
bash "$HERE/gui1_gazebo.sh"
echo "画面存在于 run 进行期(~6 分钟);讲解:起飞→frontier_lite 低速平移→降落。"
wait $RUN_PID
tail -2 /home/ai4s/gui_b_run.log
echo "=== GUI-B run 结束(Gazebo 窗口画面消失属正常) ==="
